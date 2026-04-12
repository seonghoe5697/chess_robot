"""
core/board.py
체스 보드 관련 공통 상수와 유틸리티를 한 곳에서 관리합니다.
기존 파일들마다 따로 정의되어 있던 PIECE_SYMBOLS, PIECE_VALUES 등을 통합합니다.
"""

import chess

# ── 기물 상수 ──────────────────────────────────────────────────────────────

# 기물 문자 → 이미지 파일명 (images/ 폴더 기준)
PIECE_SYMBOLS: dict[str, str] = {
    'P': 'wp', 'R': 'wr', 'N': 'wn', 'B': 'wb', 'Q': 'wq', 'K': 'wk',
    'p': 'bp', 'r': 'br', 'n': 'bn', 'b': 'bb', 'q': 'bq', 'k': 'bk',
}

# 기물 타입 → 점수 (재료 우위 계산용)
PIECE_VALUES: dict[int, int] = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
    chess.KING: 0,
}

# CNN 레이블 인덱스 ↔ 기물 문자 양방향 매핑
LABEL_TO_PIECE: dict[int, str] = {
    0: 'P', 1: 'N', 2: 'B', 3: 'R', 4: 'Q', 5: 'K',
    6: 'p', 7: 'n', 8: 'b', 9: 'r', 10: 'q', 11: 'k',
    12: '.',  # 빈 칸
}
PIECE_TO_LABEL: dict[str, int] = {v: k for k, v in LABEL_TO_PIECE.items()}

# ── 보드 유틸리티 ──────────────────────────────────────────────────────────

def square_to_screen(
    square: int,
    square_size: int,
    player_color: bool = chess.WHITE,
) -> tuple[int, int]:
    """
    chess.Square → 화면 픽셀 좌표 (center x, center y) 변환.
    player_color에 따라 보드 방향(뒤집기)을 처리합니다.
    """
    file_idx = chess.square_file(square)
    rank_idx = chess.square_rank(square)

    if player_color == chess.WHITE:
        col = file_idx
        row = 7 - rank_idx
    else:
        col = 7 - file_idx
        row = rank_idx

    cx = col * square_size + square_size // 2
    cy = row * square_size + square_size // 2
    return cx, cy


def screen_to_square(
    x: int,
    y: int,
    square_size: int,
    player_color: bool = chess.WHITE,
) -> int:
    """
    화면 클릭 좌표 → chess.Square 변환.
    player_color에 따라 보드 방향을 처리합니다.
    """
    col_raw = x // square_size
    row_raw = y // square_size

    if player_color == chess.WHITE:
        file_idx = col_raw
        rank_idx = 7 - row_raw
    else:
        file_idx = 7 - col_raw
        rank_idx = row_raw

    file_idx = max(0, min(7, file_idx))
    rank_idx = max(0, min(7, rank_idx))
    return chess.square(file_idx, rank_idx)


def material_score(board: chess.Board, pov: bool = chess.WHITE) -> int:
    """
    현재 보드에서 pov 진영의 재료 우위 점수를 반환합니다.
    양수 = pov 우세, 음수 = 상대 우세.
    """
    def side_value(color: bool) -> int:
        return sum(
            PIECE_VALUES[p.piece_type]
            for p in board.piece_map().values()
            if p.color == color
        )

    score = side_value(pov) - side_value(not pov)
    return score
