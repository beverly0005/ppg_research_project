import os
import numpy as np
import pandas as pd
from scipy.signal import resample, find_peaks
from sklearn.preprocessing import MinMaxScaler
import joblib
import torch

from filtering_spline import bandpass_ppg, spline_baseline_removal_v2
from multimodal_model import MultiModalModel

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))

def glucose_range_label(val):
    if val < 70:
        return "LOW", "range-low"
    elif val > 140:
        return "HIGH", "range-high"
    else:
        return "NORMAL", "range-normal"

def run_preprocessing(raw_signal, demographics: dict):
    result = {}
    raw_signal = np.array(raw_signal, dtype=float)
    signal = -raw_signal

    OLD_FS = 40.5
    NEW_FS = 100.0
    n_new = int(len(signal) * NEW_FS / OLD_FS)
    resampled = resample(signal, n_new)
    result["original"] = raw_signal
    result["resampled"] = resampled

    filtered = bandpass_ppg(resampled, fs=NEW_FS, low=0.5, high=6.0, order=3)
    valleys, _ = find_peaks(-filtered, distance=int(0.5 * NEW_FS))
    detrended, baseline, segments = spline_baseline_removal_v2(filtered, valleys)
    
    result["filtered"] = filtered
    result["baseline"] = baseline
    result["valleys"] = valleys
    result["detrended"] = detrended
    result["segments"] = segments
    result["n_segments"] = len(segments)

    N_SEG, SEG_LEN = 15, 100
    last_15 = segments[-N_SEG:]
    lengths = [len(s) for s in last_15]
    concat_last_15 = np.concatenate(last_15)
    
    scaler_mm = MinMaxScaler(feature_range=(0, 1))
    normalized_concat = scaler_mm.fit_transform(concat_last_15.reshape(-1, 1)).flatten()
    
    normalized_concat_segments = []
    idx = 0
    for length in lengths:
        normalized_concat_segments.append(normalized_concat[idx:idx+length])
        idx += length

    padded, masks = [], []
    for seg in normalized_concat_segments:
        seg = np.asarray(seg)[:SEG_LEN]
        real_len = len(seg)
        pad = SEG_LEN - real_len
        padded.append(np.pad(seg, (0, pad), constant_values=0))
        masks.append(np.concatenate([np.ones(real_len), np.zeros(pad)]))

    signal_1500 = np.concatenate(padded)
    mask_1500 = np.concatenate(masks)
    result["signal_1500"] = signal_1500
    result["mask_1500"] = mask_1500
    result["n_seg_used"] = len(last_15)

    def sample_heart_rate(sig, fs):
        min_dist = int(0.4 * fs)
        pks, _ = find_peaks(sig, distance=min_dist, prominence=0.01)
        if len(pks) < 2: return float("nan")
        return round(60.0 / np.mean(np.diff(pks) / fs), 1)

    hr_derived = sample_heart_rate(detrended, NEW_FS)
    result["hr_derived"] = hr_derived

    age, weight, height = demographics["age"], demographics["weight"], demographics["height"]
    bmi = weight / (height / 100) ** 2
    sex, preop_htn, preop_dm = demographics["sex"], demographics["preop_htn"], demographics["preop_dm"]

    scaler_path = os.path.join(PROJECT_ROOT, "scaler.pkl")
    if os.path.exists(scaler_path):
        std_scaler = joblib.load(scaler_path)
        cont = pd.DataFrame([[age, weight, bmi, height, hr_derived if not np.isnan(hr_derived) else 70]],
                            columns=["age", "weight", "bmi", "height", "actual_hr"])
        age_s, weight_s, bmi_s, height_s, hr_s = std_scaler.transform(cont)[0]
    else:
        # Fallback pseudo-scaling if file missing
        means, stds = dict(age=50, weight=70, bmi=25, height=170, hr=75), dict(age=15, weight=15, bmi=5, height=10, hr=15)
        hr_val = hr_derived if not np.isnan(hr_derived) else 70
        age_s = (age - means["age"]) / stds["age"]
        weight_s = (weight - means["weight"]) / stds["weight"]
        bmi_s = (bmi - means["bmi"]) / stds["bmi"]
        height_s = (height - means["height"]) / stds["height"]
        hr_s = (hr_val - means["hr"]) / stds["hr"]

    result["bmi"] = bmi
    
    model_path = os.path.join(PROJECT_ROOT, "best_model.pt")
    if os.path.exists(model_path):
        try:
            model = MultiModalModel()
            model.load_state_dict(torch.load(model_path, map_location="cpu"))
            model.eval()
            x = torch.tensor(signal_1500, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
            m = torch.tensor(mask_1500, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
            demo = torch.tensor([[age_s, height_s, weight_s, bmi_s, hr_s, sex, preop_dm, preop_htn]], dtype=torch.float32)
            with torch.no_grad():
                result["prediction"] = model(x, m=m, d=demo).item()
        except Exception as e:
            result["model_error"] = str(e)
            result["prediction"] = float(np.random.normal(loc=100, scale=15))
    else:
        result["prediction"] = float(np.random.normal(loc=100, scale=15))
        result["model_error"] = "best_model.pt not found — showing demo value"

    return result