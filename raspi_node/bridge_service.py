import json
import os
from datetime import datetime

STATE_FILE = "data/state/bridge_state.json"
LOG_FILE = "data/state/command_log.txt"

# 폴더 자동 생성
os.makedirs("data/state", exist_ok=True)

async def update_state(status: str, params: dict = None):
    state_data = {
        "status": status,
        "last_update": datetime.now().isoformat(),
        "params": params or {}
    }
    # 파일 쓰기
    with open(STATE_FILE, 'w') as f:
        json.dump(state_data, f, indent=4)
    
    # 로그 기록
    with open(LOG_FILE, 'a') as f:
        f.write(f"[{datetime.now()}] Status: {status} | Data: {params}\n")

async def get_state():
    if not os.path.exists(STATE_FILE):
        return {"status": "idle", "msg": "No state file found"}
    
    try:
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        return {"status": "error", "msg": str(e)}