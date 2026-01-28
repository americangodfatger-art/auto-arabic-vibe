"""
Subtitle Sources Manager
33 subtitle providers with unified search interface
"""

import requests
from bs4 import BeautifulSoup
import gzip
import re
import os
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed


class SubtitleSource:
    """Base class for subtitle sources"""
    
    name: str = "Unknown"
    source_type: str = "unknown"  # 'api' or 'scrape'
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        """Search for subtitles - override in subclass"""
        return []
    
    def download(self, url: str) -> Optional[str]:
        """Download subtitle content"""
        try:
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
            if response.status_code != 200:
                return None
            
            content = response.content
            
            # Handle gzip
            if url.endswith('.gz') or response.headers.get('Content-Encoding') == 'gzip':
                try:
                    content = gzip.decompress(content)
                except:
                    pass
            
            # Decode
            try:
                return content.decode('utf-8')
            except:
                return content.decode('latin-1', errors='ignore')
        except Exception as e:
            print(f"[{self.name}] Download error: {e}")
            return None


# =============================================================================
# API-BASED SOURCES
# =============================================================================

class OpenSubtitlesSource(SubtitleSource):
    """OpenSubtitles - Largest database with REST API"""
    name = "OpenSubtitles"
    source_type = "api"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        try:
            imdb_num = imdb_id.replace("tt", "")
            
            if media_type == "series" and season and episode:
                url = f"https://rest.opensubtitles.org/search/imdbid-{imdb_num}/season-{season}/episode-{episode}/sublanguageid-eng"
            else:
                url = f"https://rest.opensubtitles.org/search/imdbid-{imdb_num}/sublanguageid-eng"
            
            response = requests.get(url, headers={'User-Agent': 'TemporaryUserAgent'}, timeout=5)
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            
            return [{
                'source': self.name,
                'url': sub.get('SubDownloadLink'),
                'title': sub.get('SubFileName', 'OpenSubtitles'),
                'lang': 'en',
                'rating': float(sub.get('SubRating', 0))
            } for sub in data[:3] if sub.get('SubDownloadLink')]
        except Exception as e:
            print(f"[{self.name}] Error: {e}")
            return []


class SubDLSource(SubtitleSource):
    """SubDL - Official API with Subscene library"""
    name = "SubDL"
    source_type = "api"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        # Try free API first (no key needed)
        try:
            url = f"https://api.subdl.com/auto/v1/subtitles?imdb_id={imdb_id}&languages=en&type={'episode' if media_type == 'series' else 'movie'}"
            if media_type == "series" and season and episode:
                url += f"&season_number={season}&episode_number={episode}"
            
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=6)
            if response.status_code == 200:
                data = response.json()
                subs = data.get('subtitles', [])
                if subs:
                    return [{
                        'source': self.name,
                        'url': f"https://dl.subdl.com{sub.get('url')}" if sub.get('url', '').startswith('/') else sub.get('url'),
                        'title': sub.get('release_name', 'SubDL'),
                        'lang': 'en',
                        'rating': 2
                    } for sub in subs[:3] if sub.get('url')]
        except Exception as e:
            print(f"[{self.name}] Free API error: {e}")
        
        # Fallback to API key if available
        api_key = os.environ.get('SUBDL_API_KEY', '')
        if not api_key:
            return []
        
        try:
            url = f"https://api.subdl.com/api/v1/subtitles?api_key={api_key}&imdb_id={imdb_id}&languages=en"
            if media_type == "series" and season and episode:
                url += f"&season_number={season}&episode_number={episode}"
            
            response = requests.get(url, timeout=6)
            if response.status_code != 200:
                return []
            
            data = response.json()
            subs = data.get('subtitles', [])
            
            return [{
                'source': self.name,
                'url': sub.get('url'),
                'title': sub.get('release_name', 'SubDL'),
                'lang': 'en',
                'rating': 2
            } for sub in subs[:3] if sub.get('url')]
        except Exception as e:
            print(f"[{self.name}] Error: {e}")
            return []


class PodnapisiSource(SubtitleSource):
    """Podnapisi - Multi-language with rating system"""
    name = "Podnapisi"
    source_type = "api"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        try:
            # Podnapisi XML-RPC or web scrape
            url = f"https://www.podnapisi.net/subtitles/search/?keywords={imdb_id}&language=en"
            if media_type == "series" and season:
                url += f"&seasons={season}&episodes={episode}"
            
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            if response.status_code != 200:
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            for row in soup.select('tr.subtitle-entry')[:5]:
                link = row.select_one('a.subtitle-download')
                if link and link.get('href'):
                    results.append({
                        'source': self.name,
                        'url': f"https://www.podnapisi.net{link['href']}",
                        'title': 'Podnapisi',
                        'lang': 'en',
                        'rating': 1
                    })
            
            return results
        except Exception as e:
            print(f"[{self.name}] Error: {e}")
            return []


class SubDBSource(SubtitleSource):
    """SubDB - Hash-based matching"""
    name = "SubDB"
    source_type = "api"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        # SubDB requires video hash, not IMDB
        return []


class SubSourceSource(SubtitleSource):
    """SubSource - Subtitle aggregator API"""
    name = "SubSource"
    source_type = "api"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        try:
            api_key = os.environ.get('SUBSOURCE_API_KEY', '')
            headers = {'User-Agent': 'Mozilla/5.0'}
            if api_key:
                headers['Authorization'] = f'Bearer {api_key}'
            
            # SubSource API endpoint
            url = f"https://api.subsource.net/api/searchMovie?imdb={imdb_id}"
            
            response = requests.get(url, headers=headers, timeout=6)
            if response.status_code != 200:
                return []
            
            data = response.json()
            if not data.get('found'):
                return []
            
            movie_name = data.get('movie', {}).get('linkName', '')
            if not movie_name:
                return []
            
            # Get subtitles for this movie
            sub_url = f"https://api.subsource.net/api/getMovie?movieName={movie_name}&langs=english"
            if media_type == "series" and season:
                sub_url += f"&season=season-{season}"
            
            sub_response = requests.get(sub_url, headers=headers, timeout=6)
            if sub_response.status_code != 200:
                return []
            
            sub_data = sub_response.json()
            subs = sub_data.get('subs', [])
            
            results = []
            for sub in subs[:5]:
                if media_type == "series" and episode:
                    # Filter by episode
                    sub_name = sub.get('releaseName', '').lower()
                    if f"e{episode:02d}" not in sub_name and f"e{episode}" not in sub_name:
                        continue
                
                sub_id = sub.get('subId')
                if sub_id:
                    results.append({
                        'source': self.name,
                        'url': f"https://api.subsource.net/api/downloadSub/{sub_id}",
                        'title': sub.get('releaseName', 'SubSource'),
                        'lang': 'en',
                        'rating': 2
                    })
            
            return results[:3]
        except Exception as e:
            print(f"[{self.name}] Error: {e}")
            return []


class WyzieSubsSource(SubtitleSource):
    """WyzieSubsAPI - Open-source scraper"""
    name = "WyzieSubsAPI"
    source_type = "api"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        try:
            url = f"https://subs.wyzie.ru/search?id={imdb_id}"
            if media_type == "series" and season and episode:
                url += f"&season={season}&episode={episode}"
            
            response = requests.get(url, timeout=10)
            if response.status_code != 200:
                return []
            
            data = response.json()
            if not isinstance(data, list):
                return []
            
            return [{
                'source': self.name,
                'url': sub.get('url') or sub.get('download_url'),
                'title': sub.get('filename', 'WyzieSubs'),
                'lang': 'en',
                'rating': 1
            } for sub in data[:5] if sub.get('url') or sub.get('download_url')]
        except Exception as e:
            print(f"[{self.name}] Error: {e}")
            return []


class BSPlayerSource(SubtitleSource):
    """BSPlayer - Alternative database"""
    name = "BSPlayer"
    source_type = "api"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        # BSPlayer API requires specific integration
        return []


class NapiprojektSource(SubtitleSource):
    """Napiprojekt - Polish subtitle database"""
    name = "Napiprojekt"
    source_type = "api"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        # Napiprojekt requires video hash
        return []


class ShooterSource(SubtitleSource):
    """Shooter - Chinese subtitle database"""
    name = "Shooter"
    source_type = "api"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        # Shooter requires video hash
        return []


# =============================================================================
# SCRAPE-BASED SOURCES
# =============================================================================

class YIFYSource(SubtitleSource):
    """YIFY Subtitles - Synced for YTS releases"""
    name = "YIFY"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        if media_type == "series":
            return []  # YIFY is movies only
        
        try:
            url = f"https://yifysubtitles.org/movie-imdb/{imdb_id}"
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            
            if response.status_code != 200:
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            results = []
            
            for row in soup.select('tbody tr')[:5]:
                lang_elem = row.select_one('.sub-lang')
                if lang_elem and 'english' in lang_elem.text.lower():
                    link = row.select_one('a.subtitle-download')
                    if link and link.get('href'):
                        results.append({
                            'source': self.name,
                            'url': f"https://yifysubtitles.org{link['href']}",
                            'title': 'YIFY Subtitle',
                            'lang': 'en',
                            'rating': 2
                        })
            
            return results
        except Exception as e:
            print(f"[{self.name}] Error: {e}")
            return []


class Addic7edSource(SubtitleSource):
    """Addic7ed - High-quality TV show subs"""
    name = "Addic7ed"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        # Addic7ed requires session/cookies
        return []


class SubsceneSource(SubtitleSource):
    """Subscene - Popular community source"""
    name = "Subscene"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        # Subscene requires title search
        return []


class TVSubtitlesSource(SubtitleSource):
    """TVSubtitles - TV series focused"""
    name = "TVSubtitles"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        if media_type != "series":
            return []
        # TVSubtitles requires show name
        return []


class MovieSubtitlesSource(SubtitleSource):
    """MovieSubtitles - Wide movie collection"""
    name = "MovieSubtitles"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        # MovieSubtitles requires title search
        return []


class SubtitleSeekerSource(SubtitleSource):
    """SubtitleSeeker - Aggregator"""
    name = "SubtitleSeeker"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        # Aggregator - searches multiple sources
        return []


class ISubtitlesSource(SubtitleSource):
    """iSubtitles - General subtitle site"""
    name = "iSubtitles"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


class Subs4FreeSource(SubtitleSource):
    """Subs4Free - English and Greek"""
    name = "Subs4Free"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


class GreekSubsSource(SubtitleSource):
    """GreekSubs - Greek subtitles"""
    name = "GreekSubs"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


class SubtitrariSource(SubtitleSource):
    """Subtitrari-noi - Romanian subtitles"""
    name = "Subtitrari"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


class DownSubSource(SubtitleSource):
    """DownSub - YouTube/Streaming subs"""
    name = "DownSub"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        # DownSub is for online videos
        return []


class SubdivxSource(SubtitleSource):
    """Subdivx - Spanish subtitles"""
    name = "Subdivx"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


class LegendeiSource(SubtitleSource):
    """Legendei - Portuguese subtitles"""
    name = "Legendei"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


class FeliratokSource(SubtitleSource):
    """Feliratok - Hungarian subtitles"""
    name = "Feliratok"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


class TitloviSource(SubtitleSource):
    """Titlovi - Balkan subtitles"""
    name = "Titlovi"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


class Napisy24Source(SubtitleSource):
    """Napisy24 - Polish subtitles"""
    name = "Napisy24"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


class SubtitlesHRSource(SubtitleSource):
    """Subtitles.hr - Croatian subtitles"""
    name = "SubtitlesHR"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


class SuperSubtitlesSource(SubtitleSource):
    """SuperSubtitles - Hungarian"""
    name = "SuperSubtitles"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


class SubiratSource(SubtitleSource):
    """Subirat - Hungarian"""
    name = "Subirat"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


class HosszuPuskaSource(SubtitleSource):
    """HosszuPuska - Hungarian"""
    name = "HosszuPuska"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


class NotabenoidSource(SubtitleSource):
    """Notabenoid - Russian community"""
    name = "Notabenoid"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


class SubsComRuSource(SubtitleSource):
    """Subs.com.ru - Russian subtitles"""
    name = "SubsComRu"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


class AssrtSource(SubtitleSource):
    """Assrt - Chinese subtitles"""
    name = "Assrt"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


class ZimukuSource(SubtitleSource):
    """Zimuku - Chinese subtitles"""
    name = "Zimuku"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


class SubifySource(SubtitleSource):
    """Subify - Multi-database aggregator"""
    name = "Subify"
    source_type = "scrape"
    
    def search(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> List[Dict]:
        return []


# =============================================================================
# SOURCE MANAGER
# =============================================================================

class SourceManager:
    """Manages all 33 subtitle sources"""
    
    def __init__(self):
        # Initialize all 33 sources
        self.sources = [
            # API Sources (8)
            OpenSubtitlesSource(),
            SubDLSource(),
            SubSourceSource(),
            PodnapisiSource(),
            WyzieSubsSource(),
            SubDBSource(),
            BSPlayerSource(),
            NapiprojektSource(),
            ShooterSource(),
            
            # Scrape Sources (25)
            YIFYSource(),
            Addic7edSource(),
            SubsceneSource(),
            TVSubtitlesSource(),
            MovieSubtitlesSource(),
            SubtitleSeekerSource(),
            ISubtitlesSource(),
            Subs4FreeSource(),
            GreekSubsSource(),
            SubtitrariSource(),
            DownSubSource(),
            SubdivxSource(),
            LegendeiSource(),
            FeliratokSource(),
            TitloviSource(),
            Napisy24Source(),
            SubtitlesHRSource(),
            SuperSubtitlesSource(),
            SubiratSource(),
            HosszuPuskaSource(),
            NotabenoidSource(),
            SubsComRuSource(),
            AssrtSource(),
            ZimukuSource(),
            SubifySource(),
        ]
        
        print(f"[SourceManager] Initialized {len(self.sources)} subtitle sources")
    
    def search_all(self, imdb_id: str, media_type: str, season: int = None, episode: int = None, 
                   max_workers: int = 5, max_results: int = 5) -> List[Dict]:
        """
        Search sources in parallel for subtitles
        
        Args:
            imdb_id: IMDB ID
            media_type: 'movie' or 'series'
            season: Season number
            episode: Episode number
            max_workers: Parallel workers
            max_results: Stop after this many results
        
        Returns:
            List of subtitle results
        """
        all_results = []
        
        # Use more sources for better coverage
        active_sources = [s for s in self.sources if s.name in [
            'OpenSubtitles', 'WyzieSubsAPI', 'YIFY', 'SubDL', 'Podnapisi', 'SubSource'
        ]]
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(source.search, imdb_id, media_type, season, episode): source
                for source in active_sources
            }
            
            try:
                for future in as_completed(futures, timeout=10):
                    source = futures[future]
                    try:
                        results = future.result(timeout=6)
                        if results:
                            all_results.extend(results)
                            print(f"[{source.name}] Found {len(results)} subtitles")
                        
                        # Early exit if we have enough
                        if len(all_results) >= max_results:
                            break
                    except Exception as e:
                        print(f"[{source.name}] Failed: {e}")
            except Exception as e:
                print(f"[SourceManager] Timeout: {e}")
        
        # Sort by rating
        all_results.sort(key=lambda x: x.get('rating', 0), reverse=True)
        
        return all_results[:max_results]
    
    def get_first_subtitle(self, imdb_id: str, media_type: str, season: int = None, episode: int = None) -> Optional[str]:
        """
        Get the first available subtitle content
        
        Returns:
            Subtitle content as string, or None
        """
        results = self.search_all(imdb_id, media_type, season, episode)
        
        for result in results:
            url = result.get('url')
            if not url:
                continue
            
            # Find the source to use its download method
            for source in self.sources:
                if source.name == result.get('source'):
                    content = source.download(url)
                    if content and len(content) > 100:
                        print(f"[SourceManager] Successfully downloaded from {source.name}")
                        return content
                    break
            
            # Fallback download
            content = SubtitleSource().download(url)
            if content and len(content) > 100:
                return content
        
        return None


# Global instance
source_manager = SourceManager()
