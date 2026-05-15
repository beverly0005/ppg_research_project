#!/usr/bin/env python3
"""
tools/find_select_ops.py
────────────────────────
Traces your model and reports any ops that become SELECT in TFLite,
so you know exactly where in your code to make changes.

Usage:
    python tools/find_select_ops.py --pt best_model.pt
"""
import argparse, sys
import torch

parser = argparse.ArgumentParser()
parser.add_argument("--pt", default="best_model.pt")
args = parser.parse_args()

sys.path.insert(0, ".")
from multimodal_model import MultiModalModel

model = MultiModalModel()
model.load_state_dict(torch.load(args.pt, map_location="cpu"))
model.eval()

x    = torch.randn(1, 1, 1500)
mask = torch.ones (1, 1, 1500)
demo = torch.randn(1, 8)

# Trace the model graph
traced = torch.jit.trace(model, (x, mask, demo))
graph  = traced.graph
torch._C._jit_pass_inline(graph)

SELECT_OPS = {
    "aten::where",
    "aten::masked_fill",
    "aten::masked_fill_",
    "aten::masked_select",
    "aten::index",
}

found = []
for node in graph.nodes():
    kind = node.kind()
    if any(op in kind for op in SELECT_OPS):
        found.append(kind)

if found:
    print(f"Found {len(found)} op(s) that map to SELECT in TFLite:")
    for op in found:
        print(f"  {op}")
    print()
    print("Replacement guide:")
    print("  aten::where / torch.where(cond, a, b)")
    print("    → a * cond.float() + b * (1 - cond.float())")
    print()
    print("  tensor.masked_fill(mask == 0, val)")
    print("    → tensor + (1 - mask.float()) * val")
    print()
    print("  aten::masked_select")
    print("    → use element-wise multiply instead of boolean indexing")
else:
    print("No SELECT-producing ops found. The ONNX route should convert cleanly.")
    print("If you still see SELECT errors, try Route 1 (ai_edge_torch) in convert_model.py")
