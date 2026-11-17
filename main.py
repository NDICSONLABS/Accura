from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from app.core.config import settings
from app.core.logging import setup_logging, RequestContextMiddleware, SecurityHeadersMiddleware
from app.core.security import get_current_user, csrf_protect
from app.core.templates import templates
from app.models.user import User
from app.routers import (
    auth, settings as settings_router, coa, journals, accruals, reporting,
    budget, statements, audit, assets, grants, budget_admin, closing
)

setup_logging()

app = FastAPI(
    title="Accura SYCEBNL",
    version="1.0.0",
    dependencies=[Depends(csrf_protect)],
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None,
)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    from app.core.i18n import translate_message

    accepts_html = "text/html" in request.headers.get("accept", "")

    if exc.status_code == 401 and accepts_html:
        return RedirectResponse(url="/auth/login", status_code=303)

    if exc.status_code in (403, 429) and accepts_html:
        message = translate_message(request, str(exc.detail))
        return HTMLResponse(
            f"<h1>{exc.status_code}</h1><p>{message}</p>",
            status_code=exc.status_code,
        )

    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "environment": settings.ENVIRONMENT}


app.include_router(auth.router)
app.include_router(settings_router.router)
app.include_router(coa.router)
app.include_router(journals.router)
app.include_router(accruals.router)
app.include_router(reporting.router)
app.include_router(budget.router)
app.include_router(statements.router)
app.include_router(audit.router)
app.include_router(assets.router)
app.include_router(grants.router)
app.include_router(budget_admin.router)
app.include_router(closing.router)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(get_current_user)) -> HTMLResponse:
    return templates.TemplateResponse(request, "dashboard.html", {
        "title": "Tableau de bord", "user": user,
    })

@app.get("/health")
async def health():
    return {"status": "ok", "message": "SYCEBNL Lockdown Engine Active"}

@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}
