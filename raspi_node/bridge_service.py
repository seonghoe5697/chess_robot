# 이 파일은 로봇의 현재 상태를 json 파일로 저장하고 읽어오는 역할을 합니다.

import json
import os

STATE_FILE = "data/state/bridge_state.json"

def get_state():
    if not os.path.exists(STATE_FILE):
        return {"status": "idle", "last_command": None}
    with open(STATE_FILE, 'r') as f:
        return json.load(f)

def update_state(status, command=None):
    state = get_state()
    state["status"] = status
    if command:
        state["last_command"] = command
    
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)