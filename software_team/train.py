"""
train.py  ―  기물 인식 CNN 재학습 (클래스 불균형 해소 버전)
core/ 패키지의 ChessPieceCNN을 사용합니다.

핵심 개선사항
-------------
1. WeightedRandomSampler  : 빈칸(80%) 과다 문제 해결 → 13클래스 균등 샘플링
2. CosineAnnealingLR      : 고정 lr 대신 에포크마다 자동 조정
3. 클래스별 정확도 출력   : 어떤 기물이 잘 안 되는지 매 에포크 확인
4. 조기 종료(Early Stop)  : val_loss 기준, 5에포크 개선 없으면 자동 중단
5. GPU 자동 감지          : Intel Arc (IPEX) → NVIDIA (CUDA+AMP) → CPU 순서로 자동 선택
"""

import os
import random
import argparse
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset, WeightedRandomSampler
from torchvision import transforms
from PIL import Image
from tqdm import tqdm
from collections import Counter, defaultdict

from core import ChessPieceCNN, PIECE_TO_LABEL, LABEL_TO_PIECE
from core.model import TRANSFORM  # 추론용 전처리 (core와 동일하게 유지)

try:
    import intel_extension_for_pytorch as ipex
    HAS_IPEX = True
except ImportError:
    HAS_IPEX = False

# ── 설정 ──────────────────────────────────────────────────────────────────

MODEL_SAVE  = "chess_model_pure.pth"
BATCH_SIZE  = 64
EPOCHS      = 20
LR          = 3e-4     # Adam + Cosine 조합에 맞는 초기 lr
VAL_SPLIT   = 0.1      # 학습 데이터의 10%를 검증용으로
EARLY_STOP  = 5        # val_loss 개선 없으면 5에포크 후 중단

# 학습 시 데이터 증강 (과적합 방지)
TRANSFORM_TRAIN = transforms.Compose([
    transforms.Resize((50, 50)),
    transforms.RandomHorizontalFlip(p=0.1),   # 체스판 특성상 과도한 flip은 금지
    transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.2),
    transforms.ToTensor(),
    transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
])


# ── 데이터셋 ──────────────────────────────────────────────────────────────

class ChessDataset(Dataset):
    """파일명이 FEN 배치 형식(-로 구분)인 이미지 데이터셋."""

    def __init__(self, img_names: list, folder_path: str, transform=None):
        self.folder_path = folder_path
        self.img_names = img_names
        self.transform = transform
        # 전체 레이블을 미리 집계 (WeightedSampler 계산용)
        self.all_labels: list[int] = []
        for name in img_names:
            self.all_labels.extend(self._parse_labels(name))

    def __len__(self):
        return len(self.img_names)

    def __getitem__(self, idx):
        img_path = os.path.join(self.folder_path, self.img_names[idx])
        img = Image.open(img_path).convert("RGB")
        labels = self._parse_labels(self.img_names[idx])

        w, h = img.size
        sw, sh = w // 8, h // 8
        squares = []
        for i in range(8):
            for j in range(8):
                crop = img.crop((j*sw, i*sh, (j+1)*sw, (i+1)*sh))
                squares.append(self.transform(crop) if self.transform else transforms.ToTensor()(crop))

        return torch.stack(squares), torch.tensor(labels)

    @staticmethod
    def _parse_labels(filename: str) -> list[int]:
        fen_str = filename.split(".")[0]
        labels = []
        for row in fen_str.split("-"):
            for ch in row:
                if ch.isdigit():
                    labels.extend([12] * int(ch))
                else:
                    labels.append(PIECE_TO_LABEL.get(ch, 12))
        return labels


def make_weighted_sampler(dataset: ChessDataset) -> WeightedRandomSampler:
    """
    클래스 불균형 해소: 빈칸(80%)을 down-sampling, 기물(20%)을 up-sampling.
    각 이미지의 대표 레이블(비어있지 않은 칸 중 가장 많은 기물)로 샘플 가중치 계산.
    """
    label_counts = Counter(dataset.all_labels)
    total = sum(label_counts.values())
    # 클래스 가중치: 희귀할수록 높은 가중치
    class_weight = {cls: total / (len(label_counts) * cnt) for cls, cnt in label_counts.items()}

    # 이미지별 가중치: 해당 이미지에서 가장 많이 나온 기물 클래스 기준
    sample_weights = []
    labels_per_img = 64
    for i in range(len(dataset)):
        img_labels = dataset.all_labels[i*labels_per_img:(i+1)*labels_per_img]
        # 빈칸 제외한 레이블 중 대표값
        piece_labels = [l for l in img_labels if l != 12]
        if piece_labels:
            dominant = Counter(piece_labels).most_common(1)[0][0]
        else:
            dominant = 12
        sample_weights.append(class_weight[dominant])

    return WeightedRandomSampler(sample_weights, num_samples=len(sample_weights), replacement=True)


# ── 학습 ──────────────────────────────────────────────────────────────────

def train(data_path: str):
    # 디바이스 선택 (Intel Arc XPU → NVIDIA CUDA → CPU 순서로 자동 감지)
    if hasattr(torch, "xpu") and torch.xpu.is_available():
        device = torch.device("xpu")
        use_amp = False
        print(f"✅ Intel Arc GPU: {torch.xpu.get_device_name(0)}")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
        use_amp = True    # NVIDIA: AMP(자동 혼합 정밀도)로 학습 가속
        print(f"✅ NVIDIA GPU: {torch.cuda.get_device_name(0)}")
    else:
        device = torch.device("cpu")
        use_amp = False
        print("⚠️  CPU 학습 (느릴 수 있음)")

    # 파일 목록 로드
    all_files = [f for f in os.listdir(data_path) if f.lower().endswith((".jpeg", ".jpg", ".png"))]
    print(f"📂 전체 이미지: {len(all_files):,}장")

    # train / val 분리
    random.seed(42)
    random.shuffle(all_files)
    val_size = int(len(all_files) * VAL_SPLIT)
    val_files = all_files[:val_size]
    train_files = all_files[val_size:]
    print(f"   학습: {len(train_files):,}장 / 검증: {len(val_files):,}장")

    train_dataset = ChessDataset(train_files, data_path, transform=TRANSFORM_TRAIN)
    val_dataset   = ChessDataset(val_files,   data_path, transform=TRANSFORM)

    # 클래스 분포 출력
    label_cnt = Counter(train_dataset.all_labels)
    print("\n📊 학습 데이터 클래스 분포:")
    for cls in range(13):
        cnt = label_cnt.get(cls, 0)
        pct = cnt / sum(label_cnt.values()) * 100
        bar = '█' * int(pct / 2)
        print(f"   {LABEL_TO_PIECE[cls]:2s} (label {cls:2d}): {cnt:8,}개  {pct:5.1f}%  {bar}")

    sampler = make_weighted_sampler(train_dataset)
    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, sampler=sampler,  num_workers=0)
    val_loader   = DataLoader(val_dataset,   batch_size=BATCH_SIZE, shuffle=False, num_workers=0)

    # 모델
    model = ChessPieceCNN().to(device)
    total_params = sum(p.numel() for p in model.parameters())
    print(f"\n🧠 모델 파라미터: {total_params:,}개")

    # 기존 모델 이어받기 (파인튜닝)
    if os.path.exists(MODEL_SAVE):
        try:
            model.load_state_dict(torch.load(MODEL_SAVE, map_location=device, weights_only=True))
            print(f"📥 기존 모델 로드 완료 → 파인튜닝 모드")
        except Exception as e:
            print(f"⚠️  기존 모델 로드 실패 ({e}) → 처음부터 학습")

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=LR, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS, eta_min=1e-6)

    if HAS_IPEX and device.type == "xpu":
        model, optimizer = ipex.optimize(model, optimizer=optimizer)
        print("✅ IPEX 최적화 적용 (Intel Arc)")
    elif device.type == "xpu":
        print("✅ Intel Arc XPU (네이티브 PyTorch)")
    elif device.type == "cuda":
        print("✅ AMP(자동 혼합 정밀도) 적용 (NVIDIA)")

    # AMP scaler (NVIDIA 전용)
    scaler = torch.amp.GradScaler("cuda") if use_amp else None

    # 학습 루프
    print(f"\n🚀 학습 시작 (epochs={EPOCHS}, batch={BATCH_SIZE}, lr={LR})\n")
    best_val_loss = float("inf")
    no_improve = 0

    for epoch in range(EPOCHS):
        # ── Train ─────────────────────────────────────────────────────────
        model.train()
        train_loss = 0.0
        loop = tqdm(train_loader, desc=f"Epoch [{epoch+1:2d}/{EPOCHS}] Train")
        for images, labels in loop:
            images = images.view(-1, 3, 50, 50).to(device)
            labels = labels.view(-1).to(device)
            optimizer.zero_grad()

            # AMP 적용: NVIDIA GPU일 때 자동 혼합 정밀도 사용
            with torch.amp.autocast("cuda", enabled=use_amp):
                loss = criterion(model(images), labels)

            if scaler:
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            else:
                loss.backward()
                optimizer.step()

            train_loss += loss.item()
            loop.set_postfix(loss=f"{loss.item():.4f}")
        train_loss /= len(train_loader)

        # ── Validation ────────────────────────────────────────────────────
        model.eval()
        val_loss = 0.0
        class_correct = defaultdict(int)
        class_total   = defaultdict(int)

        with torch.no_grad():
            for images, labels in val_loader:
                images = images.view(-1, 3, 50, 50).to(device)
                labels = labels.view(-1).to(device)
                outputs = model(images)
                val_loss += criterion(outputs, labels).item()
                preds = outputs.argmax(dim=1)
                for pred, gt in zip(preds.cpu(), labels.cpu()):
                    class_total[gt.item()] += 1
                    if pred.item() == gt.item():
                        class_correct[gt.item()] += 1

        val_loss /= len(val_loader)
        overall_acc = sum(class_correct.values()) / max(sum(class_total.values()), 1) * 100
        scheduler.step()

        print(f"\n📈 Epoch {epoch+1:2d} | train_loss={train_loss:.4f}  val_loss={val_loss:.4f}  acc={overall_acc:.1f}%  lr={scheduler.get_last_lr()[0]:.2e}")

        # 클래스별 정확도 출력
        print("   클래스별 정확도:")
        for cls in range(13):
            if class_total[cls] > 0:
                acc = class_correct[cls] / class_total[cls] * 100
                bar = '█' * int(acc / 5)
                flag = " ⚠️" if acc < 50 else ""
                print(f"   {LABEL_TO_PIECE[cls]:2s}: {acc:5.1f}%  {bar}{flag}")

        # 베스트 모델 저장
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            no_improve = 0
            torch.save(model.state_dict(), MODEL_SAVE)
            print(f"   💾 베스트 모델 저장 (val_loss={val_loss:.4f})")
        else:
            no_improve += 1
            print(f"   ⏳ 개선 없음 {no_improve}/{EARLY_STOP}")
            if no_improve >= EARLY_STOP:
                print(f"\n🛑 Early stopping (val_loss {EARLY_STOP}에포크 개선 없음)")
                break

    print(f"\n🏁 학습 완료! 최고 val_loss: {best_val_loss:.4f}")
    print(f"   저장 경로: {os.path.abspath(MODEL_SAVE)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="체스 기물 CNN 학습")
    parser.add_argument("--data", required=True, help="학습 데이터 경로 (이미지 폴더)")
    args = parser.parse_args()
    train(args.data)
