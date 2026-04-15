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
        print(f"[CameraService] 라즈베리파이 스트림: {self.stream_url}")

    def get_frames(self):
        """라즈베리파이 /video_feed 스트림을 그대로 프록시."""
        while True:
            try:
                req = urllib.request.urlopen(self.stream_url, timeout=5)
                boundary = b"--frame"
                buf = b""
                while True:
                    chunk = req.read(4096)
                    if not chunk:
                        break
                    buf += chunk
                    # multipart 경계 분리
                    while boundary in buf:
                        _, buf = buf.split(boundary, 1)
                        if b"\r\n\r\n" in buf:
                            header, rest = buf.split(b"\r\n\r\n", 1)
                            # 다음 경계까지가 JPEG 데이터
                            if boundary in rest:
                                jpg_data, buf = rest.split(boundary, 1)
                                jpg_data = jpg_data.rstrip(b"\r\n")
                                yield (b"--frame\r\n"
                                       b"Content-Type: image/jpeg\r\n\r\n"
                                       + jpg_data + b"\r\n")
            except Exception as e:
                print(f"[CameraService] 스트림 끊김: {e} — 2초 후 재연결")
                # 연결 실패 시 빈 프레임 대신 잠깐 대기
                time.sleep(2)

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