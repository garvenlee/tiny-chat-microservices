from typing import Optional

from blacksheep.server.application import Application
from blacksheep_prometheus.middleware import PrometheusMiddleware
from blacksheep_prometheus.view import metrics


def use_prometheus_metrics(
    app: Application,
    *,
    auth_decorator,
    endpoint: str = "/metrics/",
    middleware: Optional[PrometheusMiddleware] = None,
) -> None:
    """
    Configures the given application to use Prometheus and provide services that can be
    injected in request handlers.
    """
    middleware = middleware or PrometheusMiddleware()
    app.middlewares.append(middleware)
    app.router.add_get(endpoint, auth_decorator(metrics))
