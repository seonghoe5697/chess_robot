import chess
import chess.engine
import chess.pgn
import datetime
import os

from core import create_engine, safe_quit

# 게임당 무승부 최대 재시도 횟수 (무한 루프 방지)
MAX_DRAW_RETRIES = 10


def collect_ai_games(num_games=100, output_file="ai_games.pgn"):
    try:
        engine = create_engine(elo=2850)
        print("체스 엔진 로드 완료. 데이터 수집을 시작합니다...")
    except (FileNotFoundError, RuntimeError) as e:
        print(f"엔진 실행 중 오류 발생: {e}")
        return

    try:
        with open(output_file, "a", encoding="utf-8") as pgn_file:
            current_count = 1
            draw_retries = 0

            while current_count <= num_games:
                board = chess.Board()
                game = chess.pgn.Game()

                now = datetime.datetime.now()
                game.headers["Event"] = f"AI Self-Play #{current_count}"
                game.headers["Site"] = "Busan, KOR"
                game.headers["Date"] = now.strftime("%Y.%m.%d")
                game.headers["Round"] = str(current_count)
                game.headers["White"] = "Stockfish_White"
                game.headers["Black"] = "Stockfish_Black"

                node = game

                while not board.is_game_over():
                    result = engine.play(board, chess.engine.Limit(time=0.01))
                    if result.move:
                        board.push(result.move)
                        node = node.add_variation(result.move)
                    else:
                        break

                raw_result = board.result()

                # 무승부: 재시도 (상한 초과 시 건너뛰기)
                if raw_result == "1/2-1/2":
                    draw_retries += 1
                    if draw_retries >= MAX_DRAW_RETRIES:
                        print(f"[-] Game {current_count}: 무승부 {MAX_DRAW_RETRIES}회 연속 → 건너뜁니다.")
                        current_count += 1
                        draw_retries = 0
                    else:
                        print(f"[-] Game {current_count}: 무승부 발생 (재시도 {draw_retries}/{MAX_DRAW_RETRIES})")
                    continue

                draw_retries = 0
                game.headers["Result"] = raw_result
                pgn_file.write(str(game) + "\n\n")

                result_map = {"1-0": "백색 승리", "0-1": "흑색 승리"}
                display_result = result_map.get(raw_result, f"기타 ({raw_result})")
                print(f"[+] Game {current_count} 수집 완료: {display_result}")
                current_count += 1

    finally:
        safe_quit(engine)

    print(f"\n==========================================")
    print(f"모든 작업이 완료되었습니다!")
    print(f"최종 저장 파일: {os.path.abspath(output_file)}")
    print(f"==========================================")


if __name__ == "__main__":
    collect_ai_games(100)