"""Main FastAPI application."""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from database import db
from routers import tasks, logs, mcp
from config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    await db.connect()
    yield
    # Shutdown
    await db.disconnect()


app = FastAPI(
    title="Supatask",
    description="Redis-based Local Task Manager",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(tasks.router)
app.include_router(logs.router)
app.include_router(mcp.router)

# Serve static files
app.mount("/", StaticFiles(directory="static", html=True), name="static")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    is_healthy = await db.ping()
    return {
        "status": "healthy" if is_healthy else "unhealthy",
        "redis": "connected" if is_healthy else "disconnected"
    }
