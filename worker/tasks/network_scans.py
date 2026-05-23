import subprocess

import structlog
from sqlalchemy.exc import SQLAlchemyError

from worker.celery_app import celery_app
from core.db.session import SessionLocal
from core.db.models import SecurityScan

logger = structlog.get_logger(__name__)


@celery_app.task(bind=True, name="scan_ip", max_retries=3)
def scan_ip(self, ip_address: str):
    # Bind task-scoped context so every log line carries task_id + target_ip.
    log = logger.bind(task_id=self.request.id, target_ip=ip_address)
    log.info("scan.started")

    command = ["nmap", "-Pn", "-F", "-T4", ip_address]

    try:
        # 1. Ejecución del Escaneo
        result = subprocess.run(
            command, capture_output=True, text=True, check=True, timeout=120
        )
        output = result.stdout
        open_ports_count = output.count("open")

        # 2. Persistencia en Base de Datos
        with SessionLocal() as session:
            try:
                scan_record = SecurityScan(
                    celery_task_id=self.request.id,
                    target_ip=ip_address,
                    open_ports_count=open_ports_count,
                    raw_output=output,
                )
                session.add(scan_record)
                session.commit()
                log.info("scan.persisted", open_ports_count=open_ports_count)

            except SQLAlchemyError as db_exc:
                session.rollback()
                log.warning("scan.db_error", error=str(db_exc))
                raise self.retry(exc=db_exc, countdown=15)

        # 3. Retorno a Redis (Result Backend)
        log.info("scan.completed", open_ports_count=open_ports_count)
        return {
            "ip": ip_address,
            "status": "completed",
            "open_ports_detected": open_ports_count,
            "db_persisted": True,
        }

    except subprocess.TimeoutExpired as exc:
        log.warning("scan.timeout", retry_countdown=30)
        raise self.retry(exc=exc, countdown=30)
    except subprocess.CalledProcessError as exc:
        log.warning("scan.nmap_error", returncode=exc.returncode, retry_countdown=30)
        raise self.retry(exc=exc, countdown=30)
    except FileNotFoundError:
        log.error("scan.nmap_not_found")
        raise RuntimeError("Binario Nmap no encontrado en el sistema.")
