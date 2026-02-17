"""
Celery configuration for ig_song_finder project.
"""
import os
from celery import Celery
from dotenv import load_dotenv

load_dotenv()

# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ig_song_finder.settings')

app = Celery('ig_song_finder')

# Load config from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')
