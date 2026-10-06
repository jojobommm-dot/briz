"""Точка входа.

Запуск:
    uvicorn app.main:app --host 127.0.0.1 --port 8200
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .routers import pages
from .templating import templates

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

app = FastAPI(title=settings.app_name, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=settings.static_root), name="static")
app.include_router(pages.router)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    text = "Такой страницы нет" if exc.status_code == 404 else "Что-то пошло не так"
    # Страница ошибки нужна человеку в браузере; на POST и прочее — коротко
    if request.method != "GET":
        return HTMLResponse(text, status_code=exc.status_code)
    return templates.TemplateResponse(
        request, "error.html", {"code": exc.status_code, "text": text}, status_code=exc.status_code
    )
