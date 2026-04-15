"""
Tobot Chess Integrated Launcher
--------------------------------
하나의 UI에서 소프트웨어팀 / 하드웨어팀 / 라즈베리파이팀 실행물을 관리하는 통합 런처.

폴더 구조:
    project/
    ├── main_launcher.py        ← 이 파일
    ├── software_team/
    │   ├── ai_human_chess.py   (도봇 연동 버전)
    │   ├── ai_chess.py         (도봇 연동 버전)
    │   ├── robot_bridge.py     (hardware_team 자동 참조)
    │   ├── app.py
    │   └── core/ ...
    ├── hardware_team/
    │   ├── dual_dobot_controller.py
    │   ├── config.py
    │   └── ...
    └── raspi_team/
        └── server.py           (라즈베리파이에서 직접 실행)

실행:
    python main_launcher.py

주의:
- sw_human / sw_auto 는 software_team/ 에서 실행되며
  robot_bridge.py 가 hardware_team/ 을 자동으로 sys.path 에 추가합니다.
- 도봇 없이 테스트할 때: software_team/robot_bridge.py 의 ROBOT_ENABLED = False
- Pi 서버(server.py)는 라즈베리파이에서 직접 실행하세요. (IP: 192.168.0.133)
"""

from __future__ import annotations

import os
import sys
import signal
import subprocess
import threading
import time
import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

ROOT   = Path(__file__).resolve().parent
PYTHON = sys.executable

SW_DIR = ROOT / "software_team"
HW_DIR = ROOT / "hardware_team"
PI_DIR = ROOT / "raspi_team"

PI_HOST = "http://192.168.0.133:8000"

BG    = "#1f2328"
CARD  = "#2b3138"
FG    = "#e6edf3"
MUTED = "#9aa4ad"
OK    = "#3fb950"
WARN  = "#d29922"
ERR   = "#f85149"
ACC   = "#58a6ff"


@dataclass
class ManagedProcess:
    name:    str
    command: list[str]
    cwd:     Path
    proc:    subprocess.Popen | None = None

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        if self.is_running():
            return
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("QT_QPA_PLATFORM",  "xcb")
        self.proc = subprocess.Popen(
            self.command,
            cwd=str(self.cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

    def stop(self) -> None:
        if not self.is_running():
            return
        assert self.proc is not None
        try:
            if os.name == "nt":
                self.proc.terminate()
            else:
                self.proc.send_signal(signal.SIGTERM)
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


class LauncherApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Tobot Chess 통합 런처")
        self.root.geometry("980x760")
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.processes: dict[str, ManagedProcess] = {
            "sw_streamlit": ManagedProcess(
                "SW 분석기 (Streamlit)",
                [PYTHON, "-m", "streamlit", "run", "app.py"],
                SW_DIR,
            ),
            "sw_human": ManagedProcess(
                "사람 vs AI + 도봇",
                [PYTHON, "ai_human_chess.py"],
                SW_DIR,   # software_team/ 에서 실행 → robot_bridge가 hw 경로 자동 추가
            ),
            "sw_auto": ManagedProcess(
                "AI vs AI + 도봇",
                [PYTHON, "ai_chess.py"],
                SW_DIR,
            ),
            "hw_gui": ManagedProcess(
                "HW 도봇 전용 GUI",
                [PYTHON, "chess_robot_gui.py"],
                HW_DIR,
            ),
        }

        self.status_labels: dict[str, tk.Label] = {}
        self.log_text:      tk.Text | None       = None
        self.pi_state_var = tk.StringVar(value="Pi 상태: 확인 전")

        self._build_ui()
        self._start_monitors()

    # ── UI ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(header, text="Tobot Chess 통합 실행 UI",
                 bg=BG, fg=FG, font=("Arial", 20, "bold")).pack(anchor="w")
        tk.Label(header,
                 text="소프트웨어(도봇 연동) · 하드웨어 GUI · 라즈베리파이 브릿지를 한 곳에서 관리합니다.",
                 bg=BG, fg=MUTED, font=("Arial", 10)).pack(anchor="w", pady=(2, 0))

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=16, pady=8)
        self.tab_control = tk.Frame(notebook, bg=BG)
        self.tab_log     = tk.Frame(notebook, bg=BG)
        notebook.add(self.tab_control, text="실행 제어")
        notebook.add(self.tab_log,     text="통합 로그")

        self._build_control_tab()
        self._build_log_tab()

        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", padx=16, pady=(0, 12))
        tk.Button(footer, text="전체 실행", command=self.start_all,
                  bg="#1f6feb", fg="white", relief="flat",
                  padx=16, pady=8).pack(side="left", padx=(0, 8))
        tk.Button(footer, text="전체 중지", command=self.stop_all,
                  bg="#8b1a1a", fg="white", relief="flat",
                  padx=16, pady=8).pack(side="left")
        tk.Label(footer, textvariable=self.pi_state_var,
                 bg=BG, fg=MUTED, font=("Consolas", 10)).pack(side="right")

    def _build_control_tab(self) -> None:
        sections = [
            (
                "소프트웨어 팀  —  도봇 자동 연동",
                [
                    ("sw_streamlit", "이미지 업로드 → CNN → FEN → Stockfish 추천 (웹 UI)"),
                    ("sw_human",     "사람 vs AI GUI  |  수 결정 시 도봇이 실제로 말을 움직임"),
                    ("sw_auto",      "AI vs AI 자동 대국  |  모든 수를 도봇이 자동 구동"),
                ],
            ),
            (
                "하드웨어 팀  —  도봇 전용 제어 GUI (선택 사용)",
                [
                    ("hw_gui", "도봇 2대 직접 제어 · 카메라 보드 스캔 · 수동 승인 실행"),
                ],
            ),
        ]

        for title, items in sections:
            box = tk.Frame(self.tab_control, bg=CARD, padx=12, pady=10)
            box.pack(fill="x", padx=4, pady=8)
            tk.Label(box, text=title, bg=CARD, fg=FG,
                     font=("Arial", 13, "bold")).pack(anchor="w", pady=(0, 4))
            for key, desc in items:
                row = tk.Frame(box, bg=CARD)
                row.pack(fill="x", pady=5)
                tk.Label(row, text=self.processes[key].name,
                         bg=CARD, fg=FG, width=22, anchor="w",
                         font=("Arial", 10, "bold")).pack(side="left")
                tk.Label(row, text=desc, bg=CARD, fg=MUTED,
                         anchor="w").pack(side="left", fill="x", expand=True)
                status = tk.Label(row, text="중지", bg=CARD, fg=WARN, width=8)
                status.pack(side="left", padx=8)
                self.status_labels[key] = status
                tk.Button(row, text="실행",
                          command=lambda k=key: self.start_process(k),
                          bg="#238636", fg="white", relief="flat",
                          width=8).pack(side="left", padx=2)
                tk.Button(row, text="중지",
                          command=lambda k=key: self.stop_process(k),
                          bg="#6e1111", fg="white", relief="flat",
                          width=8).pack(side="left", padx=2)

        # 라즈베리파이 상태 카드 (버튼 없음)
        pi_box = tk.Frame(self.tab_control, bg=CARD, padx=12, pady=10)
        pi_box.pack(fill="x", padx=4, pady=8)
        tk.Label(pi_box, text="라즈베리파이 팀  —  Pi에서 직접 실행",
                 bg=CARD, fg=FG, font=("Arial", 13, "bold")).pack(anchor="w", pady=(0, 4))
        pi_row = tk.Frame(pi_box, bg=CARD)
        pi_row.pack(fill="x", pady=5)
        tk.Label(pi_row, text="Pi 카메라 서버",
                 bg=CARD, fg=FG, width=22, anchor="w",
                 font=("Arial", 10, "bold")).pack(side="left")
        tk.Label(pi_row, text=f"라즈베리파이에서 직접 실행 | {PI_HOST}",
                 bg=CARD, fg=MUTED, anchor="w").pack(side="left", fill="x", expand=True)
        self.pi_conn_label = tk.Label(pi_row, text="확인 중",
                                      bg=CARD, fg=WARN, width=8)
        self.pi_conn_label.pack(side="left", padx=8)

        info = tk.Frame(self.tab_control, bg=BG)
        info.pack(fill="x", padx=4, pady=(8, 0))
        tk.Label(
            info,
            text=(
                "• sw_human / sw_auto 는 software_team/ 에서 실행되며, "
                "robot_bridge.py 가 hardware_team/ 을 자동으로 참조합니다.\n"
                "• 도봇 없이 테스트: software_team/robot_bridge.py → ROBOT_ENABLED = False\n"
                f"• Pi 서버가 켜지면 {PI_HOST} 에서 카메라/히스토리를 확인할 수 있습니다."
            ),
            bg=BG, fg=MUTED, justify="left", anchor="w",
        ).pack(anchor="w")

    def _build_log_tab(self) -> None:
        self.log_text = tk.Text(
            self.tab_log,
            bg="#0d1117", fg="#c9d1d9", insertbackground=FG,
            font=("Consolas", 10), relief="flat", wrap="word",
        )
        self.log_text.pack(fill="both", expand=True, padx=4, pady=4)

    # ── 프로세스 제어 ────────────────────────────────────────

    def log(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        if self.log_text is None:
            return
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")

    def start_process(self, key: str) -> None:
        mp = self.processes[key]
        try:
            mp.start()
            self.log(f"▶ {mp.name}  (cwd: {mp.cwd.name}/)")
            if mp.proc and mp.proc.stdout:
                threading.Thread(
                    target=self._pipe_output, args=(key, mp), daemon=True
                ).start()
        except Exception as e:
            self.log(f"✗ {mp.name} 실행 실패: {e}")
            messagebox.showerror("실행 실패", f"{mp.name}\n{e}")

    def stop_process(self, key: str) -> None:
        self.processes[key].stop()
        self.log(f"■ {self.processes[key].name} 중지")

    def start_all(self) -> None:
        for key in ["sw_streamlit", "sw_human"]:
            self.start_process(key)
            time.sleep(0.5)

    def stop_all(self) -> None:
        for key in list(self.processes.keys()):
            self.stop_process(key)

    def _pipe_output(self, key: str, mp: ManagedProcess) -> None:
        if not mp.proc or not mp.proc.stdout:
            return
        for line in mp.proc.stdout:
            self.root.after(
                0, lambda l=line.rstrip(), n=mp.name: self.log(f"[{n}] {l}")
            )

    # ── 모니터링 ─────────────────────────────────────────────

    def _start_monitors(self) -> None:
        self._refresh_process_status()
        threading.Thread(target=self._pi_state_loop, daemon=True).start()

    def _refresh_process_status(self) -> None:
        for key, mp in self.processes.items():
            lbl = self.status_labels.get(key)
            if lbl:
                lbl.config(text="실행중" if mp.is_running() else "중지",
                           fg=OK if mp.is_running() else WARN)
        self.root.after(1000, self._refresh_process_status)

    def _pi_state_loop(self) -> None:
        while True:
            try:
                with urllib.request.urlopen(f"{PI_HOST}/state", timeout=1.5) as r:
                    data    = json.loads(r.read().decode("utf-8"))
                history = data.get("logic", {}).get("history", [])
                last    = history[0] if history else {}
                txt     = f"Pi: {last.get('status','ok')}  {last.get('time','')}"
                self.root.after(0, lambda t=txt: self.pi_state_var.set(t))
                self.root.after(0, lambda: self.pi_conn_label.config(text="연결됨", fg=OK))
            except Exception:
                self.root.after(0, lambda: self.pi_state_var.set("Pi 상태: 서버 미연결"))
                self.root.after(0, lambda: self.pi_conn_label.config(text="미연결", fg=ERR))
            time.sleep(2)

    def on_close(self) -> None:
        if messagebox.askyesno("종료", "실행 중인 하위 프로그램을 모두 종료하고 닫을까요?"):
            self.stop_all()
            self.root.destroy()


def main() -> None:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass
    LauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
