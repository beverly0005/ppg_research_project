import torch
from torch import nn

class ResidualBlock(nn.Module):
    def __init__(self, in_c, out_c, stride=1):
        super().__init__()
        self.conv1 = nn.Conv1d(in_c, out_c, 3, stride, 1, bias=False)
        self.bn1 = nn.BatchNorm1d(out_c)
        self.relu = nn.ReLU(inplace=True)
        self.conv2 = nn.Conv1d(out_c, out_c, 3, 1, 1, bias=False)
        self.bn2 = nn.BatchNorm1d(out_c)
        self.shortcut = nn.Sequential()
        if stride != 1 or in_c != out_c:
            self.shortcut = nn.Sequential(nn.Conv1d(in_c, out_c, 1, stride, bias=False), nn.BatchNorm1d(out_c))

    def forward(self, x):
        return self.relu(self.bn2(self.conv2(self.relu(self.bn1(self.conv1(x))))) + self.shortcut(x))

class ResNet16_Masked(nn.Module):
    def __init__(self, input_len=3000):
        super().__init__()
        self.initial = nn.Sequential(
            nn.Conv1d(1, 64, 7, 2, 3, bias=False),
            nn.BatchNorm1d(64),
            nn.ReLU(inplace=True),
            nn.MaxPool1d(3, 2, 1)
        )
        self.layer1 = self._make_layer(64, 64, 2, 1)
        self.layer2 = self._make_layer(64, 128, 2, 2)
        self.layer3 = self._make_layer(128, 256, 2, 2)
        self.layer4 = self._make_layer(256, 512, 2, 2)

        self.fc = nn.Sequential(nn.Linear(512, 256), nn.ReLU(), nn.Dropout(0.3), nn.Linear(256, 1))

    def _make_layer(self, in_c, out_c, blocks, stride):
        layers = [ResidualBlock(in_c, out_c, stride)]
        for _ in range(1, blocks): layers.append(ResidualBlock(out_c, out_c, 1))
        return nn.Sequential(*layers)

    def forward(self, x, lengths):
        B, C, T_in = x.shape
        x = self.initial(x)
        x = self.layer1(x)
        x = self.layer2(x)
        x = self.layer3(x)
        features = self.layer4(x) # Target for GradCAM

        _, _, T_feat = features.shape
        scale = T_feat / T_in
        scaled_lens = (lengths.float() * scale).long().clamp(min=1, max=T_feat)

        indices = torch.arange(T_feat, device=x.device).unsqueeze(0)
        mask = (indices < scaled_lens.unsqueeze(1)).float().unsqueeze(1)

        masked_features = features * mask
        gap = masked_features.sum(dim=-1) / mask.sum(dim=-1).clamp(min=1e-8)

        return self.fc(gap).squeeze()