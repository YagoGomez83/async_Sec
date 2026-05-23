import logging

import structlog


def configure_logging(log_level: str = "INFO", json_logs: bool = False) -> None:
    """Configure structlog globally for the entire process.

    Call this once at application startup (API server or Celery worker).

    Args:
        log_level: Minimum log level to emit (DEBUG/INFO/WARNING/ERROR/CRITICAL).
        json_logs: When True, emits newline-delimited JSON (for Docker / Loki / ELK).
                   When False, uses a colored human-readable console renderer.
    """
    level = logging.getLevelName(log_level.upper())

    # Processors applied to every log event regardless of output format.
    shared_processors: list = [
        # Merge any context variables bound with structlog.contextvars.bind_contextvars()
        # (used by the HTTP request-logging middleware to propagate request_id, etc.)
        structlog.contextvars.merge_contextvars,
        # Add 'level' key (info / warning / error …)
        structlog.processors.add_log_level,
        # Add UTC ISO-8601 timestamp
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]

    if json_logs:
        # Production: one JSON object per line — easy to ingest with any log aggregator.
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,  # exceptions → dict, not string
            structlog.processors.JSONRenderer(),
        ]
    else:
        # Development: colored, aligned key=value output for readability.
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        # make_filtering_bound_logger creates a fast, type-safe logger class
        # that drops calls below the configured level at zero cost.
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        # PrintLoggerFactory writes directly to stdout — ideal for containers
        # (no stdlib handler needed; the container runtime captures stdout).
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
