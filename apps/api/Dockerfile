FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates curl fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY apps/api/requirements.txt /app/apps/api/requirements.txt
RUN pip install -r /app/apps/api/requirements.txt
ARG YUNET_MODEL_URL=https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
ARG YUNET_MODEL_SHA256=8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4
RUN mkdir -p /opt/models/face_detection \
    && curl -L --fail --silent --show-error "$YUNET_MODEL_URL" -o /opt/models/face_detection/face_detection_yunet_2023mar.onnx \
    && echo "$YUNET_MODEL_SHA256  /opt/models/face_detection/face_detection_yunet_2023mar.onnx" | sha256sum --check --status
COPY apps /app/apps
COPY scripts /app/scripts
RUN mkdir -p /data/downloads /data/work /data/rendered /data/subtitles /data/thumbnails \
    /data/credentials /data/logs /data/models /data/profiles /data/smoke_tests /data/analysis

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
