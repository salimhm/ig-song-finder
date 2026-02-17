"""
API Views for song identification.
"""
import re
import uuid
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Sum

from .models import SongSearch, TaskStatus
from .serializers import (
    FindSongRequestSerializer,
    SongSearchSerializer,
    StatsResponseSerializer,
)
from .tasks import identify_song_task


def extract_media_id(url: str) -> str:
    """
    Extract Instagram media ID from URL.
    The media ID is the alphanumeric code after /p/, /reel/, or /reels/.
    """
    patterns = [
        r'instagram\.com/(?:p|reel|reels)/([A-Za-z0-9_-]+)',
        r'instagram\.com/stories/[^/]+/(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    # Fallback: use URL hash as ID
    return str(uuid.uuid5(uuid.NAMESPACE_URL, url))


class FindSongView(APIView):
    """
    POST /api/v1/find-song/
    
    Accept Instagram URL, check cache, and identify song.
    Returns cached result immediately if available, otherwise
    returns a task_id for polling or waits for result.
    """
    
    def post(self, request):
        # Validate request
        serializer = FindSongRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error_code': 'INVALID_URL',
                'message': serializer.errors.get('url', ['Invalid URL'])[0],
            }, status=status.HTTP_400_BAD_REQUEST)
        
        url = serializer.validated_data['url']
        media_id = extract_media_id(url)
        
        # Check cache first
        try:
            cached_result = SongSearch.objects.get(ig_media_id=media_id)
            cached_result.increment_search_count()
            
            return Response({
                'success': True,
                'cached': True,
                'data': SongSearchSerializer(cached_result).data,
            }, status=status.HTTP_200_OK)
            
        except SongSearch.DoesNotExist:
            pass
        
        # Create task for async processing
        task_id = str(uuid.uuid4())
        
        # Create task status record
        task_status_obj = TaskStatus.objects.create(
            task_id=task_id,
            status=TaskStatus.PENDING
        )
        
        # Queue Celery task
        identify_song_task.delay(
            task_id=task_id,
            url=url,
            media_id=media_id
        )
        
        return Response({
            'success': True,
            'cached': False,
            'task_id': task_id,
            'status': 'pending',
            'message': 'Song identification in progress. Poll /api/v1/task-status/{task_id}/ for results.',
        }, status=status.HTTP_202_ACCEPTED)


class TaskStatusView(APIView):
    """
    GET /api/v1/task-status/<task_id>/
    
    Poll for async task status and results.
    """
    
    def get(self, request, task_id):
        try:
            task_status_obj = TaskStatus.objects.get(task_id=task_id)
        except TaskStatus.DoesNotExist:
            return Response({
                'success': False,
                'error_code': 'TASK_NOT_FOUND',
                'message': 'Task not found.',
            }, status=status.HTTP_404_NOT_FOUND)
        
        response_data = {
            'success': True,
            'task_id': task_id,
            'status': task_status_obj.status,
        }
        
        if task_status_obj.status == TaskStatus.COMPLETED:
            if task_status_obj.song_search:
                response_data['data'] = SongSearchSerializer(task_status_obj.song_search).data
            else:
                response_data['error_code'] = 'NO_SONG_FOUND'
                response_data['message'] = 'No song was identified in this content.'
                
        elif task_status_obj.status == TaskStatus.FAILED:
            response_data['success'] = False
            response_data['error_code'] = task_status_obj.error_code or 'UNKNOWN_ERROR'
            response_data['message'] = task_status_obj.error_message or 'An error occurred.'
        
        return Response(response_data)


class StatsView(APIView):
    """
    GET /api/v1/stats/
    
    Return trending songs for "What's Hot" section.
    """
    
    def get(self, request):
        # Get top 10 most searched songs
        trending = SongSearch.objects.filter(
            song_title__isnull=False
        ).exclude(
            song_title=''
        ).order_by('-search_count')[:10]
        
        # Calculate totals
        total_searches = SongSearch.objects.aggregate(
            total=Sum('search_count')
        )['total'] or 0
        
        unique_songs = SongSearch.objects.exclude(song_title='').count()
        
        return Response({
            'trending_songs': SongSearchSerializer(trending, many=True).data,
            'total_searches': total_searches,
            'unique_songs': unique_songs,
        })
