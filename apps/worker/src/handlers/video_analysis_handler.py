import re
from packages.shared.src.video_metadata import VideoMetadata


def extract_video_metadata(video_id: str) -> VideoMetadata:
    # Simulate video content for extraction
    mock_video_content = {
        "video_123": "This is a sample caption with #awesome and #python. Also mentioning @user1 and @user2. #coding",
        "video_456": "Another video caption about #AI and machine learning. Shoutout to @developer."
    }

    caption = mock_video_content.get(video_id, "")
    hashtags = re.findall(r"#(\\w+)", caption)
    mentions = re.findall(r"@(\\w+)", caption)

    return VideoMetadata(
        video_id=video_id,
        captions=caption,
        hashtags=hashtags,
        mentions=mentions,
    )
