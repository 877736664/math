"""FastAPI 入口，仅负责暴露组装后的应用实例。"""

from app.core.application import create_app


app = create_app()
