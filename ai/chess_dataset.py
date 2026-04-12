import chess
import chess.engine
import chess.pgn
import datetime
import os

def collect_ai_games(num_games=100, output_file="ai_games.pgn"):
    # 1. 엔진 경로 설정 (본인의 실제 파일명과 일치하는지 확인하세요)
    STOCKFISH_PATH = r"C:\Users\user\Desktop\tobot_chess\stockfish-windows-x86-64.exe"
    
    if not os.path.exists(STOCKFISH_PATH):
        print(f"오류: 엔진 파일을 찾을 수 없습니다. 경로를 확인하세요: {STOCKFISH_PATH}")
        return

    try:
        # 엔진 실행 및 초기 설정
        engine = chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH)
        
        # 최신 엔진은 Contempt 대신 UCI_Elo를 사용하여 실력을 조절합니다.
        # 무승부를 줄이기 위해 높은 Elo를 설정합니다.
        engine.configure({
            "UCI_LimitStrength": True, 
            "UCI_Elo": 2850
        })
        print("체스 엔진 로드 완료. 데이터 수집을 시작합니다...")
    except Exception as e:
        print(f"엔진 실행 중 오류 발생: {e}")
        return

    # 2. 파일 쓰기 모드 (기존 파일이 있으면 뒤에 이어붙입니다)
    with open(output_file, "a", encoding="utf-8") as pgn_file:
        current_count = 1
        
        while current_count <= num_games:
            board = chess.Board()
            game = chess.pgn.Game()
            
            # 상세 헤더 정보 설정
            now = datetime.datetime.now()
            game.headers["Event"] = f"AI Self-Play #{current_count}"
            game.headers["Site"] = "Busan, KOR"
            game.headers["Date"] = now.strftime("%Y.%m.%d")
            game.headers["Round"] = str(current_count)
            game.headers["White"] = "Stockfish_White"
            game.headers["Black"] = "Stockfish_Black"
            
            # 현재 기보 노드 위치 초기화
            node = game 
            
            # 3. 실제 대국 진행 루프
            while not board.is_game_over():
                # 엔진 수 읽기 (0.01초 제한)
                result = engine.play(board, chess.engine.Limit(time=0.01))
                
                if result.move:
                    board.push(result.move)
                    # 기보 트리에 수 추가
                    node = node.add_variation(result.move)
                else:
                    break
            
            # 4. 결과 판정 및 처리
            raw_result = board.result()
            
            # 무승부일 경우 저장하지 않고 재경기 (번호 유지)
            if raw_result == "1/2-1/2":
                print(f"[-] Game {current_count}: 무승부 발생 - 데이터를 저장하지 않고 재경기합니다.")
                continue
            
            # 승패가 결정된 경우에만 파일 저장 및 카운트 증가
            game.headers["Result"] = raw_result
            pgn_file.write(str(game) + "\n\n")
            
            # 한글 결과 매핑
            if raw_result == "1-0":
                display_result = "백색 승리"
            elif raw_result == "0-1":
                display_result = "흑색 승리"
            else:
                display_result = f"기타 ({raw_result})"
                
            print(f"[+] Game {current_count} 수집 완료: {display_result}")
            current_count += 1
            
    # 5. 엔진 종료
    engine.quit()
    print(f"\n==========================================")
    print(f"모든 작업이 완료되었습니다!")
    print(f"최종 저장 파일: {os.path.abspath(output_file)}")
    print(f"==========================================")

if __name__ == "__main__":
    # 원하는 수집 판수를 입력하세요 (예: 100판)
    collect_ai_games(100)