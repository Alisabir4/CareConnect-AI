"""Vercel Services ASGI entrypoint; local development continues using app.main."""
from app.main import app

__all__ = ["app"]
