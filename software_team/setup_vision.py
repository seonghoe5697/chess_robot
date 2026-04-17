"""
setup_vision.py  ―  Tkinter 기반 비전 최초 설정

chess_robot_gui.py의 캘리브 방식 차용:
  - 카메라 프레임을 Tkinter Canvas에 띄우고 클릭으로 4코너 입력
    (OpenCV Qt 백엔드 문제 회피)
  - 도봇 실측 입력 불필요 — config.py의 square_to_mm_for로 mm 자동 계산

생성 파일:
  - board_corners.json       (vision.py의 _warp용)
  - vision_robot_calib.json  (VisionRobotCalib용)
"""

import sys
import json
from pathlib import Path

# hardware_team config.py 참조
_HW_DIR = Path(__file__).resolve().parent.parent / "hardware_team"
if str(_HW_DIR) not in sys.path:
    sys.path.insert(0, str(_HW_DIR))

import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import numpy as np
import cv2

from vision import _open_camera_with_fallback, CORNERS_PATH
from vision_coord import VisionRobotCalib, CALIB_SAVE_PATH
from dual_dobot_controller import square_to_mm_for, Robot


# 클릭 순서 — vision.py의 _warp 순서(좌상→우상→우하→좌하)와 일치
SQUARES = ["a8", "h8", "h1", "a1"]
LABELS  = ["a8 (좌상)", "h8 (우상)", "h1 (우하)", "a1 (좌하)"]


# ═════════════════════════════════════════════════════════════
def main():
    print("=" * 60)
    print("  비전 최초 설정")
    print("=" * 60)

    # ── 카메라 프레임 캡처 ───────────────────────────────
    print("\n[1/2] 카메라에서 1프레임 캡처")
    print("-" * 60)

    cap, used = _open_camera_with_fallback()
    if cap is None:
        print("✗ 카메라 연결 실패 — Pi 서버 또는 로컬 카메라 확인")
        return
    print(f"  카메라 소스: {used}")

    frame = None
    for _ in range(10):      # 초기 프레임 몇 장 버리고 안정화
        ok, f = cap.read()
        if ok:
            frame = f
    cap.release()
    if frame is None:
        print("✗ 프레임 읽기 실패")
        return

    orig_h, orig_w = frame.shape[:2]
    print(f"  해상도: {orig_w}×{orig_h}")

    # ── Tkinter 창으로 4코너 클릭 ─────────────────────────
    print(f"\n[2/2] Tkinter 창에서 4코너 클릭")
    print(f"  순서: {' → '.join(LABELS)}")
    print(f"  각 칸의 중심을 정확히 클릭하세요.\n")

    _run_calib_window(frame, orig_w, orig_h)


# ═════════════════════════════════════════════════════════════
def _run_calib_window(frame, orig_w, orig_h):
    root = tk.Tk()
    root.title("체스판 캘리브레이션 — 4코너 클릭")
    root.configure(bg="#1f2328")

    # 디스플레이 크기 — 원본보다 작으면 축소, 크면 원본
    DISP_W = min(1100, orig_w)
    DISP_H = int(DISP_W * orig_h / orig_w)
    scale_x = orig_w / DISP_W
    scale_y = orig_h / DISP_H

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    img = Image.fromarray(rgb).resize((DISP_W, DISP_H), Image.LANCZOS)
    imgtk = ImageTk.PhotoImage(image=img)

    guide_var = tk.StringVar(value=f"① 클릭: {LABELS[0]}  (0/4)")
    tk.Label(root, textvariable=guide_var, font=("Arial", 14, "bold"),
             bg="#1f2328", fg="#3fb950").pack(pady=6)

    canvas = tk.Canvas(root, width=DISP_W, height=DISP_H,
                       bg="#111", highlightthickness=0, cursor="crosshair")
    canvas.pack(padx=10, pady=4)
    canvas.create_image(0, 0, anchor="nw", image=imgtk)
    canvas.imgtk = imgtk                               # 참조 유지

    btn_row = tk.Frame(root, bg="#1f2328")
    btn_row.pack(fill="x", padx=10, pady=8)

    points = []                                         # 원본 해상도 기준 (px, py)
    COLORS = ["#00ff88", "#ffdd00", "#ff6688", "#44bbff"]

    def redraw():
        canvas.delete("marker")
        for i, (px, py) in enumerate(points):
            dx, dy = px / scale_x, py / scale_y
            canvas.create_oval(dx-10, dy-10, dx+10, dy+10,
                               outline=COLORS[i], width=3, tags="marker")
            canvas.create_text(dx+14, dy-12, text=LABELS[i],
                               fill=COLORS[i],
                               font=("Consolas", 11, "bold"),
                               anchor="w", tags="marker")
        if len(points) >= 2:
            for i in range(len(points) - 1):
                x1, y1 = points[i][0]/scale_x,   points[i][1]/scale_y
                x2, y2 = points[i+1][0]/scale_x, points[i+1][1]/scale_y
                canvas.create_line(x1, y1, x2, y2,
                                   fill="#66ff66", width=2, tags="marker")
            if len(points) == 4:
                x1, y1 = points[3][0]/scale_x, points[3][1]/scale_y
                x2, y2 = points[0][0]/scale_x, points[0][1]/scale_y
                canvas.create_line(x1, y1, x2, y2,
                                   fill="#66ff66", width=2, tags="marker")

    def update_guide():
        n = len(points)
        if n < 4:
            guide_var.set(f"{'①②③④'[n]} 클릭: {LABELS[n]}  ({n}/4)")
        else:
            guide_var.set("4점 완료 — 저장하거나 되돌리기")

    def on_click(event):
        if len(points) >= 4:
            return
        points.append((event.x * scale_x, event.y * scale_y))
        redraw(); update_guide()

    def on_undo():
        if points:
            points.pop(); redraw(); update_guide()

    def on_reset():
        points.clear(); redraw(); update_guide()

    def on_save():
        if len(points) != 4:
            messagebox.showwarning("경고", "4점을 모두 클릭하세요")
            return
        root.destroy()
        _do_save(points)

    def on_cancel():
        print("취소됨")
        points.clear()
        root.destroy()

    canvas.bind("<Button-1>", on_click)

    tk.Button(btn_row, text="↩ 되돌리기", command=on_undo,
              bg="#444", fg="#fff", width=12,
              relief="flat").pack(side="left", padx=4, ipady=4)
    tk.Button(btn_row, text="🔄 리셋", command=on_reset,
              bg="#555", fg="#fff", width=12,
              relief="flat").pack(side="left", padx=4, ipady=4)
    tk.Button(btn_row, text="✗ 취소", command=on_cancel,
              bg="#8b1a1a", fg="#fff", width=12,
              relief="flat").pack(side="right", padx=4, ipady=4)
    tk.Button(btn_row, text="✓ 저장", command=on_save,
              bg="#238636", fg="#fff", width=12,
              relief="flat",
              font=("Arial", 10, "bold")).pack(side="right", padx=4, ipady=4)

    root.protocol("WM_DELETE_WINDOW", on_cancel)
    root.mainloop()


# ═════════════════════════════════════════════════════════════
def _do_save(points):
    if len(points) != 4:
        return

    # ── board_corners.json ──────────────────────────────
    Path(CORNERS_PATH).write_text(
        json.dumps(
            {"corners": [[round(p[0], 1), round(p[1], 1)] for p in points]},
            indent=2,
        )
    )
    print(f"✓ 저장: {CORNERS_PATH}")

    # ── vision_robot_calib.json ─────────────────────────
    # mm은 square_to_mm_for(Robot.A, <square>)로 자동 계산
    try:
        pixel_pts = [tuple(p) for p in points]
        mm_pts    = [tuple(square_to_mm_for(Robot.A, sq)) for sq in SQUARES]

        print("\n  mm 자동 계산 (square_to_mm_for):")
        for sq, mm in zip(SQUARES, mm_pts):
            print(f"    {sq}: ({mm[0]:+.1f}, {mm[1]:+.1f})")

        calib = VisionRobotCalib()
        calib.calibrate(pixel_pts, mm_pts, robot_label="A")
        print(f"\n✓ 저장: {CALIB_SAVE_PATH}")

        # 역변환 검증
        print("\n[검증] 4코너 역변환 오차:")
        for sq, pp, mp in zip(SQUARES, pixel_pts, mm_pts):
            rx, ry = calib.pixel_to_mm(*pp)
            err = (abs(rx - mp[0]), abs(ry - mp[1]))
            print(f"  {sq}: 예상({mp[0]:+.1f},{mp[1]:+.1f}) "
                  f"역산({rx:+.1f},{ry:+.1f}) 오차({err[0]:.2f},{err[1]:.2f})mm")

    except Exception as e:
        print(f"✗ 캘리브 저장 오류: {e}")
        return

    print()
    print("=" * 60)
    print("  설정 완료")
    print("=" * 60)
    print("이제 ai_human_chess.py / ai_chess.py 실행 시")
    print("RobotBridge가 자동으로 '비전 ON' 모드로 동작합니다.\n")


# ═════════════════════════════════════════════════════════════
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n중단")
        sys.exit(1)