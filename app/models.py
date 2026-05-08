from pydantic import BaseModel, HttpUrl
from typing import Optional, List, Dict, Any

class DownloadRequest(BaseModel):
    """Request model for video download"""
    url: str
    quality: Optional[str] = "best"  # best, high, medium, low

class VideoResponse(BaseModel):
    """Response model for successful download"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    message: Optional[str] = None

class VideoInfo(BaseModel):
    """Video information model"""
    video_url: str
    thumbnail: str
    title: str
    username: str
    duration: int
    width: Optional[int] = 0
    height: Optional[int] = 0