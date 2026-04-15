# 체스 로봇 프로젝트
**또봇 2대를 활용한 자동 체스 대전 시스템**  
***(체스 엔진 + 비전 인식 + 로봇 제어 통합 프로젝트)***

## 목차
* [1.환경설정 및 설치](#1환경설정-및-설치)
* [2.프로젝트 개요](#2프로젝트-개요-overview)
* [3.목표](#3목표-goals)
* [4.시연 영상](#4시연-영상-demo)
* [5.주요 기능](#5주요-기능-core-features)
* [6.기술 스텍](#6기술-스텍-technical-stack)
* [7.팀원 및 역할](#7팀원-및-역할-tasks)
* [8.트러블슈팅](#8트러블슈팅-trouble-shooting)

## 1.환경설정 및 설치
```bash
#저장소 복제
git clone https://github.com/seonghoe5697/chess_robot.git
cd chess_robot

# 가상환경 생성
python3 -m venv venv
source venv/bin/activate
pip install \ -r ~/Documents/chess_robot/raspi_node/requirements.txt
```
## 2.프로젝트 개요 (Overview)
또봇 2대를 체스판 양측에 배치하여 중앙 제어 소프트웨어가 게임 상태를 판단하고<br/> 각 로봇에 이동 명령을 전달하여 실제 체스 대국을 수행하는 시스템
* 체스 엔진 기반 자동 수 계산
* 비전 기반 보드 상태 인식
* 로봇 제어를 통한 실제 말 이동

## 3.목표 (Goals)
* 자동 체스 대국 시스템 구현
* 로봇 기반 물리적 말 이동 구현
* 게임 상태 관리 및 UI 제공
* 실제 시연 가능한 프로토타입 완성

## 4.시연 영상 (Demo)
![]()

## 5.주요 기능 (Core Features)
* 체스 규칙 처리 및 상태 관리
* Stockfish 기반 수 계산
* 보드 상태 인식 (CNN)
* 로봇 이동 명령 생성 및 실행
* 게임 로그 및 오류 복구
* 자동 대국 / 사람 vs 로봇 모드

## 6.기술 스텍 (Technical Stack)
1. Software
    * Python 
    * OpenCV (비전 처리)
    * Stockfish (체스 엔진) 
    * Robot SDK (로봇 제어)

1. Hardware
    * Raspberry Pi (FastAPI)
    * Dobot

## 7.팀원 및 역할 (Tasks)
| 팀원 | 역할  |
|:---:|:---:|  
| 구형진 | PM / 시스템 통합 |  
| 김상윤 | 체스 로직 / 엔진 |  
| 김효성 | 보드 상태 / 테스트 |  
| 이승재 | 로봇 제어 |  
| 최성회 | 서버 UI / 문서화 |  

## 8.트러블슈팅 (Trouble Shooting)
* 비전 인식 정확도 문제
* 좌표 오차 및 로봇 정밀도
* 통신 지연 및 동기화 문제
* FEN 상태 완전 복원 문제