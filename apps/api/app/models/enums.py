from enum import Enum


class OAuthProvider(str, Enum):
    """OAuth provider enumeration."""
    GOOGLE = "google"
