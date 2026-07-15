#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESTINATION="${FACE_DETECTOR_MODEL_PATH:-$ROOT_DIR/data/models/face_detection/face_detection_yunet_2023mar.onnx}"
URL="https://github.com/opencv/opencv_zoo/raw/refs/heads/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
SHA256="8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"

mkdir -p "$(dirname "$DESTINATION")"
if [[ -f "$DESTINATION" ]] && echo "$SHA256  $DESTINATION" | sha256sum --check --status; then
  echo "YuNet model already present and checksum-valid."
  exit 0
fi
if ! command -v curl >/dev/null; then
  echo "curl is required to download the YuNet model." >&2
  exit 1
fi
TEMPORARY="${DESTINATION}.tmp"
curl -L --fail --silent --show-error "$URL" -o "$TEMPORARY"
echo "$SHA256  $TEMPORARY" | sha256sum --check --status || {
  rm -f "$TEMPORARY"
  echo "YuNet model checksum validation failed." >&2
  exit 1
}
mv "$TEMPORARY" "$DESTINATION"
chmod 0644 "$DESTINATION"
echo "Installed YuNet model at $DESTINATION"
