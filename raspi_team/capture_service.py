import cv2
import os
import time
import urllib.request
import numpy as np
from datetime import datetime

# ── 라즈베리파이 서버 주소 ──────────────────────────────────
PI_HOST = "http://192.168.0.133:8000"
# ────────────────────────────────────────────────────────────

class CameraService:
    def __init__(self):
        self.save_dir = "data/captures"
        os.makedirs(self.save_dir, exist_ok=True)
        self.stream_url = f"{PI_HOST}/video_feed"
        self.capture_url = f"{PI_HOST}/capture"
        self._cap = cv2.VideoCapture(0, cv2.CAP_V4L2)
        print(f"[CameraService] 라즈베리파이 스트림: {self.stream_url}")

    def get_frames(self):
        """카메라에서 직접 읽어서 스트리밍."""
        while True:
                ret, frame = self._cap.read()
                if not ret:
                    print("[CameraService] 카메라 읽기 실패")
                    time.sleep(0.1)
                    continue
                _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 50])
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n"
                       + jpeg.tobytes() + b"\r\n")

    async def capture_board(self):
        """라즈베리파이 /capture 엔드포인트 호출 → 이미지를 로컬에 저장."""
        try:
            import urllib.request, json as _json
            req = urllib.request.Request(
                f"{PI_HOST}/capture",
                method="POST",
                headers={"Content-Type": "application/json"},
                data=b"{}",
            )
            with urllib.request.urlopen(req, timeout=5) as r:
                data = _json.loads(r.read().decode())
            # 라즈베리파이가 저장한 경로를 그대로 반환 (HW팀은 Pi 경로 참조)
            return data.get("path")
        except Exception as e:
            print(f"[CameraService] capture 실패: {e}")
            return None

    def release_camera(self):
        # 네트워크 스트림이므로 별도 해제 불필요
        pass


camera_instance = CameraService()

def get_frames():
    return camera_instance.get_frames()

async def capture_board():
    return await camera_instance.capture_board()

def release_camera():
    camera_instance.release_camera()