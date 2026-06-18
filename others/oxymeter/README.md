# GlucoSense — PPG Blood Glucose Predictor

A Streamlit app that records PPG signals from a USB-connected sensor, preprocesses them through the full pipeline, and predicts blood glucose levels using your trained model.

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Place your model files alongside app.py:
#    - best_model.pt         (trained PyTorch model)
#    - multimodal_model.py   (model class definition)
#    - scaler.pkl            (fitted StandardScaler from training)

# 3. Run the app
streamlit run app.py
```

## File layout expected

```
your_project/
├── app.py
├── requirements.txt
├── best_model.pt           ← your trained model
├── multimodal_model.py     ← MultiModalModel class
└── scaler.pkl              ← StandardScaler fitted on training data
```

> **Without model files:** The app still runs and demos the full preprocessing pipeline, showing a randomly sampled glucose value as a placeholder.

## Usage

1. **Sidebar** — Enter patient demographics (age, sex, height, weight, medical history)
2. **Device** — Select the correct serial port and baud rate (default: 115200)
3. **Recording** — Click **▶ Start Recording**; the live waveform streams in real time
4. **Results** — After recording, the preprocessing pipeline runs automatically and results are displayed across 4 tabs:
   - **Resampling** — Original vs 100 Hz resampled signal
   - **Filtering & Baseline** — Bandpass filter, spline baseline, valleys, detrended signal
   - **Segments** — All extracted pulse segments (up to 15)
   - **Final Input** — 1500-sample padded model input + mask overlay
5. The **blood glucose estimate** (mg/dL) is shown prominently with a Normal / Low / High indicator.

## Preprocessing pipeline (mirrors `15seg_demo_huber10.ipynb`)

| Step | Detail |
|------|--------|
| Resample | 40.5 Hz → 100 Hz via `scipy.signal.resample` |
| Bandpass filter | 0.5–6.0 Hz Butterworth (order 4) |
| MinMax scale | [0, 1] |
| Valley detection | `find_peaks` on inverted signal |
| Spline baseline | `CubicSpline` through valleys, subtracted |
| Segmentation | Slice between consecutive valleys |
| Padding | First 15 segments → 100 samples each (zero-padded) |
| Derived features | Heart rate (peak spacing), Sample entropy (m=2) |
| Demographics scaling | StandardScaler fitted on training data |
| Inference | `MultiModalModel(x, m=mask, d=demographics)` |
