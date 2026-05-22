import torch
import torch.nn as nn
import torch.nn.functional as F

class CNNBackbone(nn.Module):
  def __init__(self, in_channels=1, out_channels=1):
    super().__init__()
    self.conv1 = nn.Conv1d(in_channels, 64, kernel_size=7, stride=2, padding=3)
    self.bn1 = nn.BatchNorm1d(64)

    self.conv2 = nn.Conv1d(64, 128, kernel_size=5, stride=2, padding=2)
    self.bn2 = nn.BatchNorm1d(128)

    self.conv3 = nn.Conv1d(128, 256, kernel_size=3, stride=2, padding=1)
    self.bn3 = nn.BatchNorm1d(256)

    # self.conv4 = nn.Conv1d(256, 128, kernel_size=3, stride=1, padding=2, dilation=2, bias=False)
    # self.bn4 = nn.BatchNorm1d(128)

    self.emb_dim = 256

  def forward(self, x):
    x = F.relu(self.bn1(self.conv1(x)))
    x = F.relu(self.bn2(self.conv2(x)))
    x = F.relu(self.bn3(self.conv3(x)))
    # x = F.relu(self.bn4(self.conv4(x)))
    return x

def masked_gap_from_zero_padding(features, mask, eps=1e-6):
  """
  features: [B, C, T_feat]
  returns:  [B, C]
  """
  if mask.dim() == 2:
        mask = mask.unsqueeze(1)
  B, C, T_feat = features.shape
  mask_feat = F.interpolate(mask.float(), size=T_feat, mode="area")  # [B,1,T_feat]
  masked = features * mask_feat
  denom = mask_feat.sum(dim=-1).clamp(min=eps)  # [B,1]
  return masked.sum(dim=-1) / denom             # [B,C]

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
        nn.Linear(64,1)
    )

  def forward(self, x, m=None, d=None):
    feats = self.cnn(x)
    sig_emb = masked_gap_from_zero_padding(feats, m)
    if d is None:
      fused = sig_emb
    else:
      demo_emb = self.mlp(d)
      # print(sig_emb.shape)
      # print(demo_emb.shape)
      fused = torch.cat([sig_emb, demo_emb], dim=1)

    out = self.head(fused).squeeze(-1)
    return out