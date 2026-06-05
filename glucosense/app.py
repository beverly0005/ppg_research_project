import streamlit as st
import threading
import time
import queue
import numpy as np
import pandas as pd
import os
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# Import from our modular core
from src.config import get_default_state, PLOT_THEME, APP_CSS
from src.hardware import get_serial_ports, continuous_serial_reader
from src.processing import run_preprocessing, glucose_range_label
from src.storage import RECORDINGS_DIR, load_calibration, save_calibration, save_recording_csv

# ─── Page config & CSS ──────────────────────────────────────────────────────
st.set_page_config(page_title="GlucoSense", page_icon="🩸", layout="wide", initial_sidebar_state="expanded")
st.markdown(APP_CSS, unsafe_allow_html=True)

# ─── Session state init ─────────────────────────────────────────────────────
for k, v in get_default_state().items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─── Global Hardware Manager ────────────────────────────────────────────────
@st.cache_resource
def get_hardware_manager():
    """Stores thread references globally so they survive browser refreshes."""
    return {
        "thread": None,
        "shutdown_event": threading.Event()
    }

hw_manager = get_hardware_manager()

# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🧬 Patient Demographics")
    
    st.markdown('<div class="section-header">Identity</div>', unsafe_allow_html=True)
    patient_name = st.text_input("Patient Name", value="", placeholder="e.g. Jane Doe")
    user_cal = load_calibration(patient_name)
    if patient_name.strip():
        if user_cal is not None:
            st.success(f"✅ Calibrated (Offset: {user_cal:+.1f} mg/dL)")
        else:
            st.info("ℹ️ Uncalibrated. Profile will save after next reading.")
            
    st.markdown('<div class="section-header" style="margin-top:1rem;">Measurement Context</div>', unsafe_allow_html=True)
    
    # Fix: Calculate default time only ONCE
    if "default_meal_date" not in st.session_state:
        st.session_state.default_meal_date = datetime.now().date()
    if "default_meal_time" not in st.session_state:
        st.session_state.default_meal_time = datetime.now().time().replace(second=0, microsecond=0)

    meal_date = st.date_input("Date of Last Meal", value=st.session_state.default_meal_date)
    meal_time = st.time_input("Time of Last Meal", value=st.session_state.default_meal_time, step=300)
    time_meal = f"{meal_date} {meal_time.strftime('%H:%M:%S')}"
    
    # NEW: Meal state and Split Finger Locations
    meal_state = st.selectbox("Meal State", ["Pre-meal (Fasting)", "Post-meal (Prandial)"])
    all_fingers = [
        "Right Thumb", "Right Index", "Right Middle", "Right Ring", "Right Pinky",
        "Left Thumb", "Left Index", "Left Middle", "Left Ring", "Left Pinky"
    ]
    finger_prick_location = st.selectbox("Finger Prick Location (Glucometer)", all_fingers, index=1)
    finger_sensor_location = st.selectbox("Finger Sensor Location (PPG)", ["Right Index", "Left Index"], index=0)

    st.markdown('<div class="section-header" style="margin-top:1rem;">Biometrics</div>', unsafe_allow_html=True)
    
    # NEW: Race
    race = st.selectbox("Race", ["Chinese", "Indian", "Malay", "Burmese", "Thai", "Filipino", "Vietnamese", "Caucasian", "Others"])
    
    age = st.number_input("Age", min_value=1, max_value=120, value=30, step=1)
    sex = st.selectbox("Biological Sex", ["Female (0)", "Male (1)"])
    sex_val = 0 if sex.startswith("Female") else 1
    col1, col2 = st.columns(2)
    with col1: height = st.number_input("Height (cm)", min_value=100, max_value=250, value=170, step=1)
    with col2: weight = st.number_input("Weight (kg)", min_value=20, max_value=300, value=70, step=1)

    bmi_live = weight / (height / 100) ** 2
    st.markdown(f'<div class="metric-card"><div class="metric-label">BMI</div><div class="metric-value">{bmi_live:.1f}</div></div>', unsafe_allow_html=True)

    st.markdown('<div class="section-header" style="margin-top:1rem;">Medical History</div>', unsafe_allow_html=True)
    preop_htn_val = 1 if st.selectbox("Hypertension", ["No (0)", "Yes (1)"]).startswith("Yes") else 0
    preop_dm_val = 1 if st.selectbox("Diabetes", ["No (0)", "Yes (1)"]).startswith("Yes") else 0

    st.markdown('<div class="section-header" style="margin-top:1rem;">Device</div>', unsafe_allow_html=True)
    port = st.selectbox("Serial Port", get_serial_ports())
    baud = st.selectbox("Baud Rate", [115200, 9600, 57600], index=0)
    
    min_duration = st.slider("Minimum Duration (s)", min_value=5, max_value=120, value=30, step=5)
    duration = st.slider("Recording Duration (s)", min_value=10, max_value=120, value=60, step=5)
    
    # Update duration reference for thread
    st.session_state.duration_box[0] = duration
    st.session_state.min_duration_box[0] = min_duration

    # Thread Management
    if (st.session_state.active_port != port or 
        st.session_state.active_baud != baud or 
        hw_manager["thread"] is None or 
        not hw_manager["thread"].is_alive()):
        
        if hw_manager["thread"] is not None:
            hw_manager["shutdown_event"].set()
            hw_manager["thread"].join(timeout=1.0) 
            
        hw_manager["shutdown_event"].clear()
        st.session_state.record_event.clear()
        while not st.session_state.signal_queue.empty():
            try: st.session_state.signal_queue.get_nowait()
            except queue.Empty: break
            
        st.session_state.active_port = port
        st.session_state.active_baud = baud
        
        t = threading.Thread(
            target=continuous_serial_reader,
            args=(port, baud, st.session_state.duration_box, st.session_state.min_duration_box, st.session_state.signal_queue, st.session_state.record_event, hw_manager["shutdown_event"]),
            daemon=True
        )
        t.start()
        hw_manager["thread"] = t
        time.sleep(0.2)

    st.markdown('<div class="section-header" style="margin-top:1rem;">Remarks</div>', unsafe_allow_html=True)
    remarks = st.text_area("Additional Comments", placeholder="Enter notes here...", label_visibility="collapsed")

    # Store all demographics
    demographics = dict(age=age, sex=sex_val, height=height, weight=weight, preop_htn=preop_htn_val, preop_dm=preop_dm_val, race=race)

    st.markdown('<div class="section-header" style="margin-top:1.5rem;">Saved Recordings</div>', unsafe_allow_html=True)
    if os.path.exists(RECORDINGS_DIR):
        csv_files = sorted([f for f in os.listdir(RECORDINGS_DIR) if f.endswith(".csv")], reverse=True)
        if csv_files:
            st.caption(f"{len(csv_files)} file(s) in /recordings")
            for fname in csv_files[:8]: st.markdown(f'<div style="font-size:0.7rem; color:#64748b; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">📄 {fname}</div>', unsafe_allow_html=True)
            if len(csv_files) > 8: st.caption(f"+ {len(csv_files) - 8} more…")
        else: st.caption("No recordings yet.")
    else: st.caption("No recordings yet.")

# ════════════════════════════════════════════════════════════════════════════
# MAIN CONTENT
# ════════════════════════════════════════════════════════════════════════════
st.markdown("# GlucoSense")
st.markdown("*Non-invasive blood glucose estimation via PPG signal analysis*")

status_map = {"idle": ("IDLE", "status-idle"), "recording": ("● RECORDING", "status-recording"), "processing": ("⟳ PROCESSING", "status-processing"), "done": ("✓ COMPLETE", "status-done")}
label, cls = status_map[st.session_state.status]
st.markdown(f'<span class="status-pill {cls}">{label}</span>', unsafe_allow_html=True)
st.progress(min(st.session_state.elapsed / duration, 1.0))
st.markdown("")

col_btn, _ = st.columns([1, 5])
with col_btn:
    status = st.session_state.status
    btn_label = "■ Stop Recording" if status == "recording" else ("⟳ Processing..." if status == "processing" else "▶ Start Recording")
    
    if status == "idle" and not patient_name.strip(): st.warning("Enter a patient name.")

    if st.button(btn_label, disabled=(status == "processing") or (status == "idle" and not patient_name.strip())):
        if status == "recording":
            st.session_state.record_event.clear() 
            st.session_state.recording = False
            if st.session_state.elapsed >= st.session_state.min_duration_box[0]:
                st.session_state.status = "processing"
            else:
                st.session_state.status = "idle"
                st.warning("Recording stopped before minimum duration was reached.")
            st.rerun()
        elif status in ["idle", "done"]:
            st.session_state.raw_signal, st.session_state.timestamps, st.session_state.u2_vitals = [], [], []
            st.session_state.prediction, st.session_state.preprocessed, st.session_state.error = None, {}, None
            while not st.session_state.signal_queue.empty():
                try: st.session_state.signal_queue.get_nowait()
                except queue.Empty: break
                
            st.session_state.recording = True
            st.session_state.status = "recording"
            st.session_state.elapsed = 0.0
            st.session_state.saved_csv_path = None
            st.session_state.recording_start_dt = datetime.now() 
            st.session_state.record_event.set()
            st.rerun()

# ── Queue processing ────────────────────────────────────────────────────────
if st.session_state.recording:
    st.markdown('<div class="section-header">📡 Live Signal Monitor</div>', unsafe_allow_html=True)
    live_plot_placeholder = st.empty()
    
    done = False
    while not done:
        try:
            msg_type, payload = st.session_state.signal_queue.get_nowait()
            if msg_type == "error":
                st.session_state.error = payload
                st.session_state.recording, done = False, True
                st.session_state.status = "idle"
            elif msg_type == "reset": st.session_state.raw_signal, st.session_state.timestamps = [], []
            elif msg_type == "u1":
                st.session_state.timestamps.append(payload[0])
                st.session_state.raw_signal.append(payload[1])
            elif msg_type == "u2": st.session_state.u2_vitals.append(payload)
            elif msg_type == "done":
                st.session_state.recording, done = False, True
                st.session_state.status = "processing"
            elif msg_type == "time": st.session_state.elapsed = payload
        except queue.Empty: break

    if len(st.session_state.raw_signal) > 0:
        display_data = [-x for x in st.session_state.raw_signal[-300:]]
        fig_live = go.Figure(go.Scatter(y=display_data, mode="lines", line=dict(color="#00d4aa", width=2)))
        fig_live.update_layout(**PLOT_THEME)
        fig_live.update_layout(height=250, margin=dict(l=0, r=0, t=10, b=10), xaxis=dict(visible=False, showgrid=False), yaxis=dict(visible=False, showgrid=False))
        live_plot_placeholder.plotly_chart(fig_live, width='stretch', key="live_oscilloscope")

    if done and st.session_state.status == "processing":
        if len(st.session_state.raw_signal) > 200:
            try:
                res = run_preprocessing(st.session_state.raw_signal, demographics)
                st.session_state.preprocessed, st.session_state.prediction = res, res["prediction"]
                st.session_state.status = "done"
            except Exception as e:
                st.session_state.error, st.session_state.status = f"Preprocessing failed: {e}", "idle"
        else:
            st.session_state.error, st.session_state.status = "Not enough signal data collected.", "idle"
        st.rerun() 

    if st.session_state.recording:
        time.sleep(0.1)
        st.rerun()

if st.session_state.error: st.error(f"⚠️ {st.session_state.error}")

# ── Results rendering ────────────────────────────────────────────────────────
if st.session_state.status == "done" and st.session_state.preprocessed:
    p = st.session_state.preprocessed
    st.markdown("---")

    pred = st.session_state.prediction
    name_display = patient_name.strip() or "Unknown"
    user_cal = load_calibration(patient_name)
    
    if user_cal is not None:
        final_mgdl = pred + user_cal
        final_mmol = final_mgdl / 18.0182
        banner_title = "CALIBRATED BLOOD GLUCOSE"
        subtext = f"RAW PREDICTION: {pred:.0f} mg/dL &nbsp;|&nbsp; OFFSET: {user_cal:+.1f} mg/dL"
    else:
        final_mgdl, final_mmol = pred, pred / 18.0182
        banner_title = "ESTIMATED GLUCOSE (UNCALIBRATED)"
        subtext = "Awaiting actual BGL to establish baseline."

    range_text, range_cls = glucose_range_label(final_mgdl)

    col_pred, col_actual = st.columns([3, 2])
    with col_pred:
        rec_id_disp = p.get("rec_id", "—")
        st.markdown(f"""
            <div class="glucose-banner">
              <div style="font-size:0.72rem; color:#64748b; letter-spacing:0.1em; margin-bottom:0.5rem; font-family:'Space Mono',monospace;">
                REC #{str(rec_id_disp).zfill(4)} &nbsp;·&nbsp; {name_display}
              </div>
              <div class="glucose-label" style="font-weight:bold;">{banner_title}</div>
                <div style="display:flex; flex-direction:row; justify-content:center; align-items:baseline; gap:1rem; flex-wrap:wrap;">
                    <div><span class="glucose-number">{final_mmol:.1f}</span><span class="glucose-label" style="margin-left:0.3rem;">mmol/L</span></div>
                    <div style="color:#1e2d47; font-size:2rem; align-self:center;">|</div>
                    <div><span class="glucose-number" style="font-size:2.5rem; color:#00a3ff;">{final_mgdl:.0f}</span><span class="glucose-label" style="margin-left:0.3rem;">mg/dL</span></div>
                </div>
                <div><span class="glucose-range {range_cls}">{range_text}</span></div>
                <div style="margin-top:1rem; font-size:0.75rem; color:var(--muted); font-family:'Space Mono',monospace;">{subtext}</div>
            </div>
            """, unsafe_allow_html=True)

    with col_actual:
        st.markdown('<div class="glucose-banner" style="height:100%; display:flex; flex-direction:column; justify-content:center;"><div class="glucose-label" style="margin-bottom:0.8rem;">ACTUAL BLOOD GLUCOSE</div>', unsafe_allow_html=True)
        actual_val_mmol = st.number_input("Actual BGL (mmol/L)", min_value=1.0, max_value=33.3, value=None, step=0.1, format="%.1f", label_visibility="collapsed")
        st.markdown("</div>", unsafe_allow_html=True)

        if actual_val_mmol is not None:
            actual_val_mgdl = actual_val_mmol * 18.0182
            a_range_text, a_range_cls = glucose_range_label(actual_val_mgdl)
            error_mmol = final_mmol - actual_val_mmol
            error_pct = (error_mmol / actual_val_mmol) * 100

            st.markdown(f"""
                <div style="text-align:center; margin-top:0.5rem;">
                <div style="display:flex; flex-direction:row; justify-content:center; align-items:baseline; gap:1rem;">
                    <div><span style="font-family:'Space Mono',monospace; font-size:1.8rem; font-weight:700; color:#ffc857;">{actual_val_mmol:.1f}</span><span style="font-size:0.9rem; color:#64748b; margin-left:0.3rem;">mmol/L</span></div>
                    <div style="color:#1e2d47; font-size:1.5rem; align-self:center;">|</div>
                    <div><span style="font-family:'Space Mono',monospace; font-size:1.8rem; font-weight:700; color:#ffc857;">{actual_val_mgdl:.0f}</span><span style="font-size:0.9rem; color:#64748b; margin-left:0.3rem;">mg/dL</span></div>
                </div>
                <span class="glucose-range {a_range_cls}">{a_range_text}</span>
                <div style="margin-top:0.8rem; font-size:0.8rem; font-family:'Space Mono',monospace; color:#64748b;">
                    ERROR (vs Final Display) <span style="color:{'#ff6b6b' if abs(error_pct) > 20 else '#00d4aa'};">{error_mmol:+.2f} mmol/L &nbsp;|&nbsp; {error_mmol * 18.0182:+.1f} mg/dL &nbsp; ({error_pct:+.1f}%)</span>
                </div></div>
                """, unsafe_allow_html=True)

            if st.session_state.actual_glucose != actual_val_mmol:
                st.session_state.actual_glucose = actual_val_mmol
                if user_cal is None and patient_name.strip():
                    save_calibration(patient_name, actual_val_mgdl, pred)
                    st.toast(f"✅ Calibration saved for {patient_name}!")
                try:
                    saved_path, rec_id = save_recording_csv(
                        patient_name, demographics, st.session_state.timestamps, st.session_state.raw_signal,
                        st.session_state.u2_vitals, pred, final_mgdl if user_cal is not None else None,
                        st.session_state.recording_start_dt or datetime.now(), actual_val_mmol, 
                        time_meal, meal_state, finger_prick_location, finger_sensor_location, remarks
                    )
                    st.session_state.saved_csv_path, st.session_state.preprocessed["rec_id"] = saved_path, rec_id
                except Exception as e: st.session_state.error = f"CSV write failed: {e}"
        else: st.session_state.actual_glucose = None

    # Pipeline Plots
    st.markdown("---")
    st.markdown("### 🔬 Signal Preprocessing Pipeline")
    t1, t2, t3, t4 = st.tabs(["Resampling", "Filtering & Baseline", "Segments", "Final Input"])

    with t1:
        fig = make_subplots(rows=2, cols=1, subplot_titles=("Original PPG Signal", "Inverted & Resampled to 100 Hz"))
        fig.add_trace(go.Scatter(y=p["original"], line=dict(color="#00d4aa", width=1.2)), row=1, col=1)
        fig.add_trace(go.Scatter(y=p["resampled"], line=dict(color="#00a3ff", width=1.2)), row=2, col=1)
        fig.update_layout(**PLOT_THEME, height=400, showlegend=False)
        st.plotly_chart(fig, width='stretch')

    with t2:
        fig2 = make_subplots(rows=3, cols=1, subplot_titles=("Resampled", "Filtered + Baseline + Valleys", "After Baseline Removal"))
        fig2.add_trace(go.Scatter(y=p["resampled"], line=dict(color="#64748b", width=1), name="Resampled"), row=1, col=1)
        fig2.add_trace(go.Scatter(y=p["filtered"], line=dict(color="#00d4aa", width=1.2), name="Filtered"), row=2, col=1)
        fig2.add_trace(go.Scatter(y=p["baseline"], line=dict(color="#ffc857", width=1.5, dash="dash"), name="Baseline"), row=2, col=1)
        if len(p["valleys"]) > 0: fig2.add_trace(go.Scatter(x=p["valleys"], y=p["filtered"][p["valleys"]], mode="markers", marker=dict(color="#ff6b6b", size=6), name="Valleys"), row=2, col=1)
        fig2.add_trace(go.Scatter(y=p["detrended"], line=dict(color="#00a3ff", width=1.2), name="Detrended"), row=3, col=1)
        fig2.update_layout(**PLOT_THEME, height=600)
        st.plotly_chart(fig2, width='stretch')

    with t3:
        segs = p.get("segments", [])[-15:]
        if not segs: st.warning("No segments extracted.")
        else:
            rows = (len(segs) + 4) // 5
            fig3 = make_subplots(rows=rows, cols=5, subplot_titles=[f"Pulse {i+1}" for i in range(len(segs))], horizontal_spacing=0.05, vertical_spacing=0.12)
            for i, s in enumerate(segs): fig3.add_trace(go.Scatter(y=s, line=dict(color=f"hsl({int(i * 360 / len(segs))},70%,60%)", width=1.5), showlegend=False), row=(i//5)+1, col=(i%5)+1)
            fig3.update_layout(**PLOT_THEME, height=max(250 * rows, 300))
            fig3.update_xaxes(showticklabels=False); fig3.update_yaxes(showticklabels=False)
            st.plotly_chart(fig3, width='stretch')

    with t4:
        fig4 = go.Figure()
        x_axis = np.arange(len(p["signal_1500"]))
        fig4.add_trace(go.Scatter(x=x_axis, y=p["signal_1500"], line=dict(color="#00d4aa", width=1.2), name="Signal"))
        fig4.add_trace(go.Scatter(x=x_axis, y=p["mask_1500"], line=dict(color="#ff6b6b", width=1, dash="dot"), opacity=0.5, name="Mask"))
        for i in range(1, 15): fig4.add_vline(x=i * 100, line_color="#1e2d47", line_width=1)
        fig4.update_layout(**PLOT_THEME, height=300, title="15 Padded Segments — Model Input")
        st.plotly_chart(fig4, width='stretch')

    if st.button("🔄 New Recording"):
        st.session_state.status = "idle"
        st.session_state.raw_signal, st.session_state.timestamps, st.session_state.preprocessed, st.session_state.prediction = [], [], {}, None
        st.rerun()

if st.session_state.status == "idle" and not st.session_state.raw_signal:
    st.markdown("---")
    st.markdown('<div style="text-align:center; padding: 3rem; color: #64748b;"><div style="font-size:3rem; margin-bottom:1rem;">🩺</div><div style="font-family:\'Space Mono\',monospace; font-size:0.85rem; letter-spacing:0.1em;">AWAITING SIGNAL</div></div>', unsafe_allow_html=True)