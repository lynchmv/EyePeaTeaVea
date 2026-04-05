"""
Observability module for metrics, structured logging, and health monitoring.

This module provides:
- Prometheus metrics via prometheus-fastapi-instrumentator
- Structured JSON logging via python-json-logger
- Custom business metrics for M3U parsing, caching, etc.
- Enhanced health check utilities
"""
import os
import logging
import sys
from datetime import datetime
from typing import Callable

from fastapi import FastAPI, Request, Response
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from prometheus_fastapi_instrumentator.metrics import Info
from prometheus_client import Counter, Histogram, Gauge, Info as PrometheusInfo
from pythonjsonlogger import jsonlogger

# Environment configuration
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.getenv("LOG_FORMAT", "json")  # "json" or "text"
METRICS_ENABLED = os.getenv("METRICS_ENABLED", "true").lower() == "true"

# ============================================================================
# Custom Business Metrics
# ============================================================================

# M3U Parsing metrics
m3u_parse_total = Counter(
    "eyepeateavea_m3u_parse_total",
    "Total number of M3U parse operations",
    ["secret_str_prefix", "status"]  # status: success, failure
)

m3u_parse_duration_seconds = Histogram(
    "eyepeateavea_m3u_parse_duration_seconds",
    "Duration of M3U parse operations in seconds",
    ["secret_str_prefix"],
    buckets=[0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0]
)

m3u_channels_parsed = Histogram(
    "eyepeateavea_m3u_channels_parsed",
    "Number of channels parsed from M3U sources",
    ["secret_str_prefix"],
    buckets=[10, 50, 100, 250, 500, 1000, 2500, 5000]
)

# EPG Parsing metrics
epg_parse_total = Counter(
    "eyepeateavea_epg_parse_total",
    "Total number of EPG parse operations",
    ["secret_str_prefix", "status"]
)

epg_programs_parsed = Histogram(
    "eyepeateavea_epg_programs_parsed",
    "Number of programs parsed from EPG sources",
    ["secret_str_prefix"],
    buckets=[100, 500, 1000, 5000, 10000, 50000]
)

# Image processing metrics
image_process_total = Counter(
    "eyepeateavea_image_process_total",
    "Total number of image processing operations",
    ["image_type", "status"]  # image_type: poster, background, logo, icon; status: success, cache_hit, fallback, placeholder
)

image_process_duration_seconds = Histogram(
    "eyepeateavea_image_process_duration_seconds",
    "Duration of image processing operations in seconds",
    ["image_type"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

image_cache_operations = Counter(
    "eyepeateavea_image_cache_total",
    "Image cache operations",
    ["operation"]  # operation: hit, miss, store
)

# Redis metrics
redis_operation_total = Counter(
    "eyepeateavea_redis_operation_total",
    "Total Redis operations",
    ["operation", "status"]  # operation: get, set, delete, etc.; status: success, failure
)

redis_operation_duration_seconds = Histogram(
    "eyepeateavea_redis_operation_duration_seconds",
    "Duration of Redis operations in seconds",
    ["operation"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]
)

# User/Channel gauges
active_users_total = Gauge(
    "eyepeateavea_active_users_total",
    "Total number of configured users"
)

channels_total = Gauge(
    "eyepeateavea_channels_total",
    "Total number of channels across all users"
)

# Scheduler metrics
scheduler_job_total = Counter(
    "eyepeateavea_scheduler_job_total",
    "Total scheduler job executions",
    ["job_type", "status"]  # job_type: m3u_fetch; status: success, failure
)

scheduler_job_duration_seconds = Histogram(
    "eyepeateavea_scheduler_job_duration_seconds",
    "Duration of scheduler job executions in seconds",
    ["job_type"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)

scheduler_jobs_active = Gauge(
    "eyepeateavea_scheduler_jobs_active",
    "Number of active scheduled jobs"
)

# Application info
app_info = PrometheusInfo(
    "eyepeateavea_app",
    "Application information"
)


# ============================================================================
# Structured Logging Setup
# ============================================================================

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter that adds standard fields to all log records.
    """
    
    def add_fields(self, log_record: dict, record: logging.LogRecord, message_dict: dict) -> None:
        super().add_fields(log_record, record, message_dict)
        
        # Add timestamp in ISO format
        log_record["timestamp"] = datetime.utcnow().isoformat() + "Z"
        
        # Add log level
        log_record["level"] = record.levelname
        
        # Add logger name
        log_record["logger"] = record.name
        
        # Add source location
        log_record["source"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName
        }
        
        # Add service name
        log_record["service"] = "eyepeateavea"
        
        # Move message to a standard field
        if "message" not in log_record and record.getMessage():
            log_record["message"] = record.getMessage()


def setup_logging() -> None:
    """
    Configure structured logging for the application.
    
    Uses JSON format by default (configurable via LOG_FORMAT env var).
    Log level configurable via LOG_LEVEL env var.
    """
    # Get the root logger
    root_logger = logging.getLogger()
    
    # Clear existing handlers
    root_logger.handlers.clear()
    
    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    
    # Set formatter based on configuration
    if LOG_FORMAT == "json":
        formatter = CustomJsonFormatter(
            "%(timestamp)s %(level)s %(name)s %(message)s"
        )
    else:
        # Text format for local development
        formatter = logging.Formatter(
            "%(asctime)s - %(levelname)s - %(name)s - %(message)s"
        )
    
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    
    # Set log level
    log_level = getattr(logging, LOG_LEVEL, logging.INFO)
    root_logger.setLevel(log_level)
    
    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.INFO)
    
    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured",
        extra={
            "log_level": LOG_LEVEL,
            "log_format": LOG_FORMAT,
            "metrics_enabled": METRICS_ENABLED
        }
    )


# ============================================================================
# Prometheus Instrumentation
# ============================================================================

def setup_metrics(app: FastAPI, app_version: str = "1.0.0") -> Instrumentator:
    """
    Set up Prometheus metrics for the FastAPI application.
    
    Args:
        app: FastAPI application instance
        app_version: Application version string
        
    Returns:
        Configured Instrumentator instance
    """
    if not METRICS_ENABLED:
        logging.getLogger(__name__).info("Metrics disabled via METRICS_ENABLED=false")
        return None
    
    # Set application info
    app_info.info({
        "version": app_version,
        "python_version": sys.version.split()[0]
    })
    
    # Create instrumentator with sensible defaults
    instrumentator = Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        should_respect_env_var=True,
        should_instrument_requests_inprogress=True,
        excluded_handlers=[
            "/health",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json"
        ],
        inprogress_name="eyepeateavea_http_requests_inprogress",
        inprogress_labels=True,
    )
    
    # Add default metrics with simpler configuration
    # The instrumentator already provides good defaults
    instrumentator.add(
        metrics.latency(
            metric_namespace="eyepeateavea",
            metric_subsystem="http",
        )
    ).add(
        metrics.request_size(
            metric_namespace="eyepeateavea",
            metric_subsystem="http",
        )
    ).add(
        metrics.response_size(
            metric_namespace="eyepeateavea",
            metric_subsystem="http",
        )
    ).add(
        metrics.requests(
            metric_namespace="eyepeateavea",
            metric_subsystem="http",
        )
    )
    
    # Instrument the app and expose metrics endpoint
    instrumentator.instrument(app).expose(
        app,
        endpoint="/metrics",
        include_in_schema=True,
        tags=["Monitoring"]
    )
    
    logging.getLogger(__name__).info("Prometheus metrics configured at /metrics")
    
    return instrumentator


# ============================================================================
# Metric Helper Functions
# ============================================================================

def record_m3u_parse(
    secret_str: str,
    success: bool,
    duration_seconds: float,
    channel_count: int
) -> None:
    """
    Record metrics for an M3U parse operation.
    
    Args:
        secret_str: User's secret string (first 8 chars used as label)
        success: Whether the parse was successful
        duration_seconds: Duration of the parse operation
        channel_count: Number of channels parsed
    """
    prefix = secret_str[:8] if secret_str else "unknown"
    status = "success" if success else "failure"
    
    m3u_parse_total.labels(secret_str_prefix=prefix, status=status).inc()
    m3u_parse_duration_seconds.labels(secret_str_prefix=prefix).observe(duration_seconds)
    
    if success and channel_count > 0:
        m3u_channels_parsed.labels(secret_str_prefix=prefix).observe(channel_count)


def record_epg_parse(
    secret_str: str,
    success: bool,
    program_count: int = 0
) -> None:
    """
    Record metrics for an EPG parse operation.
    
    Args:
        secret_str: User's secret string
        success: Whether the parse was successful
        program_count: Number of programs parsed
    """
    prefix = secret_str[:8] if secret_str else "unknown"
    status = "success" if success else "failure"
    
    epg_parse_total.labels(secret_str_prefix=prefix, status=status).inc()
    
    if success and program_count > 0:
        epg_programs_parsed.labels(secret_str_prefix=prefix).observe(program_count)


def record_image_process(
    image_type: str,
    status: str,
    duration_seconds: float = None
) -> None:
    """
    Record metrics for an image processing operation.
    
    Args:
        image_type: Type of image (poster, background, logo, icon)
        status: Result status (success, cache_hit, fallback, placeholder)
        duration_seconds: Duration of processing (optional)
    """
    image_process_total.labels(image_type=image_type, status=status).inc()
    
    if duration_seconds is not None:
        image_process_duration_seconds.labels(image_type=image_type).observe(duration_seconds)


def record_cache_operation(operation: str) -> None:
    """
    Record a cache operation (hit, miss, store).
    
    Args:
        operation: Type of operation (hit, miss, store)
    """
    image_cache_operations.labels(operation=operation).inc()


def record_redis_operation(
    operation: str,
    success: bool,
    duration_seconds: float = None
) -> None:
    """
    Record metrics for a Redis operation.
    
    Args:
        operation: Type of operation (get, set, delete, etc.)
        success: Whether the operation was successful
        duration_seconds: Duration of the operation (optional)
    """
    status = "success" if success else "failure"
    redis_operation_total.labels(operation=operation, status=status).inc()
    
    if duration_seconds is not None and success:
        redis_operation_duration_seconds.labels(operation=operation).observe(duration_seconds)


def record_scheduler_job(
    job_type: str,
    success: bool,
    duration_seconds: float
) -> None:
    """
    Record metrics for a scheduler job execution.
    
    Args:
        job_type: Type of job (m3u_fetch, etc.)
        success: Whether the job completed successfully
        duration_seconds: Duration of the job execution
    """
    status = "success" if success else "failure"
    scheduler_job_total.labels(job_type=job_type, status=status).inc()
    scheduler_job_duration_seconds.labels(job_type=job_type).observe(duration_seconds)


def update_gauge_metrics(
    user_count: int = None,
    channel_count: int = None,
    active_jobs: int = None
) -> None:
    """
    Update gauge metrics with current values.
    
    Args:
        user_count: Current number of users (optional)
        channel_count: Current total channels (optional)
        active_jobs: Current number of active scheduler jobs (optional)
    """
    if user_count is not None:
        active_users_total.set(user_count)
    
    if channel_count is not None:
        channels_total.set(channel_count)
    
    if active_jobs is not None:
        scheduler_jobs_active.set(active_jobs)


# ============================================================================
# Health Check Utilities
# ============================================================================

def get_scheduler_health(scheduler) -> dict:
    """
    Get health status of the scheduler.
    
    Args:
        scheduler: Scheduler instance
        
    Returns:
        Dictionary with scheduler health information
    """
    try:
        if scheduler is None:
            return {
                "status": "unknown",
                "running": False,
                "message": "Scheduler instance not available"
            }
        
        is_running = scheduler.scheduler.running if hasattr(scheduler, 'scheduler') else False
        jobs = scheduler.scheduler.get_jobs() if is_running else []
        
        job_info = []
        for job in jobs:
            next_run = job.next_run_time.isoformat() if job.next_run_time else None
            job_info.append({
                "id": job.id,
                "name": job.name,
                "next_run": next_run
            })
        
        # Update gauge metric
        update_gauge_metrics(active_jobs=len(jobs))
        
        return {
            "status": "healthy" if is_running else "stopped",
            "running": is_running,
            "job_count": len(jobs),
            "jobs": job_info
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "running": False,
            "error": str(e)
        }
