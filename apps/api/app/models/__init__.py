"""
SQLAlchemy ORM models.
All models inherit from Base, UUIDMixin, and TimestampMixin for consistency.
"""

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.user import OAuthAccount, User

__all__ = [
    "Base",
    "UUIDMixin",
    "TimestampMixin",
    "User",
    "OAuthAccount",
]
