from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # API Settings
    PROJECT_NAME: str = "Async Security Processor API"
    API_V1_STR: str = "/api/v1"

    # Authentication
    API_KEY: str  # Required — no default; app fails fast if missing

    # Logging
    LOG_LEVEL: str = "INFO"  # DEBUG | INFO | WARNING | ERROR | CRITICAL
    LOG_JSON: bool = False  # True in production/Docker for machine-readable output

    # RabbitMQ (Broker)
    RABBITMQ_USER: str = "sec_admin"
    RABBITMQ_PASS: str = "StrongPassw0rd!"
    RABBITMQ_HOST: str = "localhost"  # 'rabbitmq' cuando usemos Docker Compose completo
    RABBITMQ_PORT: str = "5672"

    # Redis (Result Backend)
    REDIS_PASS: str = "AnotherStrongPassw0rd!"
    REDIS_HOST: str = "localhost"  # 'redis' cuando usemos Docker Compose completo
    REDIS_PORT: str = "6379"

    # PostgreSQL (Database)
    POSTGRES_USER: str = "sec_db_admin2"
    POSTGRES_PASSWORD: str = "Super2SecureDBPassword123!"
    POSTGRES_DB: str = "security2_scans_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: str = "5432"

    @property
    def CELERY_BROKER_URL(self) -> str:
        return f"amqp://{self.RABBITMQ_USER}:{self.RABBITMQ_PASS}@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}//"

    @property
    def CELERY_RESULT_BACKEND(self) -> str:
        return f"redis://:{self.REDIS_PASS}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    @property
    def DATABASE_URI(self) -> str:
        """
        Construye la URL de conexión segura para SQLAlchemy usando el driver psycopg3.
        """
        return f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()
