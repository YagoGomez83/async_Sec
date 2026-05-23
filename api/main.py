import time
import uuid

import structlog
from fastapi import FastAPI, HTTPException, Depends, Query
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from celery.result import AsyncResult
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from api.schemas import ScanRequest, TaskResponse, ScanListResponse
from api.dependencies import verify_api_key, get_db
from core.db.models import SecurityScan
from core.logging import configure_logging
from core.config import settings
from worker.tasks.network_scans import scan_ip
from worker.celery_app import celery_app

# Configure structured logging before the app object is created so that
# every log call (including middleware) uses the right renderer from the start.
configure_logging(log_level=settings.LOG_LEVEL, json_logs=settings.LOG_JSON)

logger = structlog.get_logger(__name__)

# Rate limiter: track request counts per client IP
limiter = Limiter(key_func=get_remote_address)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request/response with timing and a per-request correlation ID."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())

        # Bind context vars so all log calls within this request carry the same fields.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        start = time.perf_counter()
        logger.info("http.request_started")

        response = await call_next(request)

        elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "http.request_finished",
            status_code=response.status_code,
            duration_ms=elapsed_ms,
        )

        # Expose the correlation ID to the caller for distributed tracing.
        response.headers["X-Request-ID"] = request_id
        return response


# Inicialización de la aplicación FastAPI
app = FastAPI(
    title="Async Security Processor API",
    description="API Gateway DevSecOps para encolar tareas distribuidas.",
    version="1.0.0",
)

# Register the limiter and its 429 exception handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(RequestLoggingMiddleware)


@app.post(
    "/api/v1/scans",
    response_model=TaskResponse,
    status_code=202,
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("5/minute")
async def create_scan_task(request: Request, scan_request: ScanRequest):
    """
    Encola una nueva tarea de escaneo de seguridad sin bloquear la API.
    """
    try:
        # 1. Sanitización/Casteo: Pydantic validó la IP, pero Celery necesita tipos primitivos
        ip_str = str(scan_request.target_ip)

        # 2. Delegación asíncrona: Lanzamos la tarea a RabbitMQ
        task = scan_ip.delay(ip_address=ip_str)

        logger.info("scan.enqueued", task_id=task.id, target_ip=ip_str)

        # 3. Respuesta inmediata al cliente
        return TaskResponse(
            task_id=task.id,
            status="PENDING",
            message="Tarea encolada exitosamente en el broker.",
        )  # type: ignore[return-value]
    except Exception as e:
        logger.error("scan.enqueue_failed", error=str(e))
        raise HTTPException(
            status_code=500, detail="Error interno de encolado de mensajes."
        )


@app.get("/api/v1/scans/{task_id}", dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
async def get_scan_status(request: Request, task_id: str):
    """
    Consulta el backend de resultados (Redis) para obtener el estado de una tarea.
    """
    # Instanciamos el objeto de resultado vinculándolo a nuestra app de Celery
    task_result = AsyncResult(task_id, app=celery_app)

    response = {
        "task_id": task_id,
        "status": task_result.status,
    }

    # Manejo de estados de la tarea
    if task_result.status == "SUCCESS":
        response["result"] = task_result.result
    elif task_result.status == "FAILURE":
        # Retornamos el error como string para no exponer el stack trace completo
        response["error"] = str(task_result.result)

    logger.debug("scan.status_queried", task_id=task_id, status=task_result.status)
    return response


@app.get(
    "/api/v1/scans",
    response_model=ScanListResponse,
    dependencies=[Depends(verify_api_key)],
)
async def list_scans(
    skip: int = Query(0, ge=0, description="Número de registros a omitir (offset)."),
    limit: int = Query(
        20, ge=1, le=100, description="Máximo de registros a devolver (1-100)."
    ),
    db: Session = Depends(get_db),
):
    """
    Devuelve el histórico paginado de escaneos persistidos en PostgreSQL.
    Ordenado por fecha de creación descendente (más reciente primero).
    """
    total = db.scalar(select(func.count()).select_from(SecurityScan))
    scans = db.scalars(
        select(SecurityScan)
        .order_by(SecurityScan.created_at.desc())
        .offset(skip)
        .limit(limit)
    ).all()

    logger.debug("scans.list_queried", total=total, skip=skip, limit=limit)
    return ScanListResponse(total=total, skip=skip, limit=limit, items=scans)
