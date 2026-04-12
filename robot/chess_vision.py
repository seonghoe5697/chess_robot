"""
chess_vision.py
---------------
탑뷰 카메라 → 체스판 인식 → 보드 상태 반환.

담당 기능:
  - 카메라 캡처
  - 호모그래피 캘리브레이션 (자동 / 수동 클릭)
  - CNN 기반 말 분류 (ResNet18, 배치 추론)
  - 다중 프레임 투표로 인식 안정화
  - 체스 표기 ↔ 도봇 mm 좌표 변환
"""

import json
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import torch
import torch.nn as nn
from torchvision import transforms, models

import config

# ─────────────────────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────────────────────
FILES = list("abcdefgh")  # a=col0 … h=col7
RANKS = list("12345678")  # "1"=row7(하단) … "8"=row0(상단)


# ─────────────────────────────────────────────────────────────
# CNN 모델 (ResNet18 기반, 교체 가능)
# ─────────────────────────────────────────────────────────────
class ChessCNN(nn.Module):
    """
    ResNet18 백본 + 분류 FC 교체.
    학습 시 다른 구조를 사용했다면 이 클래스를 대체하거나
    ChessVision(model=<your_model>) 으로 직접 주입.
    """

    def __init__(self, num_classes: int = len(config.PIECE_CLASSES)):
        super().__init__()
        self.backbone = models.resnet18(weights=None)
        self.backbone.fc = nn.Linear(self.backbone.fc.in_features, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.backbone(x)


# ─────────────────────────────────────────────────────────────
# 전처리 파이프라인
# ─────────────────────────────────────────────────────────────
_INFER_TRANSFORM = transforms.Compose(
    [
        transforms.ToPILImage(),
        transforms.Resize((config.CNN_INPUT_SIZE, config.CNN_INPUT_SIZE)),
        transforms.ToTensor(),
        transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
    ]
)


# ─────────────────────────────────────────────────────────────
# 메인 클래스
# ─────────────────────────────────────────────────────────────
class ChessVision:
    """
    Parameters
    ----------
    model_path  : 학습된 .pt 파일 경로 (state_dict 형식)
    camera_index: cv2.VideoCapture 인덱스
    calib_path  : 캘리브레이션 저장/로드 경로 (JSON)
    board_mm    : 체스판 실물 한 변 크기 (mm, 정사각형 가정)
    origin_mm   : 체스판 a1 코너의 도봇 (x, y) 좌표 (mm)
    model       : 직접 nn.Module 전달 시 사용 (model_path 무시)
    device      : 'cpu' | 'cuda' | 'mps'
    """

    def __init__(
        self,
        model_path: str = config.MODEL_PATH,
        camera_index: int = config.CAMERA_INDEX,
        calib_path: str = config.CALIB_PATH,
        board_mm: float = config.BOARD_MM,
        origin_mm: tuple = (config.ORIGIN_X_MM, config.ORIGIN_Y_MM),
        model: Optional[nn.Module] = None,
        device: str = "cpu",
    ):
        self.camera_index = camera_index
        self.calib_path = Path(calib_path)
        self.board_mm = board_mm
        self.origin_mm = np.array(origin_mm, dtype=float)
        self.cell_mm = board_mm / 8.0
        self.device = torch.device(device)
        self.dummy_mode = False
        self.H: Optional[np.ndarray] = None  # 3×3 호모그래피

        self._load_model(model, model_path)
        self._load_calib()
        self._open_camera()

    # ── 모델 ────────────────────────────────────────────────
    def _load_model(
        self,
        model: Optional[nn.Module],
        model_path: str,
    ) -> None:
        if model is not None:
            self.model = model.to(self.device).eval()
            return

        path = Path(model_path)
        if path.exists():
            self.model = ChessCNN(len(config.PIECE_CLASSES)).to(self.device)
            state = torch.load(model_path, map_location=self.device)
            # 체크포인트 딕셔너리 처리
            if isinstance(state, dict) and "state_dict" in state:
                state = state["state_dict"]
            if isinstance(state, dict):
                self.model.load_state_dict(state)
            else:
                self.model = state.to(self.device)
            self.model.eval()
            print(f"[Vision] 모델 로드 완료: {model_path}")
        else:
            self.model = None
            self.dummy_mode = True
            print("[Vision] ⚠ 더미 모드: 모델 없음. 좌표 변환만 동작.")

    # ── 카메라 ──────────────────────────────────────────────
    def _open_camera(self) -> None:
        self.cap = cv2.VideoCapture(self.camera_index)

        # ✅ 워밍업 전에 먼저 열림 확인
        if not self.cap.isOpened():
            raise RuntimeError(
                f"카메라 {self.camera_index} 열기 실패 — "
                f"ls /dev/video* 로 인덱스 확인 후 config.py 수정"
            )

        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        # 워밍업
        for _ in range(5):
            self.cap.read()
        print(f"[Vision] 카메라 {self.camera_index} 연결됨")

    def _grab(self) -> np.ndarray:
        """최신 프레임 3회 읽어 마지막 반환 (버퍼 flush)."""
        frame = None
        for _ in range(3):
            ret, frame = self.cap.read()
        if not ret or frame is None:
            raise RuntimeError("카메라 프레임 읽기 실패")
        return frame

    # ── 캘리브레이션 ────────────────────────────────────────
    def calibrate(
        self,
        auto: bool = True,
        manual_points: Optional[list] = None,
    ) -> None:
        """
        체스판 4 코너를 감지해 호모그래피를 계산하고 저장.

        auto=True      : 자동 감지 시도 → 실패 시 수동 클릭
        auto=False     : 수동 클릭 강제
        manual_points  : [(px,py)×4] 직접 전달 시 클릭 생략
                         순서: a8(좌상) → h8(우상) → h1(우하) → a1(좌하)
        """
        frame = self._grab()

        if manual_points is not None:
            src = np.array(manual_points, dtype=np.float32)
        elif auto:
            src = self._auto_detect_corners(frame)
            if src is None:
                print("[Vision] 자동 감지 실패 → 수동 클릭 모드")
                src = self._manual_click_corners(frame)
        else:
            src = self._manual_click_corners(frame)

        W = 800
        dst = np.array([[0, 0], [W, 0], [W, W], [0, W]], dtype=np.float32)
        self.H, _ = cv2.findHomography(src, dst)
        self._save_calib()
        print("[Vision] 캘리브레이션 완료 및 저장")

    def _auto_detect_corners(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """내부 코너 7×7 감지 → 외곽 4점 추출."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        ret, corners = cv2.findChessboardCorners(gray, (7, 7), None)
        if not ret:
            return None
        corners = cv2.cornerSubPix(
            gray,
            corners,
            (11, 11),
            (-1, -1),
            criteria=(cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001),
        )
        corners = corners.reshape(-1, 2)
        return np.array(
            [corners[0], corners[6], corners[-1], corners[-7]],
            dtype=np.float32,
        )

    def _manual_click_corners(self, frame: np.ndarray) -> np.ndarray:
        """Chess Vision 창에서 4코너를 클릭으로 수집."""
        labels = ["a8 좌상", "h8 우상", "h1 우하", "a1 좌하"]
        points = []
        clone = frame.copy()
        win = "Chess Vision"

        def _on_click(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
                points.append((x, y))
                cv2.circle(clone, (x, y), 8, (0, 255, 0), -1)
                cv2.putText(
                    clone,
                    labels[len(points) - 1],
                    (x + 10, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (0, 255, 0),
                    2,
                )

        cv2.setMouseCallback(win, _on_click)
        print(f"[캘리브] Chess Vision 창에서 순서대로 클릭: {labels}")

        while len(points) < 4:
            disp = clone.copy()
            msg = f"클릭: {labels[len(points)]}  ({len(points)}/4)"
            cv2.putText(
                disp, msg, (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (0, 200, 255), 2
            )
            cv2.imshow(win, disp)
            if cv2.waitKey(30) == 27:
                raise RuntimeError("캘리브레이션 취소")

        cv2.setMouseCallback(win, lambda *a: None)
        print(f"[캘리브] 4점 완료: {points}")
        return np.array(points, dtype=np.float32)

    def _save_calib(self) -> None:
        self.calib_path.write_text(json.dumps({"H": self.H.tolist()}))

    def _load_calib(self) -> None:
        if self.calib_path.exists():
            data = json.loads(self.calib_path.read_text())
            self.H = np.array(data["H"])
            print(f"[Vision] 캘리브레이션 로드: {self.calib_path}")

    # ── 이미지 변환 ─────────────────────────────────────────
    def _warp(self, frame: np.ndarray, size: int = 800) -> np.ndarray:
        """호모그래피 적용 → 정사각형 탑뷰 체스판."""
        if self.H is None:
            raise RuntimeError("캘리브레이션 먼저 실행: vision.calibrate()")
        return cv2.warpPerspective(frame, self.H, (size, size))

    def _crop_cell(
        self,
        warped: np.ndarray,
        row: int,
        col: int,
        margin: float = 0.1,
    ) -> np.ndarray:
        """
        워핑 이미지에서 (row, col) 칸을 크롭.
        row 0 = rank8(상단), col 0 = file a(좌측).
        margin: 경계선 제거 비율 (0.0~0.3)
        """
        H, W = warped.shape[:2]
        cell_h = H // 8
        cell_w = W // 8
        y0 = row * cell_h + int(cell_h * margin)
        y1 = (row + 1) * cell_h - int(cell_h * margin)
        x0 = col * cell_w + int(cell_w * margin)
        x1 = (col + 1) * cell_w - int(cell_w * margin)
        return warped[y0:y1, x0:x1]

    # ── 추론 ────────────────────────────────────────────────
    def _infer_batch(self, warped: np.ndarray) -> list[str]:
        """64칸 배치 추론 → 레이블 리스트 (row0col0 ~ row7col7)."""
        if self.dummy_mode:
            return ["empty"] * 64

        tensors = []
        for row in range(8):
            for col in range(8):
                cell = self._crop_cell(warped, row, col)
                cell_rgb = cv2.cvtColor(cell, cv2.COLOR_BGR2RGB)
                tensors.append(_INFER_TRANSFORM(cell_rgb))

        batch = torch.stack(tensors).to(self.device)  # (64, 3, H, W)
        with torch.no_grad():
            indices = self.model(batch).argmax(dim=1).tolist()
        return [config.PIECE_CLASSES[i] for i in indices]

    # ── 공개 API ────────────────────────────────────────────
    def get_board(self, n_frames: int = config.VISION_N_FRAMES) -> dict:
        """
        n_frames 프레임 투표 다수결로 보드 상태 반환.

        Returns
        -------
        dict  {"a1": "wP", "e1": "wK", ...}  빈 칸은 키 없음
        """
        if self.dummy_mode:
            print("[Vision] 더미 모드 — get_board() 빈 보드 반환")
            return {}

        votes: list[dict[str, int]] = [{} for _ in range(64)]

        for _ in range(n_frames):
            frame = self._grab()
            warped = self._warp(frame)
            labels = self._infer_batch(warped)
            for i, lbl in enumerate(labels):
                votes[i][lbl] = votes[i].get(lbl, 0) + 1
            time.sleep(0.05)

        board: dict[str, str] = {}
        for i, vote in enumerate(votes):
            label = max(vote, key=vote.get)
            if label == "empty":
                continue
            row = i // 8
            col = i % 8
            rank = RANKS[7 - row]
            file = FILES[col]
            board[f"{file}{rank}"] = label

        return board

    def square_to_mm(self, square: str) -> tuple[float, float]:
        """
        체스 표기 → 도봇 XY mm 좌표 (칸 중심).

        배치 가정: a1이 origin_mm, a→h 방향이 +X, 1→8 방향이 +Y.
        실제 배치에 따라 config.py에서 부호/축 조정.
        """
        file = square[0].lower()
        rank = square[1]
        col = FILES.index(file)
        row = RANKS.index(rank)

        x_mm = self.origin_mm[0] + (col + 0.5) * self.cell_mm
        y_mm = self.origin_mm[1] + (row + 0.5) * self.cell_mm
        return (round(x_mm, 1), round(y_mm, 1))

    def squares_to_move(self, from_sq: str, to_sq: str) -> tuple[tuple, tuple]:
        """이동 명령 → (from_mm, to_mm) 튜플 쌍."""
        return self.square_to_mm(from_sq), self.square_to_mm(to_sq)

    # ── 디버그 뷰 ────────────────────────────────────────────
    def debug_view(self, board: Optional[dict] = None, wait: int = 0) -> None:
        """워핑 체스판 + 그리드 + 말 레이블 오버레이 표시."""
        frame = self._grab()
        warped = self._warp(frame)
        if board is None:
            board = self.get_board()

        overlay = warped.copy()
        H, W = overlay.shape[:2]
        cell_h, cell_w = H // 8, W // 8

        for row in range(8):
            for col in range(8):
                x0, y0 = col * cell_w, row * cell_h
                x1, y1 = x0 + cell_w, y0 + cell_h
                color = (200, 200, 200) if (row + col) % 2 == 0 else (80, 80, 80)
                cv2.rectangle(overlay, (x0, y0), (x1, y1), color, 1)

                rank = RANKS[7 - row]
                file = FILES[col]
                piece = board.get(f"{file}{rank}", "")
                if piece:
                    clr = (50, 220, 50) if piece.startswith("w") else (50, 50, 220)
                    cv2.putText(
                        overlay,
                        piece,
                        (x0 + 5, y0 + cell_h - 8),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.45,
                        clr,
                        1,
                    )

        for i, f in enumerate(FILES):
            cv2.putText(
                overlay,
                f,
                (i * cell_w + cell_w // 2 - 5, H - 4),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (255, 255, 100),
                1,
            )
        for i, r in enumerate(RANKS):
            cv2.putText(
                overlay,
                r,
                (2, (7 - i) * cell_h + cell_h // 2 + 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (255, 255, 100),
                1,
            )

        cv2.imshow("Chess Vision Debug", overlay)
        cv2.waitKey(wait)

    def release(self) -> None:
        self.cap.release()
        cv2.destroyAllWindows()
