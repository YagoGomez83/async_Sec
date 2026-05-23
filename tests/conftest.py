"""
Fixtures de pytest para los tests del proyecto.

IMPORTANTE: los os.environ.update() deben ejecutarse ANTES de cualquier
import del proyecto, porque pydantic-settings lee las variables en el
momento en que `settings = Settings()` es invocado (nivel de módulo en
core/config.py).  pytest carga conftest.py antes que cualquier test file,
por lo que este orden está garantizado.
"""

import os

# --- Variables de entorno para el entorno de test ---
# Las env vars tienen mayor prioridad que el archivo .env en pydantic-settings.
os.environ.update(
    {
        "API_KEY": "test-key-for-pytest",
        "RABBITMQ_USER": "guest",
        "RABBITMQ_PASS": "guest",
        "RABBITMQ_HOST": "localhost",
        "RABBITMQ_PORT": "5672",
        "REDIS_PASS": "testpass",
        "REDIS_HOST": "localhost",
        "REDIS_PORT": "6379",
        "POSTGRES_USER": "test",
        "POSTGRES_PASSWORD": "test",
        "POSTGRES_DB": "test_db",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
    }
)

# --- Imports del proyecto (DESPUÉS de setear env vars) ---
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from api.main import app
from api.dependencies import get_db
from core.db.models import Base

# ────────────────────────────────────────────────────────────────────────────
# Constante pública — usada en los archivos de test para construir headers
# ────────────────────────────────────────────────────────────────────────────
TEST_API_KEY = "test-key-for-pytest"

# URL de SQLite en memoria compartida.
# StaticPool garantiza que todas las sesiones usen la MISMA conexión subyacente,
# lo que es imprescindible para que los datos de un flush sean visibles a otras
# sesiones en la misma base de datos en memoria.
_SQLITE_TEST_URL = "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine():
    """
    Crea el engine de SQLite en memoria una sola vez por sesión de pytest
    y levanta todas las tablas del ORM. Al terminar la sesión, las elimina.
    """
    eng = create_engine(
        _SQLITE_TEST_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture
def db_session(engine):
    """
    Provee una sesión de BD aislada por test.
    Hace rollback al finalizar para que cada test comience con un estado limpio.
    """
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client(db_session):
    """
    TestClient de FastAPI con la dependencia get_db reemplazada por la
    sesión de SQLite del test.  La autenticación NO se bypasea: los tests
    deben enviar la cabecera X-API-Key con TEST_API_KEY.
    """

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
