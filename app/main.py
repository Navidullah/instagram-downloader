from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os
from datetime import datetime
import uvicorn

from models import DownloadRequest, VideoResponse
from downloader import InstagramDownloader

# Initialize FastAPI app
app = FastAPI(
    title="Instagram Video Downloader API",
    description="Download Instagram reels, posts, and videos",
    version="2.0.0"
)

# CORS configuration - Allow all origins for now (configure for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to your domain in production
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
    - Stories
    - Highlights
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
                "title": result.get('title', 'Instagram Video'),
                "username": result.get('username', 'Unknown'),
                "duration": result.get('duration', 0),
                "width": result.get('width', 0),
                "height": result.get('height', 0),
                "type": result.get('type', 'unknown'),
                "method": result.get('method', 'unknown')
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
                "title": result.get('title', 'Instagram Video'),
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
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=False
    )