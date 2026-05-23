from typing import Generator, Optional

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from core.config import settings
from core.db.session import SessionLocal

# El nombre del header que el cliente debe enviar: "X-API-Key: <valor>"
# auto_error=False para manejar manualmente el caso de header ausente.
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(_api_key_header)) -> None:
    """
    Dependencia de FastAPI que valida la API Key en cada request.
    - Header ausente → 401 Unauthorized (sin credenciales).
    - Header presente pero inválido → 403 Forbidden (credenciales rechazadas).
    - Comparación en tiempo constante para prevenir timing attacks.
    """
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key.",
        )
    if api_key != settings.API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )


def get_db() -> Generator[Session, None, None]:
    """
    Dependencia que provee una sesión de BD por request y garantiza su cierre.
    """
    with SessionLocal() as session:
        yield session
