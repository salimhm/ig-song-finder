"""
Shazam API integration for music identification.
"""
import logging
import os
from typing import Optional, Dict, Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# Shazam Core API endpoints on RapidAPI
# X_RAPIDAPI_HOST = "shazam-core7.p.rapidapi.com"
# SHAZAM_DETECT_URL = "https://shazam-core7.p.rapidapi.com/songs/recognize-song"
SHAZAM_DETECT_URL = "https://shazam-song-recognition-api.p.rapidapi.com/recognize/file"
X_RAPIDAPI_HOST = "shazam-song-recognition-api.p.rapidapi.com"

def identify_song_with_shazam(audio_path: str) -> Optional[Dict[str, Any]]:
    """
    Identify a song using the Shazam Core API via RapidAPI.
    Uses multipart/form-data file upload.
    
    Args:
        audio_path: Path to the audio file to identify (.mp3, .wav, .ogg - 2-4 seconds, max 1MB)
    
    Returns:
        Shazam API response dict if successful, None otherwise
    """
    rapidapi_key = getattr(settings, 'RAPIDAPI_KEY', '') or os.getenv('RAPIDAPI_KEY', '')
    
    if not rapidapi_key:
        logger.error("RAPIDAPI_KEY not configured")
        raise Exception("API_KEY_MISSING: Shazam API key not configured")
    
    if not os.path.exists(audio_path):
        logger.error(f"Audio file not found: {audio_path}")
        raise Exception("AUDIO_NOT_FOUND: Audio file not found")
    
    # Check file size (max 1MB recommended)
    file_size = os.path.getsize(audio_path)
    if file_size > 1024 * 1024:  # 1MB
        logger.warning(f"Audio file is larger than recommended: {file_size} bytes")
    
    try:
        logger.info(f"Sending audio file to Shazam API: {audio_path}")
        
        # Determine content type based on file extension
        ext = os.path.splitext(audio_path)[1].lower()
        content_types = {
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.ogg': 'audio/ogg',
            '.m4a': 'audio/mp4',
        }
        content_type = content_types.get(ext, 'audio/mpeg')
        
        # Prepare headers - new API expects raw binary data, not multipart
        headers = {
            "X-RapidAPI-Key": rapidapi_key,
            "X-RapidAPI-Host": X_RAPIDAPI_HOST,
            "Content-Type": content_type,
        }
        
        # Send file as raw binary data (Media Type: BINARY)
        with open(audio_path, 'rb') as audio_file:
            file_data = audio_file.read()
            
            response = requests.post(
                SHAZAM_DETECT_URL,
                headers=headers,
                data=file_data,
                timeout=60
            )
        
        logger.info(f"Shazam API response status: {response.status_code}")
        
        if response.status_code == 429:
            logger.error("Shazam API rate limit exceeded")
            raise Exception("RATE_LIMIT: API rate limit exceeded. Please try again later.")
        
        if response.status_code == 401 or response.status_code == 403:
            raise Exception(f"AUTH_ERROR: Shazam 403. Body: {response.text}. Key prefix: {rapidapi_key[:8]}. Host: {X_RAPIDAPI_HOST}")
        
        if response.status_code != 200:
            logger.error(f"Shazam API error: {response.status_code} - {response.text}")
            raise Exception(f"API_ERROR: Shazam API returned status {response.status_code}")
        
        result = response.json()
        
        # Log raw response for debugging
        logger.debug(f"Shazam API raw response: {result}")
        
        # Check if a track was found
        # The response structure may vary - check common patterns
        if isinstance(result, list) and len(result) > 0:
            # Response is a list of matches
            track = result[0] if result else None
            if track:
                logger.info(f"Song identified: {track.get('title', 'Unknown')}")
                return {'track': track, 'matches': result}
        elif isinstance(result, dict):
            # Response is a dict with track info
            if result.get('track'):
                logger.info(f"Song identified: {result['track'].get('title', 'Unknown')}")
                return result
            elif result.get('title'):
                # Track info is directly in the response
                logger.info(f"Song identified: {result.get('title', 'Unknown')}")
                return {'track': result}
        
        logger.info("No song identified by Shazam")
        return None
        
    except requests.RequestException as e:
        logger.error(f"Shazam API request error: {e}")
        raise Exception(f"NETWORK_ERROR: Failed to connect to Shazam API")
    except Exception as e:
        if str(e).startswith(('RATE_LIMIT', 'AUTH_ERROR', 'API_ERROR', 'NETWORK_ERROR', 'API_KEY_MISSING', 'AUDIO_NOT_FOUND')):
            raise
        logger.error(f"Error in Shazam identification: {e}", exc_info=True)
        raise Exception(f"SHAZAM_ERROR: {str(e)}")
