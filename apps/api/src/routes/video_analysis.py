
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from packages.shared.src.video_metadata import VideoMetadata
from apps.worker.src.handlers.video_analysis_handler import extract_video_metadata
from apps.worker.src.queue.mock_queue import mock_queue


router = APIRouter()

class VideoAnalysisRequest(BaseModel):
    video_id: str

class VideoAnalysisResponse(BaseModel):
    message: str
    video_id: str

@router.post("/analyze-video", response_model=VideoAnalysisResponse, status_code=202)

async def analyze_video(request: VideoAnalysisRequest):
    try:
        # In a real scenario, this would submit a job to a queue
        # and return a job ID. For now, we'll directly call the worker function.
        task_id = mock_queue.enqueue("video_analysis", {"video_id": request.video_id})
        return {"message": f"Video analysis job enqueued with ID: {task_id}", "video_id": request.video_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Video analysis failed: {e}")


# Placeholder for retrieving metadata (Task 4)
@router.get("/video-metadata/{video_id}", response_model=VideoMetadata)
async def get_video_metadata(video_id: str):
    # In a real scenario, this would fetch from a database or storage
    # For now, we'll re-run the extraction or simulate a retrieval
    metadata = extract_video_metadata(video_id)  # Simulating retrieval for now
    if not metadata.captions and not metadata.hashtags and not metadata.mentions:
        raise HTTPException(status_code=404, detail="Video metadata not found or not yet processed")
    return metadata
