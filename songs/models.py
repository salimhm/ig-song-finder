"""
Database models for song identification.
"""
import uuid
from django.db import models


class SongSearch(models.Model):
    """
    Stores cached song identification results.
    Uses Instagram Media ID as unique key to avoid duplicate API calls.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Instagram metadata
    ig_media_id = models.CharField(max_length=255, unique=True, db_index=True)
    ig_url = models.TextField()
    
    # Song metadata from Shazam
    song_title = models.CharField(max_length=500, blank=True, default='')
    artist_name = models.CharField(max_length=500, blank=True, default='')
    album_artwork = models.TextField(blank=True, default='')
    
    # Streaming links
    spotify_link = models.TextField(blank=True, default='')
    apple_music_link = models.TextField(blank=True, default='')
    
    # Shazam metadata
    shazam_track_id = models.CharField(max_length=100, blank=True, default='')
    shazam_url = models.TextField(blank=True, default='')
    
    # Analytics
    search_count = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Song Search'
        verbose_name_plural = 'Song Searches'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.song_title} by {self.artist_name}" if self.song_title else f"Search: {self.ig_media_id}"
    
    def increment_search_count(self):
        """Increment search count and save."""
        self.search_count += 1
        self.save(update_fields=['search_count', 'updated_at'])


class TaskStatus(models.Model):
    """
    Tracks async task status for polling support.
    """
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (PROCESSING, 'Processing'),
        (COMPLETED, 'Completed'),
        (FAILED, 'Failed'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_id = models.CharField(max_length=255, unique=True, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    
    # Link to result
    song_search = models.ForeignKey(
        SongSearch, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='tasks'
    )
    
    # Error tracking
    error_code = models.CharField(max_length=50, blank=True, default='')
    error_message = models.TextField(blank=True, default='')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'Task Status'
        verbose_name_plural = 'Task Statuses'
    
    def __str__(self):
        return f"Task {self.task_id}: {self.status}"
