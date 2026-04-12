import json
import chess
import chess.engine
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Callable

from core.engine import create_engine, safe_quit
from core.fen import board_to_fen


class TurnState(Enum):
    IDLE        = auto()
    THINKING    = auto()
    AWAITING_HW = auto()
    HW_DONE     = auto()
    GAME_OVER   = auto()


class PlayerType(Enum):
    HUMAN = "human"
    AI    = "ai"


class Msg:
    """SW <-> HW JSON 메시지 빌더"""

    @staticmethod
    def command(board: chess.Board, move: chess.Move) -> dict:
        """SW -> HW: 로봇 이동 지시 메시지"""
        is_capture = board.is_capture(move)
        captured = None
        if is_capture:
            p = board.piece_at(move.to_square)
            if p:
                captured = p.symbol()

        special = None
        if board.is_castling(move):
            special = "castling_kingside" if chess.square_file(move.to_square) == 6 else "castling_queenside"
        elif board.is_en_passant(move):
            special = "en_passant"
        elif move.promotion:
            special = f"promotion_{chess.piece_name(move.promotion)}"

        return {
            "type": "move",
            "uci": move.uci(),
            "from_sq": chess.square_name(move.from_square),
            "to_sq": chess.square_name(move.to_square),
            "turn": "w" if board.turn == chess.WHITE else "b",
            "is_capture": is_capture,
            "captured_piece": captured,
            "special": special,
            "fen_before": board_to_fen(board),
        }

    @staticmethod
    def state(board: chess.Board, move_number: int) -> dict:
        """SW -> HW: 보드 전체 상태 동기화 메시지"""
        return {
            "type": "state",
            "fen": board_to_fen(board),
            "turn": "w" if board.turn == chess.WHITE else "b",
            "move_number": move_number,
            "game_over": board.is_game_over(),
            "result": board.result() if board.is_game_over() else None,
        }

    @staticmethod
    def result_ok(uci: str) -> dict:
        """HW -> SW: 로봇 실행 완료"""
        return {"type": "done", "uci": uci, "status": "ok", "error": None}

    @staticmethod
    def result_error(uci: str, message: str) -> dict:
        """HW -> SW: 로봇 실행 실패"""
        return {"type": "done", "uci": uci, "status": "error", "error": message}

    @staticmethod
    def error(code: str, message: str) -> dict:
        return {"type": "error", "code": code, "message": message}

    @staticmethod
    def to_json(msg: dict, indent=None) -> str:
        return json.dumps(msg, ensure_ascii=False, indent=indent)

    @staticmethod
    def from_json(text: str) -> dict:
        return json.loads(text)


@dataclass
class GameSession:
    """
    대국 중앙 상태 관리자.

    Turn FSM: IDLE -> THINKING -> AWAITING_HW -> HW_DONE -> IDLE (반복)
                                                           -> GAME_OVER

    on_hw_command  콜백이 등록되면 하드웨어 연동 모드로 동작합니다.
    등록이 없으면 GUI 단독 테스트 모드로 동작합니다.

    사용 예시:
        session = GameSession(white=PlayerType.AI, black=PlayerType.AI)
        session.on_hw_command = lambda msg: socket.send(Msg.to_json(msg))
        session.on_state_change = lambda s: gui.refresh()
        session.start()
        while not session.is_game_over():
            session.tick()
    """

    white: PlayerType = PlayerType.AI
    black: PlayerType = PlayerType.AI
    engine_path: str = None
    elo: int = 2850

    on_hw_command:   Callable[[dict], None] = field(default=None, repr=False)
    on_state_change: Callable[["GameSession"], None] = field(default=None, repr=False)
    on_game_over:    Callable[[str], None] = field(default=None, repr=False)

    board:        chess.Board = field(default_factory=chess.Board, init=False)
    state:        TurnState   = field(default=TurnState.IDLE, init=False)
    move_number:  int         = field(default=1, init=False)
    last_command: dict        = field(default=None, init=False)
    _engine:      object      = field(default=None, init=False, repr=False)

    # ── 생명주기 ──────────────────────────────────────────────────────────

    def start(self) -> None:
        if self._engine is None:
            kwargs = {"elo": self.elo}
            if self.engine_path:
                kwargs["path"] = self.engine_path
            self._engine = create_engine(**kwargs)
        self.board.reset()
        self.move_number = 1
        self._transition(TurnState.IDLE)

    def quit(self) -> None:
        if self._engine:
            safe_quit(self._engine)
            self._engine = None

    # ── 메인 루프 ─────────────────────────────────────────────────────────

    def tick(self, engine_time: float = 0.1) -> None:
        """FSM 한 단계 진행. GUI after() 루프나 스레드에서 주기적으로 호출."""
        if self.state == TurnState.IDLE:
            self._begin_turn(engine_time)
        elif self.state == TurnState.HW_DONE:
            self._advance_turn()

    # ── 외부 이벤트 ───────────────────────────────────────────────────────

    def apply_human_move(self, uci: str) -> bool:
        """사람 수를 UCI 문자열로 적용. 합법 수면 True, 불법 수면 False."""
        try:
            move = chess.Move.from_uci(uci)
        except ValueError:
            return False
        if move not in self.board.legal_moves:
            return False
        self._execute_move(move)
        return True

    def receive_hw_result(self, json_text: str) -> None:
        """HW -> SW: 로봇 실행 완료 JSON 수신 시 호출."""
        try:
            msg = Msg.from_json(json_text)
            if msg.get("type") == "done" and msg.get("status") == "ok":
                self._transition(TurnState.HW_DONE)
        except json.JSONDecodeError:
            pass

    def receive_vision_fen(self, fen: str) -> None:
        """비전 카메라 스캔 FEN 수신. 기물 배치 불일치 감지."""
        try:
            scanned = chess.Board(fen)
            if scanned.piece_map() != self.board.piece_map():
                print(f"[Vision] 보드 불일치 감지: {fen}")
        except Exception as e:
            print(f"[Vision] FEN 파싱 오류: {e}")

    # ── 상태 조회 ─────────────────────────────────────────────────────────

    @property
    def current_turn(self) -> PlayerType:
        return self.white if self.board.turn == chess.WHITE else self.black

    @property
    def fen(self) -> str:
        return board_to_fen(self.board)

    def is_game_over(self) -> bool:
        return self.state == TurnState.GAME_OVER

    def get_state_msg(self) -> dict:
        """현재 상태를 HW 동기화용 JSON dict로 반환."""
        return Msg.state(self.board, self.move_number)

    # ── 내부 FSM ──────────────────────────────────────────────────────────

    def _transition(self, new_state: TurnState) -> None:
        self.state = new_state
        if self.on_state_change:
            self.on_state_change(self)

    def _begin_turn(self, engine_time: float) -> None:
        if self.board.is_game_over():
            result = self.board.result()
            self._transition(TurnState.GAME_OVER)
            if self.on_game_over:
                self.on_game_over(result)
            return
        if self.current_turn == PlayerType.AI:
            self._transition(TurnState.THINKING)
            move = self._get_engine_move(engine_time)
            if move:
                self._execute_move(move)

    def _get_engine_move(self, engine_time: float):
        if not self._engine:
            return None
        try:
            result = self._engine.play(self.board, chess.engine.Limit(time=engine_time))
            return result.move
        except chess.engine.EngineTerminatedError:
            return None

    def _execute_move(self, move: chess.Move) -> None:
        cmd = Msg.command(self.board, move)
        self.last_command = cmd
        self.board.push(move)
        self.move_number += 1
        if self.on_hw_command:
            self.on_hw_command(cmd)
            self._transition(TurnState.AWAITING_HW)
        else:
            self._transition(TurnState.HW_DONE)
            self._advance_turn()

    def _advance_turn(self) -> None:
        if self.board.is_game_over():
            result = self.board.result()
            self._transition(TurnState.GAME_OVER)
            if self.on_game_over:
                self.on_game_over(result)
        else:
            self._transition(TurnState.IDLE)
