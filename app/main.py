"""Точка входа.

Запуск:
    uvicorn app.main:app --host 127.0.0.1 --port 8200
"""

import logging
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .auth import LoginRequired
from .config import settings
from .database import dispose, init_db
from .routers import cabinet, manage, order, pages
from .templating import templates

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await dispose()


app = FastAPI(
    title=settings.app_name, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
)
app.mount("/static", StaticFiles(directory=settings.static_root), name="static")
app.include_router(pages.router)
app.include_router(order.router)
app.include_router(cabinet.router)
app.include_router(manage.public)
app.include_router(manage.router)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.exception_handler(LoginRequired)
async def login_required(request: Request, exc: LoginRequired):
    # Опрос со страницы после истечения сессии — не перенаправлять, а честно сказать 401
    if "/api/" in request.url.path:
        return JSONResponse({"error": "Нужно войти"}, status_code=401)
    return RedirectResponse(f"{exc.login_url}?next={quote(exc.next_url)}", status_code=303)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    text = "Такой страницы нет" if exc.status_code == 404 else "Что-то пошло не так"
    # API отвечает JSON-ом, а не страницей
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": text}, status_code=exc.status_code)
    # Страница ошибки нужна человеку в браузере; на POST и прочее — коротко
    if request.method != "GET":
        return HTMLResponse(text, status_code=exc.status_code)
    return templates.TemplateResponse(
        request, "error.html", {"code": exc.status_code, "text": text}, status_code=exc.status_code
    )
