# Non-Invasive PPG Blood Glucose Research Project

## 📖 Overview

This repository contains the hardware firmware, software interfaces, and machine learning pipelines for a research project focused on non-invasive blood glucose estimation using Photoplethysmography (PPG) signals.

The project bridges edge-based hardware data collection and real-time signal processing to interpret the morphology of PPG waveforms. By feeding these processed signals—alongside patient demographics—into deep learning models, the system predicts continuous blood glucose levels without the need for traditional invasive methods.

---

## 📂 Repository Structure

The repository is divided into several interconnected modules covering different hardware form factors, sensor testing, and user interfaces.

```text
📦 ppg-research-repo
 ┣ 📂 esp32_glucose/    # ESP32-S3 Edge Inference Firmware
 ┣ 📂 glucosense/       # Streamlit UI & PyTorch Processing Pipeline
 ┣ 📂 ppg_earbud/       # Earbud PPG Hardware Module (Under Development)
 ┗ 📂 other/            # Sensor Playground & Validation Scripts

```

### 1. `esp32_glucose/` (Edge Hardware & TFLite Inference)

This directory contains the C++ ESP-IDF project for an ESP32-S3-based standalone blood glucose monitor. It is designed to capture data from an oximeter module via UART, process it on the edge, and display results directly on an I²C OLED screen.

- **Key Tech:** ESP-IDF, TensorFlow Lite Micro (with ESP-NN SIMD acceleration), C++ DSP filtering.
- **Hardware Integration:** Interacts with a UART oximeter, SH1106G OLED display, and a 4×4 Matrix Keypad.
- **Machine Learning:** Runs a heavily optimized `.tflite` multimodal model natively on the ESP32-S3, bypassing standard Arduino IDE limitations to ensure full operation support (including `SUM` and `SELECT_V2`).

### 2. `glucosense/` (Desktop UI & Real-Time Processing)

A real-time Python/Streamlit web application that serves as the central hub for live PPG visualization and heavy-duty mathematical processing.

- **Key Tech:** Python, Streamlit, PyTorch, SciPy, PySerial.
- **Signal Processing:** Handles high-frequency time-series data via background threading. Applies Butterworth bandpass filtering, systolic peak/valley detection, and Cubic Spline interpolation to remove baseline wandering.
- **Predictive Modeling:** Utilizes a multimodal PyTorch deep learning architecture combining a 1D Convolutional Neural Network (CNN) for waveform feature extraction and a Multi-Layer Perceptron (MLP) for demographic fusion (Age, BMI, etc.).

### 3. `ppg_earbud/` (Form Factor Exploration)

_Documentation pending._ This directory contains the ongoing development for adapting the PPG sensors into an earbud form factor, allowing for alternative signal acquisition sites and potentially higher-fidelity readings from the ear canal or lobe.

### 4. `other/` (Sensor Testing & Calibration)

A testing ground and sandbox environment. This folder contains various scripts and mini-projects used to validate, debug, and calibrate new hardware sensors before integrating them into the main `esp32_glucose` or `ppg_earbud` pipelines.

---

## 🚀 Getting Started

Because this project spans both embedded C++ and high-level Python, the setup instructions depend on the module you are working with:

- **For the Python UI / PC Pipeline:** Navigate to the `glucosense/` directory, install the requirements via `pip install -r requirements.txt`, and run `streamlit run app.py`.
- **For the ESP32-S3 Firmware:** Navigate to `esp32_glucose/`, ensure the ESP-IDF environment (v5.2.1+) is sourced, and use `idf.py build flash monitor` to deploy to the board.

_(For detailed setup, wiring, and build steps, please refer to the specific `README.md` inside each sub-folder)._
