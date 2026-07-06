import queue
import threading

def get_default_state():
    return {
        "recording": False,
        "raw_signal": [],
        "timestamps": [],
        "u2_vitals": [],
        "status": "idle",
        "prediction": None,
        "preprocessed": {},
        "error": None,
        "duration": 20,
        "serial_thread": None,
        "signal_queue": queue.Queue(),
        "shutdown_event": threading.Event(), 
        "record_event": threading.Event(),
        "active_port": None,
        "active_baud": None,
        "duration_box": [60],
        "min_duration_box": [15],
        "elapsed": 0.0,
        "saved_csv_path": None,   
        "recording_start_dt": None,  
        "actual_glucose": None,
    }

PLOT_THEME = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="DM Sans", color="#e2e8f0", size=12),
    xaxis=dict(gridcolor="#1e2d47", zerolinecolor="#1e2d47", showgrid=True),
    yaxis=dict(gridcolor="#1e2d47", zerolinecolor="#1e2d47", showgrid=True),
    margin=dict(l=50, r=20, t=40, b=40),
)

# Custom CSS extracted from your original file
APP_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');
  :root { --bg: #0b0f1a; --surface: #131929; --border: #1e2d47; --accent: #00d4aa; --accent2: #ff6b6b; --accent3: #ffc857; --text: #e2e8f0; --muted: #64748b; }
  html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; background-color: var(--bg) !important; color: var(--text) !important; }
  [data-testid="stSidebar"] { background-color: var(--surface) !important; border-right: 1px solid var(--border); }
  [data-testid="stSidebar"] * { color: var(--text) !important; }
  .stApp { background-color: var(--bg) !important; }
  h1, h2, h3 { font-family: 'Space Mono', monospace !important; letter-spacing: -0.02em; }
  h1 { font-size: 2.2rem !important; background: linear-gradient(135deg, #00d4aa, #00a3ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; padding-bottom: 0.2rem; }
  .metric-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 1.2rem 1.5rem; text-align: center; position: relative; overflow: hidden; }
  .metric-card::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px; background: linear-gradient(90deg, #00d4aa, #00a3ff); }
  .metric-label { font-size: 0.72rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--muted); margin-bottom: 0.4rem; font-family: 'Space Mono', monospace; }
  .metric-value { font-size: 2rem; font-weight: 700; font-family: 'Space Mono', monospace; color: var(--accent); }
  .status-pill { display: inline-flex; align-items: center; gap: 0.4rem; padding: 0.3rem 0.8rem; border-radius: 999px; font-size: 0.8rem; font-family: 'Space Mono', monospace; font-weight: 700; letter-spacing: 0.05em; }
  .status-idle { background: #1e2d47; color: #64748b; border: 1px solid #1e2d47; }
  .status-recording { background: rgba(255,107,107,0.15); color: #ff6b6b; border: 1px solid #ff6b6b; animation: pulse 1.5s infinite; }
  .status-processing { background: rgba(255,200,87,0.15); color: #ffc857; border: 1px solid #ffc857; }
  .status-done { background: rgba(0,212,170,0.15); color: #00d4aa; border: 1px solid #00d4aa; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
  .section-header { font-family: 'Space Mono', monospace; font-size: 0.7rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--muted); border-bottom: 1px solid var(--border); padding-bottom: 0.5rem; margin-bottom: 1rem; }
  .glucose-banner { background: linear-gradient(135deg, rgba(0,212,170,0.12), rgba(0,163,255,0.12)); border: 1px solid rgba(0,212,170,0.3); border-radius: 16px; padding: 2rem; text-align: center; margin: 1rem 0; }
  .glucose-number { font-family: 'Space Mono', monospace; font-size: 4rem; font-weight: 700; color: #00d4aa; line-height: 1; }
  .glucose-label { font-size: 0.85rem; color: var(--muted); letter-spacing: 0.05em; margin-top: 0.5rem; }
  .glucose-range { display: inline-block; margin-top: 0.8rem; padding: 0.25rem 0.8rem; border-radius: 999px; font-size: 0.8rem; font-weight: 600; }
  .range-normal { background: rgba(0,212,170,0.2); color: #00d4aa; }
  .range-low { background: rgba(255,200,87,0.2); color: #ffc857; }
  .range-high { background: rgba(255,107,107,0.2); color: #ff6b6b; }
  .stNumberInput input, .stSelectbox select, .stTextInput input { background-color: var(--surface) !important; border: 1px solid var(--border) !important; color: var(--text) !important; border-radius: 8px !important; }
  .stDateInput input, .stTimeInput input, .stTimeInput [data-baseweb="select"] *, .stSelectbox [data-baseweb="select"] *, .stTextArea textarea {color: var(--text) !important;}
#   .stDateInput input, .stTimeInput input, .stTimeInput [data-baseweb="select"] *, .stSelectbox [data-baseweb="select"] *, .stTextArea textarea { color: #0b0f1a !important; }
  .stButton > button { background: linear-gradient(135deg, #00d4aa, #00a3ff) !important; color: #0b0f1a !important; border: none !important; border-radius: 8px !important; font-family: 'Space Mono', monospace !important; font-weight: 700 !important; letter-spacing: 0.05em !important; padding: 0.6rem 1.5rem !important; width: 100%; }
  .stButton > button:hover { opacity: 0.9 !important; transform: translateY(-1px) !important; }
  [data-testid="stMetric"] { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 0.8rem 1rem; }
  .stProgress > div > div { background: linear-gradient(90deg, #00d4aa, #00a3ff) !important; }
  .stAlert { border-radius: 8px !important; }
  .stTabs [data-baseweb="tab-list"] { gap: 0.5rem; border-bottom: 1px solid var(--border); }
  .stTabs [data-baseweb="tab"] { font-family: 'Space Mono', monospace; font-size: 0.78rem; letter-spacing: 0.05em; padding: 0.5rem 1rem; border-radius: 6px 6px 0 0; color: var(--muted) !important; }
  .stTabs [aria-selected="true"] { color: var(--accent) !important; border-bottom: 2px solid var(--accent) !important; background: rgba(0,212,170,0.05) !important; }
</style>
"""