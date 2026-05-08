from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import re
import yt_dlp
import aiohttp
import asyncio
import os
from datetime import datetime
import uvicorn
from urllib.parse import urlparse, parse_qs

# ============ MODELS ============
class DownloadRequest(BaseModel):
    url: str
    quality: Optional[str] = "best"

# ============ DOWNLOADER CLASS ============
class InstagramDownloader:
    def __init__(self):
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
    def validate_url(self, url: str) -> Dict[str, Any]:
        """Validate Instagram URL and determine content type"""
        patterns = {
            'reel': r'instagram\.com/reel/',
            'post': r'instagram\.com/p/',
            'tv': r'instagram\.com/tv/',
        }
        
        for content_type, pattern in patterns.items():
            if re.search(pattern, url):
                return {'valid': True, 'type': content_type}
        
        if re.search(r'instagram\.com/', url):
            return {'valid': True, 'type': 'unknown'}
        
        return {'valid': False, 'type': None}
    
    def clean_url(self, url: str) -> str:
        """Remove tracking parameters from URL"""
        parsed = urlparse(url)
        clean_params = {}
        for k, v in parse_qs(parsed.query).items():
            if not k.startswith('utm_') and k not in ['igsh', 'ig_mid', 'from', 'ref']:
                clean_params[k] = v[0]
        
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
    
    def clean_title(self, title: str, max_length: int = 20) -> str:
        """Clean and shorten video title to just one meaningful word"""
        if not title:
            return "video"
        
        # Remove common Instagram patterns
        title = re.sub(r'Instagram video from\s*', '', title, flags=re.IGNORECASE)
        title = re.sub(r'#\w+', '', title)  # Remove hashtags
        title = re.sub(r'@\w+', '', title)  # Remove mentions
        title = re.sub(r'https?://\S+', '', title)  # Remove URLs
        title = re.sub(r'[^\w\s]', '', title)  # Remove special characters
        title = re.sub(r'\s+', ' ', title)  # Remove extra spaces
        
        # Split into words and take first meaningful word
        words = title.strip().split()
        
        # Common stop words to filter out
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 
                      'for', 'of', 'with', 'by', 'this', 'that', 'these', 'those', 
                      'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 
                      'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'so', 
                      'if', 'then', 'else', 'when', 'where', 'which', 'while', 
                      'who', 'whom', 'no', 'nor', 'not', 'only', 'own', 'same', 
                      'than', 'then', 'there', 'they', 'through', 'until', 'up', 
                      'via', 'with', 'without', 'after', 'before', 'between', 
                      'into', 'onto', 'upon', 'within'}
        
        # Find first meaningful word
        for word in words:
            word_lower = word.lower()
            if len(word) > 2 and word_lower not in stop_words:
                # Return the word, limited to max_length
                return word[:max_length]
        
        # Fallback to first word or default
        return words[0][:max_length] if words else "video"
    
    async def download_video(self, url: str, quality: str = "best") -> Dict[str, Any]:
        """Download video using yt-dlp"""
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
            'no_check_certificate': True,
            # Prevent writing metadata to file
            'writesubtitles': False,
            'writeautomaticsub': False,
            'writeinfojson': False,
            'writethumbnail': False,
        }
        
        try:
            loop = asyncio.get_event_loop()
            
            def extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(None, extract_info)
            
            if not info:
                return {'success': False, 'error': 'No video information extracted'}
            
            # Get video URL
            video_url = info.get('url')
            if not video_url and 'formats' in info:
                video_formats = [f for f in info['formats'] if f.get('vcodec') != 'none']
                if video_formats:
                    best_format = max(video_formats, key=lambda x: x.get('height', 0))
                    video_url = best_format.get('url')
            
            if not video_url:
                return {'success': False, 'error': 'No video URL found'}
            
            # Get clean, short title (just one meaningful word)
            original_title = info.get('title', '')
            clean_short_title = self.clean_title(original_title)
            
            # Also try to get a simple filename from username if available
            uploader = info.get('uploader', '')
            if uploader:
                clean_uploader = re.sub(r'[^\w]', '', uploader)[:15]
                final_title = clean_uploader or clean_short_title
            else:
                final_title = clean_short_title or "video"
            
            return {
                'success': True,
                'video_url': video_url,
                'thumbnail': info.get('thumbnail', ''),
                'title': final_title,  # Short title for download
                'full_title': original_title,  # Keep original for display
                'username': info.get('uploader', 'Unknown'),
                'duration': info.get('duration', 0),
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def fallback_download(self, url: str) -> Dict[str, Any]:
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
                                    'title': 'video',
                                    'username': data.get('username', 'Unknown'),
                                    'duration': 0,
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
        result = await self.download_video(url, quality)
        
        # If primary fails, try fallback
        if not result['success']:
            result = await self.fallback_download(url)
        
        # Add content type to result
        if result.get('success'):
            result['type'] = validation['type']
        
        return result

# ============ FASTAPI APP ============
app = FastAPI(
    title="Instagram Video Downloader API",
    description="Download Instagram reels, posts, and videos",
    version="2.0.0"
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://www.shopyor.com",
        "https://shopyor.com",
        "*"  # Allow all for testing (remove in production)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize downloader
downloader = InstagramDownloader()

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Instagram Video Downloader API",
        "version": "2.0.0",
        "status": "active",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "POST": "/api/download - Download Instagram video",
            "GET": "/api/health - Health check",
            "GET": "/api/info - Get video info",
            "GET": "/docs - Interactive documentation"
        }
    }

@app.get("/api/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0"
    }

@app.post("/api/download")
async def download_video(request: DownloadRequest):
    """
    Download Instagram video from provided URL
    
    Supports:
    - Reels
    - Posts
    - IGTV videos
    """
    try:
        # Validate input
        if not request.url or not request.url.strip():
            raise HTTPException(status_code=400, detail="URL is required")
        
        # Get video information
        result = await downloader.get_video(request.url, request.quality)
        
        if not result.get('success'):
            raise HTTPException(
                status_code=500,
                detail=result.get('error', 'Failed to download video. Please check if the video is public.')
            )
        
        # Return successful response
        return {
            "success": True,
            "data": {
                "videoUrl": result['video_url'],
                "thumbnail": result.get('thumbnail', ''),
                "title": result.get('title', 'video'),
                "fullTitle": result.get('full_title', ''),
                "username": result.get('username', 'Unknown'),
                "duration": result.get('duration', 0),
                "type": result.get('type', 'unknown')
            },
            "message": "Video downloaded successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

@app.get("/api/info")
async def get_video_info(url: str):
    """
    Get video information without downloading
    
    Returns metadata about the video
    """
    try:
        if not url or not url.strip():
            raise HTTPException(status_code=400, detail="URL is required")
        
        # Get video information
        result = await downloader.get_video(url, "best")
        
        if not result.get('success'):
            raise HTTPException(
                status_code=500,
                detail=result.get('error', 'Failed to get video information')
            )
        
        return {
            "success": True,
            "info": {
                "title": result.get('title', 'video'),
                "fullTitle": result.get('full_title', ''),
                "username": result.get('username', 'Unknown'),
                "duration": result.get('duration', 0),
                "type": result.get('type', 'unknown'),
                "thumbnail": result.get('thumbnail', '')
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3001))
    uvicorn.run(app, host="0.0.0.0", port=port)