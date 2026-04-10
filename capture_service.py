# 카메라 서버 역할을 하며, 사진을 찍어 data/captures/에 저장합니다.

import cv2
import os
from datetime import datetime

def capture_board():
    cap = cv2.VideoCapture(0) # 0번은 기본 카메라
    ret, frame = cap.read()
    
    if ret:
        filename = f"cap_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        save_path = os.path.join("data/captures", filename)
        cv2.imwrite(save_path, frame)
        cap.release()
        return save_path
    
    cap.release()
    return None