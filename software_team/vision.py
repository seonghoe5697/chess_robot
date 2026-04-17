"""
vision.py
---------
체스판 실시간 비전 — CNN 분류 + OpenCV 컨투어 중심 (Option B)

카메라 소스 우선순위:
  1) 라즈베리파이 MJPEG 스트림 (PI_STREAM_URL)
  2) 로컬 USB 카메라 (config.CAMERA_INDEX)
  3) 둘 다 실패 시 → DummyVision

Pi 서버(server.py + capture_service.py)가 돌아가고 있으면 자동으로 Pi 스트림 사용.
Pi가 꺼져 있으면 PC 로컬 카메라로 폴백.

vision_coord_patch.py의 VisionGuidedController가 요구하는 인터페이스:
  - yolo_mode (bool)
  - get_piece_pixel(square) -> (px, py) | None
"""

import json
import threading
import time
from pathlib import Path
from typing import Optional, Union

import cv2
import numpy as np
import torch

import sys
from pathlib import Path
_HW_DIR = Path(__file__).resolve().parent.parent / "hardware_team"
if str(_HW_DIR) not in sys.path:
    sys.path.insert(0, str(_HW_DIR))

import config

FILES = list("abcdefgh")
RANKS = list("12345678")

CORNERS_PATH    = "board_corners.json"
DEFAULT_CNN     = "chess_model_pure.pth"

# ─── Pi 카메라 스트림 URL (capture_service.py의 PI_HOST와 일치시킬 것) ───
PI_STREAM_URL   = "http://192.168.0.133:8000/video_feed"


# ═════════════════════════════════════════════════════════════
#   카메라 소스 열기 헬퍼
# ═════════════════════════════════════════════════════════════
def _try_open(source: Union[int, str]) -> Optional[cv2.VideoCapture]:
    """
    카메라 소스 열기 시도. 프레임 1장 실제로 읽혀야 성공으로 간주.
    실패 시 None 반환 (자원 해제 완료).
    """
    try:
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            cap.release()
            return None
        # URL 스트림은 첫 프레임까지 시간 걸릴 수 있음
        for _ in range(10):
            ok, _ = cap.read()
            if ok:
                return cap
            time.sleep(0.2)
        cap.release()
        return None
    except Exception:
        return None


def _open_camera_with_fallback(
    preferred: Optional[Union[int, str]] = None,
    log=print,
) -> tuple[Optional[cv2.VideoCapture], Optional[Union[int, str]]]:
    """
    preferred가 지정되면 그것만 시도.
    None이면: Pi 스트림 → 로컬 카메라 순서로 시도.
    성공 시 (cap, 사용된_소스), 실패 시 (None, None).
    """
    if preferred is not None:
        sources = [preferred]
    else:
        sources = [PI_STREAM_URL, config.CAMERA_INDEX]

    for src in sources:
        log(f"[Vision] 카메라 시도: {src}")
        cap = _try_open(src)
        if cap is not None:
            log(f"[Vision] 카메라 연결 성공: {src}")
            return cap, src
        log(f"[Vision] 카메라 실패: {src}")
    return None, None


# ═════════════════════════════════════════════════════════════
#   메인 비전 클래스
# ═════════════════════════════════════════════════════════════
class ChessVision:

    WARP_SIZE = 800

    def __init__(
        self,
        camera_source: Optional[Union[int, str]] = None,
        model_path:    Optional[str]             = None,
        corners_path:  str                       = CORNERS_PATH,
        conf_thresh:   float                     = 0.55,
    ):
        """
        Parameters
        ----------
        camera_source : None | int | str
            None이면 자동 (Pi 스트림 → 로컬 카메라 폴백).
            int면 로컬 USB 인덱스, str이면 MJPEG/RTSP URL.
        """
        self.camera_source = camera_source
        self.model_path  = model_path if model_path is not None else DEFAULT_CNN
        self.conf_thresh = conf_thresh

        self.yolo_mode:  bool = True
        self.dummy_mode: bool = False

        self._cap: Optional[cv2.VideoCapture] = None
        self._source_used = None
        self.model  = None
        self.device = "cpu"
        self._transform = None

        self._corners: Optional[list] = None

        self._square_pixels: dict[str, tuple[float, float]] = {}
        self._last_ts = 0.0
        self._lock    = threading.Lock()

        self._stop_flag = False
        self._thread: Optional[threading.Thread] = None

        self._load_corners(corners_path)
        self._init_camera()
        self._init_cnn()

    # ─────────────────────────────────────────────────────────
    # 초기화
    # ─────────────────────────────────────────────────────────
    def _load_corners(self, path: str) -> None:
        p = Path(path)
        if not p.exists():
            print(f"[Vision] 코너 파일 없음: {path} → 중앙 크롭 폴백")
            print("         setup_vision.py 먼저 실행하세요.")
            return
        try:
            data = json.loads(p.read_text())
            self._corners = [tuple(c) for c in data["corners"]]
            print(f"[Vision] 코너 로드: {self._corners}")
        except Exception as e:
            print(f"[Vision] 코너 로드 실패: {e}")

    def _init_camera(self) -> None:
        cap, used = _open_camera_with_fallback(self.camera_source)
        if cap is None:
            print("[Vision] 카메라 전부 실패 → 더미 모드")
            self.dummy_mode = True
            self.yolo_mode  = False
            return

        # 로컬 USB 카메라만 속성 설정 의미 있음 (스트림 URL엔 무효)
        if isinstance(used, int):
            cap.set(cv2.CAP_PROP_CONTRAST,   config.CAMERA_CONTRAST)
            cap.set(cv2.CAP_PROP_SATURATION, config.CAMERA_SATURATION)
            cap.set(cv2.CAP_PROP_BRIGHTNESS, config.CAMERA_BRIGHTNESS)
            cap.set(cv2.CAP_PROP_FPS,        config.CAMERA_FPS)

        self._cap = cap
        self._source_used = used

    def _init_cnn(self) -> None:
        if self.dummy_mode:
            return
        try:
            try:
                from core import load_model
                self.model, self.device = load_model(self.model_path)
            except Exception:
                self.model = torch.load(self.model_path, map_location="cpu")
                if hasattr(self.model, "eval"):
                    self.model.eval()
                self.device = torch.device(
                    "cuda" if torch.cuda.is_available() else "cpu"
                )
                if hasattr(self.model, "to"):
                    self.model = self.model.to(self.device)

            try:
                from core.model import TRANSFORM
                self._transform = TRANSFORM
            except Exception:
                from torchvision import transforms
                self._transform = transforms.Compose([
                    transforms.Resize((50, 50)),
                    transforms.ToTensor(),
                    transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
                ])
            print(f"[Vision] CNN 로드: {self.model_path}  device={self.device}")
        except Exception as e:
            print(f"[Vision] CNN 로드 실패 → 비전 비활성: {e}")
            self.yolo_mode = False

    # ─────────────────────────────────────────────────────────
    # 프레임 / 워핑
    # ─────────────────────────────────────────────────────────
    def _grab(self) -> np.ndarray:
        if self._cap is None:
            raise RuntimeError("카메라 미연결")
        # 로컬 카메라: 버퍼 드레인해서 최신 프레임 확보
        # 네트워크 스트림: grab 반복은 지연만 발생 → 1회 read
        if isinstance(self._source_used, int):
            for _ in range(3):
                self._cap.grab()
        ok, frame = self._cap.read()
        if not ok or frame is None:
            raise RuntimeError("프레임 획득 실패")
        return frame

    def _warp(self, frame: np.ndarray) -> np.ndarray:
        W = self.WARP_SIZE
        if self._corners is None:
            h, w = frame.shape[:2]
            s = min(h, w)
            y0, x0 = (h - s) // 2, (w - s) // 2
            return cv2.resize(frame[y0:y0+s, x0:x0+s], (W, W))
        src = np.array(self._corners, dtype=np.float32)
        dst = np.array([
            [0, 0], [W-1, 0], [W-1, W-1], [0, W-1],
        ], dtype=np.float32)
        M = cv2.getPerspectiveTransform(src, dst)
        return cv2.warpPerspective(frame, M, (W, W))

    def _crop_cell(self, warped: np.ndarray, row: int, col: int) -> np.ndarray:
        cell = self.WARP_SIZE // 8
        y0, x0 = row * cell, col * cell
        return warped[y0:y0+cell, x0:x0+cell]

    # ─────────────────────────────────────────────────────────
    # CNN 단일 칸 분류
    # ─────────────────────────────────────────────────────────
    def _classify_cell(self, cell_bgr: np.ndarray) -> tuple[str, float]:
        from PIL import Image
        rgb = cv2.cvtColor(cell_bgr, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb)
        tensor = self._transform(pil).unsqueeze(0).to(self.device)
        with torch.no_grad():
            logits = self.model(tensor)
            probs  = torch.softmax(logits, dim=1)[0]
            idx    = int(probs.argmax().item())
            conf   = float(probs[idx].item())
        return config.PIECE_CLASSES[idx], conf

    # ─────────────────────────────────────────────────────────
    # 컨투어 중심
    # ─────────────────────────────────────────────────────────
    def _find_centroid(self, cell_bgr: np.ndarray) -> Optional[tuple[float, float]]:
        gray = cv2.cvtColor(cell_bgr, cv2.COLOR_BGR2GRAY)
        H, W = gray.shape
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        _, th_dark  = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        _, th_light = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY     + cv2.THRESH_OTSU)

        best, best_score = None, 0.0
        kernel = np.ones((3, 3), np.uint8)

        for th in (th_dark, th_light):
            cleaned = cv2.morphologyEx(th, cv2.MORPH_OPEN,  kernel, iterations=1)
            cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel, iterations=2)
            b = 4
            cleaned[:b, :] = 0
            cleaned[-b:, :] = 0
            cleaned[:, :b] = 0
            cleaned[:, -b:] = 0

            contours, _ = cv2.findContours(
                cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            for c in contours:
                area = cv2.contourArea(c)
                if area < W * H * 0.04 or area > W * H * 0.85:
                    continue
                M = cv2.moments(c)
                if M["m00"] <= 0:
                    continue
                cx = M["m10"] / M["m00"]
                cy = M["m01"] / M["m00"]
                dist = ((cx - W/2) ** 2 + (cy - H/2) ** 2) ** 0.5
                score = area / (1.0 + dist * 0.5)
                if score > best_score:
                    best_score = score
                    best = (cx, cy)
        return best

    # ─────────────────────────────────────────────────────────
    # 전체 보드 캡처
    # ─────────────────────────────────────────────────────────
    def capture(self) -> None:
        if self.dummy_mode or not self.yolo_mode or self.model is None:
            return
        try:
            frame  = self._grab()
            warped = self._warp(frame)
            cell   = self.WARP_SIZE // 8
            new_pixels: dict[str, tuple[float, float]] = {}

            for row in range(8):
                for col in range(8):
                    cell_img = self._crop_cell(warped, row, col)
                    label, conf = self._classify_cell(cell_img)
                    if label == "empty" or conf < self.conf_thresh:
                        continue
                    centroid = self._find_centroid(cell_img)
                    if centroid is None:
                        centroid = (cell / 2, cell / 2)
                    abs_px = col * cell + centroid[0]
                    abs_py = row * cell + centroid[1]
                    sq = FILES[col] + RANKS[7 - row]
                    new_pixels[sq] = (abs_px, abs_py)

            with self._lock:
                self._square_pixels = new_pixels
                self._last_ts = time.time()
        except Exception as e:
            print(f"[Vision] capture 오류: {e}")

    # ─────────────────────────────────────────────────────────
    # 외부 API
    # ─────────────────────────────────────────────────────────
    def get_piece_pixel(self, square: str) -> Optional[tuple[float, float]]:
        if self.dummy_mode or not self.yolo_mode:
            return None
        if time.time() - self._last_ts > 0.5:
            self.capture()
        with self._lock:
            return self._square_pixels.get(square.lower())

    def start_auto_capture(self, interval: float = 0.4) -> None:
        if self._thread and self._thread.is_alive():
            return
        if self.dummy_mode:
            return
        self._stop_flag = False

        def _loop():
            while not self._stop_flag:
                self.capture()
                time.sleep(interval)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()
        print("[Vision] 자동 캡처 시작")

    def stop_auto_capture(self) -> None:
        self._stop_flag = True
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

    def release(self) -> None:
        self.stop_auto_capture()
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        print("[Vision] 카메라 해제")

    def __del__(self):
        try:
            self.release()
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════
#   더미 (비전 사용 불가 시 — 칸 중심으로 fallback)
# ═════════════════════════════════════════════════════════════
class DummyVision:
    yolo_mode  = False
    dummy_mode = True
    model      = None
    device     = "cpu"

    def get_piece_pixel(self, square: str): return None
    def capture(self):              pass
    def start_auto_capture(self, interval: float = 0.3): pass
    def stop_auto_capture(self):    pass
    def release(self):              pass


# ═════════════════════════════════════════════════════════════
#   최초 1회: 체스판 4코너 클릭 저장
# ═════════════════════════════════════════════════════════════
def pick_corners_interactive(
    camera_source: Optional[Union[int, str]] = None,
    save_path: str = CORNERS_PATH,
) -> bool:
    """
    카메라 미리보기에서 4코너 클릭 → JSON 저장.
    camera_source None이면 Pi 스트림 → 로컬 카메라 순으로 자동 선택.
    """
    cap, used = _open_camera_with_fallback(camera_source)
    if cap is None:
        raise RuntimeError("카메라 실패 (Pi 서버 + 로컬 카메라 모두)")
    print(f"[Corners] 카메라 소스: {used}")

    if isinstance(used, int):
        cap.set(cv2.CAP_PROP_CONTRAST,   config.CAMERA_CONTRAST)
        cap.set(cv2.CAP_PROP_SATURATION, config.CAMERA_SATURATION)
        cap.set(cv2.CAP_PROP_BRIGHTNESS, config.CAMERA_BRIGHTNESS)

    labels = ["a8 (좌상)", "h8 (우상)", "h1 (우하)", "a1 (좌하)"]
    clicked: list[tuple[int, int]] = []

    def on_click(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and len(clicked) < 4:
            clicked.append((x, y))
            print(f"  {len(clicked)}/4  {labels[len(clicked)-1]}: ({x}, {y})")

    win = "Board corners (click a8, h8, h1, a1) — R=reset ENTER=save ESC=cancel"
    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_click)

    print("=" * 60)
    print("  체스판 코너 설정")
    print("=" * 60)
    print("순서: a8(좌상) → h8(우상) → h1(우하) → a1(좌하)\n")

    saved = False
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                continue
            disp = frame.copy()
            for i, (x, y) in enumerate(clicked):
                cv2.circle(disp, (x, y), 8, (0, 255, 0), -1)
                cv2.putText(disp, str(i+1), (x+10, y-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            if len(clicked) < 4:
                msg = f"{len(clicked)+1}/4 {labels[len(clicked)]}"
                cv2.putText(disp, msg, (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 220, 255), 2)
            else:
                pts = np.array(clicked, dtype=np.int32)
                cv2.polylines(disp, [pts], True, (0, 255, 0), 2)
                cv2.putText(disp, "ENTER=save  R=reset", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.imshow(win, disp)
            k = cv2.waitKey(30) & 0xFF
            if k == 27:
                print("취소됨"); return False
            if k in (ord('r'), ord('R')):
                clicked.clear(); print("리셋")
            if k == 13 and len(clicked) == 4:
                saved = True
                break
    finally:
        cap.release()
        cv2.destroyWindow(win)

    if not saved:
        return False
    Path(save_path).write_text(
        json.dumps({"corners": [list(p) for p in clicked]}, indent=2)
    )
    print(f"\n저장 완료: {save_path}")
    return True
