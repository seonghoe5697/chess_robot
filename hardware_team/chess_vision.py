"""
chess_vision.py
---------------
탑뷰 카메라 → 체스판 인식 → 보드 상태 반환.

카메라 소스: 라즈베리파이 HTTP 스트림 (192.168.0.133:8000/video_feed)
"""

import json
import time
import urllib.request
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import torch
import torch.nn as nn
from torchvision import transforms, models

import config

FILES = list("abcdefgh")
RANKS = list("12345678")

# 라즈베리파이 서버 주소
PI_HOST = "http://192.168.0.133:8000"

# YOLO 클래스명 → 내부 레이블 변환
YOLO_TO_LABEL = {
    "black-bishop": "bB", "black-king":   "bK", "black-knight": "bN",
    "black-pawn":   "bP", "black-queen":  "bQ", "black-rook":   "bR",
    "white-bishop": "wB", "white-king":   "wK", "white-knight": "wN",
    "white-pawn":   "wP", "white-queen":  "wQ", "white-rook":   "wR",
}


# ─────────────────────────────────────────────────────────────
# ResNet18 CNN (YOLO 없을 때 fallback)
# ─────────────────────────────────────────────────────────────
class ChessCNN(nn.Module):
    def __init__(self, num_classes: int = len(config.PIECE_CLASSES)):
        super().__init__()
        self.backbone = models.resnet18(weights=None)
        self.backbone.fc = nn.Linear(self.backbone.fc.in_features, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.backbone(x)


_INFER_TRANSFORM = transforms.Compose([
    transforms.ToPILImage(),
    transforms.Resize((config.CNN_INPUT_SIZE, config.CNN_INPUT_SIZE)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


def _is_yolo_model(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            return b"ultralytics" in f.read(8192)
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
# 라즈베리파이 스트림에서 프레임 1장 가져오기
# ─────────────────────────────────────────────────────────────
def _grab_from_pi() -> np.ndarray:
    """
    라즈베리파이 /video_feed 스트림에서 JPEG 1프레임을 읽어 numpy 배열로 반환.
    """
    stream_url = f"{PI_HOST}/video_feed"
    try:
        req = urllib.request.urlopen(stream_url, timeout=5)
        buf = b""
        boundary  = b"--frame"
        header_sep = b"\r\n\r\n"
        while True:
            chunk = req.read(8192)
            if not chunk:
                break
            buf += chunk
            sep_idx = buf.find(header_sep)
            if sep_idx == -1:
                continue
            jpg_start = sep_idx + len(header_sep)
            next_boundary = buf.find(boundary, jpg_start)
            if next_boundary == -1:
                continue
            jpg_data = buf[jpg_start:next_boundary].rstrip(b"\r\n")
            req.close()
            arr   = np.frombuffer(jpg_data, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is not None:
                return frame
        req.close()
    except Exception as e:
        raise RuntimeError(f"라즈베리파이 카메라 프레임 수신 실패: {e}")
    raise RuntimeError("라즈베리파이 스트림에서 프레임을 찾지 못했습니다.")


# ─────────────────────────────────────────────────────────────
# 메인 클래스
# ─────────────────────────────────────────────────────────────
class ChessVision:

    def __init__(
        self,
        model_path:   str   = config.MODEL_PATH,
        camera_index: int   = config.CAMERA_INDEX,   # 라즈베리파이 모드에서는 무시
        calib_path:   str   = config.CALIB_PATH,
        board_mm:     float = config.BOARD_MM,
        origin_mm:    tuple = (config.ORIGIN_X_MM, config.ORIGIN_Y_MM),
        model: Optional[nn.Module] = None,
        device: str = "cpu",
    ):
        self.calib_path = Path(calib_path)
        self.board_mm   = board_mm
        self.origin_mm  = np.array(origin_mm, dtype=float)
        self.cell_mm    = board_mm / 8.0
        self.device     = torch.device(device)
        self.dummy_mode = False
        self.yolo_mode  = False
        self.H: Optional[np.ndarray] = None

        self.model      = None
        self.yolo_model = None

        self._load_model(model, model_path)
        self._load_calib()

        # 라즈베리파이 연결 테스트
        try:
            _grab_from_pi()
            print(f"[Vision] 라즈베리파이 카메라 연결 확인: {PI_HOST}")
        except Exception as e:
            print(f"[Vision] ⚠ 라즈베리파이 카메라 연결 실패: {e}")

    # ── 모델 로드 ────────────────────────────────────────────
    def _load_model(self, model, model_path):
        if model is not None:
            self.model = model.to(self.device).eval()
            return
        path = Path(model_path)
        if not path.exists():
            self.dummy_mode = True
            print("[Vision] ⚠ 더미 모드: 모델 없음")
            return
        if _is_yolo_model(model_path):
            self._load_yolo(model_path)
        else:
            self._load_cnn(model_path)

    def _load_yolo(self, model_path):
        try:
            from ultralytics import YOLO
            self.yolo_model = YOLO(model_path)
            self.yolo_mode  = True
            self.dummy_mode = False
            print(f"[Vision] YOLO 모델 로드 완료: {model_path}")
        except Exception as e:
            print(f"[Vision] YOLO 로드 실패: {e} → 더미 모드")
            self.dummy_mode = True

    def _load_cnn(self, model_path):
        try:
            self.model = ChessCNN(len(config.PIECE_CLASSES)).to(self.device)
            state = torch.load(model_path, map_location=self.device, weights_only=False)
            if isinstance(state, dict) and "state_dict" in state:
                state = state["state_dict"]
            if isinstance(state, dict):
                if not any(k.startswith("backbone.") for k in state.keys()):
                    state = {"backbone." + k: v for k, v in state.items()}
                self.model.load_state_dict(state)
            else:
                self.model = state.to(self.device)
            self.model.eval()
            self.dummy_mode = False
            print(f"[Vision] CNN 모델 로드 완료: {model_path}")
        except Exception as e:
            print(f"[Vision] CNN 로드 실패: {e} → 더미 모드")
            self.dummy_mode = True

    # ── 프레임 취득 (라즈베리파이) ───────────────────────────
    def _grab(self) -> np.ndarray:
        return _grab_from_pi()

    # ── 캘리브레이션 ────────────────────────────────────────
    def _save_calib(self):
        self.calib_path.write_text(json.dumps({"H": self.H.tolist()}))

    def _load_calib(self):
        if self.calib_path.exists():
            data = json.loads(self.calib_path.read_text())
            self.H = np.array(data["H"])
            print(f"[Vision] 캘리브레이션 로드: {self.calib_path}")

    # ── 이미지 변환 ─────────────────────────────────────────
    def _warp(self, frame: np.ndarray, size: int = 800) -> np.ndarray:
        if self.H is None:
            raise RuntimeError("캘리브레이션 먼저 실행")
        return cv2.warpPerspective(frame, self.H, (size, size))

    def _crop_cell(self, warped, row, col, margin=0.1):
        H, W = warped.shape[:2]
        cell_h, cell_w = H // 8, W // 8
        y0 = row * cell_h + int(cell_h * margin)
        y1 = (row + 1) * cell_h - int(cell_h * margin)
        x0 = col * cell_w + int(cell_w * margin)
        x1 = (col + 1) * cell_w - int(cell_w * margin)
        return warped[y0:y1, x0:x1]

    # ── YOLO 추론 ────────────────────────────────────────────
    def _infer_yolo(self, frame: np.ndarray) -> dict:
        results = self.yolo_model(frame, verbose=False)[0]
        detections = {}
        if self.H is None:
            return detections
        for box in results.boxes:
            cls_id   = int(box.cls[0])
            cls_name = self.yolo_model.names[cls_id]
            conf     = float(box.conf[0])
            if conf < 0.4:
                continue
            label = YOLO_TO_LABEL.get(cls_name)
            if label is None:
                continue
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cx = (x1 + x2) / 2
            cy = y2 - (y2 - y1) * 0.1
            pt = np.array([[[cx, cy]]], dtype=np.float32)
            warped_pt = cv2.perspectiveTransform(pt, self.H)[0][0]
            wx, wy = warped_pt
            cell = 800 / 8
            col  = int(wx // cell)
            row  = int(wy // cell)
            if 0 <= col <= 7 and 0 <= row <= 7:
                file   = FILES[col]
                rank   = RANKS[7 - row]
                square = f"{file}{rank}"
                if square not in detections or conf > detections[square][2]:
                    detections[square] = (label, wx, wy, conf)
        if detections:
            print(f"[YOLO 탐지] {list(detections.keys())}")
        return detections

    def get_piece_pixel(self, square: str) -> Optional[tuple]:
        if not self.yolo_mode or self.H is None:
            return None
        frame = self._grab()
        detections = self._infer_yolo(frame)
        if square in detections:
            _, wx, wy, _ = detections[square]
            return (wx, wy)
        return None

    # ── CNN 추론 (fallback) ──────────────────────────────────
    def _infer_batch(self, warped: np.ndarray) -> list:
        if self.dummy_mode or self.model is None:
            return ["empty"] * 64
        tensors = []
        for row in range(8):
            for col in range(8):
                cell     = self._crop_cell(warped, row, col)
                cell_rgb = cv2.cvtColor(cell, cv2.COLOR_BGR2RGB)
                tensors.append(_INFER_TRANSFORM(cell_rgb))
        batch = torch.stack(tensors).to(self.device)
        with torch.no_grad():
            indices = self.model(batch).argmax(dim=1).tolist()
        return [config.PIECE_CLASSES[i] for i in indices]

    # ── 보드 상태 반환 ───────────────────────────────────────
    def get_board(self, n_frames: int = config.VISION_N_FRAMES) -> dict:
        if self.dummy_mode:
            print("[Vision] 더미 모드 — 빈 보드 반환")
            return {}
        if self.yolo_mode:
            return self._get_board_yolo(n_frames)
        else:
            return self._get_board_cnn(n_frames)

    def _get_board_yolo(self, n_frames: int) -> dict:
        votes: dict[str, dict[str, int]] = {}
        for _ in range(n_frames):
            frame = self._grab()
            detections = self._infer_yolo(frame)
            for sq, (label, *_) in detections.items():
                if sq not in votes:
                    votes[sq] = {}
                votes[sq][label] = votes[sq].get(label, 0) + 1
            time.sleep(0.05)
        board = {}
        for sq, vote in votes.items():
            board[sq] = max(vote, key=vote.get)
        return board

    def _get_board_cnn(self, n_frames: int) -> dict:
        votes: list[dict[str, int]] = [{} for _ in range(64)]
        for _ in range(n_frames):
            frame  = self._grab()
            warped = self._warp(frame)
            labels = self._infer_batch(warped)
            for i, lbl in enumerate(labels):
                votes[i][lbl] = votes[i].get(lbl, 0) + 1
            time.sleep(0.05)
        board = {}
        for i, vote in enumerate(votes):
            label = max(vote, key=vote.get)
            if label == "empty":
                continue
            row, col = i // 8, i % 8
            rank = RANKS[7 - row]
            file = FILES[col]
            board[f"{file}{rank}"] = label
        return board

    def release(self) -> None:
        # 네트워크 스트림이므로 별도 해제 불필요
        pass