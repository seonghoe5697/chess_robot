from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, HTMLResponse
import uvicorn
from pydantic import BaseModel
from typing import Optional
import bridge_service as bridge
import capture_service as capture
import asyncio

app = FastAPI(title="Chess Robot Pi Node")

class RobotCommand(BaseModel):
    command: str
    params: Optional[dict] = None

@app.get("/", response_class=HTMLResponse)
async def index():
    return """
    <html>
        <head><title>Tobot Monitor</title></head>
        <body>
            <h1>Tobot Chess Real-time Feed</h1>
            <img src="/video_feed" width="640">
            <h3>System Status</h3>
            <iframe src="/state" width="640" height="100" style="border:none;"></iframe>
        </body>
    </html>
    """

@app.get("/video_feed")
async def video_feed():
    # 실시간 스트리밍 응답
    return StreamingResponse(capture.get_frames(), 
                            media_type="multipart/x-mixed-replace; boundary=frame")

@app.get("/state")
async def check_state():
    return await bridge.get_state()

@app.post("/capture")
async def run_capture():
    path = await capture.capture_board()
    if path:
        return {"result": "success", "path": path}
    # 카메라 연결 실패 시 에러 반환
    raise HTTPException(status_code=503, detail="Camera not available")

@app.post("/command")
async def receive_command(cmd: RobotCommand, background_tasks: BackgroundTasks):
    await bridge.update_state("running", cmd.dict())
    background_tasks.add_task(execute_robot_logic, cmd)
    return {"result": "command_received", "status": "running"}

async def execute_robot_logic(cmd: RobotCommand):
    try:
        # 실제 로봇 제어 로직이 들어갈 자리 (Day 6-7 작업)
        await asyncio.sleep(2) 
        await bridge.update_state("done")
    except Exception as e:
        await bridge.update_state("error", {"error_msg": str(e)})

@app.on_event("shutdown")
def shutdown_event():
    capture.release_camera()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)