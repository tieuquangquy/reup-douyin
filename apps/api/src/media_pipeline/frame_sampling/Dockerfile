# =============================================================================
# Dockerfile — Phase 1 Frame Sampling (Google Cloud Run Jobs)
# Build (đúng lệnh bạn yêu cầu):
#   cd apps/api/src/media_pipeline/frame_sampling
#   docker build -t frame-extractor .
#
# Mục tiêu: Alpine + FFmpeg tối giản → image < 100MB, cold-start thấp.
# =============================================================================

# --- Stage 1: biên dịch FFmpeg tối giản (chỉ decode/fps → JPEG), không full codec pack ---
FROM python:3.10-alpine AS ffmpeg_builder

# Toolchain build; --no-cache = không giữ index apk.
RUN apk add --no-cache \
        build-base \
        coreutils \
        nasm \
        pkgconf \
        wget \
        xz

# Tải source FFmpeg (release ổn định) và cấu hình tối thiểu cho Phase 1 sampling.
# Cần: file protocol, demux mp4/mov, decode h264, filter fps, encode mjpeg, mux image2.
WORKDIR /tmp/ffmpeg-src
RUN wget -q https://ffmpeg.org/releases/ffmpeg-6.1.2.tar.xz \
    && tar -xJf ffmpeg-6.1.2.tar.xz \
    && cd ffmpeg-6.1.2 \
    && ./configure \
        --prefix=/usr/local \
        --disable-debug \
        --disable-doc \
        --disable-ffplay \
        --disable-ffprobe \
        --disable-network \
        --disable-everything \
        --enable-small \
        --enable-protocol=file \
        --enable-demuxer=mov,matroska,mpegts \
        --enable-muxer=image2 \
        --enable-decoder=h264,mpeg4,mjpeg,png \
        --enable-encoder=mjpeg \
        --enable-parser=h264,mpeg4video,mjpeg \
        --enable-filter=fps,scale,format \
        --enable-bsf=h264_mp4toannexb \
        --enable-swscale \
        --enable-avfilter \
    && make -j"$(getconf _NPROCESSORS_ONLN)" \
    && make install \
    && strip /usr/local/bin/ffmpeg

# --- Stage 2: runtime mỏng ---
FROM python:3.10-alpine

# Không ghi .pyc; log stdout ngay; PYTHONPATH cho import src.*
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    OUTPUT_DIR=/tmp/frames \
    SAMPLE_FPS=1 \
    FFMPEG_BINARY=/usr/local/bin/ffmpeg

# Thư mục làm việc mặc định.
WORKDIR /app

# Chỉ copy binary ffmpeg đã strip (không apk add ffmpeg full).
COPY --from=ffmpeg_builder /usr/local/bin/ffmpeg /usr/local/bin/ffmpeg

# Sao chép requirements (context = thư mục frame_sampling).
COPY requirements.txt /app/requirements.txt

# Cài Python packages; --no-cache-dir = không giữ cache pip.
RUN pip install --no-cache-dir -r /app/requirements.txt

# Giữ cấu trúc src/media_pipeline/frame_sampling trong /app.
RUN mkdir -p /app/src/media_pipeline/frame_sampling \
    && printf '%s\n' '"""Container package root."""' > /app/src/__init__.py \
    && printf '%s\n' '"""Media pipeline capabilities (Cloud Run ready)."""' > /app/src/media_pipeline/__init__.py
COPY . /app/src/media_pipeline/frame_sampling/

# Thư mục output ephemeral trên Cloud Run.
RUN mkdir -p /tmp/frames \
    && chmod +x /usr/local/bin/ffmpeg

# Worker job khi container khởi động.
CMD ["python", "-m", "src.media_pipeline.frame_sampling.cloud_run_entry"]
