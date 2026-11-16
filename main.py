from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from app.core.templates import templates
from app.routers import auth, settings, coa, journals

app = FastAPI(title="Accura SYCEBNL", version="0.3.0")

app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(coa.router)
app.include_router(journals.router)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    # Notice: request is the FIRST argument, template name is SECOND, context is THIRD
    return templates.TemplateResponse(request, "dashboard.html", {"title": "Tableau de bord"})
@app.get("/health")
async def health():
    return {"status": "ok", "message": "SYCEBNL Lockdown Engine Active"}

@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/hello/{name}")
async def say_hello(name: str):
    return {"message": f"Hello {name}"}
