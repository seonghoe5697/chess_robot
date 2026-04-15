"""
core/__init__.py
또봇 체스 소프트웨어 공통 코어 패키지.
"""

from core.engine import create_engine, safe_quit, STOCKFISH_PATH
from core.board import (
    PIECE_SYMBOLS, PIECE_VALUES, LABEL_TO_PIECE, PIECE_TO_LABEL,
    square_to_screen, screen_to_square, material_score,
)
from core.fen import (
    labels_to_fen, board_to_fen, fen_to_board, validate_fen,
)
from core.interface import (
    GameState, MoveCommand, RobotResult, SafetyEvent,
    parse_message, uci_to_move, best_move_to_command,
)
from core.session import GameSession

try:
    from core.model import (
        ChessPieceCNN, TRANSFORM, load_model, predict_labels, labels_to_pieces,
    )
except ImportError:
    pass

__all__ = [
    "create_engine", "safe_quit", "STOCKFISH_PATH",
    "PIECE_SYMBOLS", "PIECE_VALUES", "LABEL_TO_PIECE", "PIECE_TO_LABEL",
    "square_to_screen", "screen_to_square", "material_score",
    "labels_to_fen", "board_to_fen", "fen_to_board", "validate_fen",
    "GameState", "MoveCommand", "RobotResult", "SafetyEvent",
    "parse_message", "uci_to_move", "best_move_to_command",
    "GameSession",
    "ChessPieceCNN", "TRANSFORM", "load_model", "predict_labels", "labels_to_pieces",
]
