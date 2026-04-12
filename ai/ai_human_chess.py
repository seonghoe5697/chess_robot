"""
ai_human_chess.py  ―  사람 vs AI GUI
core/ 패키지로 공통 로직을 분리한 버전
"""

import sys
import math
import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import chess
import chess.engine

from core import create_engine, safe_quit, PIECE_SYMBOLS, PIECE_VALUES

SQUARE_SIZE = 60


class HumanVsAIChessGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("또봇 체스 ― 사람 vs AI")

        self.board = chess.Board()
        self.images = {}
        self.small_images = {}
        self.selected_square = None
        self.is_ai_thinking = False
        self.game_over = False
        self.engine = None
        self.hint_move = None
        self.evaluation = 0.5
        self.player_color = chess.WHITE

        try:
            self.engine = create_engine(elo=1350)
        except (FileNotFoundError, RuntimeError) as e:
            messagebox.showerror("엔진 오류", str(e))
            self.root.destroy()
            return

        self._load_images()
        self._setup_ui()
        self.root.after(100, self._choose_side)

    # ── 이미지 ────────────────────────────────────────────────────────────

    def _load_images(self):
        for char, name in PIECE_SYMBOLS.items():
            img = Image.open(f"images/{name}.png")
            self.images[char] = ImageTk.PhotoImage(img.resize((SQUARE_SIZE, SQUARE_SIZE), Image.Resampling.LANCZOS))
            self.small_images[char] = ImageTk.PhotoImage(img.resize((25, 25), Image.Resampling.LANCZOS))

    # ── UI 구성 ───────────────────────────────────────────────────────────

    def _setup_ui(self):
        self.top_frame = tk.Frame(self.root, bg="#f0f0f0", pady=10)
        self.top_frame.pack(fill=tk.X, padx=10)

        diff_frame = tk.Frame(self.top_frame, bg="#f0f0f0")
        diff_frame.pack(fill=tk.X)
        tk.Label(diff_frame, text="AI 난이도:", bg="#f0f0f0", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.difficulty_scale = tk.Scale(
            diff_frame, from_=1350, to_=2850, orient=tk.HORIZONTAL,
            length=150, command=self._on_difficulty_change, bg="#f0f0f0", highlightthickness=0
        )
        self.difficulty_scale.set(1350)
        self.difficulty_scale.pack(side=tk.LEFT, padx=10)
        self.diff_label = tk.Label(diff_frame, text="초급자", fg="#2e7d32", bg="#f0f0f0")
        self.diff_label.pack(side=tk.LEFT)

        self.captured_frame = tk.Frame(self.top_frame, bg="#f0f0f0", pady=5)
        self.captured_frame.pack(fill=tk.X)
        self.captured_icons_label = tk.Label(self.captured_frame, bg="#f0f0f0")
        self.captured_icons_label.pack(side=tk.LEFT)
        self.material_score_label = tk.Label(self.captured_frame, text="기물 균형: 0", bg="#f0f0f0", font=("Arial", 10, "bold"))
        self.material_score_label.pack(side=tk.RIGHT, padx=10)

        main_frame = tk.Frame(self.root)
        main_frame.pack(pady=5, padx=10)
        self.canvas = tk.Canvas(main_frame, width=SQUARE_SIZE * 8, height=SQUARE_SIZE * 8)
        self.canvas.pack(side=tk.LEFT)
        self.canvas.bind("<Button-1>", self._on_click)

        btn_frame = tk.Frame(self.root, pady=10)
        btn_frame.pack()
        tk.Button(btn_frame, text="힌트 보기",  command=self._show_hint,        bg="#e1f5fe", width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="무르기",     command=self._undo_move,         bg="#fff9c4", width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="기권",       command=self._resign,            bg="#ffcdd2", width=10).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="리셋/진영",  command=self._reset_with_choice, width=10).pack(side=tk.LEFT, padx=5)

    # ── 설정 ──────────────────────────────────────────────────────────────

    def _on_difficulty_change(self, val):
        elo = int(val)
        if self.engine:
            self.engine.configure({"UCI_LimitStrength": True, "UCI_Elo": elo})
        if elo < 1800:
            self.diff_label.config(text="초급자", fg="#2e7d32")
        elif elo < 2300:
            self.diff_label.config(text="중급자", fg="#1565c0")
        else:
            self.diff_label.config(text="고수", fg="#c62828")

    def _choose_side(self):
        choice = messagebox.askyesno("진영 선택", "백색(White)으로 시작하시겠습니까?\n(아니오 클릭 시 흑색으로 시작)")
        self.player_color = chess.WHITE if choice else chess.BLACK
        self.board.reset()
        self.game_over = False
        self.selected_square = None
        self.hint_move = None
        self.evaluation = 0.5

        if self.player_color == chess.BLACK:
            self.is_ai_thinking = True
            self.root.after(500, self._engine_move)

        self._draw_all()

    # ── 그리기 ────────────────────────────────────────────────────────────

    def _draw_board(self):
        self.canvas.delete("all")
        colors = ["#eeeed2", "#769656"]
        last_move = self.board.peek() if self.board.move_stack else None
        is_check = self.board.is_check()
        king_sq = self.board.king(self.board.turn)

        for r in range(8):
            for c in range(8):
                disp_c = c if self.player_color == chess.WHITE else 7 - c
                disp_r = r if self.player_color == chess.WHITE else 7 - r
                square = chess.square(disp_c, 7 - disp_r)

                color = colors[(r + c) % 2]
                if last_move and square in (last_move.from_square, last_move.to_square):
                    color = "#ced26b"
                if self.selected_square == square:
                    color = "#f7f769"
                elif is_check and square == king_sq:
                    color = "#ff8a80"

                x1, y1 = c * SQUARE_SIZE, r * SQUARE_SIZE
                x2, y2 = x1 + SQUARE_SIZE, y1 + SQUARE_SIZE
                self.canvas.create_rectangle(x1, y1, x2, y2, fill=color, outline="")

                if self.selected_square is not None and not self.game_over:
                    legal_dests = [m.to_square for m in self.board.legal_moves if m.from_square == self.selected_square]
                    if square in legal_dests:
                        m = SQUARE_SIZE * 0.35
                        self.canvas.create_oval(x1 + m, y1 + m, x2 - m, y2 - m, fill="#2e7d32", stipple="gray50", outline="")

        if self.hint_move:
            self._draw_hint_arrow(self.hint_move)

        for square in chess.SQUARES:
            piece = self.board.piece_at(square)
            if piece:
                f = chess.square_file(square)
                r_idx = chess.square_rank(square)
                c_pos = f if self.player_color == chess.WHITE else 7 - f
                r_pos = 7 - r_idx if self.player_color == chess.WHITE else r_idx
                self.canvas.create_image(
                    c_pos * SQUARE_SIZE + SQUARE_SIZE // 2,
                    r_pos * SQUARE_SIZE + SQUARE_SIZE // 2,
                    image=self.images[piece.symbol()]
                )

    def _draw_hint_arrow(self, move):
        def screen_pos(sq):
            f, r = chess.square_file(sq), chess.square_rank(sq)
            c = f if self.player_color == chess.WHITE else 7 - f
            rr = 7 - r if self.player_color == chess.WHITE else r
            return c * SQUARE_SIZE + SQUARE_SIZE // 2, rr * SQUARE_SIZE + SQUARE_SIZE // 2
        x1, y1 = screen_pos(move.from_square)
        x2, y2 = screen_pos(move.to_square)
        self.canvas.create_line(x1, y1, x2, y2, fill="#0288d1", width=6, arrow=tk.LAST)

    def _draw_all(self):
        self._draw_board()
        self._update_material_info()

    # ── 클릭 ──────────────────────────────────────────────────────────────

    def _on_click(self, event):
        if self.game_over or self.is_ai_thinking or self.board.is_game_over():
            return

        c_raw, r_raw = event.x // SQUARE_SIZE, event.y // SQUARE_SIZE
        file_idx = c_raw if self.player_color == chess.WHITE else 7 - c_raw
        rank_idx = 7 - r_raw if self.player_color == chess.WHITE else r_raw

        if not (0 <= file_idx <= 7 and 0 <= rank_idx <= 7):
            return
        square = chess.square(file_idx, rank_idx)
        piece = self.board.piece_at(square)

        if self.selected_square is None:
            if piece and piece.color == self.player_color:
                self.selected_square = square
        else:
            move = next((m for m in self.board.legal_moves
                         if m.from_square == self.selected_square and m.to_square == square), None)
            if move:
                self.board.push(move)
                self.selected_square = None
                self.hint_move = None
                self._update_evaluation()
                self._draw_all()
                if not self.board.is_game_over():
                    self.is_ai_thinking = True
                    self.root.after(100, self._engine_move)
            else:
                self.selected_square = square if (piece and piece.color == self.player_color) else None
        self._draw_all()

    # ── 엔진 수 ───────────────────────────────────────────────────────────

    def _engine_move(self):
        if self.game_over:
            return

        info = self.engine.analyse(self.board, chess.engine.Limit(time=0.6))
        score_obj = info["score"].pov(self.board.turn)
        score = score_obj.score()
        mate_in = score_obj.mate()

        if (score is not None and score <= -600) or (mate_in is not None and mate_in < 0):
            self.game_over = True
            self._show_game_result("AI가 항복을 선언했습니다. 당신의 승리입니다!")
            self.is_ai_thinking = False
            return

        result = self.engine.play(self.board, chess.engine.Limit(time=0.7))
        if result.move:
            self.board.push(result.move)
            self._update_evaluation()
            self._draw_all()

        self.is_ai_thinking = False
        if self.board.is_game_over():
            self.game_over = True
            self._show_game_result()

    # ── 버튼 기능 ─────────────────────────────────────────────────────────

    def _show_hint(self):
        if self.game_over or self.is_ai_thinking or self.board.is_game_over():
            return
        res = self.engine.play(self.board, chess.engine.Limit(time=0.5))
        if res.move:
            self.hint_move = res.move
            self._draw_all()

    def _undo_move(self):
        if not self.game_over and not self.is_ai_thinking and len(self.board.move_stack) >= 2:
            self.board.pop()
            self.board.pop()
            self.hint_move = None
            self._update_evaluation()
            self._draw_all()

    def _resign(self):
        if self.game_over or self.board.is_game_over():
            return
        if messagebox.askyesno("기권", "정말로 항복하시겠습니까?"):
            self.game_over = True
            self._show_game_result("사용자가 항복하였습니다. AI 승리!")

    def _reset_with_choice(self):
        self._choose_side()

    def _show_game_result(self, custom_msg=None):
        if custom_msg:
            msg = custom_msg
        else:
            res = self.board.result()
            mapping = {"1-0": "백색 승리!", "0-1": "흑색 승리!", "1/2-1/2": "무승부"}
            msg = f"게임 종료: {mapping.get(res, res)}"
        messagebox.showinfo("결과", msg)

    # ── 정보 업데이트 ─────────────────────────────────────────────────────

    def _update_material_info(self):
        white_val = sum(PIECE_VALUES[p.piece_type] for p in self.board.piece_map().values() if p.color == chess.WHITE)
        black_val = sum(PIECE_VALUES[p.piece_type] for p in self.board.piece_map().values() if p.color == chess.BLACK)

        for w in self.captured_icons_label.winfo_children():
            w.destroy()

        opp_color = chess.BLACK if self.player_color == chess.WHITE else chess.WHITE
        opp_pieces = ['p','n','b','r','q'] if opp_color == chess.BLACK else ['P','N','B','R','Q']
        starting = {'p':8,'n':2,'b':2,'r':2,'q':1,'P':8,'N':2,'B':2,'R':2,'Q':1}
        for s in opp_pieces:
            count = len(self.board.pieces(chess.Piece.from_symbol(s).piece_type, opp_color))
            for _ in range(starting[s] - count):
                tk.Label(self.captured_icons_label, image=self.small_images[s], bg="#f0f0f0").pack(side=tk.LEFT)

        diff = white_val - black_val
        if self.player_color == chess.BLACK:
            diff = -diff
        self.material_score_label.config(text=f"기물 균형: {'+' if diff > 0 else ''}{diff}")

    def _update_evaluation(self):
        try:
            info = self.engine.analyse(self.board, chess.engine.Limit(time=0.1))
            score = info["score"].white().score()
            if score is None:
                self.evaluation = 1.0 if info["score"].white().mate() > 0 else 0.0
            else:
                self.evaluation = 1 / (1 + math.exp(-score / 300))
        except:
            pass

    # ── 종료 ──────────────────────────────────────────────────────────────

    def on_closing(self):
        safe_quit(self.engine)
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = HumanVsAIChessGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
