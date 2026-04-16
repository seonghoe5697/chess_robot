"""
robot_bridge.py  (software_team/ 폴더에 위치)
"""

import sys
import threading
import time
from pathlib import Path

import chess

_HW_DIR = Path(__file__).resolve().parent.parent / "hardware_team"
if str(_HW_DIR) not in sys.path:
    sys.path.insert(0, str(_HW_DIR))

ROBOT_ENABLED = True


class RobotBridge:
    def __init__(self):
        self._ctrl  = None
        self._lock  = threading.Lock()

        if not ROBOT_ENABLED:
            print("[RobotBridge] 더미 모드 — 도봇 미사용")
            return

        threading.Thread(target=self._init_robot, daemon=True).start()

    def _init_robot(self):
        try:
            from dual_dobot_controller import DualDobotController
            ctrl = DualDobotController(log_fn=print)
            ctrl.init()

            # init()이 내부 스레드로 동작하므로 완료까지 대기
            timeout = 30.0
            start   = time.time()
            while time.time() - start < timeout:
                ra_ok = ctrl._ra.device is not None
                rb_ok = ctrl._rb.device is not None
                if ra_ok or rb_ok:
                    break
                time.sleep(0.5)

            ra_ok = ctrl._ra.device is not None
            rb_ok = ctrl._rb.device is not None

            if not ra_ok and not rb_ok:
                raise RuntimeError("로봇A/B 모두 장치 연결 실패")

            self._ctrl = ctrl
            print(f"[RobotBridge] 도봇 초기화 완료  A={ra_ok}  B={rb_ok}")

        except Exception as e:
            print(f"[RobotBridge] 도봇 초기화 실패 → 더미 모드: {e}")
            self._ctrl = None

    def execute(self, board: chess.Board, move: chess.Move) -> None:
        if self._ctrl is None:
            uci = move.uci()
            print(f"[RobotBridge] (더미) {uci[:2].upper()} → {uci[2:].upper()}")
            return
        with self._lock:
            try:
                is_castling = board.is_castling(move)
                self._ctrl.execute_move(board, move)
                if is_castling:
                    self._execute_castling_rook(board, move)
                print(f"[RobotBridge] 이동 완료: {move.uci()}")
            except Exception as e:
                print(f"[RobotBridge] 이동 오류: {e}")

    def execute_async(self, board: chess.Board, move: chess.Move,
                      on_done=None) -> threading.Thread:
        board_copy = board.copy()
        def _run():
            self.execute(board_copy, move)
            if on_done:
                on_done()
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return t

    def go_home(self) -> None:
        if self._ctrl is None:
            return
        try:
            self._ctrl.go_home()
        except Exception as e:
            print(f"[RobotBridge] 홈 이동 오류: {e}")

    def emergency_stop(self) -> None:
        from dual_dobot_controller import request_abort
        request_abort()
        if self._ctrl is None:
            return
        try:
            self._ctrl.emergency_stop_and_recover()
        except Exception as e:
            print(f"[RobotBridge] 비상 정지 오류: {e}")

    def quit(self) -> None:
        if self._ctrl is None:
            return
        try:
            self._ctrl.quit()
            print("[RobotBridge] 도봇 종료")
        except Exception as e:
            print(f"[RobotBridge] 종료 오류: {e}")

    @property
    def is_ready(self) -> bool:
        if self._ctrl is None:
            return False
        return (self._ctrl._ra.device is not None or
                self._ctrl._rb.device is not None)

    def _execute_castling_rook(self, board: chess.Board, move: chess.Move) -> None:
        from dual_dobot_controller import square_to_mm_for, Robot, RANKS, ROW_A_MIN

        mover_is_white = board.turn == chess.WHITE
        if mover_is_white:
            rook_from, rook_to = ("h1", "f1") if move.to_square == chess.G1 else ("a1", "d1")
        else:
            rook_from, rook_to = ("h8", "f8") if move.to_square == chess.G8 else ("a8", "d8")

        from_row = RANKS.index(rook_from[1])
        to_row   = RANKS.index(rook_to[1])
        worker   = self._ctrl._select_robot(from_row, to_row)

        if worker is None:
            pk = Robot.A if from_row >= ROW_A_MIN else Robot.B
            pl = Robot.B if pk == Robot.A else Robot.A
            self._ctrl._handoff_move(
                square_to_mm_for(pk, rook_from),
                square_to_mm_for(pl, rook_to), pk, pl)
        else:
            self._ctrl._park_other(self._ctrl._other(worker))
            self._ctrl._pick_and_place_rs(
                self._ctrl._get_rs(worker),
                square_to_mm_for(worker, rook_from),
                square_to_mm_for(worker, rook_to),
                label=f"캐슬링룩({rook_from.upper()}→{rook_to.upper()})",
            )
            self._ctrl._go_standby(self._ctrl._get_rs(worker))
        print(f"[RobotBridge] 캐슬링 룩: {rook_from.upper()} → {rook_to.upper()}")