"""
Celery tasks for async song identification.
"""
import logging
import os
import tempfile
from celery import shared_task
from django.conf import settings

from .models import SongSearch, TaskStatus
from .services.instagram import extract_audio_from_instagram
from .services.shazam import identify_song_with_shazam

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=5)
def identify_song_task(self, task_id: str, url: str, media_id: str):
    """
    Main task to identify a song from an Instagram URL.
    
    1. Download audio from Instagram using yt-dlp
    2. Send audio to Shazam API for identification
    3. Store results in database
    4. Update task status
    """
    try:
        # Update task status to processing
        task_status = TaskStatus.objects.get(task_id=task_id)
        task_status.status = TaskStatus.PROCESSING
        task_status.save()
        
        logger.info(f"Starting song identification for {url}")
        
        # Step 1: Extract audio from Instagram
        audio_path = None
        try:
            audio_path = extract_audio_from_instagram(url)
            if not audio_path:
                raise Exception("Failed to extract audio from Instagram URL")
            
            logger.info(f"Audio extracted to {audio_path}")
            
            # Step 2: Identify song using Shazam
            shazam_result = identify_song_with_shazam(audio_path)
            
            if not shazam_result or not shazam_result.get('track'):
                # No song found
                task_status.status = TaskStatus.COMPLETED
                task_status.error_code = 'NO_SONG_FOUND'
                task_status.error_message = 'No song was identified in this audio.'
                task_status.save()
                return {'status': 'completed', 'song_found': False}
            
            # Step 3: Parse Shazam response and create SongSearch record
            track = shazam_result['track']
            
            # Extract streaming links from Shazam response
            apple_music_link = ''
            spotify_link = ''
            
            # Get Apple Music link from hub options
            hub = track.get('hub', {})
            for option in hub.get('options', []):
                if option.get('providername') == 'applemusic':
                    for action in option.get('actions', []):
                        if action.get('type') == 'uri':
                            apple_music_link = action.get('uri', '')
                            break
            
            # Get Spotify link from providers
            for provider in hub.get('providers', []):
                if provider.get('type') == 'SPOTIFY':
                    for action in provider.get('actions', []):
                        if action.get('uri', '').startswith('spotify:'):
                            # Convert spotify URI to web URL
                            spotify_uri = action.get('uri', '')
                            # spotify:search:... -> https://open.spotify.com/search/...
                            if spotify_uri.startswith('spotify:search:'):
                                search_term = spotify_uri.replace('spotify:search:', '')
                                spotify_link = f'https://open.spotify.com/search/{search_term}'
                            break
            
            # Get images
            images = track.get('images', {})
            album_artwork = images.get('coverart', '') or images.get('background', '')
            
            # Create or update SongSearch record
            song_search, created = SongSearch.objects.update_or_create(
                ig_media_id=media_id,
                defaults={
                    'ig_url': url,
                    'song_title': track.get('title', ''),
                    'artist_name': track.get('subtitle', ''),
                    'album_artwork': album_artwork,
                    'spotify_link': spotify_link,
                    'apple_music_link': apple_music_link,
                    'shazam_track_id': track.get('key', ''),
                    'shazam_url': track.get('url', ''),
                }
            )
            
            # Update task status
            task_status.status = TaskStatus.COMPLETED
            task_status.song_search = song_search
            task_status.save()
            
            logger.info(f"Song identified: {song_search.song_title} by {song_search.artist_name}")
            
            return {
                'status': 'completed',
                'song_found': True,
                'song_id': str(song_search.id),
            }
            
        finally:
            # Cleanup temp audio file
            if audio_path and os.path.exists(audio_path):
                try:
                    os.remove(audio_path)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp file {audio_path}: {e}")
                    
    except Exception as e:
        error_str = str(e)
        logger.error(f"Error identifying song: {error_str}", exc_info=True)
        
        # Parse error code from exception message (format: "ERROR_CODE: message")
        error_code = 'PROCESSING_ERROR'
        error_message = error_str
        
        # List of known error codes that should not be retried
        non_retryable_errors = ['PRIVATE_ACCOUNT', 'CONTENT_NOT_FOUND', 'NO_SONG_FOUND', 'INVALID_URL']
        
        if ':' in error_str:
            potential_code = error_str.split(':')[0].strip()
            if potential_code.isupper() and '_' in potential_code:
                error_code = potential_code
                error_message = error_str.split(':', 1)[1].strip() if ':' in error_str else error_str
        
        # Update task status to failed
        try:
            task_status = TaskStatus.objects.get(task_id=task_id)
            task_status.status = TaskStatus.FAILED
            task_status.error_code = error_code
            task_status.error_message = error_message
            task_status.save()
        except Exception:
            pass
        
        # Only retry for transient errors, not for user/content issues
        if error_code not in non_retryable_errors:
            raise self.retry(exc=e)
        
        # For non-retryable errors, just return without retrying
        return {'status': 'failed', 'error_code': error_code, 'error_message': error_message}

