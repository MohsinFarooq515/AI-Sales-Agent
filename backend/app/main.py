import asyncio
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.chat import router as chat_router
from app.api.chat import sales_agent
from app.api.analytics import router as analytics_router
from app.api.google_calendar import router as google_calendar_router
from app.core.config import settings
from app.rag.refresh import refresh_knowledge
from app.db.database import Base, apply_compatible_schema_updates, engine


Base.metadata.create_all(
    bind=engine
)
apply_compatible_schema_updates()


app = FastAPI(
    title="AI Sales Agent API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Admin-Key"],
)


app.include_router(
    chat_router
)
app.include_router(analytics_router)
app.include_router(google_calendar_router)


@app.on_event("startup")
async def refresh_website_knowledge():
    app.state.knowledge_refresh_task = asyncio.create_task(refresh_knowledge(sales_agent))

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
ADMIN_DIR = PROJECT_ROOT / "admin"
app.mount("/widget", StaticFiles(directory=FRONTEND_DIR), name="widget")
app.mount("/admin-assets", StaticFiles(directory=ADMIN_DIR), name="admin-assets")


@app.get("/demo", include_in_schema=False)
def demo():
    return FileResponse(FRONTEND_DIR / "demo.html")


@app.get("/admin", include_in_schema=False)
def admin():
    content = (ADMIN_DIR / "index.html").read_text(encoding="utf-8")
    content = content.replace("dashboard.js?v=5", "dashboard.js?v=6")
    return HTMLResponse(content, headers={"Cache-Control": "no-store"})


@app.get("/booking", include_in_schema=False)
def booking():
    return FileResponse(FRONTEND_DIR / "booking.html")


@app.get("/inquiry", include_in_schema=False)
def inquiry():
    return FileResponse(FRONTEND_DIR / "inquiry.html")


@app.get("/")
async def root():
    return {
        "service": "AI Sales Agent API",
        "status": "running",
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy"
    }
