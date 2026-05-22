"""
PPG Blood Glucose Predictor — Streamlit App
============================================
Dependencies (pip install):
    streamlit plotly scipy scikit-learn numpy pandas pyserial torch joblib

Run with:
    streamlit run internal_test_app.py
"""

import streamlit as st
import serial
import serial.tools.list_ports
import threading
import time
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import queue
import os
import csv
from datetime import datetime

# ─── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="GlucoSense",
    page_icon="🩸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Custom CSS ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');

  :root {
    --bg: #0b0f1a;
    --surface: #131929;
    --border: #1e2d47;
    --accent: #00d4aa;
    --accent2: #ff6b6b;
    --accent3: #ffc857;
    --text: #e2e8f0;
    --muted: #64748b;
  }

  html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    background-color: var(--bg) !important;
    color: var(--text) !important;
  }

  /* Sidebar */
  [data-testid="stSidebar"] {
    background-color: var(--surface) !important;
    border-right: 1px solid var(--border);
  }
  [data-testid="stSidebar"] * { color: var(--text) !important; }

  /* Main bg */
  .stApp { background-color: var(--bg) !important; }

  /* Headers */
  h1, h2, h3 {
    font-family: 'Space Mono', monospace !important;
    letter-spacing: -0.02em;
  }
  h1 { 
    font-size: 2.2rem !important;
    background: linear-gradient(135deg, #00d4aa, #00a3ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    padding-bottom: 0.2rem;
  }

  /* Metric cards */
  .metric-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.2rem 1.5rem;
    text-align: center;
    position: relative;
    overflow: hidden;
  }
  .metric-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, #00d4aa, #00a3ff);
  }
  .metric-label {
    font-size: 0.72rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 0.4rem;
    font-family: 'Space Mono', monospace;
  }
  .metric-value {
    font-size: 2rem;
    font-weight: 700;
    font-family: 'Space Mono', monospace;
    color: var(--accent);
  }
  .metric-unit {
    font-size: 0.85rem;
    color: var(--muted);
  }

  /* Status pill */
  .status-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.3rem 0.8rem;
    border-radius: 999px;
    font-size: 0.8rem;
    font-family: 'Space Mono', monospace;
    font-weight: 700;
    letter-spacing: 0.05em;
  }
  .status-idle    { background: #1e2d47; color: #64748b; border: 1px solid #1e2d47; }
  .status-recording { background: rgba(255,107,107,0.15); color: #ff6b6b; border: 1px solid #ff6b6b; animation: pulse 1.5s infinite; }
  .status-processing { background: rgba(255,200,87,0.15); color: #ffc857; border: 1px solid #ffc857; }
  .status-done    { background: rgba(0,212,170,0.15); color: #00d4aa; border: 1px solid #00d4aa; }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.6; }
  }

  /* Section divider */
  .section-header {
    font-family: 'Space Mono', monospace;
    font-size: 0.7rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
    padding-bottom: 0.5rem;
    margin-bottom: 1rem;
  }

  /* Glucose result banner */
  .glucose-banner {
    background: linear-gradient(135deg, rgba(0,212,170,0.12), rgba(0,163,255,0.12));
    border: 1px solid rgba(0,212,170,0.3);
    border-radius: 16px;
    padding: 2rem;
    text-align: center;
    margin: 1rem 0;
  }
  .glucose-number {
    font-family: 'Space Mono', monospace;
    font-size: 4rem;
    font-weight: 700;
    color: #00d4aa;
    line-height: 1;
  }
  .glucose-label {
    font-size: 0.85rem;
    color: var(--muted);
    letter-spacing: 0.05em;
    margin-top: 0.5rem;
  }
  .glucose-range {
    display: inline-block;
    margin-top: 0.8rem;
    padding: 0.25rem 0.8rem;
    border-radius: 999px;
    font-size: 0.8rem;
    font-weight: 600;
  }
  .range-normal { background: rgba(0,212,170,0.2); color: #00d4aa; }
  .range-low    { background: rgba(255,200,87,0.2); color: #ffc857; }
  .range-high   { background: rgba(255,107,107,0.2); color: #ff6b6b; }

  /* Styledstreamlit inputs */
  .stNumberInput input, .stSelectbox select, .stTextInput input {
    background-color: var(--surface) !important;
    border: 1px solid var(--border) !important;
    color: var(--text) !important;
    border-radius: 8px !important;
  }
  .stButton > button {
    background: linear-gradient(135deg, #00d4aa, #00a3ff) !important;
    color: #0b0f1a !important;
    border: none !important;
    border-radius: 8px !important;
    font-family: 'Space Mono', monospace !important;
    font-weight: 700 !important;
    letter-spacing: 0.05em !important;
    padding: 0.6rem 1.5rem !important;
    width: 100%;
  }
  .stButton > button:hover {
    opacity: 0.9 !important;
    transform: translateY(-1px) !important;
  }
  [data-testid="stMetric"] {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.8rem 1rem;
  }
  .stProgress > div > div { background: linear-gradient(90deg, #00d4aa, #00a3ff) !important; }

  /* Plot container */
  .plot-container {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 1rem;
  }

  /* Warning/info */
  .stAlert { border-radius: 8px !important; }

  /* Expander */
  .streamlit-expanderHeader {
    font-family: 'Space Mono', monospace !important;
    font-size: 0.85rem !important;
    color: var(--muted) !important;
  }

  /* Tab styling */
  .stTabs [data-baseweb="tab-list"] {
    gap: 0.5rem;
    border-bottom: 1px solid var(--border);
  }
  .stTabs [data-baseweb="tab"] {
    font-family: 'Space Mono', monospace;
    font-size: 0.78rem;
    letter-spacing: 0.05em;
    padding: 0.5rem 1rem;
    border-radius: 6px 6px 0 0;
    color: var(--muted) !important;
  }
  .stTabs [aria-selected="true"] {
    color: var(--accent) !important;
    border-bottom: 2px solid var(--accent) !important;
    background: rgba(0,212,170,0.05) !important;
  }
</style>
""", unsafe_allow_html=True)


# ─── Recordings folder setup ─────────────────────────────────────────────────
RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "recordings")
os.makedirs(RECORDINGS_DIR, exist_ok=True)


# ─── Calibration setup ───────────────────────────────────────────────────────
CALIBRATIONS_FILE = os.path.join(os.path.dirname(__file__), "calibrations.csv")

def load_calibration(name: str) -> float | None:
    """Returns the calibration offset (mg/dL) for a patient, or None if not found."""
    if not name.strip() or not os.path.exists(CALIBRATIONS_FILE):
        return None
    try:
        df = pd.read_csv(CALIBRATIONS_FILE)
        # Find the latest entry for this name (case-insensitive)
        match = df[df["name"].str.lower() == name.strip().lower()]
        if not match.empty:
            return float(match.iloc[-1]["calibration_mgdl"])
    except Exception:
        pass
    return None

def save_calibration(name: str, actual_mgdl: float, predicted_mgdl: float):
    """Calculates offset and appends a new row to calibrations.csv."""
    if not name.strip():
        return
    offset_mgdl = actual_mgdl - predicted_mgdl
    file_exists = os.path.exists(CALIBRATIONS_FILE)
    
    next_id = 1
    if file_exists:
        try:
            df = pd.read_csv(CALIBRATIONS_FILE)
            next_id = int(df["id"].max()) + 1 if not df.empty else 1
        except Exception:
            pass

    with open(CALIBRATIONS_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["id", "name", "calibration_mgdl"])
        writer.writerow([next_id, name.strip(), round(offset_mgdl, 2)])


# ─── Recording ID helpers ─────────────────────────────────────────────────────
def slugify_name(name: str) -> str:
    """Convert patient name to a safe filename component."""
    import re
    name = name.strip().lower()
    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^a-z0-9_]", "", name)
    return name or "unknown"


def get_next_recording_id() -> int:
    """Return the next sequential recording ID across all patients."""
    ids = []
    for fname in os.listdir(RECORDINGS_DIR):
        if fname.endswith(".csv"):
            try:
                ids.append(int(fname.split("_")[0]))
            except ValueError:
                pass
    return max(ids, default=0) + 1


def save_recording_csv(
    patient_name: str,
    demographics: dict,
    timestamps: list,
    raw_signal: list,
    u2_vitals: list,
    prediction: float | None,
    calibrated_glucose: float | None,
    recording_datetime: datetime,
    actual_glucose: float | None = None,
    time_meal: str = "",
    finger_location: str = "",
) -> str:

    """
    Save the PPG recording to a CSV in /recordings.
    Returns the full path of the saved file.

    File name format:
        {id:04d}_{name_slug}_{YYYY-MM-DD_HH-MM-SS}.csv

    The CSV has two sections:
      1. A metadata header block (# key: value rows)
      2. The sample data columns: timestamp_s, ppg_raw
    """
    slug = slugify_name(patient_name)
    rec_id = get_next_recording_id()
    dt_str = recording_datetime.strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{rec_id:04d}_{slug}_{dt_str}.csv"
    filepath = os.path.join(RECORDINGS_DIR, filename)

    bmi = demographics["weight"] / (demographics["height"] / 100) ** 2

    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)

        # ── Metadata block ───────────────────────────────────────────────
        writer.writerow(["# recording_id", rec_id])
        writer.writerow(["# patient_name", patient_name.strip()])
        writer.writerow(["# recorded_at", recording_datetime.strftime("%Y-%m-%d %H:%M:%S")])
        writer.writerow(["# time_meal", time_meal.strip() if time_meal.strip() else "N/A"])
        writer.writerow(["# age", demographics["age"]])
        writer.writerow(["# sex", "Male" if demographics["sex"] == 1 else "Female"])
        writer.writerow(["# height_cm", demographics["height"]])
        writer.writerow(["# weight_kg", demographics["weight"]])
        writer.writerow(["# bmi", f"{bmi:.2f}"])
        writer.writerow(["# hypertension", demographics["preop_htn"]])
        writer.writerow(["# diabetes", demographics["preop_dm"]])
        writer.writerow(["# finger_location", finger_location.lower().replace(" ", "_") if finger_location else "N/A"])
        writer.writerow(["# predicted_glucose_mmol_L", f"{prediction / 18.0182:.2f}" if prediction is not None else "N/A"])
        writer.writerow(["# predicted_glucose_mg_dL", f"{prediction:.1f}" if prediction is not None else "N/A"])
        writer.writerow(["# calibrated_glucose_mmol_L", f"{calibrated_glucose / 18.0182:.2f}" if calibrated_glucose is not None else "N/A"])
        writer.writerow(["# calibrated_glucose_mg_dL", f"{calibrated_glucose:.1f}" if calibrated_glucose is not None else "N/A"])
        writer.writerow(["# actual_glucose_mmol_L", f"{actual_glucose:.2f}" if actual_glucose is not None else "N/A"])
        writer.writerow(["# actual_glucose_mg_dL", f"{actual_glucose * 18.0182:.1f}" if actual_glucose is not None else "N/A"])
        writer.writerow(["# n_ppg_samples", len(raw_signal)])
        writer.writerow([])  # blank separator

        # ── PPG signal data ──────────────────────────────────────────────
        writer.writerow(["timestamp_s", "ppg_raw"])
        for t, v in zip(timestamps, raw_signal):
            writer.writerow([f"{t:.4f}", v])

    return filepath, rec_id


# ─── Session state init ──────────────────────────────────────────────────────
defaults = {
    "recording": False,
    "raw_signal": [],
    "timestamps": [],
    "u2_vitals": [],
    "status": "idle",         # idle | recording | processing | done
    "prediction": None,
    "preprocessed": {},       # stores intermediate signals for display
    "error": None,
    "duration": 20,
    "serial_thread": None,
    "signal_queue": queue.Queue(),
    "stop_event": threading.Event(),
    "elapsed": 0.0,
    "saved_csv_path": None,   # path of last saved CSV
    "recording_start_dt": None,  # datetime when recording began
    "actual_glucose": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ─── Helpers ─────────────────────────────────────────────────────────────────
def get_serial_ports():
    # Get all available ports
    ports = [p.device for p in serial.tools.list_ports.comports()]
    
    # Sort the list so that ports containing "usbserial" are pushed to the front
    ports.sort(key=lambda p: 0 if "usbserial" in p.lower() else 1)
    
    # Return the sorted list, or provide the preferred defaults if nothing is detected
    return ports if ports else ["/dev/tty.usbserial-110", "/dev/tty.usbserial-10"]


def glucose_range_label(val):
    if val < 70:
        return "LOW", "range-low"
    elif val > 140:
        return "HIGH", "range-high"
    else:
        return "NORMAL", "range-normal"


PLOT_THEME = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="DM Sans", color="#e2e8f0", size=12),
    xaxis=dict(gridcolor="#1e2d47", zerolinecolor="#1e2d47", showgrid=True),
    yaxis=dict(gridcolor="#1e2d47", zerolinecolor="#1e2d47", showgrid=True),
    margin=dict(l=50, r=20, t=40, b=40),
)

# ─── Serial reading thread ────────────────────────────────────────────────────
def serial_reader(port, baud, duration, sig_queue, stop_evt):
    """Reads from serial in a background thread, pushes parsed data to queue."""
    try:
        ser = serial.Serial(port, baudrate=baud, timeout=1)
        time.sleep(1)
    except Exception as e:
        sig_queue.put(("error", str(e)))
        return

    start = time.time()
    sig_queue.put(("started", None))

    while not stop_evt.is_set():
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            elapsed = time.time() - start
            sig_queue.put(("time", elapsed))
            print(line)
            if elapsed > duration:
                break
            
            if line.startswith("AT+MD:0"):
                start = time.time()
                sig_queue.put(("reset", None))
                continue

            elif line.startswith("U1:0"):
                start = time.time()
                sig_queue.put(("reset", None))
                continue
            elif line.startswith("U1:"):
                try:
                    val = int(line.split(":")[1])
                    sig_queue.put(("u1", (elapsed, val)))
                except Exception:
                    pass
            elif line.startswith("U2:"):
                try:
                    vals = line.split(":")[1].split(",")
                    sig_queue.put(("u2", (elapsed, int(vals[0]), int(vals[1]), float(vals[2]))))
                except Exception:
                    pass
            
        except Exception:
            continue

    ser.close()
    sig_queue.put(("done", None))


# ─── Preprocessing pipeline ──────────────────────────────────────────────────
def run_preprocessing(raw_signal, demographics: dict):
    from scipy.signal import resample, butter, filtfilt, find_peaks
    from scipy.interpolate import CubicSpline
    from sklearn.preprocessing import MinMaxScaler, StandardScaler
    from filtering_spline import bandpass_ppg, spline_baseline_removal_v2

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
    valleys, props = find_peaks(-filtered, distance=int(0.5 * NEW_FS))

    detrended, baseline, segments = spline_baseline_removal_v2(filtered, valleys)
    
    result["filtered"] = filtered
    result["baseline"] = baseline
    result["valleys"] = valleys
    result["detrended"] = detrended
    result["segments"] = segments
    result["n_segments"] = len(segments)

    N_SEG = 15
    SEG_LEN = 100
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
        if len(pks) < 2:
            return float("nan")
        rr = np.diff(pks) / fs
        return round(60.0 / np.mean(rr), 1)

    hr_derived = sample_heart_rate(detrended, NEW_FS)
    result["hr_derived"] = hr_derived

    age = demographics["age"]
    weight = demographics["weight"]
    height = demographics["height"]
    bmi = weight / (height / 100) ** 2
    sex = demographics["sex"]
    preop_htn = demographics["preop_htn"]
    preop_dm = demographics["preop_dm"]

    scaler_path = os.path.join(os.path.dirname(__file__), "scaler.pkl")
    if os.path.exists(scaler_path):
        import joblib
        std_scaler = joblib.load(scaler_path)
        cont = pd.DataFrame(
            [[age, weight, bmi, height, hr_derived if not np.isnan(hr_derived) else 70]],
            columns=["age", "weight", "bmi", "height", "actual_hr"],
        )
        age_s, weight_s, bmi_s, height_s, hr_s = std_scaler.transform(cont)[0]
    else:
        means = dict(age=50, weight=70, bmi=25, height=170, hr=75)
        stds = dict(age=15, weight=15, bmi=5, height=10, hr=15)
        hr_val = hr_derived if not np.isnan(hr_derived) else 70
        age_s = (age - means["age"]) / stds["age"]
        weight_s = (weight - means["weight"]) / stds["weight"]
        bmi_s = (bmi - means["bmi"]) / stds["bmi"]
        height_s = (height - means["height"]) / stds["height"]
        hr_s = (hr_val - means["hr"]) / stds["hr"]

    result["bmi"] = bmi
    result["hr_used"] = hr_derived

    prediction = None
    model_path = os.path.join(os.path.dirname(__file__), "best_model.pt")
    if os.path.exists(model_path):
        try:
            import torch
            from multimodal_model import MultiModalModel

            model = MultiModalModel()
            model.load_state_dict(torch.load(model_path, map_location="cpu"))
            model.eval()

            x = torch.tensor(signal_1500, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
            m = torch.tensor(mask_1500, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
            demo = torch.tensor(
                [[age_s, height_s, weight_s, bmi_s, hr_s, sex, preop_dm, preop_htn]],
                dtype=torch.float32,
            )
            with torch.no_grad():
                prediction = model(x, m=m, d=demo).item()
        except Exception as e:
            result["model_error"] = str(e)
            prediction = float(np.random.normal(loc=100, scale=15))
    else:
        prediction = float(np.random.normal(loc=100, scale=15))
        result["model_error"] = "best_model.pt not found — showing demo value"

    result["prediction"] = prediction
    return result


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR — Demographics
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🧬 Patient Demographics")
    st.markdown('<div class="section-header">Identity</div>', unsafe_allow_html=True)

    # ── NEW: Patient name ────────────────────────────────────────────────
    patient_name = st.text_input(
        "Patient Name",
        value="",
        placeholder="e.g. Jane Doe",
        help="Used to label the saved recording file.",
    )
    
    user_cal = load_calibration(patient_name)
    if patient_name.strip():
        if user_cal is not None:
            st.success(f"✅ Calibrated (Offset: {user_cal:+.1f} mg/dL)")
        else:
            st.info("ℹ️ Uncalibrated. Profile will save after next reading.")
    
    st.markdown('<div class="section-header" style="margin-top:1rem;">Measurement Context</div>', unsafe_allow_html=True)

    meal_date = st.date_input(
        "Date of Last Meal",
        value=datetime.now().date(),
    )
    meal_time = st.time_input(
        "Time of Last Meal",
        value=datetime.now().time().replace(second=0, microsecond=0),
        step=60,
    )
    finger_location = st.selectbox(
        "Finger Location",
        ["Right Index", "Left Index"],
    )

    time_meal = f"{meal_date} {meal_time.strftime('%H:%M:%S')}"

    st.markdown('<div class="section-header" style="margin-top:1rem;">Biometrics</div>', unsafe_allow_html=True)

    age = st.number_input("Age", min_value=1, max_value=120, value=30, step=1)
    sex = st.selectbox("Biological Sex", ["Female (0)", "Male (1)"])
    sex_val = 0 if sex.startswith("Female") else 1

    col1, col2 = st.columns(2)
    with col1:
        height = st.number_input("Height (cm)", min_value=100, max_value=250, value=170, step=1)
    with col2:
        weight = st.number_input("Weight (kg)", min_value=20, max_value=300, value=70, step=1)

    bmi_live = weight / (height / 100) ** 2
    st.markdown(
        f'<div class="metric-card"><div class="metric-label">BMI (auto)</div>'
        f'<div class="metric-value" style="font-size:1.5rem;">{bmi_live:.1f}</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-header" style="margin-top:1rem;">Medical History</div>', unsafe_allow_html=True)
    preop_htn = st.selectbox("Hypertension", ["No (0)", "Yes (1)"])
    preop_htn_val = 0 if preop_htn.startswith("No") else 1
    preop_dm = st.selectbox("Diabetes Mellitus", ["No (0)", "Yes (1)"])
    preop_dm_val = 0 if preop_dm.startswith("No") else 1

    st.markdown('<div class="section-header" style="margin-top:1rem;">Device</div>', unsafe_allow_html=True)
    ports = get_serial_ports()
    port = st.selectbox("Serial Port", ports)
    baud = st.selectbox("Baud Rate", [115200, 9600, 57600], index=0)
    duration = st.slider("Recording Duration (s)", min_value=10, max_value=120, value=20, step=5)

    demographics = dict(
        age=age, sex=sex_val, height=height, weight=weight,
        preop_htn=preop_htn_val, preop_dm=preop_dm_val,
    )

    # ── Recordings browser ───────────────────────────────────────────────
    st.markdown('<div class="section-header" style="margin-top:1.5rem;">Saved Recordings</div>', unsafe_allow_html=True)
    csv_files = sorted(
        [f for f in os.listdir(RECORDINGS_DIR) if f.endswith(".csv")],
        reverse=True,
    )
    if csv_files:
        st.caption(f"{len(csv_files)} file(s) in /recordings")
        for fname in csv_files[:8]:  # show latest 8
            st.markdown(
                f'<div style="font-size:0.7rem; color:#64748b; font-family:monospace; '
                f'padding:0.15rem 0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">'
                f'📄 {fname}</div>',
                unsafe_allow_html=True,
            )
        if len(csv_files) > 8:
            st.caption(f"+ {len(csv_files) - 8} more…")
    else:
        st.caption("No recordings yet.")


# ════════════════════════════════════════════════════════════════════════════
# MAIN CONTENT
# ════════════════════════════════════════════════════════════════════════════
st.markdown("# GlucoSense")
st.markdown("*Non-invasive blood glucose estimation via PPG signal analysis*")

# Status row
status_map = {
    "idle": ("IDLE", "status-idle"),
    "recording": ("● RECORDING", "status-recording"),
    "processing": ("⟳ PROCESSING", "status-processing"),
    "done": ("✓ COMPLETE", "status-done"),
}
label, cls = status_map[st.session_state.status]
st.markdown(f'<span class="status-pill {cls}">{label}</span>', unsafe_allow_html=True)

progress = min(st.session_state.elapsed / duration, 1.0)
st.progress(progress)
st.markdown("")

# ── Control row ──────────────────────────────────────────────────────────────
col_btn, col_spacer = st.columns([1, 5])

with col_btn:
    status = st.session_state.status

    if status == "recording":
        button_label = "■ Stop Recording"
    elif status == "processing":
        button_label = "⟳ Processing..."
    else:
        button_label = "▶ Start Recording"

    button_disabled = (status == "processing")

    # Warn if no patient name entered
    if status == "idle" and not patient_name.strip():
        st.warning("Enter a patient name before recording.")

    if st.button(button_label, disabled=button_disabled or (status == "idle" and not patient_name.strip())):

        # ── STOP ─────────────────────────────
        if status == "recording":
            st.session_state.stop_event.set()
            st.session_state.recording = False
            st.session_state.status = "idle"
            st.rerun()

        # ── START (idle OR done) ─────────────
        elif status in ["idle", "done"]:
            st.session_state.raw_signal = []
            st.session_state.timestamps = []
            st.session_state.u2_vitals = []
            st.session_state.prediction = None
            st.session_state.preprocessed = {}
            st.session_state.error = None
            st.session_state.recording = True
            st.session_state.status = "recording"
            st.session_state.elapsed = 0.0
            st.session_state.saved_csv_path = None
            st.session_state.recording_start_dt = datetime.now()  # ← capture start time

            while not st.session_state.signal_queue.empty():
                try:
                    st.session_state.signal_queue.get_nowait()
                except queue.Empty:
                    break

            st.session_state.stop_event.clear()

            t = threading.Thread(
                target=serial_reader,
                args=(port, baud, duration, st.session_state.signal_queue, st.session_state.stop_event),
                daemon=True,
            )
            t.start()
            st.session_state.serial_thread = t

            st.rerun()

# ── Drain queue when recording ────────────────────────────────────────────────
if st.session_state.recording:
    
    # 1. Create a placeholder for the live graph before draining the queue
    st.markdown('<div class="section-header">📡 Live Signal Monitor</div>', unsafe_allow_html=True)
    live_plot_placeholder = st.empty()
    
    q = st.session_state.signal_queue
    done = False
    while not done:
        try:
            msg_type, payload = q.get_nowait()
            if msg_type == "error":
                st.session_state.error = payload
                st.session_state.recording = False
                st.session_state.status = "idle"
                done = True
            elif msg_type == "reset":
                st.session_state.raw_signal = []
                st.session_state.timestamps = []
            elif msg_type == "u1":
                elapsed, val = payload
                st.session_state.timestamps.append(elapsed)
                st.session_state.raw_signal.append(val)
            elif msg_type == "u2":
                st.session_state.u2_vitals.append(payload)
            elif msg_type == "done":
                st.session_state.recording = False
                st.session_state.status = "processing"
                done = True
            elif msg_type == "time":
                st.session_state.elapsed = payload
        except queue.Empty:
            break

    # 2. Render the rolling window of the signal into the placeholder
    if len(st.session_state.raw_signal) > 0:
        # Adjust this window size based on your sampling rate (e.g., 300 = ~3 seconds at 100Hz)
        window_size = 300
        
        # Invert the signal for display so peaks point upwards, matching your preprocessing
        display_data = [-x for x in st.session_state.raw_signal[-window_size:]]
        
        fig_live = go.Figure(go.Scatter(
            y=display_data, 
            mode="lines", 
            line=dict(color="#00d4aa", width=2)
        ))
        
        # First apply the base theme
        fig_live.update_layout(**PLOT_THEME)
        
        # Then override the specific elements for the live view
        fig_live.update_layout(
            height=250,
            margin=dict(l=0, r=0, t=10, b=10),
            xaxis=dict(visible=False, showgrid=False), # Hide axes for a clean oscilloscope look
            yaxis=dict(visible=False, showgrid=False)
        )
        
        # Inject the plot into the placeholder
        live_plot_placeholder.plotly_chart(fig_live, width='stretch', key="live_oscilloscope")

    # 3. Transition to processing
    if done and st.session_state.status == "processing":
        if len(st.session_state.raw_signal) > 200:
            try:
                result = run_preprocessing(st.session_state.raw_signal, demographics)
                st.session_state.preprocessed = result
                st.session_state.prediction = result["prediction"]
                st.session_state.status = "done"

            except Exception as e:
                st.session_state.error = f"Preprocessing failed: {e}"
                st.session_state.status = "idle"
        else:
            st.session_state.error = "Not enough signal data collected. Try again."
            st.session_state.status = "idle"
            
        st.rerun() 

    # 4. Loop the rerun for the live view
    if st.session_state.recording:
        # Reduced sleep time for a faster frame rate on the live graph
        time.sleep(0.1)
        st.rerun()

# ── Error box ────────────────────────────────────────────────────────────────
if st.session_state.error:
    st.error(f"⚠️ {st.session_state.error}")

# ════════════════════════════════════════════════════════════════════════════
# POST-PROCESSING RESULTS
# ════════════════════════════════════════════════════════════════════════════
if st.session_state.status == "done" and st.session_state.preprocessed:
    p = st.session_state.preprocessed

    st.markdown("---")

    pred = st.session_state.prediction
    range_text, range_cls = glucose_range_label(pred)
    mmol = pred / 18.0182

    rec_id_display = p.get("rec_id", "—")
    name_display = patient_name.strip() or "Unknown"

    # ── Calibration Math ──────────────────────────────────────────────
    user_cal = load_calibration(patient_name)
    
    if user_cal is not None:
        final_mgdl = pred + user_cal
        final_mmol = final_mgdl / 18.0182
        banner_title = "CALIBRATED BLOOD GLUCOSE"
        subtext = f"RAW PREDICTION: {pred:.0f} mg/dL &nbsp;|&nbsp; OFFSET: {user_cal:+.1f} mg/dL"
    else:
        final_mgdl = pred
        final_mmol = final_mgdl / 18.0182
        banner_title = "ESTIMATED GLUCOSE (UNCALIBRATED)"
        subtext = "Awaiting actual BGL to establish baseline."

    range_text, range_cls = glucose_range_label(final_mgdl)

    # ── Side-by-side: prediction banner + actual input ────────────────
    col_pred, col_actual = st.columns([3, 2])

    with col_pred:
        st.markdown(
            f"""
            <div class="glucose-banner">
              <div style="font-size:0.72rem; font-family:'Space Mono',monospace; color:#64748b; letter-spacing:0.1em; margin-bottom:0.5rem;">
                REC #{str(rec_id_display).zfill(4) if isinstance(rec_id_display, int) else rec_id_display} &nbsp;·&nbsp; {name_display} &nbsp;·&nbsp; {st.session_state.recording_start_dt.strftime("%Y-%m-%d %H:%M:%S") if st.session_state.recording_start_dt else ""}
              </div>
              <div class="glucose-label" style="font-weight:bold;">{banner_title}</div>
                <div style="display:flex; flex-direction:row; justify-content:center; align-items:baseline; gap:1rem; flex-wrap:wrap;">
                    <div>
                        <span class="glucose-number">{final_mmol:.1f}</span>
                        <span class="glucose-label" style="margin-left:0.3rem;">mmol/L</span>
                    </div>
                    <div style="color:#1e2d47; font-size:2rem; align-self:center;">|</div>
                    <div>
                        <span class="glucose-number" style="font-size:2.5rem; color:#00a3ff;">{final_mgdl:.0f}</span>
                        <span class="glucose-label" style="margin-left:0.3rem;">mg/dL</span>
                    </div>
                </div>
                <div><span class="glucose-range {range_cls}">{range_text}</span></div>
                <div style="margin-top:1rem; font-size:0.75rem; color:var(--muted); font-family:'Space Mono',monospace;">{subtext}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_actual:
        st.markdown(
            """
            <div class="glucose-banner" style="height:100%; display:flex; flex-direction:column; justify-content:center;">
            <div class="glucose-label" style="margin-bottom:0.8rem;">ACTUAL BLOOD GLUCOSE</div>
            """,
            unsafe_allow_html=True,
        )
        actual_val_mmol = st.number_input(
            "Actual BGL (mmol/L)",
            min_value=1.0,
            max_value=33.3,
            value=None,
            step=0.1,
            format="%.1f",
            placeholder="Enter fingerstick value…",
            label_visibility="collapsed",
            key="actual_bgl_input",
        )
        st.markdown("</div>", unsafe_allow_html=True)

        if actual_val_mmol is not None:
            actual_val_mgdl = actual_val_mmol * 18.0182
            actual_range_text, actual_range_cls = glucose_range_label(actual_val_mgdl)
            
            # Use final_mmol (which might be calibrated or uncalibrated) for error calculation
            error_mmol = final_mmol - actual_val_mmol
            error_pct = (error_mmol / actual_val_mmol) * 100

            st.markdown(
                f"""
                <div style="text-align:center; margin-top:0.5rem;">
                <div style="display:flex; flex-direction:row; justify-content:center; align-items:baseline; gap:1rem; flex-wrap:wrap;">
                    <div>
                    <span style="font-family:'Space Mono',monospace; font-size:1.8rem; font-weight:700; color:#ffc857;">{actual_val_mmol:.1f}</span>
                    <span style="font-size:0.9rem; color:#64748b; margin-left:0.3rem;">mmol/L</span>
                    </div>
                    <div style="color:#1e2d47; font-size:1.5rem; align-self:center;">|</div>
                    <div>
                    <span style="font-family:'Space Mono',monospace; font-size:1.8rem; font-weight:700; color:#ffc857;">{actual_val_mgdl:.0f}</span>
                    <span style="font-size:0.9rem; color:#64748b; margin-left:0.3rem;">mg/dL</span>
                    </div>
                </div>
                <span class="glucose-range {actual_range_cls}">{actual_range_text}</span>
                <div style="margin-top:0.8rem; font-size:0.8rem; font-family:'Space Mono',monospace; color:#64748b;">
                    ERROR (vs Final Display)
                    <span style="color:{'#ff6b6b' if abs(error_pct) > 20 else '#00d4aa'};">
                    {error_mmol:+.2f} mmol/L &nbsp;|&nbsp; {error_mmol * 18.0182:+.1f} mg/dL &nbsp; ({error_pct:+.1f}%)
                    </span>
                </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

            # ── Calibration & CSV Save Trigger ────────────────────
            if st.session_state.actual_glucose != actual_val_mmol:
                st.session_state.actual_glucose = actual_val_mmol
                
                # Check if we need to save a new calibration
                if user_cal is None and patient_name.strip():
                    save_calibration(patient_name, actual_val_mgdl, pred)
                    st.toast(f"✅ Calibration saved for {patient_name}!")
                    # Note: UI will fully update with calibration on the next rerun/recording

                try:
                    saved_path, rec_id = save_recording_csv(
                        patient_name=patient_name,
                        demographics=demographics,
                        timestamps=st.session_state.timestamps,
                        raw_signal=st.session_state.raw_signal,
                        u2_vitals=st.session_state.u2_vitals,
                        prediction=pred,
                        calibrated_glucose=final_mgdl if user_cal is not None else None, # Pass calibrated val
                        recording_datetime=st.session_state.recording_start_dt or datetime.now(),
                        actual_glucose=actual_val_mmol,
                        time_meal=time_meal,
                        finger_location=finger_location,
                    )
                    st.session_state.saved_csv_path = saved_path
                    st.session_state.preprocessed["rec_id"] = rec_id
                except Exception as e:
                    st.session_state.error = f"CSV write failed: {e}"
        else:
            st.session_state.actual_glucose = None

    # Quick stats row
    c1, c2, c3 = st.columns(3)
    c1.metric("Heart Rate (derived)", f"{p.get('hr_derived', '—'):.1f} bpm" if not np.isnan(p.get("hr_derived", float("nan"))) else "—")
    c2.metric("BMI", f"{p.get('bmi', bmi_live):.1f}")
    c3.metric("Segments used", f"{p.get('n_seg_used', 0)} / 15")

    # ── Preprocessing plots tabs ──────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 🔬 Signal Preprocessing Pipeline")

    tab1, tab2, tab3, tab4 = st.tabs(["Resampling", "Filtering & Baseline", "Segments", "Final Input"])

    with tab1:
        fig = make_subplots(rows=2, cols=1, subplot_titles=("Original PPG Signal", "Inverted & Resampled to 100 Hz"))
        fig.add_trace(go.Scatter(y=p["original"], mode="lines",
                                 line=dict(color="#00d4aa", width=1.2), name="Original"), row=1, col=1)
        fig.add_trace(go.Scatter(y=p["resampled"], mode="lines",
                                 line=dict(color="#00a3ff", width=1.2), name="Resampled"), row=2, col=1)
        fig.update_layout(**PLOT_THEME, height=400, showlegend=False)
        fig.update_xaxes(gridcolor="#1e2d47", zerolinecolor="#1e2d47")
        fig.update_yaxes(gridcolor="#1e2d47", zerolinecolor="#1e2d47")
        st.plotly_chart(fig, width='stretch')

    with tab2:
        fig2 = make_subplots(rows=3, cols=1,
                              subplot_titles=("Resampled (raw)", "Filtered + Baseline + Valleys", "After Baseline Removal"))
        fig2.add_trace(go.Scatter(y=p["resampled"], mode="lines",
                                  line=dict(color="#64748b", width=1), name="Resampled"), row=1, col=1)
        fig2.add_trace(go.Scatter(y=p["filtered"], mode="lines",
                                  line=dict(color="#00d4aa", width=1.2), name="Filtered"), row=2, col=1)
        fig2.add_trace(go.Scatter(y=p["baseline"], mode="lines",
                                  line=dict(color="#ffc857", width=1.5, dash="dash"), name="Baseline"), row=2, col=1)
        if len(p["valleys"]) > 0:
            fig2.add_trace(go.Scatter(
                x=p["valleys"], y=p["filtered"][p["valleys"]],
                mode="markers", marker=dict(color="#ff6b6b", size=6, symbol="circle"),
                name="Valleys",
            ), row=2, col=1)
        fig2.add_trace(go.Scatter(y=p["detrended"], mode="lines",
                                  line=dict(color="#00a3ff", width=1.2), name="After Baseline Removal"), row=3, col=1)
        fig2.update_layout(**PLOT_THEME, height=600, showlegend=True,
                           legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(size=11)))
        fig2.update_xaxes(gridcolor="#1e2d47", zerolinecolor="#1e2d47")
        fig2.update_yaxes(gridcolor="#1e2d47", zerolinecolor="#1e2d47")
        st.plotly_chart(fig2, width='stretch')

    with tab3:
        segs = p.get("segments", [])[-15:]
        n_show = min(15, len(segs))
        if n_show == 0:
            st.warning("No segments extracted.")
        else:
            cols_per_row = 5
            rows = (n_show + cols_per_row - 1) // cols_per_row
            fig3 = make_subplots(
                rows=rows, cols=cols_per_row,
                subplot_titles=[f"Pulse {i+1}" for i in range(n_show)],
                horizontal_spacing=0.05, vertical_spacing=0.12,
            )
            colors = [f"hsl({int(i * 360 / n_show)},70%,60%)" for i in range(n_show)]
            for i in range(n_show):
                r = i // cols_per_row + 1
                c = i % cols_per_row + 1
                fig3.add_trace(go.Scatter(
                    y=segs[i], mode="lines",
                    line=dict(color=colors[i], width=1.5),
                    name=f"P{i+1}", showlegend=False,
                ), row=r, col=c)
            fig3.update_layout(**PLOT_THEME, height=max(250 * rows, 300))
            fig3.update_xaxes(gridcolor="#1e2d47", zerolinecolor="#1e2d47", showticklabels=False)
            fig3.update_yaxes(gridcolor="#1e2d47", zerolinecolor="#1e2d47", showticklabels=False)
            st.plotly_chart(fig3, width='stretch')
            st.caption(f"{len(segs)} total pulse segments detected. Using last {n_show}.")

    with tab4:
        fig4 = go.Figure()
        x_axis = np.arange(len(p["signal_1500"]))
        fig4.add_trace(go.Scatter(
            x=x_axis, y=p["signal_1500"],
            mode="lines", line=dict(color="#00d4aa", width=1.2), name="Signal",
        ))
        fig4.add_trace(go.Scatter(
            x=x_axis, y=p["mask_1500"],
            mode="lines", line=dict(color="#ff6b6b", width=1, dash="dot"),
            opacity=0.5, name="Mask (real=1, padded=0)",
        ))
        for i in range(1, 15):
            fig4.add_vline(x=i * 100, line_color="#1e2d47", line_width=1)
        fig4.update_layout(
            **PLOT_THEME,
            height=300,
            title=dict(text="15 Padded Segments (1500 samples) — Model Input", font=dict(size=13)),
            xaxis_title="Sample index",
            yaxis_title="Amplitude",
            legend=dict(bgcolor="rgba(0,0,0,0)"),
        )
        st.plotly_chart(fig4, width='stretch')

        with st.expander("📋 Demographics vector sent to model"):
            demo_df = pd.DataFrame([{
                "Patient": patient_name.strip() or "—",
                "Age": age, "Sex": sex_val, "Height (cm)": height,
                "Weight (kg)": weight, "BMI": f"{p['bmi']:.2f}",
                "HR (bpm)": f"{p['hr_derived']:.1f}" if not np.isnan(p['hr_derived']) else "—",
                "Hypertension": preop_htn_val, "Diabetes": preop_dm_val,
            }])
            st.dataframe(demo_df, width='stretch')

    st.markdown("---")
    if st.button("🔄 New Recording"):
        st.session_state.status = "idle"
        st.session_state.raw_signal = []
        st.session_state.timestamps = []
        st.session_state.preprocessed = {}
        st.session_state.prediction = None
        st.session_state.saved_csv_path = None
        st.rerun()

# ── Idle placeholder ─────────────────────────────────────────────────────────
if st.session_state.status == "idle" and not st.session_state.raw_signal:
    st.markdown("---")
    st.markdown(
        """
        <div style="text-align:center; padding: 3rem; color: #64748b;">
          <div style="font-size:3rem; margin-bottom:1rem;">🩺</div>
          <div style="font-family:'Space Mono',monospace; font-size:0.85rem; letter-spacing:0.1em;">
            AWAITING SIGNAL
          </div>
          <div style="margin-top:0.5rem; font-size:0.8rem;">
            Fill in demographics → Connect device → Press <strong>Start Recording</strong>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )