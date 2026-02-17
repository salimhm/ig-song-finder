"""
WSGI config for ig_song_finder project.
"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ig_song_finder.settings')
application = get_wsgi_application()
