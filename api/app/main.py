"""
Boilerplate API - Main FastAPI application.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.db import engine
from app.models.base import Base
from app.routers import auth, health, items


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager to create tables on startup."""
    # Create tables on startup
    Base.metadata.create_all(bind=engine)
    yield


# Create FastAPI app
app = FastAPI(
    title="Boilerplate API",
    description="Production-ready full-stack boilerplate API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware - Allow requests from frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost", "http://api:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(items.router)


@app.get("/")
def root() -> dict[str, str]:
    """API root endpoint."""
    return {
        "message": "Welcome to Boilerplate API",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }
