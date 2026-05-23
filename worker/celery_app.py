from celery import Celery
from celery.signals import worker_process_init

from core.config import settings
from core.logging import configure_logging

# 1. Inicialización de la app Celery
celery_app = Celery(
    "security_workers",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# 2. Configuración estricta (Buenas prácticas y Seguridad)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # Hard kill a la hora (Evita workers zombie)
    task_soft_time_limit=3000,  # Lanza excepción antes del hard kill para limpieza
    worker_prefetch_multiplier=1,  # Fair dispatching (evita cuellos de botella)
    broker_connection_retry_on_startup=True,
)

# 3. Auto-descubrimiento de tareas
celery_app.autodiscover_tasks(["worker.tasks.network_scans"])


# 4. Configure structured logging after each worker process forks.
#    Using worker_process_init ensures logging is set up in every pool process,
#    not just the main supervisor process.
@worker_process_init.connect
def init_worker_logging(**kwargs):
    configure_logging(log_level=settings.LOG_LEVEL, json_logs=settings.LOG_JSON)
