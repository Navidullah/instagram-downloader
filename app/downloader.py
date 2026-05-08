import re
import yt_dlp
import aiohttp
import asyncio
from typing import Dict, Any, Optional
from urllib.parse import urlparse, parse_qs

class InstagramDownloader:
    def __init__(self):
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
    def validate_url(self, url: str) -> Dict[str, Any]:
        """Validate Instagram URL and determine content type"""
        patterns = {
            'reel': r'instagram\.com/reel/',
            'post': r'instagram\.com/p/',
            'tv': r'instagram\.com/tv/',
            'story': r'instagram\.com/stories/',
            'highlight': r'instagram\.com/stories/highlights/'
        }
        
        for content_type, pattern in patterns.items():
            if re.search(pattern, url):
                return {'valid': True, 'type': content_type}
        
        # Check if it's any Instagram URL
        if re.search(r'instagram\.com/', url):
            return {'valid': True, 'type': 'unknown'}
        
        return {'valid': False, 'type': None}
    
    def clean_url(self, url: str) -> str:
        """Remove tracking parameters from URL"""
        parsed = urlparse(url)
        # Remove tracking parameters
        clean_params = {}
        for k, v in parse_qs(parsed.query).items():
            if not k.startswith('utm_') and k not in ['igsh', 'ig_mid', 'from', 'ref']:
                clean_params[k] = v[0]
        
        # Rebuild URL without tracking
        from urllib.parse import urlunparse
        query_string = '&'.join([f"{k}={v}" for k, v in clean_params.items()])
        
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            query_string,
            parsed.fragment
        ))
    
    def clean_title(self, title: str, max_length: int = 60) -> str:
        """Clean and shorten video title"""
        if not title:
            return "Instagram Video"
        
        # Remove common patterns
        title = re.sub(r'Instagram video from\s*', '', title, flags=re.IGNORECASE)
        title = re.sub(r'#\w+', '', title)  # Remove hashtags
        title = re.sub(r'@\w+', '', title)  # Remove mentions
        title = re.sub(r'https?://\S+', '', title)  # Remove URLs
        title = re.sub(r'\s+', ' ', title)  # Remove extra spaces
        
        # Truncate if needed
        if len(title) > max_length:
            title = title[:max_length] + "..."
        
        return title.strip() or "Instagram Video"
    
    async def download_with_ytdlp(self, url: str, quality: str = "best") -> Dict[str, Any]:
        """Download video using yt-dlp (most reliable)"""
        
        quality_map = {
            "best": "best[ext=mp4]/best",
            "high": "best[height<=1080][ext=mp4]",
            "medium": "best[height<=720][ext=mp4]",
            "low": "best[height<=480][ext=mp4]",
        }
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': quality_map.get(quality, quality_map['best']),
            'user_agent': self.user_agent,
            'ignoreerrors': True,
            'extract_flat': False,
            'no_check_certificate': True,
            'prefer_insecure': True,
        }
        
        try:
            # Run yt-dlp in a thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            
            def extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(None, extract_info)
            
            if not info:
                return {'success': False, 'error': 'No video information extracted'}
            
            # Extract video URL
            video_url = info.get('url')
            if not video_url and 'formats' in info:
                # Find best quality video
                video_formats = [f for f in info['formats'] if f.get('vcodec') != 'none']
                if video_formats:
                    best_format = max(video_formats, key=lambda x: x.get('height', 0))
                    video_url = best_format.get('url')
            
            if not video_url:
                return {'success': False, 'error': 'No video URL found'}
            
            # Get thumbnail
            thumbnail = info.get('thumbnail', '')
            if not thumbnail and 'thumbnails' in info and info['thumbnails']:
                thumbnail = info['thumbnails'][-1].get('url', '')
            
            # Get duration
            duration = info.get('duration', 0)
            
            # Get title
            title = self.clean_title(info.get('title', ''))
            
            # Get uploader
            uploader = info.get('uploader', info.get('channel', 'Unknown'))
            
            # Get dimensions
            width = info.get('width', 0)
            height = info.get('height', 0)
            
            return {
                'success': True,
                'video_url': video_url,
                'thumbnail': thumbnail,
                'title': title,
                'username': uploader,
                'duration': duration,
                'width': width,
                'height': height,
                'method': 'yt-dlp'
            }
            
        except Exception as e:
            return {'success': False, 'error': str(e), 'method': 'yt-dlp'}
    
    async def download_with_fallback(self, url: str) -> Dict[str, Any]:
        """Fallback method using free API services"""
        
        services = [
            {
                'url': 'https://saveig.app/api/ajaxSearch',
                'data': {'q': url, 't': 'media', 'lang': 'en'},
                'video_key': 'video'
            },
            {
                'url': 'https://instasave.io/api/ajaxSearch',
                'data': {'q': url, 'lang': 'en'},
                'video_key': 'media'
            },
            {
                'url': 'https://snapinsta.app/api/ajaxSearch',
                'data': {'q': url, 't': 'media', 'lang': 'en'},
                'video_key': 'download_url'
            }
        ]
        
        async with aiohttp.ClientSession() as session:
            for service in services:
                try:
                    async with session.post(
                        service['url'],
                        data=service['data'],
                        headers={
                            'User-Agent': self.user_agent,
                            'X-Requested-With': 'XMLHttpRequest',
                            'Content-Type': 'application/x-www-form-urlencoded'
                        },
                        timeout=aiohttp.ClientTimeout(total=15)
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            video_url = None
                            for key in ['video', 'media', 'download_url', 'url']:
                                if key in data and data[key]:
                                    video_url = data[key]
                                    break
                            
                            if video_url:
                                return {
                                    'success': True,
                                    'video_url': video_url,
                                    'thumbnail': data.get('thumbnail', data.get('thumb', '')),
                                    'title': data.get('title', 'Instagram Video'),
                                    'username': data.get('username', 'Unknown'),
                                    'duration': 0,
                                    'method': 'fallback'
                                }
                except Exception:
                    continue
        
        return {'success': False, 'error': 'All fallback methods failed'}
    
    async def get_video(self, url: str, quality: str = "best") -> Dict[str, Any]:
        """Main method to get video information"""
        
        # Validate URL
        validation = self.validate_url(url)
        if not validation['valid']:
            return {'success': False, 'error': 'Invalid Instagram URL'}
        
        # Clean URL
        url = self.clean_url(url)
        
        # Try primary method first
        result = await self.download_with_ytdlp(url, quality)
        
        # If primary fails, try fallback
        if not result['success']:
            result = await self.download_with_fallback(url)
        
        # Add content type to result
        if result.get('success'):
            result['type'] = validation['type']
        
        return result