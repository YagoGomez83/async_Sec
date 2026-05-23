import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# Clase base de SQLAlchemy 2.0
class Base(DeclarativeBase):
    pass


class SecurityScan(Base):
    """
    Modelo de datos inmutable para el histórico de escaneos de seguridad.
    """

    __tablename__ = "security_scans"

    # UUID previene ataques de enumeración (IDOR)
    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )

    # Vinculamos el registro de la BD con el ID de la tarea de Celery para trazabilidad
    celery_task_id: Mapped[str] = mapped_column(String, index=True, nullable=False)

    target_ip: Mapped[str] = mapped_column(String(45), nullable=False, index=True)
    open_ports_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # Guardamos la salida raw por si un analista necesita revisar firmas de puertos
    raw_output: Mapped[str] = mapped_column(Text, nullable=False)

    # Timestamp en UTC estricto. NUNCA uses hora local en bases de datos.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
