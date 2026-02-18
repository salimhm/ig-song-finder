"""
Instagram audio extraction service using yt-dlp.
"""
import logging
import os
import re
import tempfile
import subprocess
import time
from typing import Optional

import yt_dlp
from django.conf import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = 10
RETRY_DELAY = 5  # seconds between retries


def extract_audio_from_instagram(url: str, duration: int = 10) -> Optional[str]:
    """
    Extract audio from an Instagram URL using yt-dlp.
    
    Args:
        url: Instagram URL (Reel, Post, or Story)
        duration: Length of audio snippet to extract (seconds)
    
    Returns:
        Path to the extracted audio file, or None if extraction failed
    """
    # Validate URL pattern
    unsupported_patterns = [
        r'/reels/audio/',
        r'/explore/',
        r'/accounts/',
    ]
    for pattern in unsupported_patterns:
        if re.search(pattern, url):
            raise Exception(
                "INVALID_URL: This URL type is not supported. "
                "Please provide a direct reel URL (e.g. https://www.instagram.com/reels/ABC123/)"
            )
    
    # Create temp directory if it doesn't exist
    temp_dir = getattr(settings, 'AUDIO_TEMP_DIR', tempfile.gettempdir())
    os.makedirs(temp_dir, exist_ok=True)
    
    # Generate unique filename
    output_template = os.path.join(temp_dir, '%(id)s.%(ext)s')
    
    # Common options shared between extraction and download
    common_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'cookiefile': None,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        },
    }
    
    proxy_url = os.getenv('PROXIES', '')
    
    # Step 1: Extract info (metadata only) via proxy to bypass rate limits
    extract_opts = {**common_opts}
    if proxy_url:
        extract_opts['proxy'] = proxy_url
        logger.info(f"Using proxy for metadata extraction: {proxy_url.split('@')[-1] if '@' in proxy_url else 'configured'}")
    
    last_exception = None
    info = None
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with yt_dlp.YoutubeDL(extract_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    logger.error(f"Failed to extract info from {url}")
                    return None
                
                logger.info(f"Metadata extracted successfully on attempt {attempt}/{MAX_RETRIES}")
                break  # Success, exit retry loop
                
        except yt_dlp.DownloadError as e:
            error_msg = str(e).lower()
            last_exception = e
            
            # Non-retryable: content genuinely doesn't exist
            if 'not exist' in error_msg or '404' in error_msg:
                logger.error(f"Content not found: {url}")
                raise Exception("CONTENT_NOT_FOUND: The Instagram content does not exist or has been deleted")
            
            # Retryable: rate-limit / login required / proxy issues
            if 'private' in error_msg or 'login required' in error_msg or 'rate' in error_msg:
                logger.warning(f"Attempt {attempt}/{MAX_RETRIES} failed for {url}: rate-limit or login required")
                if attempt < MAX_RETRIES:
                    logger.info(f"Retrying in {RETRY_DELAY}s...")
                    time.sleep(RETRY_DELAY)
                    continue
                else:
                    logger.error(f"All {MAX_RETRIES} attempts failed for {url}")
                    raise Exception("PRIVATE_ACCOUNT: Cannot access content from private accounts")
            
            # Other download errors - also retry
            logger.warning(f"Attempt {attempt}/{MAX_RETRIES} failed for {url}: {e}")
            if attempt < MAX_RETRIES:
                logger.info(f"Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            else:
                logger.error(f"All {MAX_RETRIES} attempts failed for {url}")
                raise Exception(f"DOWNLOAD_ERROR: {str(e)}")
            
        except Exception as e:
            last_exception = e
            logger.warning(f"Attempt {attempt}/{MAX_RETRIES} - unexpected error for {url}: {e}")
            if attempt < MAX_RETRIES:
                logger.info(f"Retrying in {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            else:
                logger.error(f"All {MAX_RETRIES} attempts failed for {url}", exc_info=True)
                raise
    
    if not info:
        if last_exception:
            raise last_exception
        return None
    
    # Step 2: Download the media directly WITHOUT proxy (saves bandwidth)
    download_opts = {
        **common_opts,
        # No proxy here - download directly
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }],
    }
    
    try:
        logger.info(f"Downloading media directly (no proxy) for {info.get('id', 'unknown')}")
        with yt_dlp.YoutubeDL(download_opts) as ydl:
            ydl.process_ie_result(info, download=True)
    except Exception as e:
        logger.error(f"Direct download failed: {e}")
        raise Exception(f"DOWNLOAD_ERROR: Failed to download media: {str(e)}")
    
    video_id = info.get('id', 'unknown')
    
    # The output file will be .mp3 after post-processing
    audio_path = os.path.join(temp_dir, f"{video_id}.mp3")
    
    if not os.path.exists(audio_path):
        # Try common alternatives
        for ext in ['m4a', 'mp4', 'webm']:
            alt_path = os.path.join(temp_dir, f"{video_id}.{ext}")
            if os.path.exists(alt_path):
                audio_path = alt_path
                break
    
    if not os.path.exists(audio_path):
        logger.error(f"Audio file not found after extraction: {audio_path}")
        return None
    
    # Trim to specified duration using ffmpeg
    trimmed_path = trim_audio(audio_path, duration)
    
    # Use trimmed version if successful, otherwise use full file
    if trimmed_path and os.path.exists(trimmed_path):
        # Remove original, keep trimmed
        if trimmed_path != audio_path:
            try:
                os.remove(audio_path)
            except:
                pass
        return trimmed_path
    
    return audio_path


def trim_audio(audio_path: str, duration: int) -> Optional[str]:
    """
    Trim audio file to specified duration using ffmpeg.
    
    Args:
        audio_path: Path to input audio file
        duration: Desired duration in seconds
    
    Returns:
        Path to trimmed audio file, or original path if trimming failed
    """
    if not os.path.exists(audio_path):
        return None
    
    # Generate output path
    base, ext = os.path.splitext(audio_path)
    output_path = f"{base}_trimmed{ext}"
    
    try:
        # Use ffmpeg to trim audio
        cmd = [
            'ffmpeg',
            '-y',  # Overwrite output
            '-i', audio_path,
            '-t', str(duration),
            '-acodec', 'copy',
            output_path
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30
        )
        
        if result.returncode == 0 and os.path.exists(output_path):
            return output_path
        else:
            logger.warning(f"FFmpeg trim failed: {result.stderr.decode()}")
            return audio_path
            
    except subprocess.TimeoutExpired:
        logger.warning("FFmpeg trim timed out")
        return audio_path
    except FileNotFoundError:
        logger.warning("FFmpeg not found, skipping audio trim")
        return audio_path
    except Exception as e:
        logger.warning(f"Error trimming audio: {e}")
        return audio_path
