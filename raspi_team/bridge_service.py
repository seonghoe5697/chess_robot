import json
import os
from datetime import datetime

STATE_FILE = "data/state/bridge_state.json"
MAX_HISTORY = 5

async def update_state(status: str, params: dict = None):
    # 1. 기존 데이터 로드 (없으면 빈 리스트)
    history = []
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                history = data.get("history", [])
        except:
            history = []

    # 2. 새 상태 생성
    new_entry = {
        "status": status,
        "time": datetime.now().strftime("%H:%M:%S"),
        "data": params or {}
    }

    # 3. 리스트 맨 앞에 추가하고 최대 개수(5개) 유지
    history.insert(0, new_entry)
    history = history[:MAX_HISTORY]

    # 4. 파일 저장
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, 'w') as f:
        json.dump({"history": history}, f, indent=4)


async def get_state():
    if not os.path.exists(STATE_FILE):
        return {
            "camera": {"status": "unknown"},
            "logic": {"history": []}
        }
    try:
        with open(STATE_FILE, 'r') as f:
            data = json.load(f)
        return {
            "camera": {"status": "ok"},
            "logic": data
        }
    except Exception as e:
        return {
            "camera": {"status": "error"},
            "logic": {"history": [], "error": str(e)}
        }