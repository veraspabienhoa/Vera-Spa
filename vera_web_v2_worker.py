"""Worker-only ASGI entrypoint: ``uvicorn vera_web_v2_worker:app``.

Load the canonical installer/policy chain but expose no business/auth routes.
Importing this module performs no background work; ASGI lifespan owns all loops.
FaceGate, TimeSoft and existing external schedules are intentionally unchanged.
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI

if os.environ.get('VERA_SERVICE_ROLE', 'worker').strip().lower() != 'worker':
    raise RuntimeError('The worker entrypoint requires VERA_SERVICE_ROLE=worker')
os.environ['VERA_SERVICE_ROLE'] = 'worker'

from vera_web_v2_api_v38 import app as canonical_app
from vera_worker_runtime import install_health_routes, service_role

if service_role() != 'worker':
    raise RuntimeError('Managed configuration must preserve the explicit worker role')


@asynccontextmanager
async def lifespan(application):
    async with canonical_app.router.lifespan_context(canonical_app) as state:
        yield state


app = FastAPI(title='VERA SPA background worker', lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)
install_health_routes(app, canonical_app.state.worker_runtime)
