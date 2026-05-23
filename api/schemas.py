from datetime import datetime
from pydantic import BaseModel, IPvAnyAddress, Field


class ScanRequest(BaseModel):
    """
    Modelo de entrada para la solicitud de un escaneo de seguridad.
    """

    target_ip: IPvAnyAddress = Field(
        ...,
        description="Dirección IP (v4 o v6) objetivo para el análisis.",
        json_schema_extra={"example": "8.8.8.8"},
    )


class TaskResponse(BaseModel):
    """
    Modelo de salida estandarizado para la creación de tareas asíncronas.
    """

    task_id: str = Field(
        ..., description="ID único (UUID) de la tarea generada por Celery."
    )
    status: str = Field(
        ..., description="Estado actual de la tarea en el broker (ej. PENDING)."
    )
    message: str = Field(..., description="Mensaje informativo para el cliente API.")


class ScanRecord(BaseModel):
    """
    Representación de un registro del histórico de escaneos (sin raw_output).
    """

    id: str
    celery_task_id: str
    target_ip: str
    open_ports_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ScanListResponse(BaseModel):
    """
    Respuesta paginada para el listado de escaneos históricos.
    """

    total: int = Field(..., description="Total de registros en la base de datos.")
    skip: int = Field(..., description="Registros omitidos (offset).")
    limit: int = Field(..., description="Máximo de registros devueltos en esta página.")
    items: list[ScanRecord]
