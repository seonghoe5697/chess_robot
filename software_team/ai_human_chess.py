"""
ai_human_chess.py  ―  사람 vs AI GUI + 도봇 연동
위치: software_team/ai_human_chess.py
"""

import math
import threading
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import chess
import chess.engine

from core import create_engine, safe_quit, PIECE_SYMBOLS, PIECE_VALUES
from robot_bridge import RobotBridge

SQUARE_SIZE = 60


class HumanVsAIChessGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("또봇 체스 ― 사람 vs AI (도봇 연동)")

        self.board           = chess.Board()
        self.images          = {}
        self.small_images    = {}
        self.selected_square = None
        self.is_ai_thinking  = False
        self.game_over       = False
        self.engine          = None
        self.hint_move       = None
        self.player_color    = chess.WHITE
        self._robot_busy     = False

        try:
            self.engine = create_engine(elo=1350)
        except (FileNotFoundError, RuntimeError) as e:
            messagebox.showerror("엔진 오류", str(e))
            self.root.destroy()
            return

        self._load_images()
        self._setup_ui()

        # GUI 완전히 뜬 뒤 도봇 초기화 (스레드 안전)
        self.robot = RobotBridge()
        # 2초 후 연결 상태 UI 반영
        self.root.after(2000, self._refresh_robot_status)
        self.root.after(100, self._choose_side)

    # ── 도봇 상태 갱신 ───────────────────────────────────────

    def _refresh_robot_status(self) -> None:
        if self.robot.is_ready:
            self._status_var.set("🤖 도봇 연결됨 — 준비 완료")
            self._robot_badge.config(text="🤖 도봇 연결됨", fg="#2e7d32")
        else:
            self._status_var.set("🤖 더미 모드 — 도봇 미연결")
            self._robot_badge.config(text="🤖 더미 모드", fg="#888888")
        # 5초마다 재확인
        self.root.after(5000, self._refresh_robot_status)

    # ── 이미지 ───────────────────────────────────────────────

    def _load_images(self):
        for char, name in PIECE_SYMBOLS.items():
            try:
                img = Image.open(f"images/{name}.png")
                self.images[char] = ImageTk.PhotoImage(
                    img.resize((SQUARE_SIZE, SQUARE_SIZE), Image.Resampling.LANCZOS))
                self.small_images[char] = ImageTk.PhotoImage(
                    img.resize((25, 25), Image.Resampling.LANCZOS))
            except Exception as e:
                print(f"이미지 로드 실패: {name}.png — {e}")

    # ── UI ───────────────────────────────────────────────────

    def _setup_ui(self):
        top = tk.Frame(self.root, bg="#f0f0f0", pady=10)
        top.pack(fill=tk.X, padx=10)

        diff_row = tk.Frame(top, bg="#f0f0f0")
        diff_row.pack(fill=tk.X)
        tk.Label(diff_row, text="AI 난이도:", bg="#f0f0f0",
                 font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.difficulty_scale = tk.Scale(
            diff_row, from_=1350, to_=2850, orient=tk.HORIZONTAL,
            length=150, command=self._on_difficulty_change,
            bg="#f0f0f0", highlightthickness=0)
        self.difficulty_scale.set(1350)
        self.difficulty_scale.pack(side=tk.LEFT, padx=10)
        self.diff_label = tk.Label(diff_row, text="초급자", fg="#2e7d32", bg="#f0f0f0")
        self.diff_label.pack(side=tk.LEFT)

        # 도봇 상태 배지 (초기: 확인중)
        self._robot_badge = tk.Label(diff_row, text="🤖 도봇 확인 중...",
                                     bg="#f0f0f0", fg="#888888",
                                     font=("Arial", 9, "bold"))
        self._robot_badge.pack(side=tk.LEFT, padx=10)

        cap_row = tk.Frame(top, bg="#f0f0f0", pady=5)
        cap_row.pack(fill=tk.X)
        self.captured_icons_label = tk.Label(cap_row, bg="#f0f0f0")
        self.captured_icons_label.pack(side=tk.LEFT)
        self.material_score_label = tk.Label(cap_row, text="기물 균형: 0",
                                             bg="#f0f0f0", font=("Arial", 10, "bold"))
        self.material_score_label.pack(side=tk.RIGHT, padx=10)

        main = tk.Frame(self.root)
        main.pack(pady=5, padx=10)
        self.canvas = tk.Canvas(main, width=SQUARE_SIZE*8, height=SQUARE_SIZE*8)
        self.canvas.pack(side=tk.LEFT)
        self.canvas.bind("<Button-1>", self._on_click)

        btn = tk.Frame(self.root, pady=10)
        btn.pack()
        for text, cmd, bg in [
            ("힌트 보기",  self._show_hint,        "#e1f5fe"),
            ("무르기",     self._undo_move,         "#fff9c4"),
            ("기권",       self._resign,            "#ffcdd2"),
            ("리셋/진영",  self._reset_with_choice, "#eeeeee"),
            ("🏠 홈 이동", self._robot_go_home,     "#e8f5e9"),
        ]:
            tk.Button(btn, text=text, command=cmd, bg=bg,
                      width=10).pack(side=tk.LEFT, padx=5)

        self._status_var = tk.StringVar(value="초기화 중...")
        tk.Label(self.root, textvariable=self._status_var,
                 bg="#222", fg="#aaffaa", font=("Consolas", 9),
                 anchor="w", padx=8).pack(fill=tk.X, side=tk.BOTTOM)

    # ── 설정 ─────────────────────────────────────────────────

    def _on_difficulty_change(self, val):
        elo = int(val)
        if self.engine:
            self.engine.configure({"UCI_LimitStrength": True, "UCI_Elo": elo})
        if elo < 1800:
            self.diff_label.config(text="초급자", fg="#2e7d32")
        elif elo < 2300:
            self.diff_label.config(text="중급자", fg="#1565c0")
        else:
            self.diff_label.config(text="고수",   fg="#c62828")

    def _choose_side(self):
        choice = messagebox.askyesno("진영 선택",
                                     "백색(White)으로 시작하시겠습니까?\n(아니오 = 흑색)")
        self.player_color    = chess.WHITE if choice else chess.BLACK
        self.board.reset()
        self.game_over       = False
        self.selected_square = None
        self.hint_move       = None
        if self.player_color == chess.BLACK:
            self.is_ai_thinking = True
            self.root.after(500, self._engine_move)
        self._draw_all()

    # ── 그리기 ───────────────────────────────────────────────

    def _draw_board(self):
        self.canvas.delete("all")
        colors    = ["#eeeed2", "#769656"]
        last_move = self.board.peek() if self.board.move_stack else None
        is_check  = self.board.is_check()
        king_sq   = self.board.king(self.board.turn)

        for r in range(8):
            for c in range(8):
                dc = c if self.player_color == chess.WHITE else 7 - c
                dr = r if self.player_color == chess.WHITE else 7 - r
                sq = chess.square(dc, 7 - dr)
                color = colors[(r + c) % 2]
                if last_move and sq in (last_move.from_square, last_move.to_square):
                    color = "#ced26b"
                if self.selected_square == sq:
                    color = "#f7f769"
                elif is_check and sq == king_sq:
                    color = "#ff8a80"
                x1, y1 = c * SQUARE_SIZE, r * SQUARE_SIZE
                x2, y2 = x1 + SQUARE_SIZE, y1 + SQUARE_SIZE
                self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="")
                if self.selected_square is not None and not self.game_over:
                    dests = [m.to_square for m in self.board.legal_moves
                             if m.from_square == self.selected_square]
                    if sq in dests:
                        m = SQUARE_SIZE * 0.35
                        self.canvas.create_oval(x1+m, y1+m, x2-m, y2-m,
                                                fill="#2e7d32", stipple="gray50", outline="")
        if self.hint_move:
            self._draw_hint_arrow(self.hint_move)
        for sq in chess.SQUARES:
            piece = self.board.piece_at(sq)
            if piece and piece.symbol() in self.images:
                f  = chess.square_file(sq)
                ri = chess.square_rank(sq)
                cp = f  if self.player_color == chess.WHITE else 7 - f
                rp = 7 - ri if self.player_color == chess.WHITE else ri
                self.canvas.create_image(
                    cp * SQUARE_SIZE + SQUARE_SIZE // 2,
                    rp * SQUARE_SIZE + SQUARE_SIZE // 2,
                    image=self.images[piece.symbol()])

    def _draw_hint_arrow(self, move):
        def pos(sq):
            f, r = chess.square_file(sq), chess.square_rank(sq)
            c  = f  if self.player_color == chess.WHITE else 7 - f
            rr = 7 - r if self.player_color == chess.WHITE else r
            return c*SQUARE_SIZE + SQUARE_SIZE//2, rr*SQUARE_SIZE + SQUARE_SIZE//2
        x1, y1 = pos(move.from_square)
        x2, y2 = pos(move.to_square)
        self.canvas.create_line(x1, y1, x2, y2, fill="#0288d1", width=6, arrow=tk.LAST)

    def _draw_all(self):
        self._draw_board()
        self._update_material_info()

    # ── 클릭 ─────────────────────────────────────────────────

    def _on_click(self, event):
        if self.game_over or self.is_ai_thinking or self._robot_busy:
            return
        c_raw = event.x // SQUARE_SIZE
        r_raw = event.y // SQUARE_SIZE
        fi = c_raw if self.player_color == chess.WHITE else 7 - c_raw
        ri = 7 - r_raw if self.player_color == chess.WHITE else r_raw
        if not (0 <= fi <= 7 and 0 <= ri <= 7):
            return
        sq    = chess.square(fi, ri)
        piece = self.board.piece_at(sq)
        if self.selected_square is None:
            if piece and piece.color == self.player_color:
                self.selected_square = sq
        else:
            candidates = [m for m in self.board.legal_moves
                          if m.from_square == self.selected_square and m.to_square == sq]
            if not candidates:
                self.selected_square = (sq if (piece and piece.color == self.player_color) else None)
            elif len(candidates) > 1:
                move = self._ask_promotion(candidates)
                if move:
                    self._push_player_move(move)
            else:
                self._push_player_move(candidates[0])
        self._draw_all()

    def _ask_promotion(self, candidates):
        names = {chess.QUEEN: "퀸(Q)", chess.ROOK: "룩(R)",
                 chess.BISHOP: "비숍(B)", chess.KNIGHT: "나이트(N)"}
        pmap  = {names[m.promotion]: m for m in candidates if m.promotion in names}
        if not pmap:
            return candidates[0]
        top = tk.Toplevel(self.root)
        top.title("프로모션")
        top.grab_set()
        sel = [None]
        tk.Label(top, text="프로모션 기물 선택:", font=("Arial", 11, "bold"), pady=10).pack()
        for name, move in pmap.items():
            def make(m=move):
                def cb():
                    sel[0] = m
                    top.destroy()
                return cb
            tk.Button(top, text=name, width=15, font=("Arial", 10),
                      command=make()).pack(pady=3, padx=20)
        self.root.wait_window(top)
        return sel[0]

    # ── 사람 수 처리 ─────────────────────────────────────────

    def _push_player_move(self, move: chess.Move):
        self.selected_square = None
        self.hint_move       = None
        self._robot_busy     = True
        self._status_var.set(f"도봇 이동 중: {move.uci()[:2].upper()} → {move.uci()[2:].upper()}")

        pre_board = self.board.copy()
        self.board.push(move)
        self._update_evaluation()
        self._draw_all()

        if self.board.is_game_over():
            self._robot_busy = False
            self.game_over   = True
            self._show_game_result()
            return

        def on_done():
            self._robot_busy    = False
            self.is_ai_thinking = True
            self.root.after(0, lambda: self._status_var.set("도봇 완료 — AI 응수 중..."))
            self.root.after(100, self._engine_move)

        self.robot.execute_async(pre_board, move, on_done=on_done)

    # ── AI 수 처리 ────────────────────────────────────────────

    def _engine_move(self):
        if self.game_over:
            return
        info      = self.engine.analyse(self.board, chess.engine.Limit(time=0.6))
        score_obj = info["score"].pov(self.board.turn)
        score     = score_obj.score()
        mate_in   = score_obj.mate()
        if (score is not None and score <= -600) or (mate_in is not None and mate_in < 0):
            self.game_over      = True
            self.is_ai_thinking = False
            self._show_game_result("AI가 항복했습니다. 당신의 승리!")
            return

        result = self.engine.play(self.board, chess.engine.Limit(time=0.7))
        if not result.move:
            self.is_ai_thinking = False
            return

        move = result.move
        self._status_var.set(f"AI: {move.uci()[:2].upper()} → {move.uci()[2:].upper()} — 도봇 이동 중...")
        self._robot_busy = True

        pre_board = self.board.copy()
        self.board.push(move)
        self._update_evaluation()
        self._draw_all()

        def on_done():
            self._robot_busy    = False
            self.is_ai_thinking = False
            self.root.after(0, lambda: self._status_var.set("AI 이동 완료 — 당신 차례"))
            if self.board.is_game_over():
                self.game_over = True
                self._show_game_result()

        self.robot.execute_async(pre_board, move, on_done=on_done)

    # ── 버튼 ─────────────────────────────────────────────────

    def _show_hint(self):
        if self.game_over or self.is_ai_thinking or self._robot_busy:
            return
        res = self.engine.play(self.board, chess.engine.Limit(time=0.5))
        if res.move:
            self.hint_move = res.move
            self._draw_all()

    def _undo_move(self):
        if self.game_over or self.is_ai_thinking or self._robot_busy:
            return
        if len(self.board.move_stack) >= 2:
            self.board.pop()
            self.board.pop()
            self.hint_move = None
            self._update_evaluation()
            self._draw_all()

    def _resign(self):
        if self.game_over or self._robot_busy:
            return
        if messagebox.askyesno("기권", "정말로 항복하시겠습니까?"):
            self.game_over = True
            self._show_game_result("사용자 항복 — AI 승리!")

    def _reset_with_choice(self):
        if self._robot_busy:
            messagebox.showwarning("도봇 이동 중", "도봇 동작 완료 후 리셋하세요.")
            return
        self._choose_side()

    def _robot_go_home(self):
        if self._robot_busy:
            return
        threading.Thread(target=self.robot.go_home, daemon=True).start()

    def _show_game_result(self, custom_msg=None):
        msg = custom_msg or {
            "1-0": "백색 승리!", "0-1": "흑색 승리!", "1/2-1/2": "무승부",
        }.get(self.board.result(), f"게임 종료: {self.board.result()}")
        messagebox.showinfo("결과", msg)

    # ── 정보 ─────────────────────────────────────────────────

    def _update_material_info(self):
        for w in self.captured_icons_label.winfo_children():
            w.destroy()
        opp   = chess.BLACK if self.player_color == chess.WHITE else chess.WHITE
        syms  = ['p','n','b','r','q'] if opp == chess.BLACK else ['P','N','B','R','Q']
        start = {'p':8,'n':2,'b':2,'r':2,'q':1,'P':8,'N':2,'B':2,'R':2,'Q':1}
        for s in syms:
            cnt = len(self.board.pieces(chess.Piece.from_symbol(s).piece_type, opp))
            for _ in range(start[s] - cnt):
                if s in self.small_images:
                    tk.Label(self.captured_icons_label,
                             image=self.small_images[s], bg="#f0f0f0").pack(side=tk.LEFT)
        wv = sum(PIECE_VALUES[p.piece_type]
                 for p in self.board.piece_map().values() if p.color == chess.WHITE)
        bv = sum(PIECE_VALUES[p.piece_type]
                 for p in self.board.piece_map().values() if p.color == chess.BLACK)
        diff = wv - bv
        if self.player_color == chess.BLACK:
            diff = -diff
        self.material_score_label.config(
            text=f"기물 균형: {'+' if diff > 0 else ''}{diff}")

    def _update_evaluation(self):
        try:
            info  = self.engine.analyse(self.board, chess.engine.Limit(time=0.1))
            score = info["score"].white().score()
            if score is None:
                self.evaluation = 1.0 if info["score"].white().mate() > 0 else 0.0
            else:
                self.evaluation = 1 / (1 + math.exp(-score / 300))
        except Exception:
            pass

    # ── 종료 ─────────────────────────────────────────────────

    def on_closing(self):
        self.robot.quit()
        safe_quit(self.engine)
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app  = HumanVsAIChessGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()