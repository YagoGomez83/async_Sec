from typing import Generator

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from core.config import settings
from core.db.session import SessionLocal

# El nombre del header que el cliente debe enviar: "X-API-Key: <valor>"
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)


async def verify_api_key(api_key: str = Security(_api_key_header)) -> None:
    """
    Dependencia de FastAPI que valida la API Key en cada request.
    - Comparación en tiempo constante para prevenir timing attacks.
    - Lanza 403 (no 401) para no revelar que existe un mecanismo de auth.
    """
    if api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing API key.",
        )


def get_db() -> Generator[Session, None, None]:
    """
    Dependencia que provee una sesión de BD por request y garantiza su cierre.
    """
    with SessionLocal() as session:
        yield session
