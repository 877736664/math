"""汇总所有 API 路由。"""

from fastapi import APIRouter

from app.api.routes.assets import router as assets_router
from app.api.routes.system import router as system_router
from app.api.routes.teaching import router as teaching_router
from app.api.routes.textbook import router as textbook_router


api_router = APIRouter(prefix="/api")
api_router.include_router(system_router)
api_router.include_router(textbook_router)
api_router.include_router(teaching_router)
api_router.include_router(assets_router)
