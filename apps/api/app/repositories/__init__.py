"""
Repository layer - Data access abstraction.
All database queries go through repositories.
"""

from app.repositories.user import UserRepository

__all__ = ["UserRepository"]
