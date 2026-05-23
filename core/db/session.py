from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.config import settings

# 1. Configuración del Engine
engine = create_engine(
    settings.DATABASE_URI,
    pool_pre_ping=True,  # Verifica si la conexión está viva antes de usarla
    pool_size=10,  # Número de conexiones permanentes por worker
    max_overflow=20,  # Conexiones extra permitidas en picos de tráfico
)

# 2. Fábrica de Sesiones
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
