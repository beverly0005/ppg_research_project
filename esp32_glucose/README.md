# ESP32-S3 Blood Glucose Monitor — ESP-IDF Build

## Why ESP-IDF instead of Arduino IDE?

The Arduino `TensorFlowLite_ESP32` library is a stripped-down snapshot that
omits several ops (`SUM`, `SELECT_V2`, etc.). The official
[espressif/esp-tflite-micro](https://github.com/espressif/esp-tflite-micro)
component is kept in sync with upstream tflite-micro and includes **all** ops,
plus ESP-NN SIMD acceleration (inference ~40× faster on ESP32-S3 vs no optimisation).

---

## Project Structure

```
esp32_glucose/
├── CMakeLists.txt          ← top-level ESP-IDF project file
├── partitions.csv          ← 16 MB flash partition table
├── sdkconfig.defaults      ← board settings (PSRAM, flash, USB-CDC)
├── config.h                ← pin assignments, DSP constants, scaler params
├── preprocessing.h         ← full PPG pipeline (C++)
├── model_runner.h          ← TFLite Micro inference wrapper
├── ui.h                    ← SH1106 I2C driver + keypad (no Arduino libs)
├── multimodal_model.py     ← fixed PyTorch model (use for conversion)
├── main/
│   ├── CMakeLists.txt      ← component registration + esp-tflite-micro dep
│   ├── idf_component.yml   ← pulls espressif/esp-tflite-micro automatically
│   ├── main.cpp            ← app_main() — replaces the .ino
│   └── model_data.h        ← ← YOU GENERATE THIS (see Pre-Build Steps)
├── tools/
│   ├── convert_model.py    ← PyTorch → TFLite
│   ├── list_tflite_ops.py  ← audit which ops your .tflite needs
│   ├── find_select_ops.py  ← find SELECT-producing ops in PyTorch model
│   ├── compare_models.py   ← verify TFLite matches PyTorch numerically
│   └── generate_sos.py     ← print Butterworth SOS coefficients for C
└── i2c_scanner/            ← standalone debug sketch (Arduino IDE only)
```

---

## Wiring

### SH1106G OLED (I²C)

| OLED | ESP32-S3 GPIO |
| ---- | ------------- |
| VCC  | 3.3 V         |
| GND  | GND           |
| SDA  | **8**         |
| SCL  | **9**         |

### Oximeter Module (UART1)

| Module | ESP32-S3 GPIO | Notes                  |
| ------ | ------------- | ---------------------- |
| VCC    | 3.3 V / 5 V   | check module datasheet |
| GND    | GND           |                        |
| TX     | **44** (RX)   | module TX → ESP32 RX   |
| RX     | **43** (TX)   | module RX ← ESP32 TX   |

### 4×4 Matrix Keypad

| Keypad | GPIO   | Direction    |
| ------ | ------ | ------------ |
| Row 1  | **4**  | OUTPUT       |
| Row 2  | **5**  | OUTPUT       |
| Row 3  | **6**  | OUTPUT       |
| Row 4  | **7**  | OUTPUT       |
| Col 1  | **15** | INPUT_PULLUP |
| Col 2  | **16** | INPUT_PULLUP |
| Col 3  | **17** | INPUT_PULLUP |
| Col 4  | **18** | INPUT_PULLUP |

---

## Pre-Build Steps (run once on your PC)

### 1 — Install ESP-IDF

```bash
# macOS / Linux
mkdir -p ~/esp && cd ~/esp
git clone --recursive https://github.com/espressif/esp-idf.git
cd esp-idf
git checkout v5.2.1          # latest stable
./install.sh esp32s3
source export.sh             # add to ~/.zshrc or ~/.bashrc
. ~/esp-idf-v6.0.1/export.sh
```

Verify: `idf.py --version` should print `ESP-IDF v5.x.x`.

### 2 — Generate filter coefficients

```bash
pip install scipy numpy
python tools/generate_sos.py
```

Paste the output into `preprocessing.h` `SOS_COEFF[][]`.

### 3 — Convert the model

```bash
pip install ai-edge-torch torch tensorflow onnx onnxsim onnx-tf
python tools/convert_model.py --pt best_model.pt --tflite best_model.tflite
```

This uses `multimodal_model.py` (the fixed version with `mode="nearest"` and
`torch.mean`) to guarantee no `SELECT_V2` or `SUM` ops appear.

### 4 — Audit the ops in your .tflite

```bash
python tools/list_tflite_ops.py best_model.tflite
```

Cross-check with the `build_resolver()` function in `model_runner.h`.
Add any missing `AddXxx()` calls — unlike the Arduino library,
`esp-tflite-micro` supports every op.

### 5 — Generate model_data.h

```bash
xxd -i best_model.tflite > main/model_data.h
```

Then edit the first two lines of `main/model_data.h`:

```c
// Change:
unsigned char best_model_tflite[] = { ...
unsigned int  best_model_tflite_len = ...;

// To:
const unsigned char g_model_data[] = { ...
const unsigned int  g_model_data_len = ...;
```

---

## Build & Flash

```bash
cd esp32_glucose          # project root (where top-level CMakeLists.txt is)
idf.py set-target esp32s3

# First build: IDF Component Manager downloads esp-tflite-micro automatically
idf.py build

# Flash and monitor (replace port as needed)
idf.py -p /dev/cu.usbmodem1101 flash monitor
```

Press `Ctrl+]` to exit the monitor.

Expected boot output:

```
I (xxx) GLUCOSE: [BOOT] ESP32-S3 Glucose Monitor (ESP-IDF + esp-tflite-micro)
I (xxx) UI: SH1106G init OK
I (xxx) MODEL: Arena: 2048 KB in PSRAM
I (xxx) MODEL: Loaded OK. Inputs: 3. Arena used: XXXXXX bytes
```

---

## Adding/Changing Ops in the Resolver

If you see `Didn't find op for builtin opcode 'XXX'`:

1. Run `python tools/list_tflite_ops.py best_model.tflite` to get the exact op name.
2. Find the corresponding `AddXxx()` method in the table printed by that script.
3. Add it to `build_resolver()` in `model_runner.h`.
4. Increment the resolver template parameter `<10>` to match the new count.
5. Rebuild: `idf.py build`.

Unlike the Arduino library, all ops are available — you just need to declare them.

---

## Troubleshooting

| Symptom                                 | Fix                                                                                      |
| --------------------------------------- | ---------------------------------------------------------------------------------------- |
| `idf.py: command not found`             | Run `source ~/esp/esp-idf/export.sh`                                                     |
| `Component not found: esp-tflite-micro` | Delete `managed_components/` and rebuild                                                 |
| OLED shows nothing                      | Check GPIO 8/9 wiring; run `i2c_scanner.ino` in Arduino IDE                              |
| `AllocateTensors failed`                | Check `list_tflite_ops.py` output vs `build_resolver()`                                  |
| `Schema mismatch`                       | Reconvert model with same TF version as esp-tflite-micro                                 |
| Keypad unresponsive                     | Check row/col wiring orientation                                                         |
| PSRAM alloc failed                      | Confirm `sdkconfig.defaults` applied: `idf.py menuconfig` → Component config → ESP PSRAM |
