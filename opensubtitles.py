"""
OpenSubtitles v3 API Integration
Fetches high-quality English subtitles for translation
"""

import requests
import os
import gzip
import io
from typing import Optional, List, Dict

# OpenSubtitles API configuration
OPENSUBTITLES_API_URL = "https://api.opensubtitles.com/api/v1"
OPENSUBTITLES_API_KEY = os.environ.get("OPENSUBTITLES_API_KEY", "")
OPENSUBTITLES_USER_AGENT = "AutoArabicVibe v1.0.0"


def search_subtitles(imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
    """
    Search for English subtitles on OpenSubtitles
    
    Args:
        imdb_id: IMDB ID (e.g., 'tt1234567')
        media_type: 'movie' or 'series'
        season: Season number (for series)
        episode: Episode number (for series)
    
    Returns:
        List of subtitle results
    """
    headers = {
        "Api-Key": OPENSUBTITLES_API_KEY,
        "Content-Type": "application/json",
        "User-Agent": OPENSUBTITLES_USER_AGENT
    }
    
    params = {
        "imdb_id": imdb_id.replace("tt", ""),
        "languages": "en",
        "order_by": "download_count",
        "order_direction": "desc"
    }
    
    if media_type == "series" and season and episode:
        params["season_number"] = season
        params["episode_number"] = episode
    
    try:
        response = requests.get(
            f"{OPENSUBTITLES_API_URL}/subtitles",
            headers=headers,
            params=params,
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"[OpenSubtitles] API error: {response.status_code}")
            return []
        
        data = response.json()
        return data.get("data", [])
    
    except Exception as e:
        print(f"[OpenSubtitles] Search error: {e}")
        return []


def download_subtitle(file_id: int) -> Optional[str]:
    """
    Download subtitle content from OpenSubtitles
    
    Args:
        file_id: OpenSubtitles file ID
    
    Returns:
        Subtitle content as string, or None if failed
    """
    headers = {
        "Api-Key": OPENSUBTITLES_API_KEY,
        "Content-Type": "application/json",
        "User-Agent": OPENSUBTITLES_USER_AGENT
    }
    
    try:
        # Request download link
        response = requests.post(
            f"{OPENSUBTITLES_API_URL}/download",
            headers=headers,
            json={"file_id": file_id},
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"[OpenSubtitles] Download request error: {response.status_code}")
            return None
        
        data = response.json()
        download_url = data.get("link")
        
        if not download_url:
            print("[OpenSubtitles] No download link in response")
            return None
        
        # Download the actual file
        file_response = requests.get(download_url, timeout=15)
        
        if file_response.status_code != 200:
            print(f"[OpenSubtitles] File download error: {file_response.status_code}")
            return None
        
        content = file_response.content
        
        # Handle gzipped content
        if download_url.endswith('.gz') or file_response.headers.get('Content-Encoding') == 'gzip':
            try:
                content = gzip.decompress(content)
            except:
                pass  # Not gzipped
        
        # Decode to string with proper encoding
        try:
            return content.decode('utf-8')
        except:
            try:
                return content.decode('latin-1')
            except:
                return content.decode('utf-8', errors='ignore')
    
    except Exception as e:
        print(f"[OpenSubtitles] Download error: {e}")
        return None


def get_best_english_subtitle(imdb_id: str, media_type: str, season: int = None, episode: int = None) -> Optional[str]:
    """
    Get the best English subtitle for translation
    
    Args:
        imdb_id: IMDB ID
        media_type: 'movie' or 'series'
        season: Season number (for series)
        episode: Episode number (for series)
    
    Returns:
        Subtitle content as string, or None if not found
    """
    subtitles = search_subtitles(imdb_id, media_type, season, episode)
    
    if not subtitles:
        print(f"[OpenSubtitles] No subtitles found for {imdb_id}")
        return None
    
    # Get the first (best) result
    for sub in subtitles[:5]:  # Try top 5
        try:
            files = sub.get("attributes", {}).get("files", [])
            if files:
                file_id = files[0].get("file_id")
                if file_id:
                    content = download_subtitle(file_id)
                    if content and len(content) > 100:  # Sanity check
                        print(f"[OpenSubtitles] Successfully downloaded subtitle")
                        return content
        except Exception as e:
            print(f"[OpenSubtitles] Error processing subtitle: {e}")
            continue
    
    return None


# Fallback: Use REST API (no key required, but limited)
def search_subtitles_rest(imdb_id: str, media_type: str, season: int = None, episode: int = None) -> Optional[str]:
    """
    Fallback: Search using the old REST API (no key required)
    """
    try:
        imdb_num = imdb_id.replace("tt", "")
        
        if media_type == "series" and season and episode:
            url = f"https://rest.opensubtitles.org/search/imdbid-{imdb_num}/season-{season}/episode-{episode}/sublanguageid-eng"
        else:
            url = f"https://rest.opensubtitles.org/search/imdbid-{imdb_num}/sublanguageid-eng"
        
        headers = {
            "User-Agent": "TemporaryUserAgent"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return None
        
        data = response.json()
        
        if not data:
            return None
        
        # Get the first subtitle
        sub = data[0]
        download_url = sub.get("SubDownloadLink")
        
        if not download_url:
            return None
        
        # Download
        file_response = requests.get(download_url, timeout=15)
        content = file_response.content
        
        # Decompress gzip
        try:
            content = gzip.decompress(content)
        except:
            pass
        
        try:
            return content.decode('utf-8')
        except:
            return content.decode('latin-1', errors='ignore')
    
    except Exception as e:
        print(f"[OpenSubtitles REST] Error: {e}")
        return None
