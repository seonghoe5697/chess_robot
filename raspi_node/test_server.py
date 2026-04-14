from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, HTMLResponse
import uvicorn
from pydantic import BaseModel
from typing import Optional
import asyncio
import chess
 
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "../robot"))

# 프로젝트 모듈
import bridge_service as bridge
import capture_service as capture
from robot_dual_dobot_controller import DualDobotController, Robot
 
app = FastAPI(title="Chess Robot Pi Node")
 
# 컨트롤러 싱글톤 — GUI에서 주입하거나 서버 단독 실행 시 자체 생성
dobot: Optional[DualDobotController] = None
 
# GUI에서 직접 실행할 때 공유 board 상태
_board = chess.Board()
 
 
def set_controller(ctrl: DualDobotController) -> None:
    """GUI에서 이미 초기화된 컨트롤러를 주입할 때 사용"""
    global dobot
    dobot = ctrl
 
 
def get_controller() -> DualDobotController:
    """컨트롤러가 없으면 예외 발생"""
    if dobot is None:
        raise RuntimeError("Robot controller not initialized")
    return dobot
 
 
class RobotCommand(BaseModel):
    command: str
    params: Optional[dict] = None
 
 
# ─────────────────────────────────────────────────────────────
# 라이프사이클
# ─────────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    """
    서버 단독 실행(python server.py) 시에만 dobot을 자체 초기화.
    GUI에서 임베드 실행될 때는 set_controller()로 주입되므로 건너뜀.
    """
    global dobot
    if dobot is None:
        dobot = DualDobotController()
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, dobot.init)
    await bridge.update_state("idle", {"msg": "System booting..."})
 
 
@app.on_event("shutdown")
def shutdown():
    capture.release_camera()
    if dobot is not None:
        dobot.quit()
 
 
# ─────────────────────────────────────────────────────────────
# 1. 모니터링 & 상태
# ─────────────────────────────────────────────────────────────
@app.get("/health")
async def health_check():
    """서버 생존 확인"""
    return {"status": "ok", "node": "raspberry_pi_chess"}
 
 
@app.get("/state")
async def get_full_state():
    """논리 상태 + 하드웨어 좌표 통합 반환"""
    logic_state = await bridge.get_state()
    try:
        hw_status = get_controller().get_status()
    except Exception:
        hw_status = {"error": "Could not fetch robot pose"}
    return {"logic": logic_state, "hardware": hw_status}
 
 
# ─────────────────────────────────────────────────────────────
# 2. 비전 & 대시보드
# ─────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def monitor_page():
    """현장 모니터링용 대시보드"""
    return """
    <html>
        <head>
            <title>Chess Robot Pi Monitor</title>
            <style>
                body { font-family: monospace; background: #1e1e1e; color: #e0e0e0; padding: 20px; }
                h1   { color: #4a9eff; }
                img  { border: 2px solid #333; border-radius: 6px; }
                pre  { background: #2a2a2a; padding: 12px; border-radius: 6px;
                       font-size: 13px; line-height: 1.5; overflow-x: auto; }
                .ok   { color: #7fff9a; }
                .err  { color: #ff7f7f; }
                .warn { color: #ffd080; }
            </style>
        </head>
        <body>
            <h1>♟ Chess Robot Pi Node</h1>
            <img src="/video_feed" width="640"><br><br>
            <pre id="state_view">Loading state...</pre>
            <script>
                setInterval(async () => {
                    try {
                        const res  = await fetch('/state');
                        const data = await res.json();
                        document.getElementById('state_view').innerText =
                            JSON.stringify(data, null, 2);
                    } catch (e) {
                        document.getElementById('state_view').innerText = 'Connection error';
                    }
                }, 1000);
            </script>
        </body>
    </html>
    """
 
 
@app.get("/video_feed")
async def video_feed():
    """카메라 MJPEG 스트림"""
    return StreamingResponse(
        capture.get_frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
 
 
# ─────────────────────────────────────────────────────────────
# 3. 제어 엔드포인트
# ─────────────────────────────────────────────────────────────
@app.post("/capture")
async def run_capture():
    """보드 이미지 캡처"""
    path = await capture.capture_board()
    if path:
        return {"result": "success", "path": path}
    raise HTTPException(status_code=500, detail="Capture failed")
 
 
@app.post("/command")
async def receive_command(cmd: RobotCommand, background_tasks: BackgroundTasks):
    """
    로봇 명령 수신 후 백그라운드 실행.
 
    지원 command:
      - "move"  : params={"uci": "e2e4"}  체스 수 실행
      - "home"  : 홈 이동
      - "stop"  : 비상 정지
      - "reset" : 보드 초기화
    """
    await bridge.update_state("running", cmd.dict())
    background_tasks.add_task(execute_logic, cmd)
    return {"result": "received", "status": "running"}
 
 
async def execute_logic(cmd: RobotCommand) -> None:
    """백그라운드에서 실행되는 실제 로봇 제어 로직"""
    global _board
    try:
        ctrl    = get_controller()
        command = cmd.command
        params  = cmd.params or {}
        loop    = asyncio.get_event_loop()
 
        if command == "move":
            uci = params.get("uci")
            if not uci:
                raise ValueError("uci 파라미터가 필요합니다 (예: 'e2e4')")
            move = chess.Move.from_uci(uci)
            if move not in _board.legal_moves:
                raise ValueError(f"비합법 수: {uci}")
            await loop.run_in_executor(
                None, ctrl.execute_move, _board, move
            )
            _board.push(move)
 
        elif command == "home":
            await loop.run_in_executor(None, ctrl.go_home)
 
        elif command == "stop":
            # emergency_stop은 동기 함수지만 빠르게 실행되므로 직접 호출
            ctrl.emergency_stop_and_recover()
 
        elif command == "reset":
            _board.reset()
 
        else:
            raise ValueError(f"알 수 없는 command: {command}")
 
        await bridge.update_state("done", {"command": command})
 
    except Exception as e:
        await bridge.update_state("error", {"error_msg": str(e)})
 
 
# ─────────────────────────────────────────────────────────────
# 단독 실행
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)