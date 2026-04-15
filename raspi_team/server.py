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
async def monitor_page():
    return """
    <html>
        <head>
            <title>Chess Robot Real-time Monitor</title>
            <style>
                body { font-family: sans-serif; background: #f0f0f0; padding: 20px; }
                .container { display: flex; gap: 20px; }
                .video-section { flex: 1; background: white; padding: 15px; border-radius: 8px; }
                .history-section { width: 400px; background: white; padding: 15px; border-radius: 8px; }
                table { width: 100%; border-collapse: collapse; margin-top: 10px; }
                th, td { border-bottom: 1px solid #ddd; padding: 8px; text-align: left; font-size: 14px; }
                th { background: #eee; }
                .status-running { color: orange; font-weight: bold; }
                .status-done { color: green; font-weight: bold; }
                .status-error { color: red; font-weight: bold; }
            </style>
        </head>
        <body>
            <h1> Chess Robot Live Dashboard</h1>
            <div class="container">
                <div class="video-section">
                    <h3>Live Vision</h3>
                    <img src="/video_feed" style="width:100%; border-radius:4px;">
                </div>
                <div class="history-section">
                    <h3>Recent History (Last 5)</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Status</th>
                                <th>Action</th>
                            </tr>
                        </thead>
                        <tbody id="history_table">
                            </tbody>
                    </table>
                </div>
            </div>

            <script>
                async function updateDashboard() {
                    try {
                        const res = await fetch('/state');
                        const data = await res.json();
                        const history = data.logic.history || [];
                        
                        const tableBody = document.getElementById('history_table');
                        tableBody.innerHTML = history.map(item => `
                            <tr>
                                <td>${item.time}</td>
                                <td class="status-${item.status}">${item.status.toUpperCase()}</td>
                                <td>${JSON.stringify(item.data.command || '-')}</td>
                            </tr>
                        `).join('');
                    } catch (e) { console.error("Update failed", e); }
                }

                // 1초마다 자동 업데이트
                setInterval(updateDashboard, 1000);
                updateDashboard();
            </script>
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