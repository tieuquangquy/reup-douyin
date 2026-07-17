export type HardSubEvent = {
  start_ms: number;
  end_ms: number;
  x: number;
  y: number;
  width: number;
  height: number;
  sample_count: number;
  avg_confidence: number;
  texts?: string[];
  unstable?: boolean;
};

export type OcrCreateResponse = {
  job_id: string;
  status: string;
  source_video_id: string;
};

export type OcrSummaryResponse = {
  source_video_id: string;
  pipeline_version: string | null;
  provider: string | null;
  text_object_count: number;
  frame_detection_count: number;
  hardsub_events: HardSubEvent[];
  warnings: string[];
  cleaned_video_asset_id: string | null;
  ocr_events_asset_id: string | null;
  visual_approved: boolean;
};
