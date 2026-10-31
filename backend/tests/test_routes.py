"""Every API route must be public by design, self-service, or guarded by require()."""
from fastapi.routing import APIRoute

from app.main import PUBLIC_PATHS, SELF_PATHS, app


def _api_routes():
    for r in app.routes:
        if isinstance(r, APIRoute):
            yield r
        for sub in getattr(getattr(r, "original_router", None), "routes", []):
            if isinstance(sub, APIRoute):
                yield sub


def _dependency_calls(dependant):
    for d in dependant.dependencies:
        yield d.call
        yield from _dependency_calls(d)


def test_every_route_is_protected():
    unprotected = []
    routes = list(_api_routes())
    assert len(routes) >= 20
    for route in routes:
        if route.path in PUBLIC_PATHS or route.path in SELF_PATHS:
            continue
        if not any(hasattr(c, "required_permission") for c in _dependency_calls(route.dependant)):
            unprotected.append(f"{sorted(route.methods)} {route.path}")
    assert unprotected == [], f"Routes without require(): {unprotected}"
