"""系统级接口。"""

from fastapi import APIRouter


router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    """返回服务健康状态，供前端和部署脚本探活使用。"""

    return {"status": "ok"}
