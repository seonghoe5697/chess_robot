"""
core/model.py
ChessPieceCNN 모델 정의와 추론 유틸리티를 한 곳에서 관리합니다.

기존에 app.py와 train.py에 동일한 클래스가 중복 정의되어 있었습니다.
이제 두 파일 모두 여기서 import 합니다.
"""

import torch
import torch.nn as nn
from torchvision import transforms
from PIL import Image

from core.board import LABEL_TO_PIECE

# ── 모델 아키텍처 ──────────────────────────────────────────────────────────

class ChessPieceCNN(nn.Module):
    """
    체스 기물 이미지 분류 CNN.
    입력: 50×50 RGB 이미지
    출력: 13 클래스 (백 6종 + 흑 6종 + 빈칸)
    """
    def __init__(self):
        super().__init__()
        self.conv_layers = nn.Sequential(
            nn.Conv2d(3, 32, kernel_size=3, padding=1), nn.ReLU(), nn.MaxPool2d(2, 2),
            nn.Conv2d(32, 64, kernel_size=3, padding=1), nn.ReLU(), nn.MaxPool2d(2, 2),
            nn.Conv2d(64, 128, kernel_size=3, padding=1), nn.ReLU(), nn.AdaptiveAvgPool2d((1, 1)),
        )
        self.fc_layers = nn.Sequential(
            nn.Linear(128, 64), nn.ReLU(),
            nn.Linear(64, 13),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.conv_layers(x)
        x = torch.flatten(x, 1)
        return self.fc_layers(x)


# ── 전처리 (학습/추론 동일하게 유지) ──────────────────────────────────────

TRANSFORM = transforms.Compose([
    transforms.Resize((50, 50)),
    transforms.ToTensor(),
    transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
])


# ── 디바이스 자동 감지 ───────────────────────────────────────────────────

def _auto_device() -> torch.device:
    """CUDA → CPU 순서로 사용 가능한 디바이스를 자동 선택합니다."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


# ── 모델 로딩 ─────────────────────────────────────────────────────────────

def load_model(model_path: str, device: torch.device | None = None) -> tuple[ChessPieceCNN, torch.device]:
    """
    저장된 가중치를 불러와 추론 준비 완료 상태의 모델을 반환합니다.

    Parameters
    ----------
    model_path : .pth 파일 경로
    device     : None이면 자동 감지 (CUDA → CPU)

    Returns
    -------
    (model, device)
    """
    if device is None:
        device = _auto_device()

    model = ChessPieceCNN().to(device)
    model.load_state_dict(torch.load(model_path, map_location=device, weights_only=True))
    model.eval()
    return model, device


# ── 추론 ──────────────────────────────────────────────────────────────────

def predict_labels(
    image: Image.Image,
    model: ChessPieceCNN,
    device: torch.device,
) -> list[int]:
    """
    체스판 전체 이미지를 64칸으로 잘라 배치 추론으로 기물 레이블을 반환합니다.

    Parameters
    ----------
    image  : 체스판 전체 PIL 이미지 (정사각형 권장)
    model  : load_model()로 불러온 모델
    device : 추론 디바이스

    Returns
    -------
    64개 정수 리스트 (0~12)
    """
    w, h = image.size
    sw, sh = w // 8, h // 8
    tensors = []

    for row in range(8):
        for col in range(8):
            crop = image.crop((col * sw, row * sh, (col + 1) * sw, (row + 1) * sh))
            tensors.append(TRANSFORM(crop))

    batch = torch.stack(tensors).to(device)
    with torch.no_grad():
        outputs = model(batch)
        labels = torch.argmax(outputs, dim=1).tolist()

    return labels


def labels_to_pieces(labels: list[int]) -> list[str]:
    """레이블 배열을 기물 문자 배열로 변환합니다 ('.' = 빈 칸)."""
    return [LABEL_TO_PIECE[lbl] for lbl in labels]