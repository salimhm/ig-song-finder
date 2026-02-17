"""
DRF Serializers for song identification API.
"""
import re
from rest_framework import serializers
from .models import SongSearch


class FindSongRequestSerializer(serializers.Serializer):
    """Validates incoming Instagram URL requests."""
    url = serializers.URLField(required=True)
    
    def validate_url(self, value):
        """Validate that URL is from Instagram."""
        instagram_patterns = [
            r'https?://(www\.)?instagram\.com/(p|reel|reels|stories)/[\w-]+',
            r'https?://(www\.)?instagram\.com/[\w.]+/(p|reel)/[\w-]+',
        ]
        
        for pattern in instagram_patterns:
            if re.match(pattern, value, re.IGNORECASE):
                return value
        
        raise serializers.ValidationError(
            "Invalid Instagram URL. Please provide a valid Instagram Reel, Post, or Story URL."
        )


class SongSearchSerializer(serializers.ModelSerializer):
    """Serializes song search results for API response."""
    
    class Meta:
        model = SongSearch
        fields = [
            'id',
            'ig_media_id',
            'ig_url',
            'song_title',
            'artist_name',
            'album_artwork',
            'spotify_link',
            'apple_music_link',
            'shazam_url',
            'search_count',
            'created_at',
        ]
        read_only_fields = fields


class TaskStatusResponseSerializer(serializers.Serializer):
    """Response when task is queued for processing."""
    task_id = serializers.CharField()
    status = serializers.CharField()
    message = serializers.CharField()


class FindSongResponseSerializer(serializers.Serializer):
    """Combined response that handles both cached and async results."""
    success = serializers.BooleanField()
    cached = serializers.BooleanField(required=False)
    data = SongSearchSerializer(required=False)
    task_id = serializers.CharField(required=False)
    status = serializers.CharField(required=False)
    message = serializers.CharField(required=False)
    error_code = serializers.CharField(required=False)


class StatsResponseSerializer(serializers.Serializer):
    """Trending songs statistics."""
    trending_songs = SongSearchSerializer(many=True)
    total_searches = serializers.IntegerField()
    unique_songs = serializers.IntegerField()
