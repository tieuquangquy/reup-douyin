
from collections import deque
from typing import Any, Dict
from apps.worker.src.handlers.video_analysis_handler import extract_video_metadata
from packages.shared.src.video_metadata import VideoMetadata


class MockQueue:
    _instance = None
    _queue: deque[Dict[str, Any]]
    _results: Dict[str, VideoMetadata]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(MockQueue, cls).__new__(cls)
            cls._instance._queue = deque()
            cls._instance._results = {}
        return cls._instance

    def enqueue(self, task_type: str, payload: Dict[str, Any]) -> str:
        # For simplicity, task_id is video_id
        task_id = payload.get("video_id")
        if not task_id:
            raise ValueError("Payload must contain 'video_id'")
        self._queue.append({"task_type": task_type, "payload": payload, "task_id": task_id})
        print(f"Enqueued task {task_id} of type {task_type}")
        return task_id

    def process_next_task(self):
        if self._queue:
            task = self._queue.popleft()
            task_id = task["task_id"]
            task_type = task["task_type"]
            payload = task["payload"]
            print(f"Processing task {task_id} of type {task_type}")

            if task_type == "video_analysis":
                video_id = payload["video_id"]
                metadata = extract_video_metadata(video_id)
                self._results[video_id] = metadata
                print(f"Completed processing for video_id {video_id}")
                return metadata
            else:
                print(f"Unknown task type: {task_type}")
        return None

    def get_task_result(self, task_id: str) -> Optional[VideoMetadata]:
        return self._results.get(task_id)

    def has_pending_tasks(self) -> bool:
        return bool(self._queue)


mock_queue = MockQueue()
