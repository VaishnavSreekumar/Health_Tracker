"""API v1 routers."""

from fastapi import APIRouter
from .appointments import router as appointments_router
from .delivery import router as delivery_router
from .overview import router as overview_router
from .patients import router as patients_router
from .reminders import router as reminders_router
from .system import router as system_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(overview_router, prefix="/overview", tags=["Overview"])
api_v1_router.include_router(patients_router, prefix="/patients", tags=["Patients"])
api_v1_router.include_router(appointments_router, prefix="/appointments", tags=["Appointments"])
api_v1_router.include_router(reminders_router, prefix="/reminders", tags=["Reminders"])
api_v1_router.include_router(delivery_router, prefix="/delivery", tags=["Delivery"])
api_v1_router.include_router(system_router, prefix="/system", tags=["System"])

__all__ = ["api_v1_router"]
