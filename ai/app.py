"""
app.py  ―  Streamlit 체스판 분석기
이미지 업로드 → CNN 기물 인식 → FEN → Stockfish 추천
core/ 패키지로 공통 로직을 분리한 버전
"""

import subprocess
import traceback

import streamlit as st
from PIL import Image

from core import load_model, predict_labels, labels_to_fen, validate_fen
import chess
import chess.svg
import base64
import sys


# ── Stockfish 직접 통신 (Streamlit asyncio 우회) ───────────────────────────

def analyse_with_stockfish(engine_path: str, fen: str, turn: bool = True):
    """
    turn=True  → 백 기준 점수
    turn=False → 흑 기준 점수 (cp 부호 반전)
    """
    process = subprocess.Popen(
        engine_path,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True,
    )
    commands = f"uci\nisready\nposition fen {fen}\ngo depth 15\n"
    stdout, _ = process.communicate(input=commands, timeout=15)
    process.terminate()

    best_move = None
    score_text = "분석 불가"
    last_cp = None
    last_mate = None

    for line in stdout.splitlines():
        if line.startswith("bestmove"):
            parts = line.split()
            if len(parts) > 1:
                best_move = parts[1]
        if "score cp" in line:
            try:
                last_cp = int(line.split("score cp")[1].split()[0])
                last_mate = None
            except (ValueError, IndexError):
                pass
        if "score mate" in line:
            try:
                last_mate = int(line.split("score mate")[1].split()[0])
                last_cp = None
            except (ValueError, IndexError):
                pass

    if last_cp is not None:
        # Stockfish cp는 항상 백 기준 → 흑 차례면 부호 반전
        cp = last_cp if turn else -last_cp
        score_text = f"{cp / 100:+.2f}"
    elif last_mate is not None:
        mate = last_mate if turn else -last_mate
        score_text = f"Mate in {mate}"

    return best_move, score_text


# ── Streamlit UI ──────────────────────────────────────────────────────────

st.set_page_config(page_title="AI Tobot Chess Analyzer", layout="wide")
st.title("♟️ AI 체스 분석기 (Tobot Chess)")
st.write("체스판 사진을 업로드하면 AI가 기물을 인식하고 Stockfish가 최선의 수를 추천합니다.")

st.sidebar.header("설정")
model_path = st.sidebar.text_input("모델 경로", "chess_model_pure.pth")
default_engine = "stockfish-windows-x86-64.exe" if sys.platform == "win32" else "stockfish"
engine_path = st.sidebar.text_input("Stockfish 경로", default_engine)

# 턴 선택 (FEN 복원용)
turn_choice = st.sidebar.radio("현재 차례", ["백(White)", "흑(Black)"], index=0)
import chess as _chess
turn = _chess.WHITE if turn_choice == "백(White)" else _chess.BLACK

uploaded_file = st.file_uploader("체스판 이미지를 업로드하세요", type=["png", "jpg", "jpeg"])

if uploaded_file is not None:
    image = Image.open(uploaded_file).convert("RGB")
    col1, col2 = st.columns(2)
    col1.image(image, caption="업로드된 이미지", width="stretch")

    with st.spinner("AI가 기물을 분석 중입니다..."):
        try:
            # core.load_model 사용 (캐싱은 st.cache_resource로)
            @st.cache_resource
            def get_model(path):
                return load_model(path)

            model, device = get_model(model_path)
        except FileNotFoundError:
            st.error(f"모델 파일을 찾을 수 없습니다: '{model_path}'")
            st.stop()

        labels = predict_labels(image, model, device)

        # ★ 핵심 변경: 고정값 대신 turn 정보를 반영한 FEN 생성
        fen = labels_to_fen(labels, turn=turn)

    is_valid, errors = validate_fen(fen)

    with col2:
        if not is_valid:
            st.info(f"ℹ️ 비정상 포지션이지만 참고용 분석을 제공합니다. ({', '.join(errors)})")
            st.info(f"추출된 FEN: `{fen}`")
            # 규칙 위반이지만 Stockfish 분석은 시도
            st.write("---")
            st.write("**참고용 Stockfish 분석 (규칙 무시)**")
            try:
                best_move_str, score_text = analyse_with_stockfish(engine_path, fen, turn=(turn == _chess.WHITE))
                if best_move_str and best_move_str != "(none)":
                    # 규칙 위반 FEN이라도 보드 SVG 표시
                    try:
                        ref_board = _chess.Board(fen)
                        best_move_obj = _chess.Move.from_uci(best_move_str)
                        board_svg = chess.svg.board(
                            ref_board,
                            arrows=[chess.svg.Arrow(best_move_obj.from_square, best_move_obj.to_square, color="#ffaa00")],
                            size=400,
                        )
                        pov = "백 기준" if turn == _chess.WHITE else "흑 기준"
                        st.write(f"추천 수: :green[{best_move_str}]  |  형세: {score_text} ({pov})")
                        b64 = base64.b64encode(board_svg.encode("utf-8")).decode("utf-8")
                        st.markdown(f'<img src="data:image/svg+xml;base64,{b64}"/>', unsafe_allow_html=True)
                    except Exception:
                        pov = "백 기준" if turn == _chess.WHITE else "흑 기준"
                        st.write(f"추천 수: :green[{best_move_str}]  |  형세: {score_text} ({pov})")
                else:
                    st.write("Stockfish가 이 포지션에서 수를 찾지 못했습니다.")
            except Exception as e:
                st.write(f"Stockfish 분석 실패: {e}")
        else:
            try:
                best_move_str, score_text = analyse_with_stockfish(engine_path, fen, turn=(turn == _chess.WHITE))

                if best_move_str and best_move_str != "(none)":
                    board = _chess.Board(fen)
                    best_move = _chess.Move.from_uci(best_move_str)
                    board_svg = chess.svg.board(
                        board,
                        arrows=[chess.svg.Arrow(best_move.from_square, best_move.to_square, color="#00ff00")],
                        size=400,
                    )
                    st.subheader("🤖 AI 분석 결과")
                    pov = "백 기준" if turn == _chess.WHITE else "흑 기준"
                    st.write(f"**현재 형세:** {score_text} ({pov})")
                    st.write(f"**추천 수:** :green[{best_move_str}]")
                    b64 = base64.b64encode(board_svg.encode("utf-8")).decode("utf-8")
                    st.markdown(f'<img src="data:image/svg+xml;base64,{b64}"/>', unsafe_allow_html=True)
                    st.info(f"추출된 FEN: `{fen}`")
                else:
                    st.warning("추천 수를 찾지 못했습니다.")
                    st.info(f"추출된 FEN: `{fen}`")

            except subprocess.TimeoutExpired:
                st.error("Stockfish 분석 시간 초과.")
            except FileNotFoundError:
                st.error(f"Stockfish를 찾을 수 없습니다: '{engine_path}'")
            except Exception as e:
                st.error(f"분석 중 오류: {e}")
                st.code(traceback.format_exc())