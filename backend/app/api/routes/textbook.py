"""教材目录接口。"""

from fastapi import APIRouter

from app.schemas.api import TextbookCatalogResponse
from app.repositories.textbook_repository import get_textbook_catalog


router = APIRouter(tags=["textbook"])


@router.get("/textbook-catalog", response_model=TextbookCatalogResponse)
def textbook_catalog():
    """返回前端教材选择器需要的教材目录与默认值。"""

    return TextbookCatalogResponse(**get_textbook_catalog())
