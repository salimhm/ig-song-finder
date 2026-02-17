"""
ig_song_finder package initialization.
Ensures Celery app is loaded when Django starts.
"""
from .celery import app as celery_app

__all__ = ('celery_app',)
