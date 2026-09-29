from __future__ import annotations

import logging
from typing import Any

from .config import get_settings

logger = logging.getLogger("changetrace.telemetry")


def setup_telemetry(app: Any | None = None) -> None:
    """Configure OpenTelemetry TracerProvider and Exporters based on settings."""
    settings = get_settings()
    exporter_mode = settings.otel_exporter.lower()

    if exporter_mode == "none":
        logger.debug("OpenTelemetry exporter is disabled (none)")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor

        resource = Resource.create(
            {
                "service.name": "changetrace-api",
                "service.version": "0.1.0",
                "deployment.environment": settings.environment,
            }
        )
        provider = TracerProvider(resource=resource)

        if exporter_mode == "console":
            from opentelemetry.sdk.trace.export import ConsoleSpanExporter

            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
            logger.info("Configured OpenTelemetry ConsoleSpanExporter")
        elif exporter_mode == "otlp":
            try:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

                endpoint = settings.otel_endpoint
                provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
                logger.info("Configured OpenTelemetry OTLPSpanExporter at %s", endpoint)
            except ImportError:
                logger.warning("otlp_exporter_package_not_installed; falling back to Console exporter")
                from opentelemetry.sdk.trace.export import ConsoleSpanExporter

                provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))

        trace.set_tracer_provider(provider)

        if app is not None:
            try:
                from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

                FastAPIInstrumentor.instrument_app(app)
                logger.info("Instrumented FastAPI application with OpenTelemetry")
            except Exception as exc:
                logger.warning("Could not instrument FastAPI with OpenTelemetry: %s", exc)

    except Exception as exc:
        logger.warning("Failed to initialize OpenTelemetry: %s", exc)
