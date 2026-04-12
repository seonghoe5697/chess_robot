# 이미지 5번에 있던 /frame, /capture, /command, /state 엔드포인트를 구현합니다.

from flask import Flask, request, jsonify
import bridge_service as bridge
import capture_service as capture

app = Flask(__name__)

@app.route('/state', methods=['GET'])
def check_state():
    return jsonify(bridge.get_state())

@app.route('/capture', methods=['POST'])
def run_capture():
    path = capture.capture_board()
    if path:
        return jsonify({"result": "success", "path": path})
    return jsonify({"result": "fail"}), 500

@app.route('/command', methods=['POST'])
def receive_command():
    data = request.json  # PC에서 보낸 UCI/JSON 명령
    bridge.update_state("running", data)
    
    # 여기서 실제 로봇 제어(pydobot) 로직이 호출되어야 함
    # 우선은 상태 업데이트만 수행
    print(f"Received Command: {data}")
    
    return jsonify({"result": "command_received"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000) # 외부(PC)에서 접속 가능하게 설정