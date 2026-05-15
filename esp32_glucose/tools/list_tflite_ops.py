#!/usr/bin/env python3
"""
tools/list_tflite_ops.py
────────────────────────
Lists all ops in a .tflite file so you know exactly what to add
to the MicroMutableOpResolver in model_runner.h.

Usage:
    pip install tensorflow
    python tools/list_tflite_ops.py best_model.tflite
"""
import argparse, sys
import flatbuffers

parser = argparse.ArgumentParser()
parser.add_argument("tflite", help="Path to .tflite file")
args = parser.parse_args()

import tensorflow as tf
import json

# Use TFLite flatbuffer schema to extract ops
interp = tf.lite.Interpreter(model_path=args.tflite)
interp.allocate_tensors()

# Get op details via the internal representation
try:
    # TF 2.x method
    import tensorflow.lite.python.schema_fb as schema_fb
    with open(args.tflite, 'rb') as f:
        buf = f.read()
    model = schema_fb.Model.GetRootAsModel(buf, 0)
    subgraph = model.Subgraphs(0)
    op_codes = set()
    for i in range(subgraph.OperatorsLength()):
        op = subgraph.Operators(i)
        code = model.OperatorCodes(op.OpcodeIndex())
        builtin = code.BuiltinCode()
        op_codes.add(builtin)
    print(f"Ops in {args.tflite}:")
    for c in sorted(op_codes):
        print(f"  builtin_code={c}")
except Exception:
    pass

# Simpler fallback: just print tensor/input/output info
print(f"\nInput details:")
for d in interp.get_input_details():
    print(f"  [{d['index']}] {d['name']}  {d['shape'].tolist()}  {d['dtype'].__name__}")
print(f"Output details:")
for d in interp.get_output_details():
    print(f"  [{d['index']}] {d['name']}  {d['shape'].tolist()}  {d['dtype'].__name__}")

# Most reliable: use xxd + flatbuffers to dump all ops
print(f"\nAll ops (via TFLite schema string names):")
import subprocess, re
result = subprocess.run(
    ["python3", "-c", f"""
import flatbuffers, struct
buf = open('{args.tflite}','rb').read()
# The op names are embedded as strings in the flatbuffer
import re
names = re.findall(b'[A-Z][A-Z0-9_]{{2,30}}', buf)
unique = sorted(set(n.decode() for n in names))
for n in unique:
    print(n)
"""], capture_output=True, text=True)
# Filter to known TFLite op names
known_ops = {
    'ADD','AVERAGE_POOL_2D','CONCATENATION','CONV_2D','DEPTHWISE_CONV_2D',
    'DEQUANTIZE','FULLY_CONNECTED','LOGISTIC','LSTM','MAX_POOL_2D','MEAN',
    'MUL','PACK','PAD','QUANTIZE','RELU','RELU6','RESHAPE','RESIZE_BILINEAR',
    'RESIZE_NEAREST_NEIGHBOR','SHAPE','SOFTMAX','SPLIT','SQUEEZE','STRIDED_SLICE',
    'SUB','SUM','TRANSPOSE_CONV','UNIDIRECTIONAL_SEQUENCE_LSTM','UNPACK',
    'SELECT','SELECT_V2','DIV','EXPAND_DIMS','FILL','GATHER','MAXIMUM','MINIMUM',
    'REDUCE_MAX','REDUCE_MIN','REDUCE_PROD','BATCH_MATMUL',
}
found = sorted(known_ops & set(result.stdout.split()))
for op in found:
    print(f"  {op}")

print("""
Resolver method names (add to model_runner.h build_resolver()):
  ADD                      → AddAdd()
  AVERAGE_POOL_2D          → AddAveragePool2D()
  CONCATENATION            → AddConcatenation()
  CONV_2D                  → AddConv2D()
  FULLY_CONNECTED          → AddFullyConnected()
  MEAN                     → AddMean()
  MUL                      → AddMul()
  QUANTIZE                 → AddQuantize()
  RELU                     → AddRelu()
  RESHAPE                  → AddReshape()
  RESIZE_NEAREST_NEIGHBOR  → AddResizeNearestNeighbor()
  SQUEEZE                  → AddSqueeze()
  SUM                      → AddSum()
  SELECT_V2                → AddSelectV2()
""")
