# Software Team 실행법

## 설치
```bash
cd software_team
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 실행
```bash
# 웹 분석기: 이미지 → CNN → FEN → Stockfish
streamlit run app.py

# 사람 vs AI 대국
python ai_human_chess.py

# AI vs AI 자동 대국
python ai_chess.py

# CNN 학습
python train.py --data /path/to/dataset/train
```

Stockfish가 필요합니다.
```bash
sudo apt install stockfish
# 필요하면
export STOCKFISH_PATH=/usr/games/stockfish
```
