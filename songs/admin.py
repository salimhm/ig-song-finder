from django.contrib import admin
from .models import SongSearch, TaskStatus


@admin.register(SongSearch)
class SongSearchAdmin(admin.ModelAdmin):
    list_display = ['song_title', 'artist_name', 'search_count', 'created_at']
    list_filter = ['created_at']
    search_fields = ['song_title', 'artist_name', 'ig_media_id']
    readonly_fields = ['id', 'created_at', 'updated_at']
    ordering = ['-search_count']


@admin.register(TaskStatus)
class TaskStatusAdmin(admin.ModelAdmin):
    list_display = ['task_id', 'status', 'created_at']
    list_filter = ['status', 'created_at']
    search_fields = ['task_id']
    readonly_fields = ['id', 'created_at', 'updated_at']
