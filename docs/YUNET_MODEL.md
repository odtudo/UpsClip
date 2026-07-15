# YuNet face detector model

Smart Vertical Layout uses OpenCV YuNet (`cv2.FaceDetectorYN`) for local CPU face-box detection only.
It performs no face recognition, identity matching, embeddings, or external API calls.

- Source: OpenCV Zoo, `models/face_detection_yunet/face_detection_yunet_2023mar.onnx`
- Upstream URL: `https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet`
- License: MIT, as declared in that OpenCV Zoo model directory
- SHA-256: `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`
- Size: 232589 bytes

Docker downloads and verifies the model during image build, storing it at
`/opt/models/face_detection/face_detection_yunet_2023mar.onnx`. Native setup uses:

```bash
./scripts/download_face_model.sh
```

The script writes to `data/models/face_detection/` by default, validates the same checksum, and does
not redownload a valid model. The API exposes only availability and checksum validity in
`GET /setup/status`; it does not expose the complete filesystem path.
