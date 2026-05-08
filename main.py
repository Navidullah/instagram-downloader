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

# ============ DOWNLOADER ============
class InstagramDownloader:
    def __init__(self):
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        
    def validate_url(self, url: str) -> Dict[str, Any]:
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
    
    def clean_title(self, title: str, max_length: int = 60) -> str:
        if not title:
            return "Instagram Video"
        
        title = re.sub(r'Instagram video from\s*', '', title, flags=re.IGNORECASE)
        title = re.sub(r'#\w+', '', title)
        title = re.sub(r'@\w+', '', title)
        title = re.sub(r'https?://\S+', '', title)
        title = re.sub(r'\s+', ' ', title)
        
        if len(title) > max_length:
            title = title[:max_length] + "..."
        
        return title.strip() or "Instagram Video"
    
    async def download_video(self, url: str, quality: str = "best") -> Dict[str, Any]:
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
        }
        
        try:
            loop = asyncio.get_event_loop()
            
            def extract_info():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(None, extract_info)
            
            if not info:
                return {'success': False, 'error': 'No video information extracted'}
            
            video_url = info.get('url')
            if not video_url and 'formats' in info:
                video_formats = [f for f in info['formats'] if f.get('vcodec') != 'none']
                if video_formats:
                    best_format = max(video_formats, key=lambda x: x.get('height', 0))
                    video_url = best_format.get('url')
            
            if not video_url:
                return {'success': False, 'error': 'No video URL found'}
            
            return {
                'success': True,
                'video_url': video_url,
                'thumbnail': info.get('thumbnail', ''),
                'title': self.clean_title(info.get('title', '')),
                'username': info.get('uploader', 'Unknown'),
                'duration': info.get('duration', 0),
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    async def get_video(self, url: str, quality: str = "best") -> Dict[str, Any]:
        validation = self.validate_url(url)
        if not validation['valid']:
            return {'success': False, 'error': 'Invalid Instagram URL'}
        
        url = self.clean_url(url)
        result = await self.download_video(url, quality)
        
        if result.get('success'):
            result['type'] = validation['type']
        
        return result

# ============ FASTAPI APP ============
app = FastAPI(
    title="Instagram Video Downloader API",
    description="Download Instagram reels, posts, and videos",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

downloader = InstagramDownloader()

@app.get("/")
async def root():
    return {
        "name": "Instagram Video Downloader API",
        "version": "2.0.0",
        "status": "active",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "POST": "/api/download",
            "GET": "/api/health",
            "GET": "/docs"
        }
    }

@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0"
    }

@app.post("/api/download")
async def download_video(request: DownloadRequest):
    try:
        if not request.url or not request.url.strip():
            raise HTTPException(status_code=400, detail="URL is required")
        
        result = await downloader.get_video(request.url, request.quality)
        
        if not result.get('success'):
            raise HTTPException(
                status_code=500,
                detail=result.get('error', 'Failed to download video')
            )
        
        return {
            "success": True,
            "data": {
                "videoUrl": result['video_url'],
                "thumbnail": result.get('thumbnail', ''),
                "title": result.get('title', 'Instagram Video'),
                "username": result.get('username', 'Unknown'),
                "duration": result.get('duration', 0),
                "type": result.get('type', 'unknown')
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3001))
    uvicorn.run(app, host="0.0.0.0", port=port)