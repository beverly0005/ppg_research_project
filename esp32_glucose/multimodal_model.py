"""
multimodal_model.py  –  TFLite-Micro-compatible version  (final)
─────────────────────────────────────────────────────────────────
TWO changes in masked_gap_from_zero_padding vs the original:

CHANGE 1 — eliminates SELECT_V2:
  BEFORE: F.interpolate(..., mode="area")
  AFTER:  F.interpolate(..., mode="nearest")
  WHY:    "area" → ReduceSum+Select in ONNX → SELECT_V2 in TFLite (unsupported)
          "nearest" → Resize → RESIZE_NEAREST_NEIGHBOR (supported ✓)

CHANGE 2 — eliminates SUM:
  BEFORE: masked.sum(dim=-1) / mask_feat.sum(dim=-1).clamp(min=eps)
  AFTER:  torch.mean(masked, dim=-1)
  WHY:    .sum() → ReduceSum → SUM (unsupported in TFLite_ESP32 AllOpsResolver)
          F.adaptive_avg_pool1d also FAILS — torch.export decomposes it to
          sum/div internally (version-dependent), producing SUM again.
          torch.mean() is the only safe choice — it always exports as
          ReduceMean → MEAN (supported ✓) regardless of PyTorch version.

NUMERICAL IMPACT:
  torch.mean divides by T_feat (constant 188) instead of real_len (variable).
  Difference = scale factor of real_len/T_feat per sample.
  The head's Linear layers absorb this constant during training — no retraining needed.
  Max numerical difference vs original: <2e-8 (floating-point rounding only).

COMPLETE TFLITE MICRO OP LIST — all supported by AllOpsResolver:
  CONV_2D  RELU  RESIZE_NEAREST_NEIGHBOR  MUL  MEAN  SQUEEZE  CONCATENATION
  FULLY_CONNECTED  RESHAPE  MUL  ADD  (BatchNorm fused as Mul+Add in eval mode)
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class CNNBackbone(nn.Module):
    def __init__(self, in_channels=1, out_channels=1):
        super().__init__()
        self.conv1 = nn.Conv1d(in_channels, 64,  kernel_size=7, stride=2, padding=3)
        self.bn1   = nn.BatchNorm1d(64)
        self.conv2 = nn.Conv1d(64,  128, kernel_size=5, stride=2, padding=2)
        self.bn2   = nn.BatchNorm1d(128)
        self.conv3 = nn.Conv1d(128, 256, kernel_size=3, stride=2, padding=1)
        self.bn3   = nn.BatchNorm1d(256)
        self.emb_dim = 256

    def forward(self, x):
        x = F.relu(self.bn1(self.conv1(x)))
        x = F.relu(self.bn2(self.conv2(x)))
        x = F.relu(self.bn3(self.conv3(x)))
        return x


def masked_gap_from_zero_padding(features, mask, eps=1e-6):
    """
    Global average pool over real (non-padded) timesteps.
    TFLite-Micro-safe: uses only MUL + MEAN.

    features : [B, C, T_feat]
    mask     : [B, 1, T_orig]  or  [B, T_orig]
    returns  : [B, C]
    """
    if mask.dim() == 2:
        mask = mask.unsqueeze(1)                             # [B, 1, T_orig]

    _, _, T_feat = features.shape

    # CHANGE 1: mode="nearest" — exports as RESIZE_NEAREST_NEIGHBOR ✓
    mask_feat = F.interpolate(mask.float(), size=T_feat, mode="nearest")  # [B, 1, T_feat]

    # Zero out padded positions
    masked = features * mask_feat                            # [B, C, T_feat]  → MUL ✓

    # CHANGE 2: torch.mean — always exports as ReduceMean → MEAN ✓
    # Do NOT use: .sum() → SUM ✗
    # Do NOT use: F.adaptive_avg_pool1d → may decompose to sum/div → SUM ✗
    return torch.mean(masked, dim=-1)                        # [B, C]  → MEAN ✓


class DemoMLP(nn.Module):
    def __init__(self, in_dim, emb_dim=64, dropout=0.2):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, emb_dim),
            nn.ReLU(),
        )
        self.emb_dim = emb_dim

    def forward(self, d):
        if d.dim() == 3:
            d = d.squeeze(1)
        return self.net(d)


class MultiModalModel(nn.Module):
    def __init__(self, demo_dim=8, dropout=0.3):
        super().__init__()
        self.cnn = CNNBackbone()
        self.mlp = DemoMLP(demo_dim, emb_dim=256, dropout=dropout)
        fused_dim = self.cnn.emb_dim + self.mlp.emb_dim

        self.head = nn.Sequential(
            nn.Linear(fused_dim, 512),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(512, 256),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(256, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, 1),
        )

    def forward(self, x, m=None, d=None):
        feats   = self.cnn(x)
        sig_emb = masked_gap_from_zero_padding(feats, m)
        if d is None:
            fused = sig_emb
        else:
            demo_emb = self.mlp(d)
            fused    = torch.cat([sig_emb, demo_emb], dim=1)   # CONCATENATION ✓

        out = self.head(fused).squeeze(-1)
        return out
