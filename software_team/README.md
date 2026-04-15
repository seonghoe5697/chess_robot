# CHESS_ROBOT_SW

> CNN 기물 인식 + Stockfish 체스 엔진 + 로봇 하드웨어 인터페이스를 통합한 체스 로봇 소프트웨어

![chess_robot_SW_architecture.svg](https://github.com/retriever503/chess_robot_sw/raw/main/chess_robot_SW_architecture.svg)

---

## 주요 기능

- **CNN 기물 인식**: 체스판 사진 한 장에서 64칸의 기물을 자동 분류 (13클래스, 정확도 95%+)
- **Stockfish 연동**: 인식된 포지션에서 최선의 수를 실시간 추천
- **사람 vs AI 대국**: 난이도 조절(Elo 1350~2850), 힌트, 무르기, 프로모션 선택 지원
- **로봇 하드웨어 인터페이스**: JSON 기반 SW↔HW 통신 규격, FSM 세션 관리
- **멀티 GPU 학습**: Intel Arc(네이티브 XPU) / NVIDIA(CUDA+AMP) / CPU 자동 감지

---

## 설치 및 실행

### 1. 환경 설정

```bash
# 저장소 클론
git clone https://github.com/retriever503/chess_robot_sw.git
cd chess_robot_sw

# 의존성 설치
pip install -r requirements.txt
```

### 2. Stockfish 설치

[Stockfish 공식 사이트](https://stockfishchess.org/download/)에서 OS에 맞는 바이너리를 다운로드하세요.

```bash
# Linux/macOS: 패키지 매니저 사용 가능
sudo apt install stockfish   # Ubuntu/Debian
brew install stockfish        # macOS

# 또는 환경변수로 경로 지정
export STOCKFISH_PATH="/path/to/stockfish"
```

### 3. 실행

```bash
# 웹 앱 (체스판 사진 분석)
streamlit run app.py

# 사람 vs AI 대국
python ai_human_chess.py

# AI vs AI 자동 대국
python ai_chess.py

# CNN 모델 학습
python train.py --data /path/to/dataset/train

# PGN 기보 수집
python chess_dataset.py
```

---

## 프로젝트 구조

```
chess_robot_sw/
├── app.py               # Streamlit 웹 앱 (이미지 → CNN → FEN → Stockfish)
├── ai_human_chess.py     # 사람 vs AI 대국 GUI (tkinter)
├── ai_chess.py           # AI vs AI 자동 대국 GUI
├── train.py              # CNN 학습 스크립트 (WeightedSampler + AMP)
├── chess_dataset.py      # Stockfish 자체 대국 PGN 수집
├── chess_model_pure.pth  # 학습된 CNN 가중치
├── requirements.txt
├── images/               # 기물 이미지 (GUI 렌더링용)
└── core/                 # 공통 코어 패키지
    ├── engine.py         # Stockfish 엔진 로딩/관리
    ├── board.py          # 기물 상수, 좌표 변환 유틸리티
    ├── fen.py            # CNN 결과 → FEN 변환, 캐슬링 자동 추론
    ├── model.py          # ChessPieceCNN 정의 + 배치 추론
    ├── interface.py      # SW↔HW JSON 메시지 규격 (dataclass)
    └── session.py        # 대국 FSM (IDLE→THINKING→AWAITING_HW→HW_DONE)
```

---

## 실행 파일 5개

① **app.py** — Streamlit 웹 앱. 체스판 사진을 업로드하면 CNN이 각 칸의 기물을 인식하고, FEN 문자열을 생성한 뒤, Stockfish가 다음 최선의 수를 추천해주며 subprocess로 Stockfish와 직접 통신하는 방식을 써서 Streamlit의 asyncio 충돌을 피했습니다.

② **ai_chess.py** — tkinter GUI로 AI vs AI 자동 대국을 보여줍니다. Stockfish끼리 대결하면서 체스판을 실시간으로 그려주고, 무승부가 나면 자동으로 재시작합니다.

③ **ai_human_chess.py** — 사람 vs AI 대국 GUI입니다. 난이도 슬라이더(Elo 1350~2850), 힌트 보기, 무르기, 기권 기능이 있고, AI가 형세 -600 이하로 떨어지면 스스로 항복하는 로직도 들어있습니다. 흑/백 선택 후 보드를 뒤집어 그려줍니다. 프로모션 시 기물 선택 다이얼로그를 제공합니다.

④ **train.py** — CNN 기물 인식 모델 학습 스크립트입니다. WeightedRandomSampler로 빈칸(약 80%) 과다 문제를 해결하고, CosineAnnealingLR 스케줄러와 Early Stopping을 적용했습니다. 데이터 증강(회전, 원근 왜곡, 블러)으로 실제 환경 내성을 높였습니다. Intel Arc(네이티브 XPU), NVIDIA(CUDA+AMP), CPU 순으로 디바이스를 자동 감지합니다.

⑤ **chess_dataset.py** — Stockfish 자체 대국으로 PGN 기보를 수집하는 스크립트입니다. 무승부는 버리고 승패가 결정된 게임만 저장합니다. 무승부가 연속되면 최대 재시도 횟수를 두어 무한 루프를 방지합니다.

---

## core/ 패키지 6개 모듈

① **engine.py** — Stockfish 엔진 로딩을 중앙 관리합니다. 환경변수(`STOCKFISH_PATH`) → OS별(Windows/Mac/Linux) 경로를 자동 감지하고, `create_engine()`으로 Elo 설정까지 한 번에 처리합니다.

② **board.py** — 기물 상수(PIECE_SYMBOLS, PIECE_VALUES), CNN 레이블 매핑(LABEL_TO_PIECE), 화면 좌표↔체스 좌표 변환, 재료 우위 점수 계산 등 공통 유틸리티를 모아놓은 파일입니다.

③ **fen.py** — CNN 예측 결과(64개 레이블 배열)를 완전한 FEN 문자열로 변환합니다. 턴, 캐슬링(킹/룩 초기위치 기반 자동 추론), 앙파상까지 복원하며, FEN 유효성 검사도 담당합니다.

④ **model.py** — ChessPieceCNN 클래스를 정의합니다. Conv2d 3층 + FC 2층 구조로, 50x50 RGB 이미지를 입력받아 13클래스(백 6종 + 흑 6종 + 빈칸)를 분류합니다. 64칸 배치 추론으로 빠르게 처리합니다.

⑤ **interface.py** — 로봇 하드웨어와 소프트웨어 간 JSON 메시지 규격을 정의합니다. GameState(보드 상태), MoveCommand(로봇 이동 지시), RobotResult(실행 결과), SafetyEvent(비상정지) 4가지 메시지 타입을 dataclass로 구현했고, 캐슬링/앙파상/프로모션 등 수 종류를 자동 판별합니다.

⑥ **session.py** — 대국 전체를 관리하는 FSM(유한 상태 머신)입니다. IDLE → THINKING → AWAITING\_HW → HW\_DONE 순서로 턴을 진행하며, AI 자동 대국, 사람 vs 로봇, 승인 모드 3가지를 지원합니다. 비전 카메라 FEN 수신으로 보드 불일치도 감지할 수 있습니다.

---

## 기술 스택

| 분야 | 기술 |
|------|------|
| AI/ML | PyTorch, CNN, WeightedRandomSampler, CosineAnnealingLR |
| 체스 엔진 | Stockfish (UCI 프로토콜) |
| 웹 | Streamlit |
| GUI | tkinter, Pillow |
| 하드웨어 인터페이스 | JSON 메시지, dataclass, FSM |
| GPU 지원 | NVIDIA CUDA (AMP), Intel Arc (네이티브 XPU) |

---

## 프로젝트 요약

**체스 로봇 소프트웨어** — CNN 기물 인식, Stockfish 체스 엔진 분석, 로봇 하드웨어 인터페이스를 하나로 통합한 체스 로봇 소프트웨어입니다.

- 체스판 사진 업로드 → CNN이 64칸 기물 인식 → FEN 생성 → Stockfish가 최선의 수 추천
- 난이도 조절(Elo 1350~2850), 힌트, 무르기, 기권을 지원하는 사람 vs AI 대국 GUI
- FSM 기반 대국 세션 관리자로 로봇 하드웨어와 연동
- 멀티 GPU 학습 지원: Intel Arc (네이티브 XPU), NVIDIA (CUDA+AMP), CPU 자동 감지