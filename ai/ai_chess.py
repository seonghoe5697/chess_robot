"""
ai_chess.py  ―  AI vs AI 자동 대국 GUI
core/ 패키지로 공통 로직을 분리한 버전
"""

import sys
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import chess
import chess.engine

from core import create_engine, safe_quit, PIECE_SYMBOLS

SQUARE_SIZE = 60


class AutoChessGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("또봇 체스 ― AI 자동 대국")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.board = chess.Board()
        self.is_running = True

        try:
            self.engine = create_engine(elo=2850)
        except (FileNotFoundError, RuntimeError) as e:
            messagebox.showerror("엔진 오류", str(e))
            sys.exit()

        self.canvas = tk.Canvas(self.root, width=SQUARE_SIZE * 8, height=SQUARE_SIZE * 8)
        self.canvas.pack()

        self.images = {}
        self._load_images()
        self._draw_board()

        self.canvas.bind("<Button-1>", self._on_click)
        self.selected_square = None

        self.start_btn = tk.Button(self.root, text="AI 대결 시작", command=self._start_ai_vs_ai)
        self.start_btn.pack()

    def _load_images(self):
        for char, name in PIECE_SYMBOLS.items():
            try:
                img = Image.open(f"images/{name}.png")
                img = img.resize((SQUARE_SIZE, SQUARE_SIZE), Image.Resampling.LANCZOS)
                self.images[char] = ImageTk.PhotoImage(img)
            except Exception as e:
                print(f"이미지 로드 실패: {name}.png ― {e}")

    def _draw_board(self):
        self.canvas.delete("all")
        colors = ["#eeeed2", "#769656"]
        for r in range(8):
            for c in range(8):
                color = colors[(r + c) % 2]
                x1, y1 = c * SQUARE_SIZE, r * SQUARE_SIZE
                self.canvas.create_rectangle(x1, y1, x1 + SQUARE_SIZE, y1 + SQUARE_SIZE, fill=color, outline="")

        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece and piece.symbol() in self.images:
                col = chess.square_file(square)
                row = 7 - chess.square_rank(square)
                self.canvas.create_image(
                    col * SQUARE_SIZE + SQUARE_SIZE // 2,
                    row * SQUARE_SIZE + SQUARE_SIZE // 2,
                    image=self.images[piece.symbol()],
                )

    def _on_click(self, event):
        if not self.is_running:
            return
        col = event.x // SQUARE_SIZE
        row = 7 - (event.y // SQUARE_SIZE)
        square = chess.square(col, row)
        if self.selected_square is None:
            if self.board.piece_at(square):
                self.selected_square = square
        else:
            move = chess.Move(self.selected_square, square)
            if move in self.board.legal_moves:
                self.board.push(move)
                self._draw_board()
                self.root.after(500, self._engine_move)
            self.selected_square = None

    def _engine_move(self):
        if self.is_running and not self.board.is_game_over():
            try:
                result = self.engine.play(self.board, chess.engine.Limit(time=0.1))
                self.board.push(result.move)
                self._draw_board()
                self._handle_end_game()
            except chess.engine.EngineTerminatedError:
                pass

    def _start_ai_vs_ai(self):
        if self.board.is_game_over():
            self.board.reset()
            self._draw_board()
        self._play_auto_move()

    def _play_auto_move(self):
        if not self.is_running or self.board.is_game_over():
            if self.is_running and self.board.is_game_over():
                self._handle_end_game()
            return
        try:
            result = self.engine.play(self.board, chess.engine.Limit(time=0.05))
            if result.move:
                self.board.push(result.move)
                self._draw_board()
                self.root.after(300, self._play_auto_move)
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
            winner = "백색 승리!" if res == "1-0" else "흑색 승리!"
            messagebox.showinfo("게임 종료", f"결과: {winner}")

    def on_closing(self):
        self.is_running = False
        safe_quit(self.engine)
        self.root.destroy()
        sys.exit()


if __name__ == "__main__":
    root = tk.Tk()
    app = AutoChessGUI(root)
    root.mainloop()
