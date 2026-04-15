"""
core/fen.py
FEN 문자열 생성 및 복원을 담당합니다.

기존 app.py의 labels_to_fen()은 턴·캐슬링·앙파상 정보를
전부 고정값(" w - - 0 1")으로 하드코딩했습니다.
이 모듈에서는 가능한 정보를 최대한 복원합니다.
"""

import chess
from core.board import LABEL_TO_PIECE


# ── 핵심: CNN 레이블 배열 → 완전한 FEN ────────────────────────────────────

def labels_to_fen(
    labels: list[int],
    turn: bool = chess.WHITE,
    castling_rights: str | None = None,
    en_passant_square: int | None = None,
    halfmove_clock: int = 0,
    fullmove_number: int = 1,
) -> str:
    """
    CNN이 예측한 64칸 레이블 배열을 완전한 FEN 문자열로 변환합니다.

    Parameters
    ----------
    labels           : 64개 정수 리스트 (행 우선, 0번=a8, 63번=h1)
    turn             : 다음 수를 둘 진영 (chess.WHITE / chess.BLACK)
    castling_rights  : 캐슬링 가능 여부 문자열 ("KQkq", "-" 등)
                       None이면 현재 기물 위치에서 자동 추론합니다.
    en_passant_square: 앙파상 가능한 칸 (chess.Square 또는 None)
    halfmove_clock   : 50수 규칙용 카운터
    fullmove_number  : 전체 수 번호

    Returns
    -------
    완전한 FEN 문자열 (예: "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1")
    """
    # 1. 기물 배치 파트
    piece_placement = _labels_to_placement(labels)

    # 2. 턴
    turn_str = "w" if turn == chess.WHITE else "b"

    # 3. 캐슬링: 지정이 없으면 기물 위치 기반으로 자동 추론
    if castling_rights is None:
        castling_rights = _infer_castling(piece_placement)

    # 4. 앙파상
    ep_str = chess.square_name(en_passant_square) if en_passant_square is not None else "-"

    return f"{piece_placement} {turn_str} {castling_rights} {ep_str} {halfmove_clock} {fullmove_number}"


def _labels_to_placement(labels: list[int]) -> str:
    """레이블 배열 → FEN 기물 배치 파트 (8행/로 구분)."""
    fen_rows = []
    for rank in range(8):        # rank 0 = a8 (top row in FEN)
        row_labels = labels[rank * 8: rank * 8 + 8]
        fen_row = ""
        empty_count = 0
        for label in row_labels:
            char = LABEL_TO_PIECE[label]
            if char == '.':
                empty_count += 1
            else:
                if empty_count > 0:
                    fen_row += str(empty_count)
                    empty_count = 0
                fen_row += char
        if empty_count > 0:
            fen_row += str(empty_count)
        fen_rows.append(fen_row)
    return "/".join(fen_rows)


def _infer_castling(placement: str) -> str:
    """
    기물 배치 문자열만으로 캐슬링 가능성을 추론합니다.
    킹과 룩이 초기 위치에 있을 때만 캐슬링 권리를 부여합니다.
    (실제 이동 여부는 알 수 없으므로 '가능성 있음' 기준으로 판단)
    """
    rows = placement.split("/")
    rank1 = rows[7]  # FEN 마지막 행 = rank 1 (백 진영)
    rank8 = rows[0]  # FEN 첫 번째 행 = rank 8 (흑 진영)

    rights = ""

    # 백 킹사이드: e1=K, h1=R
    if _piece_at(rank1, 4) == 'K' and _piece_at(rank1, 7) == 'R':
        rights += "K"
    # 백 퀸사이드: e1=K, a1=R
    if _piece_at(rank1, 4) == 'K' and _piece_at(rank1, 0) == 'R':
        rights += "Q"
    # 흑 킹사이드: e8=k, h8=r
    if _piece_at(rank8, 4) == 'k' and _piece_at(rank8, 7) == 'r':
        rights += "k"
    # 흑 퀸사이드: e8=k, a8=r
    if _piece_at(rank8, 4) == 'k' and _piece_at(rank8, 0) == 'r':
        rights += "q"

    return rights if rights else "-"


def _piece_at(fen_rank: str, file_idx: int) -> str | None:
    """
    FEN 랭크 문자열에서 특정 파일(0~7)의 기물 문자를 반환합니다.
    빈 칸이면 None 반환.
    """
    col = 0
    for ch in fen_rank:
        if ch.isdigit():
            col += int(ch)
        else:
            if col == file_idx:
                return ch
            col += 1
    return None


# ── 보드 상태 → FEN (Game Session 연동용) ─────────────────────────────────

def board_to_fen(board: chess.Board) -> str:
    """chess.Board 객체를 완전한 FEN 문자열로 변환합니다."""
    return board.fen()


def fen_to_board(fen: str) -> chess.Board:
    """FEN 문자열로 chess.Board 객체를 생성합니다."""
    return chess.Board(fen)


def validate_fen(fen: str) -> tuple[bool, list[str]]:
    """
    FEN 유효성을 검사하고 오류 목록을 반환합니다.

    Returns
    -------
    (is_valid, error_messages)
    """
    try:
        board = chess.Board(fen)
        errors_flag = board.status()
    except Exception as e:
        return False, [f"FEN 파싱 오류: {e}"]

    if errors_flag == chess.STATUS_VALID:
        return True, []

    messages = []
    checks = [
        (chess.STATUS_NO_WHITE_KING,        "백 킹 없음"),
        (chess.STATUS_NO_BLACK_KING,        "흑 킹 없음"),
        (chess.STATUS_TOO_MANY_KINGS,       "킹이 너무 많음"),
        (chess.STATUS_TOO_MANY_WHITE_PAWNS, "백 폰이 너무 많음"),
        (chess.STATUS_TOO_MANY_BLACK_PAWNS, "흑 폰이 너무 많음"),
        (chess.STATUS_PAWNS_ON_BACKRANK,    "폰이 마지막 랭크에 위치"),
        (chess.STATUS_TOO_MANY_WHITE_PIECES,"백 기물이 너무 많음"),
        (chess.STATUS_TOO_MANY_BLACK_PIECES,"흑 기물이 너무 많음"),
        (chess.STATUS_BAD_CASTLING_RIGHTS,  "캐슬링 권리 오류"),
        (chess.STATUS_INVALID_EP_SQUARE,    "앙파상 칸 오류"),
        (chess.STATUS_OPPOSITE_CHECK,       "차례가 아닌 쪽이 체크 상태 (비정상 포지션)"),
        (chess.STATUS_TOO_MANY_CHECKERS,    "체크 상태가 너무 많음"),
        (chess.STATUS_RACE_CHECK,           "레이스 체크 오류"),
        (chess.STATUS_RACE_OVER,            "레이스 종료 오류"),
        (chess.STATUS_RACE_MATERIAL,        "레이스 기물 오류"),
    ]
    for flag, msg in checks:
        if errors_flag & flag:
            messages.append(msg)

    # 모든 플래그를 확인했는데도 messages가 비어있으면 알 수 없는 오류
    if not messages:
        messages.append(f"알 수 없는 규칙 위반 (status={errors_flag})")

    return False, messages