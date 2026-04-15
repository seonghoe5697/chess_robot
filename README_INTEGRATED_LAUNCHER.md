# Tobot Chess 통합 런처 실행법

이 패키지는 3개 결과물을 폴더별로 유지하면서, `main_launcher.py` 하나로 실행/중지할 수 있게 만든 버전입니다.

## 폴더 구조

```text
main_launcher.py
software_team/   # CNN/FEN/Stockfish/GameSession/Streamlit/AI GUI
hardware_team/   # 도봇 2대 제어 GUI/카메라 비전/캘리브레이션
raspi_team/      # FastAPI 카메라 서버/명령 브릿지/상태 파일
```

## 실행

### Ubuntu/Linux

```bash
cd tobot_chess_integrated_launcher
python3 main_launcher.py
```

또는

```bash
./run_launcher.sh
```

### Windows

```bat
cd tobot_chess_integrated_launcher
python main_launcher.py
```

또는 `run_launcher.bat` 더블클릭.

## 통합 런처 버튼

- **SW 분석기(Streamlit)**: `software_team/app.py` 실행
- **SW 사람 vs AI**: `software_team/ai_human_chess.py` 실행
- **SW AI vs AI**: `software_team/ai_chess.py` 실행
- **HW 도봇 통합 GUI**: `hardware_team/chess_robot_gui.py` 실행
- **Pi 브릿지 서버**: `raspi_team/server.py` 실행

`전체 실행` 버튼은 발표용 기본 조합으로 `Pi 브릿지 서버 → SW 분석기 → HW 도봇 GUI` 순서로 실행합니다.

## 주의

Streamlit, Tkinter, FastAPI는 이벤트 루프가 서로 다릅니다. 그래서 한 프로세스에 억지로 합치지 않고, 통합 런처가 각 프로그램을 subprocess로 실행합니다. 이 방식이 발표 시연에서 가장 안전합니다.

## Pi 서버 확인

Pi 서버 실행 후 브라우저에서 아래 주소를 열면 됩니다.

```text
http://127.0.0.1:8000
```

상태 API:

```text
http://127.0.0.1:8000/state
```

## 실행파일(.exe)로 만들기

Windows에서 PyInstaller를 사용할 수 있습니다.

```bash
pip install pyinstaller
pyinstaller --onefile --windowed main_launcher.py
```

단, `.exe`는 런처만 묶는 것이고 `software_team`, `hardware_team`, `raspi_team` 폴더는 같은 위치에 함께 있어야 합니다.
