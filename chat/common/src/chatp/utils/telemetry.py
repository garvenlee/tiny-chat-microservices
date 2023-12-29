from ._meta import SingletonMeta

from typing import Optional
from opentelemetry.trace import set_tracer_provider
from opentelemetry.metrics import set_meter_provider
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    MetricExporter,
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes

# from opentelemetry.propagate import extract, inject


class Telemetry(metaclass=SingletonMeta):
    def setup_telemetry_tracer_provider(
        self,
        resource: Resource,
        trace_exporter: Optional[SpanExporter] = None,
        metric_exporter: Optional[MetricExporter] = None,
        use_metric: bool = False,
    ):
        trace_provider = TracerProvider(resource=resource)
        set_tracer_provider(trace_provider)
        # get_tracer_provider().add_span_processor(BatchSpanProcessor(self.exporter))
        if trace_exporter is None:
            attributes = resource.attributes
            trace_exporter = ConsoleSpanExporter(
                service_name=attributes[ResourceAttributes.SERVICE_NAME]
            )
        trace_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
        self.trace_provider = trace_provider

        if use_metric:
            if metric_exporter is None:
                metric_exporter = ConsoleMetricExporter()
            meter_provider = MeterProvider(
                resource=resource,
                metric_readers=[PeriodicExportingMetricReader(metric_exporter)],
            )
            set_meter_provider(meter_provider)
            self.meter_provider = meter_provider

    def close_telemetry_tracer_provider(self):
        provider, self.trace_provider = self.trace_provider, None
        provider.shutdown()  # no need, Provider aexit

        if (provider := getattr(self, "meter_provider", None)) is not None:
            provider.shutdown()
            self.meter_provider = None
