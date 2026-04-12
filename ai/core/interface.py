"""
core/interface.py
하드웨어 파트와 소프트웨어 파트가 주고받는 JSON 메시지 규격을 정의합니다.

설계 원칙
---------
- 모든 메시지는 Python dict로 표현하고 json.dumps/loads로 직렬화합니다.
- UCI 수 표기(예: "e2e4")를 공통 기준으로 사용합니다.
- 하드웨어 파트는 이 파일의 함수만 호출하면 되도록 인터페이스를 단순하게 유지합니다.

메시지 종류
-----------
  GameState    : 소프트웨어 → 하드웨어  (현재 보드 상태 전달)
  MoveCommand  : 소프트웨어 → 하드웨어  (로봇이 실행할 수 명령)
  RobotResult  : 하드웨어 → 소프트웨어  (수 실행 완료/실패 응답)
  SafetyEvent  : 하드웨어 → 소프트웨어  (비상정지 등 안전 이벤트)
"""

from __future__ import annotations

import json
import time
import chess
from dataclasses import dataclass, asdict, field
from typing import Literal


# ── 공통 타입 정의 ────────────────────────────────────────────────────────

MoveType = Literal["normal", "capture", "castle_king", "castle_queen", "promotion", "en_passant"]
GameMode = Literal["auto", "human_vs_robot", "approval"]
TurnStatus = Literal["waiting", "thinking", "executing", "done", "error"]


# ── 메시지 데이터클래스 ───────────────────────────────────────────────────

@dataclass
class GameState:
    """
    소프트웨어 → 하드웨어
    현재 보드 상태를 전달합니다. 로봇이 수를 실행하기 전에 항상 먼저 수신합니다.
    """
    msg_type: str = field(default="game_state", init=False)
    fen: str = ""                          # 완전한 FEN 문자열
    turn: str = "w"                        # "w" 또는 "b"
    mode: GameMode = "auto"                # 대국 모드
    status: TurnStatus = "waiting"         # 현재 턴 상태
    move_number: int = 1                   # 전체 수 번호
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str | dict) -> "GameState":
        d = json.loads(data) if isinstance(data, str) else data
        d.pop("msg_type", None)
        return cls(**d)

    @classmethod
    def from_board(cls, board: chess.Board, mode: GameMode = "auto", status: TurnStatus = "waiting") -> "GameState":
        """chess.Board 객체에서 직접 생성합니다."""
        return cls(
            fen=board.fen(),
            turn="w" if board.turn == chess.WHITE else "b",
            mode=mode,
            status=status,
            move_number=board.fullmove_number,
        )


@dataclass
class MoveCommand:
    """
    소프트웨어 → 하드웨어
    로봇이 실행해야 할 수를 전달합니다.
    """
    msg_type: str = field(default="move_command", init=False)
    uci: str = ""                          # UCI 표기 (예: "e2e4", "e1g1")
    from_square: str = ""                  # 출발 칸 이름 (예: "e2")
    to_square: str = ""                    # 도착 칸 이름 (예: "e4")
    move_type: MoveType = "normal"         # 수 종류
    captured_piece: str | None = None      # 잡힌 기물 (예: "p", "N"), 없으면 None
    promotion_piece: str | None = None     # 프로모션 기물 (예: "Q"), 없으면 None
    robot_id: str = "A"                    # 담당 로봇 ("A" 또는 "B")
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str | dict) -> "MoveCommand":
        d = json.loads(data) if isinstance(data, str) else data
        d.pop("msg_type", None)
        return cls(**d)

    @classmethod
    def from_move(cls, move: chess.Move, board: chess.Board, robot_id: str = "A") -> "MoveCommand":
        """
        chess.Move + 현재 보드 상태에서 MoveCommand를 자동 생성합니다.
        수 종류(캐슬링·앙파상·프로모션)를 자동 판별합니다.
        """
        from_sq = chess.square_name(move.from_square)
        to_sq = chess.square_name(move.to_square)
        uci = move.uci()

        # 수 종류 판별
        captured = board.piece_at(move.to_square)
        move_type: MoveType = "normal"

        if board.is_castling(move):
            if chess.square_file(move.to_square) > chess.square_file(move.from_square):
                move_type = "castle_king"
            else:
                move_type = "castle_queen"
        elif board.is_en_passant(move):
            move_type = "en_passant"
            # 앙파상은 to_square에 기물이 없어도 잡는다
            ep_rank = 4 if board.turn == chess.WHITE else 3
            ep_sq = chess.square(chess.square_file(move.to_square), ep_rank)
            captured = board.piece_at(ep_sq)
        elif move.promotion:
            move_type = "promotion"
        elif captured:
            move_type = "capture"

        return cls(
            uci=uci,
            from_square=from_sq,
            to_square=to_sq,
            move_type=move_type,
            captured_piece=captured.symbol() if captured else None,
            promotion_piece=chess.piece_symbol(move.promotion) if move.promotion else None,
            robot_id=robot_id,
        )


@dataclass
class RobotResult:
    """
    하드웨어 → 소프트웨어
    로봇의 수 실행 결과를 보고합니다.
    """
    msg_type: str = field(default="robot_result", init=False)
    success: bool = True                   # 실행 성공 여부
    uci: str = ""                          # 실행한 수 (확인용)
    fen_after: str | None = None           # 실행 후 비전이 인식한 FEN (선택)
    error: str | None = None              # 실패 시 오류 메시지
    robot_id: str = "A"
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str | dict) -> "RobotResult":
        d = json.loads(data) if isinstance(data, str) else data
        d.pop("msg_type", None)
        return cls(**d)


@dataclass
class SafetyEvent:
    """
    하드웨어 → 소프트웨어
    비상정지·알람·핸드오프 오류 등 안전 이벤트를 보고합니다.
    """
    msg_type: str = field(default="safety_event", init=False)
    event_type: Literal["emergency_stop", "alarm", "handoff_fail", "resume"] = "alarm"
    message: str = ""                      # 사람이 읽을 수 있는 설명
    robot_id: str | None = None           # 어느 로봇에서 발생했는지 (없으면 전체)
    timestamp: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, data: str | dict) -> "SafetyEvent":
        d = json.loads(data) if isinstance(data, str) else data
        d.pop("msg_type", None)
        return cls(**d)


# ── 메시지 파싱 (수신 측에서 타입 불문하고 파싱) ─────────────────────────

_MSG_REGISTRY = {
    "game_state": GameState,
    "move_command": MoveCommand,
    "robot_result": RobotResult,
    "safety_event": SafetyEvent,
}


def parse_message(data: str | dict) -> GameState | MoveCommand | RobotResult | SafetyEvent:
    """
    JSON 문자열 또는 dict를 받아 적절한 메시지 객체로 역직렬화합니다.

    Raises
    ------
    ValueError : msg_type 필드가 없거나 알 수 없는 타입일 때
    """
    d = json.loads(data) if isinstance(data, str) else data
    msg_type = d.get("msg_type")
    if msg_type not in _MSG_REGISTRY:
        raise ValueError(f"알 수 없는 msg_type: '{msg_type}'")
    return _MSG_REGISTRY[msg_type].from_json(d)


# ── UCI 유틸리티 ──────────────────────────────────────────────────────────

def uci_to_move(uci: str, board: chess.Board) -> chess.Move:
    """UCI 문자열을 chess.Move로 변환합니다. 유효하지 않으면 ValueError."""
    try:
        move = chess.Move.from_uci(uci)
    except Exception:
        raise ValueError(f"잘못된 UCI 표기: '{uci}'")
    if move not in board.legal_moves:
        raise ValueError(f"현재 보드에서 불법 수: '{uci}'")
    return move


def best_move_to_command(board: chess.Board, engine, time_limit: float = 0.5, robot_id: str = "A") -> MoveCommand:
    """
    Stockfish 엔진에서 최선의 수를 받아 MoveCommand로 변환합니다.

    Parameters
    ----------
    board      : 현재 chess.Board
    engine     : core.create_engine()으로 생성한 Stockfish 엔진
    time_limit : 엔진 탐색 시간 (초)
    robot_id   : 담당 로봇 ID

    Returns
    -------
    MoveCommand
    """
    import chess.engine
    result = engine.play(board, chess.engine.Limit(time=time_limit))
    return MoveCommand.from_move(result.move, board, robot_id=robot_id)
