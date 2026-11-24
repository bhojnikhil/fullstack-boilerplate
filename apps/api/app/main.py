"""
Boilerplate API - Main FastAPI application.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import auth, health, items

# Create FastAPI app
app = FastAPI(
    title="Boilerplate API",
    description="Production-ready full-stack boilerplate API",
    version="1.0.0",
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
