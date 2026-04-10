from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os

from backend.models.database import create_tables
from backend.api.routes import router
from backend.services.scheduler import start_scheduler, stop_scheduler
from backend.core.config import settings

app = FastAPI(
    title="Notifli API",
    description="AI-powered appointment reminder system for small businesses",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/static"))
if os.path.exists(static_path):
    app.mount("/static", StaticFiles(directory=static_path), name="static")

index_path   = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/templates/index.html"))
landing_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/templates/landing.html"))
privacy_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/templates/privacy.html"))
terms_path   = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/templates/terms.html"))

# Include API routes
app.include_router(router, prefix="/api")

@app.on_event("startup")
def startup():
    try:
        print("Initializing database tables...")
        create_tables()
        print("Database tables created successfully")
        
        print("Starting SMS scheduler...")
        start_scheduler()
        print(f"Notifli started on {settings.APP_URL}")
    except Exception as e:
        print(f"STARTUP ERROR: {e}")
        print(f"Database URL: {settings.DATABASE_URL[:50]}...")
        import traceback
        traceback.print_exc()
        raise

# Legal pages
@app.get("/privacy")
async def privacy():
    return FileResponse(privacy_path)

@app.get("/terms")
async def terms():
    return FileResponse(terms_path)

@app.on_event("shutdown")
def shutdown():
    stop_scheduler()

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "Notifli"}

# Landing page
@app.get("/", response_class=HTMLResponse)
async def serve_landing():
    with open(landing_path, "r") as f:
        return HTMLResponse(content=f.read())

# App dashboard
@app.get("/app", response_class=HTMLResponse)
@app.get("/app/{full_path:path}", response_class=HTMLResponse)
async def serve_app(full_path: str = ""):
    with open(index_path, "r") as f:
        return HTMLResponse(content=f.read())
