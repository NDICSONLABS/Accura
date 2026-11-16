from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from app.core.templates import templates
from app.routers import auth, settings, coa, journals, accruals
from app.core.security import get_current_user
from app.models.user import User

app = FastAPI(title="Accura SYCEBNL", version="0.4.1")


# --- GLOBAL EXCEPTION HANDLER FOR WEB REDIRECTS ---
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    # If the user is not authenticated (401) and requesting a web page, redirect to login
    if exc.status_code == 401:
        if "text/html" in request.headers.get("accept", ""):
            return RedirectResponse(url="/auth/login", status_code=303)

    # If the user is forbidden (403), show a simple HTML error
    if exc.status_code == 403:
        if "text/html" in request.headers.get("accept", ""):
            return HTMLResponse("<h1>403 Forbidden</h1><p>You do not have permission to access this page.</p>",
                                status_code=403)

    # Default JSON response for API calls
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(coa.router)
app.include_router(journals.router)
app.include_router(accruals.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user: User = Depends(get_current_user)) -> HTMLResponse:
    return templates.TemplateResponse(request, "dashboard.html", {"title": "Tableau de bord", "user": user})
@app.get("/health")
async def health():
    return {"status": "ok", "message": "SYCEBNL Lockdown Engine Active"}

@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}
