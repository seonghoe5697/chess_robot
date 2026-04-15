# Raspberry Pi Team 실행법

## 설치
```bash
cd raspi_team
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 실행
```bash
python server.py
```

## 접속
- 모니터: `http://<라즈베리파이IP>:8000/`
- 영상: `http://<라즈베리파이IP>:8000/video_feed`
- 캡처: `POST http://<라즈베리파이IP>:8000/capture`
- 명령: `POST http://<라즈베리파이IP>:8000/command`
- 상태: `GET http://<라즈베리파이IP>:8000/state`
