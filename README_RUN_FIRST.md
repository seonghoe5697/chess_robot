# Tobot Chess 분리 실행 패키지

폴더를 3개로 분리했습니다.

1. `software_team/`  
   체스 GUI, CNN 기물 인식, FEN 생성, Stockfish 분석, GameSession/FSM, JSON 인터페이스

2. `hardware_team/`  
   듀얼 도봇 제어, 카메라 비전, 캘리브레이션, Stockfish 승인 실행 GUI

3. `raspi_team/`  
   Raspberry Pi 카메라 스트리밍, 캡처 API, 명령 브리지, 상태 파일 관리

## 권장 연결 방향

중복되는 Stockfish/카메라/상태관리는 모두 동시에 쓰지 말고 역할을 나눕니다.

```text
software_team: 체스 판단 / FEN / Stockfish / MoveCommand 생성
        ↓ HTTP JSON
raspi_team: /command 수신, /state 상태 제공, /capture 카메라 제공
        ↓ 필요 시
hardware_team: DualDobotController로 실제 로봇 실행
```

## 발표/시연용 최소 실행 순서

1. Raspberry Pi에서 `raspi_team/server.py` 실행
2. PC에서 `software_team/app.py` 또는 `ai_human_chess.py` 실행
3. PC 또는 로봇 제어 PC에서 `hardware_team/chess_robot_gui.py` 실행

## 주의

- 세 팀 코드에 같은 이름의 파일이 많아 폴더를 분리했습니다.
- 모델 파일은 용량이 커서 각 폴더에 필요한 것만 넣었습니다.
- 실제 완전 통합은 다음 단계에서 `MoveCommand JSON → HTTP /command → DualDobotController.execute_move()` 어댑터를 추가하면 됩니다.
