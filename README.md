# 체스 로봇 프로젝트
**또봇 2대를 이용해 실제 체스판에서 자동으로 수를 두는 통합 체스 시스템 프로젝트**

## 시작하기 (Get Starting)
### **1.환경 설정 (Prerequisites)**
1. Software
    * Language : Python
    * server : fastapi
1. Hardware
    * Actuator : dobot
    * camera
### **2.설치**
```bash
#저장소 복제
git clone https://github.com/seonghoe5697/chess_robot.git
cd chess_robot

# 가상환경 생성
python3 -m venv venv
source venv/bin/activate
pip install \ -r ~/Documents/chess_robot/raspi_node/requirements.txt
```
    
## Demo 
![]()


## 개요 및 목표 (Overview & Goal)
본 프로젝트는 체스 엔진, 비전 시스템, 로봇 제어를 통합하여  또봇 2대가 교대로 체스를 두는 **자동 대국**과 **사람 vs 로봇 대국**,**실시간 게임 상태 관리** 구현을 목표로 한다.

- 체스 엔진: Stockfish 기반 수 계산
- 비전 시스템: 카메라 기반 보드 상태 인식
- 로봇 제어: 또봇 2대를 이용한 말 이동
- 운영 UI: 게임 상태 및 로그 관리

