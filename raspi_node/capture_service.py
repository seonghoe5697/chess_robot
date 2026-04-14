import cv2
import os
import time
from datetime import datetime

class CameraService:
    def __init__(self):
        self.save_dir = "data/captures"
        os.makedirs(self.save_dir, exist_ok=True)
        
        # 카메라 초기화 (0번이 안되면 1번 시도)
        self.cap = cv2.VideoCapture(0)
        
        # 해상도 설정 (체스판 인식을 위해 720p 권장)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        
        if not self.cap.isOpened():
            print("경고: 카메라를 열 수 없습니다. 인덱스를 확인하세요.")

    def get_frames(self):
        while True:
            if not self.cap.isOpened():
                time.sleep(1) # 재연결 대기
                continue

            success, frame = self.cap.read()
            if not success:
                continue
            
            # 스트리밍용 인코딩 (화질 70%로 CPU 부하 감소)
            ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if not ret:
                continue

            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
            
            # 라즈베리파이 CPU 과부하 방지 (약 20~25 FPS)
            time.sleep(0.04)

    async def capture_board(self):
        if not self.cap.isOpened():
            return None
            
        success, frame = self.cap.read()
        if success:
            # Day 5 파일명 규칙 준수
            filename = f"cap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            save_path = os.path.join(self.save_dir, filename)
            cv2.imwrite(save_path, frame)
            return save_path
        return None

    def release_camera(self):
        if self.cap.isOpened():
            self.cap.release()

camera_instance = CameraService()

def get_frames():
    return camera_instance.get_frames()

async def capture_board():
    return await camera_instance.capture_board()

def release_camera():
    camera_instance.release_camera()