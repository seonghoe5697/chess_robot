# Hardware Team 실행법

## 설치
```bash
cd hardware_team
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
sudo apt install stockfish
```

## 실행 전 확인
- `config.py`에서 도봇 포트(`/dev/ttyUSB0`, `/dev/ttyUSB1`) 확인
- 카메라 인덱스 확인: `ls /dev/video*`
- Stockfish 경로 확인: 기본 `/usr/games/stockfish`

## 실행
```bash
python chess_robot_gui.py
```

## 파킹 좌표 측정
```bash
python AxisTest.py
```
