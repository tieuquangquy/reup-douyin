
from pydantic import BaseModel, Field
from typing import List, Optional


class VideoMetadata(BaseModel):
    video_id: str = Field(..., description="Unique identifier for the video")
    captions: Optional[str] = Field(None, description="Extracted caption from the video")
    hashtags: List[str] = Field(default_factory=list, description="List of hashtags found in the video caption or description")
    mentions: List[str] = Field(default_factory=list, description="List of user mentions found in the video caption or description")

