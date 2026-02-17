"""
URL routing for songs app.
"""
from django.urls import path
from . import views

app_name = 'songs'

urlpatterns = [
    path('find-song/', views.FindSongView.as_view(), name='find-song'),
    path('task-status/<str:task_id>/', views.TaskStatusView.as_view(), name='task-status'),
    path('stats/', views.StatsView.as_view(), name='stats'),
]
