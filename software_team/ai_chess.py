"""
ai_chess.py  ―  AI vs AI 자동 대국 GUI + 도봇 연동
위치: software_team/ai_chess.py
"""

import sys
import threading
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import chess
import chess.engine

from core import create_engine, safe_quit, PIECE_SYMBOLS
from robot_bridge import RobotBridge

SQUARE_SIZE = 60


class AutoChessGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("또봇 체스 ― AI 자동 대국 (도봇 연동)")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.board       = chess.Board()
        self.is_running  = True
        self._robot_busy = False

        try:
            self.engine = create_engine(elo=2850)
        except (FileNotFoundError, RuntimeError) as e:
            messagebox.showerror("엔진 오류", str(e))
            sys.exit()

        # ── UI 먼저 빌드 ─────────────────────────────────────
        top = tk.Frame(self.root, bg="#f0f0f0", pady=8)
        top.pack(fill=tk.X, padx=10)

        diff_row = tk.Frame(top, bg="#f0f0f0")
        diff_row.pack(fill=tk.X)
        tk.Label(diff_row, text="AI 난이도:", bg="#f0f0f0",
                 font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.difficulty_scale = tk.Scale(
            diff_row, from_=1350, to_=2850, orient=tk.HORIZONTAL,
            length=150, command=self._on_difficulty_change,
            bg="#f0f0f0", highlightthickness=0)
        self.difficulty_scale.set(2850)
        self.difficulty_scale.pack(side=tk.LEFT, padx=10)
        self.diff_label = tk.Label(diff_row, text="고수", fg="#c62828", bg="#f0f0f0")
        self.diff_label.pack(side=tk.LEFT)

        self._robot_badge = tk.Label(diff_row, text="🤖 도봇 확인 중...",
                                     bg="#f0f0f0", fg="#888888",
                                     font=("Arial", 9, "bold"))
        self._robot_badge.pack(side=tk.LEFT, padx=10)

        self.canvas = tk.Canvas(self.root, width=SQUARE_SIZE*8, height=SQUARE_SIZE*8)
        self.canvas.pack()
        self.images = {}
        self._load_images()
        self._draw_board()
        self.canvas.bind("<Button-1>", self._on_click)
        self.selected_square = None

        btn = tk.Frame(self.root, bg="#f0f0f0")
        btn.pack(pady=5)
        self.btn_start = tk.Button(btn, text="AI 대결 시작", command=self._start_ai_vs_ai)
        self.btn_start.pack(side=tk.LEFT, padx=5)

        self.btn_reset = tk.Button(btn, text="리셋", command=self._reset_game, bg="#fff9c4", width=12)
        self.btn_reset.pack(side=tk.LEFT, padx=5)

        self._status_var = tk.StringVar(value="초기화 중...")
        tk.Label(self.root, textvariable=self._status_var,
                 bg="#222", fg="#aaffaa", font=("Consolas", 9),
                 anchor="w", padx=8).pack(fill=tk.X, side=tk.BOTTOM)

        # ── GUI 완전히 뜬 뒤 도봇 초기화 ───────────────────
        self.robot = RobotBridge()
        self.root.after(2000, self._refresh_robot_status)

    def _refresh_robot_status(self) -> None:
        if self.robot.is_ready:
            self._status_var.set("🤖 도봇 연결됨 — 준비 완료")
            self._robot_badge.config(text="🤖 도봇 연결됨", fg="#2e7d32")
        else:
            self._status_var.set("🤖 더미 모드 — 도봇 미연결")
            self._robot_badge.config(text="🤖 더미 모드", fg="#888888")
        self.root.after(5000, self._refresh_robot_status)

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

    def _load_images(self):
        for char, name in PIECE_SYMBOLS.items():
            try:
                img = Image.open(f"images/{name}.png")
                self.images[char] = ImageTk.PhotoImage(
                    img.resize((SQUARE_SIZE, SQUARE_SIZE), Image.Resampling.LANCZOS))
            except Exception as e:
                print(f"이미지 로드 실패: {name}.png — {e}")

    def _draw_board(self):
        self.canvas.delete("all")
        colors = ["#eeeed2", "#769656"]
        for r in range(8):
            for c in range(8):
                x1, y1 = c*SQUARE_SIZE, r*SQUARE_SIZE
                self.canvas.create_rectangle(
                    x1, y1, x1+SQUARE_SIZE, y1+SQUARE_SIZE,
                    fill=colors[(r+c)%2], outline="")
        for sq in chess.SQUARES:
            piece = self.board.piece_at(sq)
            if piece and piece.symbol() in self.images:
                col = chess.square_file(sq)
                row = 7 - chess.square_rank(sq)
                self.canvas.create_image(
                    col*SQUARE_SIZE + SQUARE_SIZE//2,
                    row*SQUARE_SIZE + SQUARE_SIZE//2,
                    image=self.images[piece.symbol()])

    def _on_click(self, event):
        if not self.is_running or self._robot_busy:
            return
        col    = event.x // SQUARE_SIZE
        row    = 7 - (event.y // SQUARE_SIZE)
        square = chess.square(col, row)
        if self.selected_square is None:
            if self.board.piece_at(square):
                self.selected_square = square
        else:
            move = chess.Move(self.selected_square, square)
            if move in self.board.legal_moves:
                self._execute_move_with_robot(move)
            self.selected_square = None

    def _execute_move_with_robot(self, move: chess.Move):
        if self._robot_busy:
            return
        self._robot_busy = True
        pre_board = self.board.copy()
        self.board.push(move)
        self._draw_board()
        self._status_var.set(
            f"도봇 이동 중: {move.uci()[:2].upper()} → {move.uci()[2:].upper()}")

        def on_done():
            self._robot_busy = False
            self.root.after(0, lambda: self._status_var.set("이동 완료"))

        self.robot.execute_async(pre_board, move, on_done=on_done)
    
    def _reset_game(self):
        self.is_running = False
        self._robot_busy = True
        self._status_var.set("리셋 중 — 정지 중...")
        self.board.reset()
        self.selected_square = None
        self._draw_board()

        # 리셋 완료 전까지 버튼 비활성화
        self.btn_reset.config(state="disabled")
        self.btn_start.config(state="disabled")

        def _stop_then_ready():
            self.robot.emergency_stop()
            self._robot_busy = False
            self.is_running = True
            self.root.after(0, lambda: [
                self.btn_reset.config(state="normal"),
                self.btn_start.config(state="normal"),
                self._status_var.set("리셋 완료 — AI 대결 시작을 누르세요"),
            ])

        threading.Thread(target=_stop_then_ready, daemon=True).start()

    def _start_ai_vs_ai(self):
        if self._robot_busy:
            messagebox.showwarning("도봇 이동 중", "현재 도봇이 동작 중입니다.")
            return
        if self.board.is_game_over():
            self.board.reset()
            self._draw_board()
        self._play_auto_move()

    def _play_auto_move(self):
        if not self.is_running or self.board.is_game_over():
            if self.is_running and self.board.is_game_over():
                self._handle_end_game()
            return
        if self._robot_busy:
            self.root.after(200, self._play_auto_move)
            return
        try:
            result = self.engine.play(self.board, chess.engine.Limit(time=0.5))
            if not result.move:
                return
            move     = result.move
            turn_str = "백" if self.board.turn == chess.WHITE else "흑"
            self._status_var.set(
                f"AI({turn_str}): {move.uci()[:2].upper()} → {move.uci()[2:].upper()} — 도봇 이동 중...")
            self._robot_busy = True
            pre_board = self.board.copy()
            self.board.push(move)
            self._draw_board()

            def on_done():
                self._robot_busy = False
                if self.is_running:
                    self.root.after(1500, self._play_auto_move)

            self.robot.execute_async(pre_board, move, on_done=on_done)
        except (chess.engine.EngineTerminatedError, RuntimeError):
            pass

    def _handle_end_game(self):
        if not self.board.is_game_over():
            return
        res = self.board.result()
        if res == "1/2-1/2":
            self.board.reset()
            self._draw_board()
            self.root.after(500, self._play_auto_move)
        else:
            messagebox.showinfo("게임 종료",
                                "백색 승리!" if res == "1-0" else "흑색 승리!")

    def on_closing(self):
        self.is_running = False
        self.robot.quit()
        safe_quit(self.engine)
        self.root.destroy()
        sys.exit()


if __name__ == "__main__":
    root = tk.Tk()
    app  = AutoChessGUI(root)
    root.mainloop()