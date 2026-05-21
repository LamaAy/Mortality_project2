"""
Saudi MOH - Electronic Death Certificate System
English UI
Hybrid ICD-10 coding:
1) Claude extracts Part I / Part II causes + intervals
2) Excel / metadata / retrieval provide candidate rows
3) Claude selects ONLY from retrieved file candidates
4) Rule-based validation checks the final certificate

Source of truth for coding = loaded ICD file rows only.
Claude is NOT allowed to invent ICD codes.
"""



import streamlit as st
import pandas as pd
import numpy as np
import re
import datetime
import os
import pickle
import html
import json
import io
from typing import List, Dict, Tuple, Optional

import anthropic

# =============================================================================
# Page config
# =============================================================================
st.set_page_config(
    page_title="Death Certificate | Saudi MOH",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =============================================================================
# CSS
# =============================================================================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

:root {
  --green:       #006940;
  --green-dark:  #004d2e;
  --green-light: #e8f5ee;
  --green-mid:   #00843D;
  --gold:        #C8A951;
  --gray-bg:     #f4f6f4;
  --text:        #1a2e1a;
  --border:      #c5d9c8;
  --muted:       #5a7060;
  --danger:      #c0392b;
  --info:        #1a4a7a;
}

html, body, [class*="css"] {
  font-family: 'Inter', sans-serif;
  direction: ltr;
  color: var(--text);
}

.main .block-container {
  background: var(--gray-bg);
  padding: 1.5rem 2rem;
  max-width: 1280px;
}

.moh-header {
  background: linear-gradient(135deg, var(--green) 0%, var(--green-mid) 55%, var(--green-dark) 100%);
  color: white;
  padding: 1.4rem 2rem;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
  box-shadow: 0 4px 18px rgba(0,105,64,.3);
  border-bottom: 3px solid var(--gold);
}
.moh-header h1 { font-size: 1.5rem; margin: 0; font-weight: 800; }
.moh-header p  { font-size: .82rem; margin: .2rem 0 0; opacity: .85; }
.moh-emblem {
  width: 80px; height: 80px;
  border: 2px solid rgba(200,169,81,.55);
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: .62rem; font-weight: 700;
  color: var(--gold);
  text-align: center;
  line-height: 1.4;
  padding: 6px;
}

section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, var(--green) 0%, var(--green-dark) 100%);
}
section[data-testid="stSidebar"] * { color: #dceee2 !important; }
section[data-testid="stSidebar"] h3 { color: white !important; font-weight: 700 !important; }
section[data-testid="stSidebar"] hr { border-color: rgba(255,255,255,.2) !important; }
section[data-testid="stSidebar"] .stTextInput input {
  background: rgba(255,255,255,.1) !important;
  border-color: rgba(255,255,255,.3) !important;
}

.section-card {
  background: white;
  border-radius: 8px;
  padding: 1.4rem 1.6rem;
  margin-bottom: 1.2rem;
  border: 1px solid var(--border);
  box-shadow: 0 1px 6px rgba(0,0,0,.05);
}

.inline-note {
  margin-top: -0.25rem;
  margin-bottom: 0.55rem;
  padding: 0.38rem 0.55rem;
  border-radius: 7px;
  font-size: 0.78rem;
  line-height: 1.35;
}
.inline-error { background:#fff1f1; color:#8a1f1f; border-left:3px solid #c0392b; }
.inline-warning { background:#fff8e6; color:#6d4b00; border-left:3px solid #d8a100; }
.inline-ok { background:#edf8f1; color:#006940; border-left:3px solid #006940; }
.mini-status {
  background:white; border:1px solid #edf2ed; border-radius:10px;
  padding:.75rem .9rem; margin-bottom:.65rem;
}
.muted-box {
  background:#f8faf8; border:1px solid #edf2ed; border-radius:8px;
  padding:.65rem .75rem; margin:.5rem 0;
}

.section-title {
  color: var(--green);
  font-size: .95rem;
  font-weight: 700;
  border-bottom: 2px solid var(--green-light);
  padding-bottom: .45rem;
  margin-bottom: 1rem;
  letter-spacing: .02em;
}

.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div > div {
  border: 1.5px solid var(--border) !important;
  border-radius: 6px !important;
  font-size: .93rem !important;
  background: #fafcfa !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
  border-color: var(--green) !important;
  box-shadow: 0 0 0 2px rgba(0,105,64,.1) !important;
}

.stButton > button,
.stDownloadButton > button {
  background: linear-gradient(135deg, var(--green), var(--green-mid));
  color: white !important;
  border: none;
  border-radius: 6px;
  font-weight: 700;
  font-size: .92rem;
  padding: .52rem 1.6rem;
  transition: box-shadow .2s, transform .15s;
  box-shadow: 0 2px 8px rgba(0,105,64,.25);
}
.stButton > button:hover,
.stDownloadButton > button:hover {
  transform: translateY(-1px);
  box-shadow: 0 5px 14px rgba(0,105,64,.35);
}

.step-bar {
  display: flex;
  justify-content: center;
  gap: 6px;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
}
.step { background:#d4ddd6; color:#5a7060; border-radius:20px; padding:5px 16px; font-size:.8rem; font-weight:600; }
.step.active { background:var(--green); color:white; }
.step.done   { background:var(--gold);  color:white; }

.cert-preview {
  background: white;
  border: 2px solid var(--green);
  border-radius: 8px;
  padding: 2.2rem;
  box-shadow: 0 4px 20px rgba(0,105,64,.1);
}
.cert-title { font-size:1.6rem; font-weight:800; color:var(--green); }
.cert-sub   { color:var(--muted); font-size:.88rem; }
.cert-field {
  display:flex; justify-content:space-between; gap:16px;
  border-bottom:1px solid #e8ede9; padding:.36rem 0; font-size:.88rem;
}
.cert-label { font-weight:700; color:var(--green); min-width:180px; }
.cert-stamp {
  border:2px solid var(--green); border-radius:50%;
  width:86px; height:86px;
  display:flex; align-items:center; justify-content:center;
  color:var(--green); font-weight:700; text-align:center; font-size:.65rem; line-height:1.5;
}

.final-block {
  border:1px solid #d8e6db;
  border-radius:6px;
  padding:.8rem 1rem;
  margin-bottom:.7rem;
  background:#f9fcfa;
}
.final-block-secondary {
  border:1px solid #d8e6db;
  border-radius:6px;
  padding:.8rem 1rem;
  margin-bottom:.7rem;
  background:#fcfcfd;
}

.stTabs [data-baseweb="tab"] { font-weight:600; font-size:.88rem; }
.stTabs [aria-selected="true"] { color:var(--green) !important; border-bottom-color:var(--green) !important; }


/* Compact agent display: show only agent name, run controls, and final output. */
.agent-checklist,
.agent-prompt,
.agent-condition,
.agent-mini-stepper {
  display: none !important;
}
.agent-card {
  padding: 1.2rem 1.35rem !important;
  min-height: auto !important;
}
.agent-subtitle {
  display: none !important;
}
.agent-output-box {
  background: #ffffff;
  border: 2px solid var(--green);
  border-radius: 18px;
  padding: 1.1rem 1.2rem;
  margin: .85rem 0 1rem;
  font-size: .95rem;
  line-height: 1.55;
  box-shadow: 0 8px 22px rgba(0, 105, 64, .08);
}
.agent-output-box.warn {
  border-color: #d8a100;
  background: #fffaf0;
}
.agent-output-box.block {
  border-color: #c0392b;
  background: #fff7f7;
}
.agent-output-status {
  font-weight: 850;
  margin-bottom: .35rem;
  color: var(--green);
}
.agent-output-status.warn { color: #a66a00; }
.agent-output-status.block { color: #c0392b; }
.agent-hidden-details-note {
  color: var(--muted);
  font-size: .78rem;
  margin-top: .25rem;
}

</style>
""", unsafe_allow_html=True)


st.markdown("""
<style>
.agent-workspace-title {
  color: var(--green);
  font-size: 1rem;
  font-weight: 800;
  margin-bottom: .6rem;
}
.agent-card {
  background: #ffffff;
  border: 1.7px solid #c8dece;
  border-radius: 18px;
  padding: 1.15rem 1.25rem;
  min-height: auto;
  box-shadow: 0 8px 22px rgba(0, 105, 64, .08);
  margin-bottom: 1rem;
}
.agent-card.active {
  border: 2px solid var(--green);
  box-shadow: 0 10px 28px rgba(0, 105, 64, .14);
}
.agent-card.done {
  border: 2px solid var(--gold);
}
.agent-card.blocked {
  border: 2px solid var(--danger);
}
.agent-kicker {
  display: inline-block;
  background: var(--green-light);
  color: var(--green);
  border-radius: 999px;
  padding: .22rem .65rem;
  font-size: .72rem;
  font-weight: 800;
  letter-spacing: .03em;
  margin-bottom: .45rem;
}
.agent-title {
  font-size: 1.05rem;
  font-weight: 850;
  color: #1a2e1a;
  margin-bottom: .25rem;
}
.agent-subtitle {
  color: var(--muted);
  font-size: .82rem;
  line-height: 1.45;
  margin-bottom: .8rem;
}
.agent-checklist {
  background: #f8faf8;
  border: 1px solid #edf2ed;
  border-radius: 12px;
  padding: .75rem .85rem;
  margin: .7rem 0;
}
.agent-checklist ul {
  margin: .25rem 0 .1rem 1.1rem;
  padding: 0;
  font-size: .82rem;
  line-height: 1.55;
}
.agent-prompt {
  background: #f7faf8;
  border: 1px dashed #bed4c3;
  border-radius: 12px;
  padding: .75rem .85rem;
  color: #435649;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
  font-size: .72rem;
  line-height: 1.5;
  white-space: pre-wrap;
}
.agent-condition {
  background: #f0f4ff;
  border-left: 4px solid #1a4a7a;
  border-radius: 10px;
  padding: .65rem .8rem;
  font-size: .82rem;
  margin: .75rem 0;
}
.agent-status-pass {
  background:#edf8f1;
  color:#006940;
  border:1px solid #b8dec6;
  border-radius:10px;
  padding:.55rem .75rem;
  font-size:.84rem;
  margin:.5rem 0;
}
.agent-status-warn {
  background:#fff8e6;
  color:#6d4b00;
  border:1px solid #edd187;
  border-radius:10px;
  padding:.55rem .75rem;
  font-size:.84rem;
  margin:.5rem 0;
}
.agent-status-error {
  background:#fff1f1;
  color:#8a1f1f;
  border:1px solid #efb8b8;
  border-radius:10px;
  padding:.55rem .75rem;
  font-size:.84rem;
  margin:.5rem 0;
}
.agent-mini-stepper {
  display:flex;
  gap:8px;
  align-items:center;
  margin-bottom:.85rem;
  flex-wrap:wrap;
}
.agent-step-pill {
  border-radius:999px;
  padding:.25rem .62rem;
  font-size:.72rem;
  font-weight:800;
  background:#d4ddd6;
  color:#526356;
}
.agent-step-pill.active {
  background:var(--green);
  color:white;
}
.agent-step-pill.done {
  background:var(--gold);
  color:white;
}
.doctor-edit-panel {
  background:white;
  border:1px solid var(--border);
  border-radius:18px;
  padding:1rem 1.15rem;
  box-shadow:0 6px 18px rgba(0,0,0,.04);
}
.agent-arrow {
  text-align:center;
  color:var(--green);
  font-size:1.55rem;
  font-weight:900;
  margin:.35rem 0;
}
.agent-preview-card {
  background:#ffffff;
  border:2px solid var(--green);
  border-radius:18px;
  padding:1rem 1.1rem;
  box-shadow:0 8px 22px rgba(0,105,64,.08);
  margin-bottom:.9rem;
}
.agent-preview-title {
  font-size:1.05rem;
  font-weight:850;
  color:#1a2e1a;
  margin:.25rem 0 .4rem;
}
.agent-preview-subtitle {
  color:var(--muted);
  font-size:.82rem;
  line-height:1.45;
  margin-bottom:.7rem;
}
.agent-goodbad-grid {
  display:grid;
  grid-template-columns:1fr;
  gap:.65rem;
}
.agent-good-box,
.agent-bad-box {
  border-radius:12px;
  padding:.75rem .85rem;
  font-size:.82rem;
  line-height:1.5;
}
.agent-good-box {
  background:#edf8f1;
  border:1px solid #b8dec6;
  color:#0c5c35;
}
.agent-bad-box {
  background:#fff8e6;
  border:1px solid #edd187;
  color:#6d4b00;
}
.agent-bad-box.error {
  background:#fff1f1;
  border-color:#efb8b8;
  color:#8a1f1f;
}
.agent-good-box ul,
.agent-bad-box ul {
  margin:.25rem 0 0 1.05rem;
  padding:0;
}
.agent-good-box li,
.agent-bad-box li {
  margin:.18rem 0;
}
</style>
""", unsafe_allow_html=True)

# =============================================================================
# Header
# =============================================================================
st.markdown("""
<div class="moh-header">
  <div>
    <h1>Electronic Death Certificate System</h1>
    <p>Ministry of Health | Kingdom of Saudi Arabia</p>
    <p style="font-size:.76rem;opacity:.72">Claude extraction + file-only ICD coding</p>
  </div>
  <div class="moh-emblem">MOH<br>KSA<br>Death<br>Cert</div>
</div>
""", unsafe_allow_html=True)

# =============================================================================
# Secrets / IDs
# =============================================================================
try:
    API_KEY = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    API_KEY = None

GDRIVE_EMBEDDINGS_ID = "1CxCGihYnqyaIc-F0IJwHNUTpLRHGmy8Y"
GDRIVE_FAISS_ID      = "17F5rDFoT3iDbRKKiHCMiSB9ZrH0ecVTP"
GDRIVE_METADATA_ID   = "1nUUdhivH1XIPGXkvWjrapxzuKfbM445B"
GDRIVE_EXCEL_ID      = "1h54uBVeae8r6xC0MJI1-G3uRJwLc7K-y"

# Optional local TABB file. In Streamlit Cloud, place tabb_rules.csv beside this app file.
TABB_RULES_CSV_PATHS = [
    "tabb_rules.csv",
    os.path.join(os.getcwd(), "tabb_rules.csv"),
    "/mnt/data/tabb_rules.csv",
]


CACHE_DIR = os.path.join(os.path.expanduser("~"), ".icd10_hybrid_cache_v1")
EMBED_MODEL_NAME = "pritamdeka/S-PubMedBert-MS-MARCO"
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# =============================================================================
# Helpers
# =============================================================================
def escape(x) -> str:
    return html.escape("" if x is None else str(x))

def sanitize_filename(s: str) -> str:
    s = re.sub(r"[^\w\-\.]+", "_", str(s).strip(), flags=re.UNICODE)
    return s[:120] if s else "certificate"

def normalize_text_basic(text: str) -> str:
    if not text:
        return ""
    text = str(text).strip().lower()
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text

def tokenize(text: str) -> List[str]:
    text = normalize_text_basic(text)
    return re.findall(r"[A-Za-z]+\d*\.?\d*|[\u0600-\u06FF]+|\d+", text)

def specificity_score(code: str) -> int:
    if not code:
        return 0
    return len(str(code).strip().upper().replace(".", ""))

def is_gender_allowed(gender_restriction: str, sex_value: str) -> bool:
    gr = normalize_text_basic(gender_restriction)
    sx = normalize_text_basic(sex_value)
    if not gr or gr in {"", "none", "n/a", "nan", "unknown"}:
        return True
    if "female" in gr and "male" in sx:
        return False
    if "male" in gr and "female" in sx:
        return False
    return True

def acceptable_main_bool(x: str) -> Optional[bool]:
    t = normalize_text_basic(x)
    if t in {"acceptable", "yes", "true", "1"}:
        return True
    if t in {"not acceptable", "no", "false", "0"}:
        return False
    return None

def query_indicates_external_cause(query: str) -> bool:
    q = normalize_text_basic(query)
    triggers = [
        "accident", "injury", "collision", "fall", "burn", "poisoning", "vehicle",
        "atv", "road traffic", "assault", "homicide", "suicide", "gunshot", "stab"
    ]
    return any(t in q for t in triggers)

def diabetes_type_hint(query: str) -> Optional[str]:
    q = normalize_text_basic(query)
    if re.search(r"\b(type\s*2|type\s*ii|non[-\s]?insulin[-\s]?dependent)\b", q):
        return "type2"
    if re.search(r"\b(type\s*1|type\s*i|insulin[-\s]?dependent)\b", q):
        return "type1"
    return None

# =============================================================================
# Query expansions
# =============================================================================
LAY_QUERY_EXPANSIONS = {
    "heart attack": ["acute myocardial infarction", "myocardial infarction", "coronary thrombosis"],
    "stroke": ["cerebral infarction", "cerebrovascular accident", "intracranial hemorrhage"],
    "kidney failure": ["renal failure", "chronic kidney disease", "acute kidney failure"],
    "high blood pressure": ["hypertension", "essential hypertension"],
    "diabetes": ["diabetes mellitus"],
    "type 2 diabetes": ["type 2 diabetes mellitus", "non insulin dependent diabetes mellitus"],
    "type ii diabetes": ["type 2 diabetes mellitus", "non insulin dependent diabetes mellitus"],
    "type 1 diabetes": ["type 1 diabetes mellitus", "insulin dependent diabetes mellitus"],
    "type i diabetes": ["type 1 diabetes mellitus", "insulin dependent diabetes mellitus"],
    "fluid in lungs": ["pulmonary edema", "acute pulmonary edema"],
    "lung infection": ["pneumonia", "lower respiratory infection"],
    "brain bleed": ["intracranial hemorrhage", "cerebral hemorrhage"],
    "blood clot in lung": ["pulmonary embolism"],
    "cancer spread": ["metastatic malignant neoplasm", "secondary malignant neoplasm"],
    "ards": ["acute respiratory distress syndrome"],
    "acute respiratory distress syndrome": ["ards"],
    "peritonitis": ["generalized peritonitis"],
    "diverticulitis": ["sigmoid diverticulitis", "diverticulitis of large intestine"],
    "septic shock": ["septic shock", "sepsis"],
    "obesity": ["obesity"],
    "metabolic syndrome": ["metabolic syndrome"],
    "vasculopathy": ["angiopathy", "vascular disease"],
}

STOPWORDS = {
    "the", "and", "or", "with", "without", "due", "to", "secondary", "of", "in",
    "acute", "chronic", "history", "known", "generalized", "severe", "mild",
    "patient", "died", "from", "which", "developed", "resulted", "occurred",
    "context", "background", "approximately", "about", "prior", "before", "after",
    "complication", "condition", "lasting", "present", "nearly", "itself"
}

# =============================================================================
# Google Drive download
# =============================================================================
def _gdrive_download(file_id: str, dest_path: str) -> None:
    import requests

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    session = requests.Session()
    url = "https://drive.google.com/uc"

    response = session.get(url, params={"export": "download", "id": file_id}, stream=True)
    token = next((v for k, v in response.cookies.items() if k.startswith("download_warning")), None)

    if token:
        response = session.get(url, params={"export": "download", "id": file_id, "confirm": token}, stream=True)

    if b"confirm=" in response.content[:5000]:
        m = re.search(rb'confirm=([0-9A-Za-z_\-]+)', response.content[:5000])
        if m:
            response = session.get(
                url,
                params={"export": "download", "id": file_id, "confirm": m.group(1).decode()},
                stream=True,
            )

    response.raise_for_status()
    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                f.write(chunk)

# =============================================================================
# Data loading
# =============================================================================
EXPECTED_COLS = [
    "Id", "Code", "CodeFormatted", "ShortDesc", "LongDesc",
    "HIPPA", "Deleted", "Classification", "AcceptableMain",
    "GenderRestriction", "MatchSource", "MatchedFromCode", "Note"
]

def _normalise_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # Accept both internal column names and Excel-friendly names.
    alias_map = {
        "Code (Formatted)": "CodeFormatted",
        "Code Formatted": "CodeFormatted",
        "Short Description": "ShortDesc",
        "Long Description": "LongDesc",
        "Acceptable as Main Cause": "AcceptableMain",
        "Gender Restriction": "GenderRestriction",
        "Match Source": "MatchSource",
        "Matched From Code": "MatchedFromCode",
    }
    df = df.rename(columns={c: alias_map.get(c, c) for c in df.columns})

    if "CodeFormatted" not in df.columns:
        if len(df.columns) == len(EXPECTED_COLS):
            df.columns = EXPECTED_COLS
        else:
            raise ValueError(f"Unexpected schema. Expected {len(EXPECTED_COLS)} columns, got {len(df.columns)}.")

    if "Deleted" in df.columns:
        df = df[df["Deleted"].astype(str).str.strip().str.lower() != "yes"].copy()

    df = df.dropna(subset=["Code"]).reset_index(drop=True)

    for col in ["Code", "CodeFormatted", "ShortDesc", "LongDesc",
                "AcceptableMain", "GenderRestriction", "Classification", "Note"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    if "EmbedText" not in df.columns:
        df["EmbedText"] = (
            df["CodeFormatted"].fillna("") + " " +
            df["ShortDesc"].fillna("") + " " +
            df["LongDesc"].fillna("") + " " +
            df["Note"].fillna("")
        )

    df["lookup_code"] = df["CodeFormatted"].str.upper().str.replace(" ", "", regex=False)
    df["combined_text"] = (
        df["ShortDesc"].fillna("") + " " +
        df["LongDesc"].fillna("") + " " +
        df["Note"].fillna("")
    ).str.lower()

    return df.reset_index(drop=True)

@st.cache_resource(show_spinner="Loading Excel from Google Drive...")
def load_excel_from_drive_file(file_id: str) -> pd.DataFrame:
    os.makedirs(CACHE_DIR, exist_ok=True)
    xlsx_path = os.path.join(CACHE_DIR, "icd_source.xlsx")
    if not os.path.exists(xlsx_path):
        _gdrive_download(file_id, xlsx_path)
    df = pd.read_excel(xlsx_path)
    return _normalise_df(df)

@st.cache_resource(show_spinner="Loading metadata...")
def load_metadata(metadata_id: str) -> pd.DataFrame:
    os.makedirs(CACHE_DIR, exist_ok=True)
    meta_path = os.path.join(CACHE_DIR, "metadata.pkl")
    if not os.path.exists(meta_path):
        _gdrive_download(metadata_id, meta_path)
    with open(meta_path, "rb") as f:
        df = pickle.load(f)
    return _normalise_df(df)

@st.cache_resource(show_spinner="Building BM25 index...")
def build_bm25_index(df: pd.DataFrame):
    try:
        from rank_bm25 import BM25Okapi
        corpus = [tokenize(x) for x in df["EmbedText"].tolist()]
        return BM25Okapi(corpus)
    except Exception:
        return None

@st.cache_resource(show_spinner="Loading embedding model...")
def get_embed_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(EMBED_MODEL_NAME)

@st.cache_resource(show_spinner="Loading FAISS resources...")
def load_faiss_resources(emb_id: str, faiss_id: str):
    os.makedirs(CACHE_DIR, exist_ok=True)
    emb_path = os.path.join(CACHE_DIR, "embeddings.npy")
    faiss_path = os.path.join(CACHE_DIR, "icd.index")

    try:
        import faiss
    except Exception:
        return None

    if faiss_id and not os.path.exists(faiss_path):
        try:
            _gdrive_download(faiss_id, faiss_path)
        except Exception:
            pass

    if os.path.exists(faiss_path):
        try:
            return faiss.read_index(faiss_path)
        except Exception:
            pass

    if emb_id and not os.path.exists(emb_path):
        try:
            _gdrive_download(emb_id, emb_path)
        except Exception:
            pass

    if os.path.exists(emb_path):
        try:
            emb = np.load(emb_path).astype("float32")
            faiss.normalize_L2(emb)
            index = faiss.IndexFlatIP(emb.shape[1])
            index.add(emb)
            return index
        except Exception:
            return None

    return None

# =============================================================================
# Retrieval
# =============================================================================
def expand_query(query: str) -> str:
    q = normalize_text_basic(query)
    expansions = []
    for key, vals in LAY_QUERY_EXPANSIONS.items():
        if key in q:
            expansions.extend(vals)
    return (query + " " + " ".join(expansions)).strip() if expansions else query

def row_to_dict(row, score: float = 0.0) -> Dict:
    return {
        "code": str(row.get("Code", "")),
        "code_formatted": str(row.get("CodeFormatted", "")),
        "short_desc": str(row.get("ShortDesc", "")),
        "long_desc": str(row.get("LongDesc", "")),
        "acceptable_main": str(row.get("AcceptableMain", "")),
        "gender_restriction": str(row.get("GenderRestriction", "")),
        "classification": str(row.get("Classification", "")),
        "note": str(row.get("Note", "")),
        "score": float(score),
    }

def exact_code_search(df: pd.DataFrame, query: str) -> List[Tuple[int, float]]:
    q = query.strip().upper().replace(" ", "")
    if re.fullmatch(r"[A-TV-Z][0-9][0-9](?:\.[0-9A-Z]+)?", q):
        mask = df["lookup_code"] == q
        hits = df.index[mask].tolist()
        return [(int(i), 1.0) for i in hits]
    return []

def semantic_search(df: pd.DataFrame, faiss_index, query: str, top_k: int = 50) -> List[Tuple[int, float]]:
    if faiss_index is None:
        return []
    try:
        model = get_embed_model()
        q_vec = model.encode([expand_query(query)], normalize_embeddings=True, convert_to_numpy=True).astype("float32")
        scores, indices = faiss_index.search(q_vec, top_k)
        return [(int(idx), float(score)) for score, idx in zip(scores[0], indices[0]) if idx != -1 and 0 <= idx < len(df)]
    except Exception:
        return []

def bm25_search(df: pd.DataFrame, bm25, query: str, top_k: int = 50) -> List[Tuple[int, float]]:
    q = expand_query(query)
    toks = tokenize(q)
    if not toks:
        return []

    if bm25 is not None:
        try:
            scores = bm25.get_scores(toks)
            order = np.argsort(scores)[::-1][:top_k]
            mx = float(scores[order[0]]) if len(order) > 0 and scores[order[0]] > 0 else 1.0
            return [(int(i), float(scores[i]) / (mx + 1e-9)) for i in order if scores[i] > 0]
        except Exception:
            pass

    scored = []
    tokset = set([t for t in toks if t not in STOPWORDS])
    for i, txt in enumerate(df["combined_text"].tolist()):
        row_tokens = set(tokenize(txt))
        overlap = len(tokset & row_tokens)
        if overlap > 0:
            scored.append((i, float(overlap)))
    scored = sorted(scored, key=lambda x: x[1], reverse=True)[:top_k]
    mx = scored[0][1] if scored else 1.0
    return [(i, s / (mx + 1e-9)) for i, s in scored]

def reciprocal_rank_fusion(rank_lists: List[List[Tuple[int, float]]], k: int = 60) -> Dict[int, float]:
    fused = {}
    for lst in rank_lists:
        for rank, (idx, _) in enumerate(lst, start=1):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank)
    return fused

def candidate_adjustment_score(row: pd.Series, query: str, sex_value: str, role: str) -> Tuple[float, List[str]]:
    reasons = []
    score = 0.0

    q = normalize_text_basic(query)
    text = normalize_text_basic(row["combined_text"])
    code = str(row["CodeFormatted"]).upper()
    acc = acceptable_main_bool(row["AcceptableMain"])
    gender_ok = is_gender_allowed(row["GenderRestriction"], sex_value)

    if q and q in text:
        score += 4.0
        reasons.append("query phrase found in ICD text")

    q_tokens = [t for t in tokenize(q) if t not in STOPWORDS]
    row_tokens = set(tokenize(text))
    overlap = len(set(q_tokens) & row_tokens)
    score += min(overlap, 8) * 0.5
    if overlap:
        reasons.append(f"token overlap={overlap}")

    score += specificity_score(code) * 0.03

    if role in {"immediate", "contributing"}:
        if acc is True:
            score += 0.7
        elif acc is False:
            score -= 1.0
            reasons.append("not acceptable as main cause")

    if not gender_ok:
        score -= 3.0
        reasons.append("gender restriction conflict")

    if code[:1] in {"V", "W", "X", "Y"} and not query_indicates_external_cause(q):
        score -= 6.0
        reasons.append("external cause chapter penalized")

    if code.startswith("Y") and not query_indicates_external_cause(q):
        score -= 4.0
        reasons.append("procedure/misadventure code penalized")

    if "acute respiratory distress syndrome" in q or re.fullmatch(r"ards", q):
        if code.startswith("J80"):
            score += 3.0
            reasons.append("preferred ARDS code")

    if "septic shock" in q:
        if code.startswith("R57.2"):
            score += 3.0
            reasons.append("preferred septic shock code")
        if code.startswith("T81.12"):
            score -= 3.0
            reasons.append("postprocedural septic shock penalized")

    if "diverticulitis" in q and code.startswith("K57"):
        score += 3.0
        reasons.append("preferred diverticulitis code")

    if "peritonitis" in q and code.startswith("K65"):
        score += 2.5
        reasons.append("preferred peritonitis code")

    d_hint = diabetes_type_hint(q)
    if d_hint == "type2":
        if code.startswith("E11"):
            score += 2.0
            reasons.append("matches type 2 diabetes")
        if code.startswith("E10"):
            score -= 2.0
            reasons.append("type 1 diabetes penalized")
    elif d_hint == "type1":
        if code.startswith("E10"):
            score += 2.0
            reasons.append("matches type 1 diabetes")
        if code.startswith("E11"):
            score -= 2.0
            reasons.append("type 2 diabetes penalized")

    if "obesity" in q and code.startswith("E66"):
        score += 2.5
        reasons.append("preferred obesity code")

    if "metabolic syndrome" in q and code.startswith(("E88.81", "E88")):
        score += 2.5
        reasons.append("preferred metabolic syndrome code")

    if "vasculopathy" in q or "angiopathy" in q:
        if code.startswith("E11.5"):
            score += 2.0
            reasons.append("preferred diabetic angiopathy family")

    return score, reasons

def search_icd_candidates(
    df_source: pd.DataFrame,
    faiss_index,
    bm25,
    query: str,
    sex_value: str,
    role: str,
    top_k: int = 12,
) -> List[Dict]:
    exact_hits = exact_code_search(df_source, query)
    sem_hits = semantic_search(df_source, faiss_index, query, top_k=50)
    bm_hits = bm25_search(df_source, bm25, query, top_k=50)

    fused = reciprocal_rank_fusion([exact_hits, sem_hits, bm_hits], k=60)

    candidates = []
    for idx, rrf_score in fused.items():
        row = df_source.iloc[idx]
        adj_score, reasons = candidate_adjustment_score(row, query, sex_value, role)
        total = rrf_score + adj_score
        item = row_to_dict(row, total)
        item["reasons"] = reasons
        candidates.append(item)

    candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)

    seen = set()
    unique = []
    for c in candidates:
        code = c["code_formatted"]
        if code not in seen:
            seen.add(code)
            unique.append(c)
        if len(unique) >= top_k:
            break
    return unique

def get_row_by_code(df: pd.DataFrame, code_str: str) -> Optional[pd.Series]:
    if df is None or not code_str:
        return None
    c = code_str.strip().upper().replace(" ", "")
    matches = df[df["lookup_code"] == c]
    if not matches.empty:
        return matches.iloc[0]
    return None

# =============================================================================
# Claude JSON helpers (robust)
# =============================================================================
def _extract_text_from_claude_response(resp) -> str:
    parts = []
    for block in getattr(resp, "content", []):
        txt = getattr(block, "text", None)
        if txt:
            parts.append(txt)
    return "\n".join(parts).strip()

def _extract_json_candidate(text: str) -> str:
    if not text:
        return ""

    text = text.strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    if (text.startswith("{") and text.endswith("}")) or (text.startswith("[") and text.endswith("]")):
        return text

    start_obj = text.find("{")
    end_obj = text.rfind("}")
    if start_obj != -1 and end_obj != -1 and end_obj > start_obj:
        return text[start_obj:end_obj + 1]

    start_arr = text.find("[")
    end_arr = text.rfind("]")
    if start_arr != -1 and end_arr != -1 and end_arr > start_arr:
        return text[start_arr:end_arr + 1]

    return text

def _try_parse_json_loose(text: str):
    if not text:
        raise json.JSONDecodeError("Empty response", "", 0)

    candidate = _extract_json_candidate(text)

    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    cleaned = candidate.strip()
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"').replace("\u2019", "'")

    return json.loads(cleaned)

def call_claude_json(
    api_key: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1200,
    fallback: Optional[dict] = None,
) -> dict:
    client = anthropic.Anthropic(api_key=api_key)

    try:
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw_text = _extract_text_from_claude_response(resp)
        return _try_parse_json_loose(raw_text)

    except Exception as e:
        if fallback is not None:
            out = fallback.copy()
            out["_error"] = f"{type(e).__name__}: {e}"
            return out
        raise

def extract_causes_with_claude(api_key: str, narrative: str, patient_info: dict) -> dict:
    system_prompt = """
You are a clinical death-certificate extraction assistant.

Task:
Extract the death certificate structure from the doctor's narrative.

Rules:
- Return only valid JSON.
- Use standard medical English terminology.
- Preserve the direct causal chain for Part I in order:
  immediate cause -> due to -> due to -> underlying cause
- Put only non-direct contributing conditions in Part II.
- Preserve time intervals when stated.
- Do not invent causes that are not in the text.
- Do not include explanatory text.
- Keep each cause as a concise medical phrase, not a full sentence.

Return JSON exactly in this schema:
{
  "part1_chain": [
    {"cause": "string", "interval": "string"}
  ],
  "part2_conditions": [
    {"cause": "string", "interval": "string"}
  ]
}
"""
    user_prompt = f"""
Patient information:
Age: {patient_info.get("age_years", "Unknown")}
Sex: {patient_info.get("sex", "Unknown")}
Death type: {patient_info.get("death_type", "Unknown")}
Chronic conditions: {", ".join(patient_info.get("chronic_conditions", []))}

Narrative:
{narrative}
"""
    return call_claude_json(
        api_key,
        system_prompt,
        user_prompt,
        max_tokens=900,
        fallback={
            "part1_chain": [],
            "part2_conditions": [],
        },
    )

def select_code_from_candidates_with_claude(
    api_key: str,
    cause_text: str,
    role: str,
    interval: str,
    sex_value: str,
    age_years: int,
    candidates: list,
) -> dict:
    if not candidates:
        return {
            "selected_code": "",
            "reason": "No retrieved file candidates available.",
            "manual_review": True,
            "acceptable_main": "Unknown",
        }

    slim_candidates = []
    for c in candidates:
        slim_candidates.append({
            "CodeFormatted": c.get("code_formatted", ""),
            "ShortDesc": c.get("short_desc", ""),
            "LongDesc": c.get("long_desc", ""),
            "AcceptableMain": c.get("acceptable_main", ""),
            "GenderRestriction": c.get("gender_restriction", ""),
            "Classification": c.get("classification", ""),
            "Note": c.get("note", ""),
        })

    system_prompt = """
You are an ICD-10 coding assistant.

You MUST choose only from the candidate rows provided.
Do NOT invent codes.
Do NOT use outside knowledge to create a new code.
If none of the candidates are adequate, return manual_review=true and selected_code="".

Return JSON exactly:
{
  "selected_code": "string",
  "reason": "string",
  "manual_review": true,
  "acceptable_main": "string"
}
"""
    user_prompt = f"""
Cause text: {cause_text}
Role: {role}
Interval: {interval}
Patient sex: {sex_value}
Patient age: {age_years}

Candidate ICD rows:
{json.dumps(slim_candidates, ensure_ascii=False, indent=2)}
"""

    result = call_claude_json(
        api_key,
        system_prompt,
        user_prompt,
        max_tokens=700,
        fallback={
            "selected_code": "",
            "reason": "Claude JSON parse failed; requires manual review.",
            "manual_review": True,
            "acceptable_main": "Unknown",
        },
    )

    if not isinstance(result, dict):
        return {
            "selected_code": "",
            "reason": "Claude returned non-dict output; requires manual review.",
            "manual_review": True,
            "acceptable_main": "Unknown",
        }

    return {
        "selected_code": str(result.get("selected_code", "") or "").strip(),
        "reason": str(result.get("reason", "") or "").strip(),
        "manual_review": bool(result.get("manual_review", True)),
        "acceptable_main": str(result.get("acceptable_main", "Unknown") or "Unknown").strip(),
    }

# =============================================================================
# Validation
# =============================================================================
def is_r_chapter(code: str) -> bool:
    return (code or "").strip().upper().startswith("R")

def _excel_text_flags(item: Dict) -> str:
    return normalize_text_basic(" ".join([
        item.get("classification", ""),
        item.get("acceptable_main", ""),
        item.get("note", ""),
        item.get("short_desc", ""),
        item.get("long_desc", ""),
    ]))

def is_excel_ill_defined(item: Dict) -> bool:
    txt = _excel_text_flags(item)
    code = str(item.get("code_formatted", "")).upper()
    return ("ill-defined" in txt or "ill defined" in txt or "illdefined" in txt or code.startswith("R"))

def is_excel_unlikely_to_cause_death(item: Dict) -> bool:
    txt = _excel_text_flags(item)
    return "unlikely" in txt or "trivial" in txt or "not likely" in txt

def has_multiple_causes_in_one_line(cause_text: str) -> bool:
    # UI/form rule: one disease/condition per line. This is not ICD coding; it prevents input ambiguity.
    c = normalize_text_basic(cause_text)
    if not c:
        return False
    markers = [";", "/", " plus ", " along with "]
    if any(m in c for m in markers):
        return True
    # Commas often indicate more than one condition.
    if "," in c:
        return True
    # "and" is suspicious unless it is part of a single ICD phrase returned by Excel later.
    if re.search(r"\b(and|with)\b", c):
        return True
    return False


def clean_cause_input(cause_text: str) -> str:
    """Clean doctor-entered cause text before validation/retrieval."""
    c = str(cause_text or "").strip()
    c = re.sub(r"^\(?[a-dA-D]\)?[\.:\-\s]+", "", c).strip()
    c = re.sub(r"^(part\s*i+\s*)?\(?[a-dA-D]\)?[\.:\-\s]+", "", c, flags=re.I).strip()
    c = re.sub(r"^(ii[-\s]*\d+|part\s*ii[-\s]*\d*)[\.:\-\s]+", "", c, flags=re.I).strip()
    c = re.sub(r"\s+", " ", c)
    return c

def looks_like_non_medical_sentence(cause_text: str) -> bool:
    """Detect narrative text that should not be placed in one COD line."""
    c = normalize_text_basic(cause_text)
    if not c:
        return False
    bad_phrases = [
        "patient died", "passed away", "became sick", "very sick", "peacefully",
        "found dead", "was admitted", "was brought", "condition deteriorated",
        "after being", "complained of", "because of unknown", "unknown reason",
    ]
    if any(p in c for p in bad_phrases):
        return True
    # Long sentence-like entries are suspicious for a structured cause line.
    token_count = len(tokenize(c))
    if token_count >= 10 and any(w in c for w in [" patient ", " died ", " admitted ", " hospital ", " after "]):
        return True
    return False

def pre_validate_structured_cod(part1_chain: List[Dict], part2_conditions: List[Dict]) -> Dict:
    """Pre-coding validation. Blocks retrieval only for form-structure errors."""
    issues = []
    cleaned_part1, cleaned_part2 = [], []

    # Clean and preserve line order.
    for x in part1_chain:
        cx = dict(x)
        cx["cause"] = clean_cause_input(cx.get("cause", ""))
        if cx["cause"]:
            cleaned_part1.append(cx)

    for x in part2_conditions:
        cx = dict(x)
        cx["cause"] = clean_cause_input(cx.get("cause", ""))
        if cx["cause"]:
            cleaned_part2.append(cx)

    if not cleaned_part1:
        issues.append({
            "severity": "error",
            "line": "Part I",
            "type": "empty_part_i",
            "message": "Part I cannot be empty. Enter at least the immediate cause of death.",
            "blocking": True,
        })

    # No skipped lines in Part I: if c/d filled while earlier line empty, block.
    filled_letters = {str(x.get("line", "")).lower() for x in cleaned_part1}
    order = ["a", "b", "c", "d"]
    for i, letter in enumerate(order):
        later_filled = any(l in filled_letters for l in order[i + 1:])
        if letter not in filled_letters and later_filled:
            issues.append({
                "severity": "error",
                "line": f"Part I ({letter})",
                "type": "skipped_line",
                "message": "Do not skip Part I lines. Fill the causal sequence consecutively from (a) downward.",
                "blocking": True,
            })

    all_lines = [(f"Part I ({x.get('line','')})", x) for x in cleaned_part1] + [(str(x.get("line", "Part II")), x) for x in cleaned_part2]
    for label, x in all_lines:
        cause = x.get("cause", "")
        if has_multiple_causes_in_one_line(cause):
            issues.append({
                "severity": "error",
                "line": label,
                "type": "multiple_causes",
                "message": "Only one disease or condition is allowed per line. Split combined causes into separate lines.",
                "blocking": True,
            })
        if looks_like_non_medical_sentence(cause):
            issues.append({
                "severity": "error",
                "line": label,
                "type": "narrative_text",
                "message": "Use a concise medical condition, not a narrative sentence.",
                "blocking": True,
            })
        issues.extend(validate_interval_text(x.get("interval", ""), label))

    # Duplicate disease check: repeated causes in Part I usually mean the causal sequence was not entered correctly.
    seen = {}
    for x in cleaned_part1:
        key = normalize_cause_key(x.get("cause", ""))
        if not key:
            continue
        current_line = str(x.get("line", "")).lower()
        if key in seen:
            issues.append({
                "severity": "error",
                "line": f"Part I ({current_line})",
                "type": "duplicate_cause",
                "message": f"This repeats Part I ({seen[key]}). Each line should contain the next cause in the causal chain, not the same condition again.",
                "blocking": True,
            })
        else:
            seen[key] = current_line

    # Adjacent same-cause sequence check.
    for prev, curr in zip(cleaned_part1, cleaned_part1[1:]):
        if normalize_cause_key(prev.get("cause", "")) == normalize_cause_key(curr.get("cause", "")):
            issues.append({
                "severity": "error",
                "line": f"Part I ({curr.get('line','')})",
                "type": "invalid_sequence_duplicate",
                "message": "The lower line should explain the line above; it cannot be the exact same condition.",
                "blocking": True,
            })

    tentative = cleaned_part1[-1] if cleaned_part1 else {}
    return {
        "part1_chain": cleaned_part1,
        "part2_conditions": cleaned_part2,
        "issues": issues,
        "blocking": any(i.get("blocking") for i in issues),
        "tentative_underlying": tentative,
    }

def doctor_issue_card(issue: Dict) -> None:
    sev = issue.get("severity", "warning")
    msg = f"{issue.get('line','')}: {issue.get('message','')}"
    if sev == "error":
        st.error(msg)
    else:
        st.warning(msg)

def compact_candidate_label(c: Dict) -> str:
    code = c.get("code_formatted", "")
    desc = c.get("short_desc", "") or c.get("long_desc", "")
    return f"{code} — {desc}" if code else desc

def strict_quality_from_results(coded_causes: List[Dict], validation: Dict, pre_issues: Optional[List[Dict]] = None) -> str:
    """Final quality: missing codes / blocking validation / sequence flags force Needs Review."""
    issues = list(validation.get("coding_issues", []) or [])
    if pre_issues and any(i.get("severity") == "error" for i in pre_issues):
        return "Needs Review"
    if not coded_causes:
        return "Needs Review"
    if any(not x.get("code_formatted") for x in coded_causes):
        return "Needs Review"
    if any(str(x.get("selection_status", "")) == "manual_review" for x in coded_causes):
        return "Needs Review"
    if issues:
        return "Needs Review" if len(issues) > 0 else "Good"
    return "Excellent"

def causal_sequence_check_with_claude(api_key: str, part1_items: List[Dict]) -> Dict:
    """AI-assisted sequence plausibility check; does not invent ICD codes."""
    filled = [
        {"line": x.get("line", ""), "cause": x.get("cause", ""), "code": x.get("code_formatted", "")}
        for x in part1_items if str(x.get("cause", "")).strip()
    ]
    if len(filled) <= 1:
        return {"valid": True, "warnings": [], "summary": "Single Part I cause; no causal chain to compare."}
    system_prompt = """
You are a death-certificate sequence reviewer.
Assess only whether each lower Part I condition can medically give rise to the condition immediately above it.
Do not add new diseases. Do not invent ICD codes. Return only valid JSON.
Schema:
{"valid": true, "warnings": ["string"], "summary": "string"}
"""
    user_prompt = "Part I chain, immediate to underlying:\n" + json.dumps(filled, ensure_ascii=False, indent=2)
    try:
        out = call_claude_json(api_key, system_prompt, user_prompt, max_tokens=500, fallback={"valid": True, "warnings": [], "summary": "Sequence check unavailable."})
        if not isinstance(out, dict):
            return {"valid": True, "warnings": [], "summary": "Sequence check returned an unexpected format."}
        return {
            "valid": bool(out.get("valid", True)),
            "warnings": list(out.get("warnings", []) or []),
            "summary": str(out.get("summary", "") or ""),
        }
    except Exception as e:
        return {"valid": True, "warnings": [], "summary": f"Sequence check failed: {type(e).__name__}: {e}"}



def normalize_cause_key(cause_text: str) -> str:
    """Normalize cause text for duplicate detection."""
    c = normalize_text_basic(clean_cause_input(cause_text))
    c = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", c)
    c = re.sub(r"\s+", " ", c).strip()
    return c

def validate_interval_text(interval_text: str, line_label: str) -> List[Dict]:
    """Doctor-facing validation for approximate interval fields."""
    t = str(interval_text or "").strip().lower()
    if not t:
        return [{
            "severity": "warning",
            "line": line_label,
            "type": "missing_interval",
            "message": "Add an approximate interval, such as 2 days, 3 hours, 6 months, or unknown.",
            "blocking": False,
        }]
    if t in {"unknown", "unk", "not known", "n/a", "na", "-", "—"}:
        return []
    # A number alone, e.g. 2 or 7, is ambiguous.
    if re.fullmatch(r"\d+(?:\.\d+)?", t):
        return [{
            "severity": "warning",
            "line": line_label,
            "type": "ambiguous_interval",
            "message": "Interval needs a time unit, e.g., 2 days, 4 hours, or 7 years.",
            "blocking": False,
        }]
    units = r"(minute|minutes|min|hour|hours|hr|hrs|day|days|week|weeks|month|months|year|years|yr|yrs)"
    if re.search(r"\b\d+(?:\.\d+)?\s*" + units + r"\b", t):
        return []
    return [{
        "severity": "warning",
        "line": line_label,
        "type": "unclear_interval",
        "message": "Interval format is unclear. Use a simple duration such as 2 days or write unknown.",
        "blocking": False,
    }]

def validate_cause_line_from_excel(
    cause_text: str,
    line_label: str,
    role: str,
    df_source: pd.DataFrame,
    faiss_index,
    bm25,
    sex_value: str,
    age_years: int = 0,
    top_k: int = 5,
) -> Tuple[List[Dict], List[Dict]]:
    issues = []
    cause = str(cause_text or "").strip()

    if not cause:
        return issues, []

    if has_multiple_causes_in_one_line(cause):
        issues.append({
            "severity": "warning",
            "line": line_label,
            "type": "multiple_causes",
            "message": "Only one disease or condition should be entered on this line.",
        })

    candidates = search_icd_candidates(
        df_source=df_source,
        faiss_index=faiss_index,
        bm25=bm25,
        query=cause,
        sex_value=sex_value,
        role=role,
        top_k=top_k,
    )

    if not candidates:
        issues.append({
            "severity": "warning",
            "line": line_label,
            "type": "no_excel_match",
            "message": "No ICD candidate was retrieved from the coding source. Please use a more specific medical term.",
        })
        return issues, candidates

    best = candidates[0]
    code = best.get("code_formatted", "")
    acc = acceptable_main_bool(best.get("acceptable_main", ""))

    if is_excel_ill_defined(best):
        issues.append({
            "severity": "warning",
            "line": line_label,
            "type": "ill_defined",
            "message": "This may be a terminal event or vague condition. Add the disease, infection source, or injury that caused it if available.",
        })

    if is_excel_unlikely_to_cause_death(best):
        issues.append({
            "severity": "warning",
            "line": line_label,
            "type": "unlikely_cause",
            "message": "This condition may be unlikely to cause death by itself. Consider a more specific fatal disease or injury.",
        })

    if role in {"underlying", "contributing", "immediate"} and acc is False:
        issues.append({
            "severity": "warning",
            "line": line_label,
            "type": "not_acceptable_main",
            "message": "This condition may not be suitable as the main underlying cause. Consider adding the more specific disease that caused it.",
        })

    if not is_gender_allowed(best.get("gender_restriction", ""), sex_value):
        issues.append({
            "severity": "error",
            "line": line_label,
            "type": "gender_conflict",
            "message": "This condition may conflict with the patient sex. Please verify the entry.",
        })

    return issues, candidates

def determine_starting_point_from_structured_part1(part1_chain: List[Dict]) -> Dict:
    filled = [x for x in part1_chain if str(x.get("cause", "")).strip()]
    if not filled:
        return {"line": "", "cause": "", "interval": "—", "rule": "No Part I cause entered."}
    if len(filled) == 1:
        out = filled[0].copy()
        out["rule"] = "SP1/SP2: single completed Part I line."
        return out
    out = filled[-1].copy()
    out["rule"] = "Structured WHO form: lowest completed Part I line is the candidate starting point/underlying cause, subject to Excel validation and sequence review."
    return out

def validate_certificate(coded_causes: List[Dict], sex_value: str) -> Dict:
    issues = []

    part1 = [x for x in coded_causes if x["role"] in {"immediate", "contributing", "underlying"}]

    if not part1:
        issues.append("Part I is empty.")
    else:
        if part1[0]["role"] != "immediate":
            issues.append("Part I should start with an immediate cause.")

    for x in part1:
        acc = acceptable_main_bool(x.get("acceptable_main", ""))
        if acc is False:
            issues.append(f"{x.get('code_formatted', 'Unknown code')} is marked as not acceptable as a main cause.")

    for x in coded_causes:
        if not is_gender_allowed(x.get("gender_restriction", ""), sex_value):
            issues.append(f"{x.get('code_formatted', 'Unknown code')} conflicts with sex-based restriction.")

    for x in part1:
        code = x.get("code_formatted", "")
        cause = normalize_text_basic(x.get("cause", ""))

        if is_excel_ill_defined(x):
            issues.append(f"{code} is flagged by the coding source as ill-defined/vague and should be replaced by a more specific disease or injury if available.")
        if is_excel_unlikely_to_cause_death(x):
            issues.append(f"{code} is flagged by the coding source as unlikely to cause death.")

        if code[:1] in {"V", "W", "X", "Y"} and not query_indicates_external_cause(cause):
            issues.append(f"{code} is an external-cause/procedure code that does not fit a natural disease phrase.")

        if "respiratory distress syndrome" in cause and code and not code.startswith("J80"):
            issues.append(f"{code} does not match ARDS well; expected J80 family.")
        if "septic shock" in cause and code and not code.startswith("R57.2"):
            issues.append(f"{code} does not match septic shock well; expected R57.2 family.")
        if "diverticulitis" in cause and code and not code.startswith("K57"):
            issues.append(f"{code} does not match diverticulitis well; expected K57 family.")
        if "peritonitis" in cause and code and not code.startswith(("K65", "K57")):
            issues.append(f"{code} does not match peritonitis/diverticulitis well.")

    for x in coded_causes:
        if x.get("selection_status") == "manual_review":
            issues.append(f"{x.get('cause', 'Cause')} requires manual review.")

    # The candidate underlying cause is the lowest completed Part I line.
    # This follows the structured WHO form layout; Excel flags may still require review.
    underlying = part1[-1].get("code_formatted", "") if part1 else ""

    if not issues:
        quality = "Excellent"
    elif len(issues) <= 2:
        quality = "Good"
    else:
        quality = "Needs Review"

    who_notes = (
        "Part I should contain the direct causal chain from the immediate cause to the most remote underlying cause. "
        "Part II should contain other significant conditions that contributed to death but were not part of the direct sequence."
    )

    return {
        "underlying_cause": underlying,
        "coding_issues": issues,
        "who_notes": who_notes,
        "overall_quality": quality,
    }

# =============================================================================
# Hybrid coding pipeline
# =============================================================================
def code_extracted_causes_with_claude(
    api_key: str,
    extracted: dict,
    df_source: pd.DataFrame,
    faiss_index,
    bm25,
    patient_info: dict,
) -> dict:
    coded_causes = []

    # Part I: structured order is immediate -> antecedent -> underlying.
    part1_items = [x for x in extracted.get("part1_chain", []) if str(x.get("cause", "")).strip()]
    for i, item in enumerate(part1_items):
        role = "immediate" if i == 0 else ("underlying" if i == len(part1_items) - 1 else "contributing")
        cause = str(item.get("cause", "")).strip()
        interval = str(item.get("interval", "—")).strip() or "—"
        line = str(item.get("line", "")).strip() or chr(ord("a") + i)

        cands = search_icd_candidates(
            df_source=df_source,
            faiss_index=faiss_index,
            bm25=bm25,
            query=cause,
            sex_value=patient_info.get("sex", ""),
            role=role,
            top_k=10,
        )

        try:
            claude_choice = select_code_from_candidates_with_claude(
                api_key=api_key,
                cause_text=cause,
                role=role,
                interval=interval,
                sex_value=patient_info.get("sex", ""),
                age_years=patient_info.get("age_years", 0),
                candidates=cands,
            )
        except Exception as e:
            claude_choice = {
                "selected_code": "",
                "reason": f"Claude selection failed: {type(e).__name__}: {e}",
                "manual_review": True,
                "acceptable_main": "Unknown",
            }

        chosen_code = claude_choice.get("selected_code", "")
        row = get_row_by_code(df_source, chosen_code)

        label = "Immediate cause" if i == 0 else ("Underlying cause" if role == "underlying" else f"Due to ({line})")
        if row is not None:
            chosen = {
                "role": role,
                "line": line,
                "label": label,
                "cause": cause,
                "interval": interval,
                "code_formatted": str(row["CodeFormatted"]),
                "short_desc": str(row["ShortDesc"]),
                "long_desc": str(row["LongDesc"]),
                "acceptable_main": str(row["AcceptableMain"]),
                "gender_restriction": str(row["GenderRestriction"]),
                "classification": str(row["Classification"]),
                "note": str(row["Note"]),
                "selection_status": "manual_review" if claude_choice.get("manual_review", False) else "auto_selected",
                "selection_notes": claude_choice.get("reason", ""),
                "candidates": cands,
            }
        else:
            chosen = {
                "role": role,
                "line": line,
                "label": label,
                "cause": cause,
                "interval": interval,
                "code_formatted": "",
                "short_desc": "",
                "long_desc": "",
                "acceptable_main": "Unknown",
                "gender_restriction": "",
                "classification": "",
                "note": "",
                "selection_status": "manual_review",
                "selection_notes": claude_choice.get("reason", "No valid candidate selected from file rows."),
                "candidates": cands,
            }
        coded_causes.append(chosen)

    # Part II
    for i, item in enumerate(extracted.get("part2_conditions", []), start=1):
        cause = str(item.get("cause", "")).strip()
        interval = str(item.get("interval", "—")).strip() or "—"
        if not cause:
            continue

        cands = search_icd_candidates(
            df_source=df_source,
            faiss_index=faiss_index,
            bm25=bm25,
            query=cause,
            sex_value=patient_info.get("sex", ""),
            role="other",
            top_k=10,
        )

        try:
            claude_choice = select_code_from_candidates_with_claude(
                api_key=api_key,
                cause_text=cause,
                role="other",
                interval=interval,
                sex_value=patient_info.get("sex", ""),
                age_years=patient_info.get("age_years", 0),
                candidates=cands,
            )
        except Exception as e:
            claude_choice = {
                "selected_code": "",
                "reason": f"Claude selection failed: {type(e).__name__}: {e}",
                "manual_review": True,
                "acceptable_main": "Unknown",
            }

        chosen_code = claude_choice.get("selected_code", "")
        row = get_row_by_code(df_source, chosen_code)

        if row is not None:
            chosen = {
                "role": "other",
                "line": f"II-{i}",
                "label": f"Other condition ({i})",
                "cause": cause,
                "interval": interval,
                "code_formatted": str(row["CodeFormatted"]),
                "short_desc": str(row["ShortDesc"]),
                "long_desc": str(row["LongDesc"]),
                "acceptable_main": str(row["AcceptableMain"]),
                "gender_restriction": str(row["GenderRestriction"]),
                "classification": str(row["Classification"]),
                "note": str(row["Note"]),
                "selection_status": "manual_review" if claude_choice.get("manual_review", False) else "auto_selected",
                "selection_notes": claude_choice.get("reason", ""),
                "candidates": cands,
            }
        else:
            chosen = {
                "role": "other",
                "line": f"II-{i}",
                "label": f"Other condition ({i})",
                "cause": cause,
                "interval": interval,
                "code_formatted": "",
                "short_desc": "",
                "long_desc": "",
                "acceptable_main": "Unknown",
                "gender_restriction": "",
                "classification": "",
                "note": "",
                "selection_status": "manual_review",
                "selection_notes": claude_choice.get("reason", "No valid candidate selected from file rows."),
                "candidates": cands,
            }
        coded_causes.append(chosen)

    validation = validate_certificate(coded_causes, patient_info.get("sex", ""))
    starting_point = determine_starting_point_from_structured_part1(part1_items)
    validation["starting_point_rule"] = starting_point.get("rule", "")

    return {
        "concepts": extracted,
        "coded_causes": coded_causes,
        "validation": validation,
    }

def code_causes_hybrid_with_claude(
    api_key: str,
    narrative: str,
    df_source: pd.DataFrame,
    faiss_index,
    bm25,
    patient_info: dict,
) -> dict:
    extracted = extract_causes_with_claude(api_key, narrative, patient_info)
    coded_causes = []

    # Part I
    for i, item in enumerate(extracted.get("part1_chain", [])):
        role = "immediate" if i == 0 else "contributing"
        cause = str(item.get("cause", "")).strip()
        interval = str(item.get("interval", "—")).strip() or "—"
        if not cause:
            continue

        cands = search_icd_candidates(
            df_source=df_source,
            faiss_index=faiss_index,
            bm25=bm25,
            query=cause,
            sex_value=patient_info.get("sex", ""),
            role=role,
            top_k=10,
        )

        try:
            claude_choice = select_code_from_candidates_with_claude(
                api_key=api_key,
                cause_text=cause,
                role=role,
                interval=interval,
                sex_value=patient_info.get("sex", ""),
                age_years=patient_info.get("age_years", 0),
                candidates=cands,
            )
        except Exception as e:
            claude_choice = {
                "selected_code": "",
                "reason": f"Claude selection failed: {type(e).__name__}: {e}",
                "manual_review": True,
                "acceptable_main": "Unknown",
            }

        chosen_code = claude_choice.get("selected_code", "")
        row = get_row_by_code(df_source, chosen_code)

        if row is not None:
            chosen = {
                "role": role,
                "label": "Immediate cause" if role == "immediate" else f"Due to ({i})",
                "cause": cause,
                "interval": interval,
                "code_formatted": str(row["CodeFormatted"]),
                "short_desc": str(row["ShortDesc"]),
                "long_desc": str(row["LongDesc"]),
                "acceptable_main": str(row["AcceptableMain"]),
                "gender_restriction": str(row["GenderRestriction"]),
                "classification": str(row["Classification"]),
                "note": str(row["Note"]),
                "selection_status": "manual_review" if claude_choice.get("manual_review", False) else "auto_selected",
                "selection_notes": claude_choice.get("reason", ""),
                "candidates": cands,
            }
        else:
            chosen = {
                "role": role,
                "label": "Immediate cause" if role == "immediate" else f"Due to ({i})",
                "cause": cause,
                "interval": interval,
                "code_formatted": "",
                "short_desc": "",
                "long_desc": "",
                "acceptable_main": "Unknown",
                "gender_restriction": "",
                "classification": "",
                "note": "",
                "selection_status": "manual_review",
                "selection_notes": claude_choice.get("reason", "No valid candidate selected from file rows."),
                "candidates": cands,
            }

        coded_causes.append(chosen)

    # Part II
    for i, item in enumerate(extracted.get("part2_conditions", []), start=1):
        cause = str(item.get("cause", "")).strip()
        interval = str(item.get("interval", "—")).strip() or "—"
        if not cause:
            continue

        cands = search_icd_candidates(
            df_source=df_source,
            faiss_index=faiss_index,
            bm25=bm25,
            query=cause,
            sex_value=patient_info.get("sex", ""),
            role="other",
            top_k=10,
        )

        try:
            claude_choice = select_code_from_candidates_with_claude(
                api_key=api_key,
                cause_text=cause,
                role="other",
                interval=interval,
                sex_value=patient_info.get("sex", ""),
                age_years=patient_info.get("age_years", 0),
                candidates=cands,
            )
        except Exception as e:
            claude_choice = {
                "selected_code": "",
                "reason": f"Claude selection failed: {type(e).__name__}: {e}",
                "manual_review": True,
                "acceptable_main": "Unknown",
            }

        chosen_code = claude_choice.get("selected_code", "")
        row = get_row_by_code(df_source, chosen_code)

        if row is not None:
            chosen = {
                "role": "other",
                "label": f"Other condition ({i})",
                "cause": cause,
                "interval": interval,
                "code_formatted": str(row["CodeFormatted"]),
                "short_desc": str(row["ShortDesc"]),
                "long_desc": str(row["LongDesc"]),
                "acceptable_main": str(row["AcceptableMain"]),
                "gender_restriction": str(row["GenderRestriction"]),
                "classification": str(row["Classification"]),
                "note": str(row["Note"]),
                "selection_status": "manual_review" if claude_choice.get("manual_review", False) else "auto_selected",
                "selection_notes": claude_choice.get("reason", ""),
                "candidates": cands,
            }
        else:
            chosen = {
                "role": "other",
                "label": f"Other condition ({i})",
                "cause": cause,
                "interval": interval,
                "code_formatted": "",
                "short_desc": "",
                "long_desc": "",
                "acceptable_main": "Unknown",
                "gender_restriction": "",
                "classification": "",
                "note": "",
                "selection_status": "manual_review",
                "selection_notes": claude_choice.get("reason", "No valid candidate selected from file rows."),
                "candidates": cands,
            }

        coded_causes.append(chosen)

    validation = validate_certificate(coded_causes, patient_info.get("sex", ""))

    return {
        "concepts": extracted,
        "coded_causes": coded_causes,
        "validation": validation,
    }

def refresh_code_from_manual_edit(df_source: pd.DataFrame, item: Dict, new_code: str, sex_value: str) -> Dict:
    row = get_row_by_code(df_source, new_code)
    updated = item.copy()

    if row is None:
        updated["code_formatted"] = new_code.strip()
        updated["short_desc"] = ""
        updated["long_desc"] = ""
        updated["acceptable_main"] = "Unknown"
        updated["gender_restriction"] = ""
        updated["classification"] = ""
        updated["note"] = ""
        updated["selection_status"] = "manual_review"
        updated["selection_notes"] = "Manual code not found in the loaded ICD source."
        return updated

    updated["code_formatted"] = str(row["CodeFormatted"])
    updated["short_desc"] = str(row["ShortDesc"])
    updated["long_desc"] = str(row["LongDesc"])
    updated["acceptable_main"] = str(row["AcceptableMain"])
    updated["gender_restriction"] = str(row["GenderRestriction"])
    updated["classification"] = str(row["Classification"])
    updated["note"] = str(row["Note"])
    updated["selection_status"] = "manual_selected"
    updated["selection_notes"] = "Manually edited code found in ICD source and refreshed."

    if not is_gender_allowed(updated["gender_restriction"], sex_value):
        updated["selection_status"] = "manual_review"
        updated["selection_notes"] = "Manual code conflicts with sex restriction."

    return updated

# =============================================================================
# PDF Generation
# =============================================================================
def generate_certificate_pdf(
    fd: dict,
    coded_causes: List[Dict],
    validation: dict,
    hospital_name: str,
    hospital_city: str,
    doctor_name: str,
) -> bytes:
    """Generate a professional PDF death certificate using reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, KeepTogether
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

    GREEN       = colors.HexColor("#006940")
    GOLD        = colors.HexColor("#C8A951")
    LIGHT_GREEN = colors.HexColor("#e8f5ee")
    LIGHT_BLUE  = colors.HexColor("#f0f4ff")
    DARK_NAVY   = colors.HexColor("#1a4a7a")
    LIGHT_GRAY  = colors.HexColor("#f7faf8")
    MID_GRAY    = colors.HexColor("#5a7060")
    BORDER_CLR  = colors.HexColor("#c8dece")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="Death Certificate - Saudi MOH",
    )

    styles = getSampleStyleSheet()
    W = A4[0] - 36 * mm  # usable width

    def S(name, **kw):
        base = styles.get(name, styles["Normal"])
        return ParagraphStyle(name + "_custom_" + str(id(kw)), parent=base, **kw)

    title_style   = S("Title",   fontSize=16, textColor=GREEN,    fontName="Helvetica-Bold",   alignment=TA_CENTER, spaceAfter=2)
    subtitle_style= S("Normal",  fontSize=9,  textColor=MID_GRAY, fontName="Helvetica",        alignment=TA_CENTER, spaceAfter=1)
    h2_style      = S("Normal",  fontSize=10, textColor=GREEN,    fontName="Helvetica-Bold",   spaceAfter=4, spaceBefore=8)
    h3_style      = S("Normal",  fontSize=9,  textColor=DARK_NAVY,fontName="Helvetica-Bold",   spaceAfter=2, spaceBefore=4)
    normal_style  = S("Normal",  fontSize=8.5,textColor=colors.black, fontName="Helvetica",    spaceAfter=2)
    small_style   = S("Normal",  fontSize=7.5,textColor=MID_GRAY, fontName="Helvetica",        spaceAfter=1)
    label_style   = S("Normal",  fontSize=8,  textColor=GREEN,    fontName="Helvetica-Bold",   spaceAfter=0)
    value_style   = S("Normal",  fontSize=8.5,textColor=colors.black, fontName="Helvetica",    spaceAfter=0)
    code_style    = S("Normal",  fontSize=10, textColor=GREEN,    fontName="Helvetica-Bold",   spaceAfter=0)
    cause_style   = S("Normal",  fontSize=9,  textColor=colors.black, fontName="Helvetica-Bold", spaceAfter=1)
    desc_style    = S("Normal",  fontSize=8,  textColor=MID_GRAY, fontName="Helvetica",        spaceAfter=0)
    center_style  = S("Normal",  fontSize=8,  textColor=colors.black, fontName="Helvetica",    alignment=TA_CENTER)
    right_style   = S("Normal",  fontSize=8,  textColor=colors.black, fontName="Helvetica",    alignment=TA_RIGHT)

    story = []

    # ── Header banner (table with green bg) ──────────────────────────────────
    cert_no = fd.get("cert_number") or f"DC-{datetime.date.today().year}-{str(fd.get('national_id', ''))[-4:]}"

    header_data = [[
        Paragraph("Kingdom of Saudi Arabia<br/><font size='8'>Ministry of Health</font>", S("Normal", fontSize=10, textColor=colors.white, fontName="Helvetica-Bold")),
        Paragraph(
            "<font size='14'><b>DEATH CERTIFICATE</b></font><br/>"
            "<font size='8'>Electronic ICD-10 Coding System</font><br/>"
            f"<font size='8'>Certificate No: {cert_no}</font>",
            S("Normal", fontSize=8, textColor=colors.white, fontName="Helvetica", alignment=TA_CENTER)
        ),
        Paragraph(f"<font size='9'><b>{hospital_name}</b></font><br/><font size='8'>{hospital_city}</font>", S("Normal", fontSize=9, textColor=colors.white, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
    ]]
    header_table = Table(header_data, colWidths=[W * 0.3, W * 0.4, W * 0.3])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), GREEN),
        ("BOTTOMPADDING", (0,0),(-1,-1), 10),
        ("TOPPADDING",    (0,0),(-1,-1), 10),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("RIGHTPADDING",  (0,0),(-1,-1), 8),
        ("LINEBELOW", (0,0),(-1,-1), 2.5, GOLD),
        ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 6 * mm))

    # ── Patient Information ───────────────────────────────────────────────────
    story.append(Paragraph("PATIENT INFORMATION", h2_style))
    story.append(HRFlowable(width=W, thickness=1, color=GREEN, spaceAfter=4))

    def prow(label, val):
        return [Paragraph(label, label_style), Paragraph(str(val) if val else "—", value_style)]

    dob = fd.get("dob", "—")
    dod = fd.get("dod", "—")
    age = fd.get("age_years", "—")
    sex = fd.get("sex", "—")

    patient_rows = [
        prow("Full Name:", fd.get("full_name", "")),
        prow("National ID / Iqama:", fd.get("national_id", "")),
        prow("Nationality:", fd.get("nationality", "")),
        prow("Date of Birth:", dob),
        prow("Sex:", sex),
        prow("Age at Death:", f"{age} years"),
        prow("Marital Status:", fd.get("marital_status", "")),
        prow("Occupation:", fd.get("occupation", "")),
        prow("Address:", fd.get("address", "")),
    ]

    # Two-column layout for patient info
    left_rows  = patient_rows[:5]
    right_rows = patient_rows[5:]

    def mini_table(rows):
        t = Table(rows, colWidths=[W * 0.18, W * 0.32])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(0,-1), LIGHT_GREEN),
            ("ROWBACKGROUNDS", (0,0),(-1,-1), [colors.white, LIGHT_GRAY]),
            ("GRID", (0,0),(-1,-1), 0.3, BORDER_CLR),
            ("LEFTPADDING",   (0,0),(-1,-1), 5),
            ("RIGHTPADDING",  (0,0),(-1,-1), 5),
            ("TOPPADDING",    (0,0),(-1,-1), 3),
            ("BOTTOMPADDING", (0,0),(-1,-1), 3),
        ]))
        return t

    death_rows = [
        prow("Date of Death:", dod),
        prow("Time of Death:", fd.get("time_of_death", "")),
        prow("Place of Death:", fd.get("place_of_death", "")),
        prow("Type of Death:", fd.get("death_type", "")),
        prow("Hospital Stay:", f"{fd.get('inpatient_days', '—')} days"),
        prow("Autopsy Required:", fd.get("autopsy_required", "")),
        prow("Recent Surgery:", fd.get("had_surgery", "")),
        prow("Certificate No:", cert_no),
        prow("Issue Date:", fd.get("date_issued", "")),
    ]

    two_col = Table(
        [[mini_table(left_rows), mini_table(death_rows)]],
        colWidths=[W * 0.5 - 3, W * 0.5 - 3],
        hAlign="LEFT"
    )
    two_col.setStyle(TableStyle([
        ("VALIGN", (0,0),(-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0),(-1,-1), 0),
        ("RIGHTPADDING", (0,0),(-1,-1), 0),
        ("INNERGRID", (0,0),(-1,-1), 0, colors.white),
        ("BOX",       (0,0),(-1,-1), 0, colors.white),
    ]))
    story.append(two_col)
    story.append(Spacer(1, 5 * mm))

    # ── Part I ────────────────────────────────────────────────────────────────
    story.append(Paragraph("PART I — DIRECT CAUSAL SEQUENCE OF DEATH", h2_style))
    story.append(HRFlowable(width=W, thickness=1, color=GREEN, spaceAfter=4))
    story.append(Paragraph(
        "Diseases or conditions directly leading to death, in order from immediate cause to underlying cause.",
        small_style
    ))
    story.append(Spacer(1, 2 * mm))

    row_labels = ["(a)", "(b)", "(c)", "(d)", "(e)"]
    part1 = [x for x in coded_causes if x["role"] in {"immediate", "contributing", "underlying"}]
    part2 = [x for x in coded_causes if x["role"] == "other"]

    for i, item in enumerate(part1):
        lbl = row_labels[i] if i < len(row_labels) else f"({i+1})"
        role_text = "Immediate cause of death" if i == 0 else f"Due to (antecedent cause)"
        code_val  = item.get("code_formatted") or "— Pending review"
        short_val = item.get("short_desc") or ""
        cause_val = item.get("cause") or "—"
        intv_val  = item.get("interval") or "—"

        block_data = [[
            Paragraph(f"<b>{lbl} {role_text}</b>", h3_style),
            Paragraph(f"<b>Interval:</b> {intv_val}", S("Normal", fontSize=8, textColor=MID_GRAY, fontName="Helvetica", alignment=TA_RIGHT)),
        ]]
        block_header = Table(block_data, colWidths=[W * 0.7, W * 0.3])
        block_header.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(-1,-1), LIGHT_GREEN),
            ("TOPPADDING",    (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
            ("RIGHTPADDING",  (0,0),(-1,-1), 6),
            ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
        ]))

        body_data = [[
            Paragraph(cause_val, cause_style),
            Paragraph(f"<b>{code_val}</b>", code_style),
        ]]
        body_table = Table(body_data, colWidths=[W * 0.62, W * 0.38])
        body_table.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), colors.white),
            ("TOPPADDING",    (0,0),(-1,-1), 6),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ("LEFTPADDING",   (0,0),(0,-1),  6),
            ("LEFTPADDING",   (1,0),(1,-1),  10),
            ("VALIGN", (0,0),(-1,-1), "TOP"),
        ]))

        if short_val:
            desc_data = [[Paragraph(short_val, desc_style)]]
            desc_table = Table(desc_data, colWidths=[W])
            desc_table.setStyle(TableStyle([
                ("BACKGROUND",    (0,0),(-1,-1), colors.white),
                ("TOPPADDING",    (0,0),(-1,-1), 0),
                ("BOTTOMPADDING", (0,0),(-1,-1), 5),
                ("LEFTPADDING",   (0,0),(-1,-1), 6),
            ]))
            combined = KeepTogether([block_header, body_table, desc_table,
                                     Table([[""]], colWidths=[W],
                                           style=[("LINEBELOW",(0,0),(-1,-1),0.5,BORDER_CLR),
                                                  ("TOPPADDING",(0,0),(-1,-1),0),
                                                  ("BOTTOMPADDING",(0,0),(-1,-1),2)])])
        else:
            combined = KeepTogether([block_header, body_table,
                                     Table([[""]], colWidths=[W],
                                           style=[("LINEBELOW",(0,0),(-1,-1),0.5,BORDER_CLR),
                                                  ("TOPPADDING",(0,0),(-1,-1),0),
                                                  ("BOTTOMPADDING",(0,0),(-1,-1),2)])])
        story.append(combined)
        story.append(Spacer(1, 1 * mm))

    if not part1:
        story.append(Paragraph("No Part I causes documented.", small_style))

    story.append(Spacer(1, 4 * mm))

    # ── Part II ───────────────────────────────────────────────────────────────
    story.append(Paragraph("PART II — OTHER SIGNIFICANT CONDITIONS", h2_style))
    story.append(HRFlowable(width=W, thickness=1, color=DARK_NAVY, spaceAfter=4))
    story.append(Paragraph(
        "Other significant conditions contributing to death but not related to the direct causal sequence.",
        small_style
    ))
    story.append(Spacer(1, 2 * mm))

    if part2:
        p2_rows = [
            [
                Paragraph(f"<b>({i+1})</b>", S("Normal", fontSize=8, fontName="Helvetica-Bold", textColor=DARK_NAVY)),
                Paragraph(item.get("cause") or "—", normal_style),
                Paragraph(f"<b>{item.get('code_formatted') or '—'}</b>", S("Normal", fontSize=9, fontName="Helvetica-Bold", textColor=DARK_NAVY)),
                Paragraph(item.get("short_desc") or "", small_style),
                Paragraph(item.get("interval") or "—", small_style),
            ]
            for i, item in enumerate(part2)
        ]
        header_row = [[
            Paragraph("#", label_style),
            Paragraph("Condition", label_style),
            Paragraph("ICD-10", label_style),
            Paragraph("Description", label_style),
            Paragraph("Interval", label_style),
        ]]
        p2_table = Table(header_row + p2_rows, colWidths=[W*0.05, W*0.32, W*0.13, W*0.35, W*0.15])
        p2_table.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,0),  LIGHT_BLUE),
            ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, LIGHT_GRAY]),
            ("GRID", (0,0),(-1,-1), 0.3, BORDER_CLR),
            ("TOPPADDING",    (0,0),(-1,-1), 4),
            ("BOTTOMPADDING", (0,0),(-1,-1), 4),
            ("LEFTPADDING",   (0,0),(-1,-1), 5),
            ("RIGHTPADDING",  (0,0),(-1,-1), 5),
            ("VALIGN", (0,0),(-1,-1), "TOP"),
        ]))
        story.append(p2_table)
    else:
        story.append(Paragraph("None documented.", small_style))

    story.append(Spacer(1, 5 * mm))

    # ── Underlying Cause Banner ───────────────────────────────────────────────
    underlying_code = validation.get("underlying_cause") or "Pending manual review"
    quality         = validation.get("overall_quality", "Needs Review")
    q_color         = {"Excellent": colors.HexColor("#006940"), "Good": colors.HexColor("#2d7a4f")}.get(quality, colors.HexColor("#c0392b"))

    uc_data = [[
        Paragraph("Underlying Cause (for mortality statistics):", S("Normal", fontSize=9, textColor=colors.white, fontName="Helvetica-Bold")),
        Paragraph(f"<b>{underlying_code}</b>", S("Normal", fontSize=13, textColor=GOLD, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
    ]]
    uc_table = Table(uc_data, colWidths=[W * 0.65, W * 0.35])
    uc_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), GREEN),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
        ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ("RIGHTPADDING",  (0,0),(-1,-1), 8),
        ("VALIGN", (0,0),(-1,-1), "MIDDLE"),
        ("LINEBELOW", (0,0),(-1,-1), 2, GOLD),
    ]))
    story.append(uc_table)
    story.append(Spacer(1, 4 * mm))

    # ── Validation ────────────────────────────────────────────────────────────
    issues = validation.get("coding_issues", [])
    story.append(Paragraph("VALIDATION SUMMARY", h2_style))
    story.append(HRFlowable(width=W, thickness=1, color=q_color, spaceAfter=3))

    qual_data = [[Paragraph(f"Overall Quality: <b>{quality}</b>", S("Normal", fontSize=9, textColor=q_color, fontName="Helvetica-Bold"))]]
    qual_table = Table(qual_data, colWidths=[W])
    qual_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), colors.white),
        ("TOPPADDING",    (0,0),(-1,-1), 4),
        ("BOTTOMPADDING", (0,0),(-1,-1), 4),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
        ("BOX", (0,0),(-1,-1), 1, q_color),
    ]))
    story.append(qual_table)
    story.append(Spacer(1, 2 * mm))

    if issues:
        for iss in issues:
            story.append(Paragraph(f"• {iss}", S("Normal", fontSize=8, textColor=colors.HexColor("#c0392b"), fontName="Helvetica", leftIndent=10, spaceAfter=2)))
    else:
        story.append(Paragraph("No validation issues detected.", S("Normal", fontSize=8, textColor=GREEN, fontName="Helvetica", spaceAfter=2)))

    who = validation.get("who_notes", "")
    if who:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(f"<i>WHO Note: {who}</i>", small_style))

    story.append(Spacer(1, 6 * mm))

    # ── Signature block ───────────────────────────────────────────────────────
    story.append(HRFlowable(width=W, thickness=0.5, color=BORDER_CLR, spaceAfter=4))
    sig_data = [[
        Paragraph(
            f"<b>Certifying Physician:</b><br/>{doctor_name or '________________________________'}<br/><br/>"
            f"Signature: ______________________________",
            S("Normal", fontSize=8, fontName="Helvetica", textColor=colors.black)
        ),
        Paragraph(
            "<b>MOH Official</b><br/>Draft / Final Review",
            center_style
        ),
        Paragraph(
            f"<b>Issue Date:</b> {fd.get('date_issued', '')}<br/><br/>"
            f"<b>Hospital Stamp:</b><br/>______________________",
            right_style
        ),
    ]]
    sig_table = Table(sig_data, colWidths=[W * 0.4, W * 0.2, W * 0.4])
    sig_table.setStyle(TableStyle([
        ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ("TOPPADDING",    (0,0),(-1,-1), 6),
        ("BOTTOMPADDING", (0,0),(-1,-1), 6),
        ("LEFTPADDING",   (0,0),(-1,-1), 4),
        ("RIGHTPADDING",  (0,0),(-1,-1), 4),
    ]))
    story.append(sig_table)

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width=W, thickness=0.5, color=GOLD, spaceAfter=3))
    story.append(Paragraph(
        f"Ministry of Health | Kingdom of Saudi Arabia | Generated: {datetime.date.today()}",
        S("Normal", fontSize=7, textColor=MID_GRAY, fontName="Helvetica", alignment=TA_CENTER)
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()

# =============================================================================
# Sidebar
# =============================================================================
with st.sidebar:
    st.markdown("### Hospital Information")
    hospital_name = st.text_input("Hospital Name", value="King Fahad Specialist Hospital")
    hospital_city = st.text_input("City", value="Riyadh")
    doctor_name   = st.text_input("Certifying Physician", value="")

    st.markdown("---")
    st.markdown("### Navigation")
    if st.button("Basic Information", use_container_width=True):
        st.session_state.page = 1
        st.rerun()
    if st.button("Medical History", use_container_width=True):
        st.session_state.page = 2
        st.rerun()
    if st.button("Cause of Death", use_container_width=True):
        st.session_state.page = 3
        st.rerun()
    if st.button("Review & Coding", use_container_width=True):
        st.session_state.page = 4
        st.rerun()
    if st.button("Final Certificate", use_container_width=True):
        st.session_state.page = 5
        st.rerun()

    with st.expander("Admin / data status", expanded=False):
        st.caption("Technical data status is hidden from the doctor workflow.")
        if API_KEY:
            st.success("API key available")
        else:
            st.error("ANTHROPIC_API_KEY missing")
        if st.button("Reload coding data", use_container_width=True):
            import shutil
            if os.path.exists(CACHE_DIR):
                shutil.rmtree(CACHE_DIR)
            st.cache_resource.clear()
            keys_to_remove = [k for k in st.session_state.keys() if k.startswith("code_edit_")]
            for k in keys_to_remove:
                del st.session_state[k]
            st.session_state["df_source"] = None
            st.session_state["df_metadata"] = None
            st.session_state["faiss_index"] = None
            st.session_state["bm25_index"] = None
            st.session_state["icd_results"] = None
            st.rerun()

    st.markdown(
        '<div style="font-size:.72rem;opacity:.65;text-align:center;line-height:2;margin-top:.8rem">'
        'Ministry of Health<br>Electronic Death Certificate</div>',
        unsafe_allow_html=True,
    )

# =============================================================================
# Session state
# =============================================================================
defaults = {
    "page": 1,
    "form_data": {},
    "icd_results": None,
    "df_source": None,
    "df_metadata": None,
    "faiss_index": None,
    "bm25_index": None,

    # Sequential LLM agent workflow state
    "agent_step": 1,
    "agent1_result": None,
    "agent2_result": None,
    "agent3_result": None,
    "agent1_done": False,
    "agent2_done": False,
    "agent3_done": False,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# =============================================================================
# Load resources
# =============================================================================
if st.session_state["df_source"] is None:
    df_excel = None
    load_errors = []

    try:
        df_excel = load_excel_from_drive_file(GDRIVE_EXCEL_ID)
        st.session_state["df_source"] = df_excel
        # data loaded; hidden from doctor workflow
    except Exception as e:
        load_errors.append(f"Excel load failed: {e}")

    try:
        df_meta = load_metadata(GDRIVE_METADATA_ID)
        st.session_state["df_metadata"] = df_meta
        # metadata loaded; hidden from doctor workflow
    except Exception as e:
        load_errors.append(f"Metadata load failed: {e}")

    try:
        faiss_index = load_faiss_resources(GDRIVE_EMBEDDINGS_ID, GDRIVE_FAISS_ID)
        st.session_state["faiss_index"] = faiss_index
        if faiss_index is not None:
            pass
        else:
            pass
    except Exception as e:
        load_errors.append(f"FAISS load failed: {e}")

    try:
        if df_excel is not None:
            bm25 = build_bm25_index(df_excel)
            st.session_state["bm25_index"] = bm25
            if bm25 is not None:
                pass
            else:
                pass
    except Exception as e:
        load_errors.append(f"BM25 load failed: {e}")

    if load_errors:
        for err in load_errors:
            pass

# =============================================================================
# Step bar
# =============================================================================
def render_steps(current: int):
    labels = [
        "Basic Information",
        "Medical History",
        "Cause of Death",
        "Review & Coding",
        "Final Certificate",
    ]
    html_s = '<div class="step-bar">'
    for i, lbl in enumerate(labels, 1):
        cls = "step active" if i == current else ("step done" if i < current else "step")
        html_s += f'<div class="{cls}">{i}. {escape(lbl)}</div>'
    html_s += "</div>"
    st.markdown(html_s, unsafe_allow_html=True)


def inline_note(message: str, level: str = "warning") -> None:
    icon = {"error": "✕", "warning": "⚠", "ok": "✓"}.get(level, "•")
    css = {"error": "inline-error", "warning": "inline-warning", "ok": "inline-ok"}.get(level, "inline-warning")
    st.markdown(f'<div class="inline-note {css}">{icon} {escape(message)}</div>', unsafe_allow_html=True)

def issue_line_key(issue: Dict) -> str:
    line = str(issue.get("line", "")).lower()
    m = re.search(r"part\s*i\s*\(([a-d])\)", line)
    if m:
        return f"part1_{m.group(1)}"
    m = re.search(r"part\s*ii\s*\(?([0-9]+)\)?", line)
    if m:
        return f"part2_{m.group(1)}"
    m = re.search(r"ii[-\s]*([0-9]+)", line)
    if m:
        return f"part2_{m.group(1)}"
    return "global"

def group_issues_by_field(issues: List[Dict]) -> Dict[str, List[Dict]]:
    out = {}
    for issue in issues:
        out.setdefault(issue_line_key(issue), []).append(issue)
    return out

def parse_interval_to_hours(interval_text: str) -> Optional[float]:
    t = normalize_text_basic(interval_text)
    if not t or t in {"unknown", "unk", "not known", "n/a", "na", "-", "—"}:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(minute|minutes|min|hour|hours|hr|hrs|day|days|week|weeks|month|months|year|years|yr|yrs)", t)
    if not m:
        return None
    val = float(m.group(1)); unit = m.group(2)
    if unit.startswith("min"): return val / 60.0
    if unit in {"hour", "hours", "hr", "hrs"}: return val
    if unit.startswith("day"): return val * 24
    if unit.startswith("week"): return val * 24 * 7
    if unit.startswith("month"): return val * 24 * 30
    if unit in {"year", "years", "yr", "yrs"}: return val * 24 * 365
    return None

def add_cross_field_cod_issues(part1_chain: List[Dict], part2_conditions: List[Dict]) -> List[Dict]:
    issues = []
    part1_keys = {normalize_cause_key(x.get("cause", "")): x for x in part1_chain if normalize_cause_key(x.get("cause", ""))}
    for x in part2_conditions:
        key = normalize_cause_key(x.get("cause", ""))
        if key and key in part1_keys:
            issues.append({"severity": "warning", "line": str(x.get("line", "Part II")), "type": "part2_repeats_part1", "message": "This condition is already in Part I. Part II should include only conditions that contributed but were not in the direct causal chain.", "blocking": False})
    cleaned = [x for x in part1_chain if x.get("cause")]
    for upper, lower in zip(cleaned, cleaned[1:]):
        h_upper = parse_interval_to_hours(upper.get("interval", ""))
        h_lower = parse_interval_to_hours(lower.get("interval", ""))
        if h_upper is not None and h_lower is not None and h_lower < h_upper:
            issues.append({"severity": "warning", "line": f"Part I ({lower.get('line','')})", "type": "interval_order", "message": "The cause below usually starts before the condition above. Check whether this interval should be longer or equal.", "blocking": False})
    return issues

def live_sequence_screen(part1_chain: List[Dict]) -> Dict:
    """
    Lightweight live screen for obvious causal-sequence problems.

    Important: this function does NOT prove SP3. It only prevents the UI from
    saying SP3 is valid when the chain is obviously disconnected. Full sequence
    reasoning still runs on the Review & Coding page.
    """
    filled = [x for x in part1_chain if str(x.get("cause", "")).strip()]
    if len(filled) <= 1:
        return {
            "valid": None,
            "status": "single",
            "message": "Single Part I cause; SP3 does not apply.",
            "problem_line": "",
        }

    # Exact duplicate adjacent causes are never a causal explanation.
    for upper, lower in zip(filled, filled[1:]):
        if normalize_cause_key(upper.get("cause", "")) == normalize_cause_key(lower.get("cause", "")):
            return {
                "valid": False,
                "status": "invalid",
                "message": "The lower line repeats the line above instead of explaining it.",
                "problem_line": str(lower.get("line", "")),
            }

    # Obvious unrelated pairs for live UX. This is intentionally conservative.
    # It catches clearly bad test cases without pretending to be a full WHO engine.
    unrelated_pairs = [
        ("chronic gastritis", "femur fracture"),
        ("chronic gastritis", "acute respiratory failure"),
        ("femur fracture", "acute respiratory failure"),
        ("migraine", "septic shock"),
        ("osteoarthritis", "septic shock"),
        ("diabetes", "acute respiratory distress syndrome"),
        ("diabetes mellitus", "acute respiratory distress syndrome"),
        ("hypertension", "acute respiratory distress syndrome"),
        ("chronic kidney disease", "pneumonia"),
    ]

    # For each pair, lower should explain upper. If lower/upper is in unrelated list, flag it.
    for upper, lower in zip(filled, filled[1:]):
        upper_c = normalize_text_basic(upper.get("cause", ""))
        lower_c = normalize_text_basic(lower.get("cause", ""))
        for bad_lower, bad_upper in unrelated_pairs:
            if bad_lower in lower_c and bad_upper in upper_c:
                return {
                    "valid": False,
                    "status": "invalid",
                    "message": f"SP3 cannot be confirmed: {lower.get('cause', '')} does not reasonably explain {upper.get('cause', '')}.",
                    "problem_line": str(lower.get("line", "")),
                }

    return {
        "valid": None,
        "status": "pending",
        "message": "SP3 requires sequence review. Format is acceptable, but the causal relationship has not been confirmed yet.",
        "problem_line": "",
    }

def decide_sp_rule_simple(part1_chain: List[Dict], blocking: bool, sequence_screen: Optional[Dict] = None) -> Dict:
    filled = [x for x in part1_chain if str(x.get("cause", "")).strip()]
    sequence_screen = sequence_screen or live_sequence_screen(filled)

    if not filled:
        return {"rule": "", "title": "No starting point yet", "selected": "", "message": "Enter Part I causes to determine the starting point.", "confirmed": False}

    if len(filled) == 1:
        return {"rule": "SP1/SP2", "title": "Single Part I cause", "selected": filled[0].get("cause", ""), "message": "Only one Part I line is completed, so that condition is the tentative starting point.", "confirmed": True}

    if blocking:
        return {"rule": "Review", "title": "Fix structure first", "selected": "", "message": "Structural issues must be fixed before any starting point is selected.", "confirmed": False}

    if sequence_screen.get("valid") is False:
        return {"rule": "SP3", "title": "Not applied", "selected": "", "message": sequence_screen.get("message", "The causal sequence cannot be confirmed."), "confirmed": False}

    # Do not claim SP3 from clean formatting alone.
    return {"rule": "SP3", "title": "Pending sequence review", "selected": "", "message": sequence_screen.get("message", "Sequence review is required before SP3 can be applied."), "confirmed": False}


# =============================================================================
# SP1-SP8 STARTING POINT ENGINE
# =============================================================================
def _certificate_conditions(part1_chain: List[Dict], part2_conditions: List[Dict]) -> List[Dict]:
    """Return all non-empty certificate conditions in certificate order."""
    rows = []
    for x in part1_chain or []:
        cause = clean_cause_input(x.get("cause", ""))
        if cause:
            rows.append({"section": "Part I", "line": str(x.get("line", "")).lower(), "cause": cause})
    for x in part2_conditions or []:
        cause = clean_cause_input(x.get("cause", ""))
        if cause:
            rows.append({"section": "Part II", "line": str(x.get("line", "")), "cause": cause})
    return rows

def _coded_by_line(coded_causes: List[Dict]) -> Dict[str, Dict]:
    out = {}
    for item in coded_causes or []:
        line = str(item.get("line", "")).lower()
        if line:
            out[line] = item
    return out

def _coded_by_cause(coded_causes: List[Dict]) -> Dict[str, Dict]:
    out = {}
    for item in coded_causes or []:
        key = normalize_cause_key(item.get("cause", ""))
        if key:
            out[key] = item
    return out

def selected_code_for_sp(sp_review: Dict, coded_causes: List[Dict]) -> str:
    """Find selected ICD code from the selected SP line/cause."""
    by_line = _coded_by_line(coded_causes)
    line = str(sp_review.get("selected_line", "")).lower()
    if line in by_line:
        return by_line[line].get("code_formatted", "")
    by_cause = _coded_by_cause(coded_causes)
    key = normalize_cause_key(sp_review.get("selected_cause", ""))
    if key in by_cause:
        return by_cause[key].get("code_formatted", "")
    return ""


def apply_sp_result_to_validation(validation: Dict, sp_review: Dict, coded_causes: List[Dict]) -> Dict:
    """
    Preserve the SP-selected starting point independently from ICD coding.

    Important logic:
    - SP3/SP4/etc. may successfully select a starting-point *cause text*.
    - ICD coding for that cause may still be missing/manual-review.
    - Therefore the certificate should not show an empty UCOD just because the ICD code is pending.
    """
    out = dict(validation or {})
    selected_cause = str(sp_review.get("selected_cause", "") or "").strip()
    selected_line = str(sp_review.get("selected_line", "") or "").strip()
    selected_code = str(sp_review.get("selected_code", "") or selected_code_for_sp(sp_review, coded_causes) or "").strip()

    out["sp_review"] = sp_review
    out["sp_rule"] = str(sp_review.get("sp_rule", "REVIEW") or "REVIEW")
    out["starting_point_rule"] = out["sp_rule"]
    out["starting_point_line"] = selected_line
    out["starting_point_text"] = selected_cause

    # Keep both text and code. Never erase the selected cause text if the code is pending.
    if selected_cause:
        out["underlying_cause_text"] = selected_cause
    else:
        out["underlying_cause_text"] = out.get("underlying_cause_text", "") or "Not confirmed"

    if selected_code:
        out["underlying_cause"] = selected_code
        out["underlying_cause_code_status"] = "selected"
    elif selected_cause:
        out["underlying_cause"] = "Pending ICD review"
        out["underlying_cause_code_status"] = "pending"
    else:
        out["underlying_cause"] = "Not confirmed"
        out["underlying_cause_code_status"] = "not_confirmed"

    return out

def condition_flag_summary(item: Dict) -> Dict:
    """Summarize Excel/metadata acceptability flags for SP7/SP8."""
    acc = acceptable_main_bool(item.get("acceptable_main", ""))
    return {
        "line": str(item.get("line", "")),
        "cause": str(item.get("cause", "")),
        "code": str(item.get("code_formatted", "")),
        "acceptable_main": acc,
        "ill_defined": is_excel_ill_defined(item),
        "unlikely_to_cause_death": is_excel_unlikely_to_cause_death(item),
        "gender_restriction": str(item.get("gender_restriction", "")),
        "note": str(item.get("note", "")),
    }

def deterministic_sp_fallback(part1_chain: List[Dict], part2_conditions: List[Dict]) -> Dict:
    """Safe fallback if LLM sequence review is unavailable."""
    conditions = _certificate_conditions(part1_chain, part2_conditions)
    part1 = [x for x in conditions if x["section"] == "Part I"]
    if len(conditions) == 1:
        x = conditions[0]
        return {
            "sp_rule": "SP1",
            "selected_line": x["line"],
            "selected_cause": x["cause"],
            "full_sequence_valid": None,
            "partial_sequence_valid": None,
            "causal_links": [],
            "warnings": [],
            "needs_manual_review": False,
            "explanation": "Only one condition is reported on the certificate.",
        }
    if len(part1) == 1:
        x = part1[0]
        return {
            "sp_rule": "SP2",
            "selected_line": x["line"],
            "selected_cause": x["cause"],
            "full_sequence_valid": None,
            "partial_sequence_valid": None,
            "causal_links": [],
            "warnings": [],
            "needs_manual_review": False,
            "explanation": "Only one line is used in Part I.",
        }
    if part1:
        return {
            "sp_rule": "REVIEW",
            "selected_line": "",
            "selected_cause": "",
            "full_sequence_valid": False,
            "partial_sequence_valid": False,
            "causal_links": [],
            "warnings": ["Medical sequence review is required before SP3-SP8 can be applied."],
            "needs_manual_review": True,
            "explanation": "Multiple Part I lines are present, so causal sequence review is required.",
        }
    return {
        "sp_rule": "REVIEW",
        "selected_line": "",
        "selected_cause": "",
        "full_sequence_valid": False,
        "partial_sequence_valid": False,
        "causal_links": [],
        "warnings": ["No Part I condition is available."],
        "needs_manual_review": True,
        "explanation": "Part I is empty.",
    }

def llm_sp1_sp8_review(api_key: str, part1_chain: List[Dict], part2_conditions: List[Dict], coded_causes: List[Dict]) -> Dict:
    """
    Apply simplified WHO-inspired SP1-SP8 logic.
    The LLM judges medical causality only. It must select only from written certificate causes.
    Excel/metadata flags are passed for SP7/SP8 refinement.
    """
    conditions = _certificate_conditions(part1_chain, part2_conditions)
    part1 = [x for x in conditions if x["section"] == "Part I"]

    # SP1/SP2 are deterministic and do not need LLM.
    base = deterministic_sp_fallback(part1_chain, part2_conditions)
    if base["sp_rule"] in {"SP1", "SP2"}:
        return base

    if not api_key or not part1:
        return base

    coded_flags = [condition_flag_summary(x) for x in coded_causes or []]

    system_prompt = """
You are a mortality-certificate starting-point reviewer.

Task:
Apply simplified WHO-inspired SP1-SP8 logic to identify the Starting Point from the certificate.
The Starting Point becomes the basis for selecting the Underlying Cause of Death (UCOD).

Strict rules:
- Use only conditions already written in Part I or Part II.
- Do not invent new diseases or add new causes.
- Do not assign ICD codes.
- Do not rewrite the doctor's causes.
- Judge whether the Part I causal sequence is medically plausible.
- If unsure, set needs_manual_review=true.
- Return only valid JSON.

SP logic:
SP1: If only one condition is reported anywhere, select it.
SP2: If only one Part I line is used, select that line.
SP3: If multiple Part I lines are used and the lowest completed Part I line explains all entries above, select the lowest line.
SP4: If the lowest line does not explain all entries above, but a valid partial sequence reaches the terminal condition on line (a), select the origin of that valid partial sequence.
SP5: If no causal relationship can be established in Part I, select the first-mentioned Part I condition.
SP6: If an obvious better underlying cause is present elsewhere on the certificate, select/suggest it.
SP7: If the selected cause is ill-defined/vague, select a more specific condition from the certificate if available.
SP8: If the selected cause is trivial or unlikely to cause death, select a more appropriate condition from the certificate if available.

Return JSON exactly:
{
  "sp_rule": "SP3|SP4|SP5|SP6|SP7|SP8|REVIEW",
  "selected_line": "a|b|c|d|II-1|II-2|II-3|",
  "selected_cause": "string",
  "full_sequence_valid": true,
  "partial_sequence_valid": true,
  "causal_links": [
    {"from_lower_line": "b", "to_upper_line": "a", "valid": true, "reason": "short reason"}
  ],
  "warnings": ["string"],
  "needs_manual_review": false,
  "explanation": "short explanation"
}
"""
    user_payload = {
        "part1_chain_immediate_to_underlying": part1_chain,
        "part2_conditions": part2_conditions,
        "excel_metadata_flags_for_certificate_causes": coded_flags,
        "instruction": "Apply SP1-SP8. Select only a cause already written in this payload. Do not invent conditions or ICD codes.",
    }

    fallback = base.copy()
    try:
        out = call_claude_json(
            api_key=api_key,
            system_prompt=system_prompt,
            user_prompt=json.dumps(user_payload, ensure_ascii=False, indent=2),
            max_tokens=1000,
            fallback=fallback,
        )
        if not isinstance(out, dict):
            return fallback
        allowed = {normalize_cause_key(x["cause"]): x for x in conditions}
        selected_key = normalize_cause_key(out.get("selected_cause", ""))
        selected_line = str(out.get("selected_line", "")).lower()
        line_ok = any(str(x["line"]).lower() == selected_line for x in conditions)
        cause_ok = selected_key in allowed if selected_key else False
        if out.get("sp_rule") not in {"SP3", "SP4", "SP5", "SP6", "SP7", "SP8", "REVIEW"}:
            out["sp_rule"] = "REVIEW"
            out["needs_manual_review"] = True
        if out.get("sp_rule") != "REVIEW" and not (line_ok or cause_ok):
            out["sp_rule"] = "REVIEW"
            out["selected_line"] = ""
            out["selected_cause"] = ""
            out.setdefault("warnings", []).append("LLM selected a condition that was not found on the certificate.")
            out["needs_manual_review"] = True
        return {
            "sp_rule": str(out.get("sp_rule", "REVIEW")),
            "selected_line": str(out.get("selected_line", "") or ""),
            "selected_cause": str(out.get("selected_cause", "") or ""),
            "full_sequence_valid": out.get("full_sequence_valid", False),
            "partial_sequence_valid": out.get("partial_sequence_valid", False),
            "causal_links": list(out.get("causal_links", []) or []),
            "warnings": list(out.get("warnings", []) or []),
            "needs_manual_review": bool(out.get("needs_manual_review", False)),
            "explanation": str(out.get("explanation", "") or ""),
        }
    except Exception as e:
        fallback.setdefault("warnings", []).append(f"SP review failed: {type(e).__name__}: {e}")
        fallback["needs_manual_review"] = True
        return fallback

def refine_sp7_sp8_with_excel(sp_review: Dict, coded_causes: List[Dict]) -> Dict:
    """Use Excel/metadata flags to refine selected starting point for SP7/SP8."""
    if not coded_causes:
        return sp_review

    by_line = _coded_by_line(coded_causes)
    by_cause = _coded_by_cause(coded_causes)
    selected = None
    line = str(sp_review.get("selected_line", "")).lower()
    if line in by_line:
        selected = by_line[line]
    else:
        selected = by_cause.get(normalize_cause_key(sp_review.get("selected_cause", "")))

    if not selected:
        return sp_review

    selected_bad_sp7 = is_excel_ill_defined(selected)
    selected_bad_sp8 = is_excel_unlikely_to_cause_death(selected) or acceptable_main_bool(selected.get("acceptable_main", "")) is False
    if not (selected_bad_sp7 or selected_bad_sp8):
        return sp_review

    # Prefer a more specific acceptable Part I cause, lowest first, then Part II.
    part1 = [x for x in coded_causes if x.get("role") in {"immediate", "contributing", "underlying"}]
    part2 = [x for x in coded_causes if x.get("role") == "other"]
    candidates = list(reversed(part1)) + part2
    replacement = None
    for item in candidates:
        if item is selected:
            continue
        if is_excel_ill_defined(item):
            continue
        if is_excel_unlikely_to_cause_death(item):
            continue
        if acceptable_main_bool(item.get("acceptable_main", "")) is False:
            continue
        if item.get("code_formatted"):
            replacement = item
            break

    out = dict(sp_review)
    out.setdefault("warnings", [])
    if selected_bad_sp7:
        out["warnings"].append(f"Selected starting point '{selected.get('cause','')}' appears ill-defined or vague based on coding metadata.")
        if replacement:
            out["sp_rule"] = "SP7"
    elif selected_bad_sp8:
        out["warnings"].append(f"Selected starting point '{selected.get('cause','')}' may be unlikely or not acceptable as the underlying cause based on coding metadata.")
        if replacement:
            out["sp_rule"] = "SP8"

    if replacement:
        out["selected_line"] = str(replacement.get("line", ""))
        out["selected_cause"] = str(replacement.get("cause", ""))
        out["needs_manual_review"] = True
        out["explanation"] = (out.get("explanation", "") + " " if out.get("explanation") else "") + "A more specific/acceptable condition from the certificate was suggested based on coding metadata."
    else:
        out["needs_manual_review"] = True
        out["explanation"] = (out.get("explanation", "") + " " if out.get("explanation") else "") + "No clearly better certificate condition was found automatically; manual review is required."
    return out

def apply_sp_engine(api_key: str, concepts: Dict, coded_causes: List[Dict]) -> Dict:
    part1_chain = concepts.get("part1_chain", []) or []
    part2_conditions = concepts.get("part2_conditions", []) or []
    sp = llm_sp1_sp8_review(api_key, part1_chain, part2_conditions, coded_causes)

    # Agent 3 must judge mortality sequence / WHO-SP / TABB only.
    # Do NOT downgrade Agent 3 because of Excel coding metadata such as
    # R-code, ill-defined, AcceptableMain, or manual_review flags. Those
    # warnings belong to Agent 2.
    #
    # If SP7/SP8 refinement is needed for final coding quality, keep it in
    # Agent 2/final review rather than the compact Agent 3 result.
    sp["selected_code"] = selected_code_for_sp(sp, coded_causes)
    return sp

def quality_from_sp_and_validation(coded_causes: List[Dict], validation: Dict, sp_review: Dict) -> str:
    if not coded_causes:
        return "Needs Review"
    if any(not x.get("code_formatted") for x in coded_causes):
        return "Needs Review"
    if any(str(x.get("selection_status", "")) == "manual_review" for x in coded_causes):
        return "Needs Review"
    if sp_review.get("needs_manual_review") or sp_review.get("sp_rule") in {"REVIEW", "SP5", "SP7", "SP8"}:
        return "Needs Review"
    if validation.get("coding_issues"):
        return "Needs Review"
    return "Excellent"


# =============================================================================
# Three LLM Agent Workflow + TABB support
# =============================================================================
AGENT1_SYSTEM_PROMPT = """
You are Agent 1: Input Validation Agent for an electronic death certificate.

Task:
Review the doctor's structured Part I and Part II entries before ICD coding.

Strict rules:
- Use only the provided certificate fields.
- Do not assign ICD codes.
- Do not add new diseases.
- Identify form and clinical-entry problems that should be fixed before retrieval.
- Return concise doctor-facing guidance.
- Return only valid JSON.

Return JSON exactly:
{
  "status": "pass|warning|block",
  "summary": "short doctor-facing summary",
  "issues": [
    {"line": "string", "severity": "error|warning|info", "message": "string"}
  ],
  "condition_to_continue": "string"
}
"""

AGENT2_SYSTEM_PROMPT = """
You are Agent 2: ICD Candidate Validation Agent for an electronic death certificate.

Task:
Review ICD-10 candidate retrieval and selected ICD codes.

Strict rules:
- The Excel/metadata ICD rows are the only coding source of truth.
- Do not invent ICD codes.
- Do not suggest codes that are not listed in the retrieved candidates.
- Review whether the selected code is plausible for the doctor's cause text.
- Review AcceptableMain, gender restrictions, vague/R-code issues, and manual-review flags.
- Return concise doctor-facing guidance.
- Return only valid JSON.

Return JSON exactly:
{
  "status": "pass|warning|block",
  "summary": "short summary",
  "issues": [
    {"line": "string", "severity": "error|warning|info", "message": "string"}
  ],
  "condition_to_continue": "string"
}
"""

AGENT3_SYSTEM_PROMPT = """
You are Agent 3: Mortality Sequence / WHO Rules Agent for an electronic death certificate.

Task:
Review the final Part I causal sequence, SP1-SP8 starting-point logic, TABB rule matches, and the UCOD decision.

Strict rules:
- Use only certificate causes and ICD codes already selected.
- Do not invent diseases or ICD codes.
- Explain whether the selected starting point / UCOD is acceptable.
- If TABB or SP logic indicates uncertainty, require manual review.
- Return concise doctor-facing guidance.
- Return only valid JSON.

Return JSON exactly:
{
  "status": "pass|warning|block",
  "summary": "short summary",
  "issues": [
    {"line": "string", "severity": "error|warning|info", "message": "string"}
  ],
  "condition_to_continue": "string"
}
"""

def reset_agent_workflow(clear_codes: bool = True) -> None:
    """Reset the sequential agent workflow after doctor edits."""
    for key in [
        "agent_step",
        "agent1_result",
        "agent2_result",
        "agent3_result",
        "agent1_done",
        "agent2_done",
        "agent3_done",
    ]:
        if key in st.session_state:
            del st.session_state[key]
    st.session_state.agent_step = 1
    if clear_codes:
        st.session_state.icd_results = None
        for k in list(st.session_state.keys()):
            if str(k).startswith("code_edit_"):
                del st.session_state[k]

def build_structured_cod_from_form_state(fd: Dict) -> Tuple[List[Dict], List[Dict]]:
    """Read the editable doctor fields from session_state/form_data."""
    part1_defs_local = [
        ("a", "immediate"),
        ("b", "contributing"),
        ("c", "contributing"),
        ("d", "underlying"),
    ]
    part1_chain = []
    for letter, role in part1_defs_local:
        cause_raw = st.session_state.get(f"agent_part1_{letter}_cause", fd.get(f"part1_{letter}_cause", ""))
        interval_raw = st.session_state.get(f"agent_part1_{letter}_interval", fd.get(f"part1_{letter}_interval", ""))
        cause = clean_cause_input(cause_raw)
        if cause:
            part1_chain.append({
                "line": letter,
                "cause": cause,
                "interval": str(interval_raw or "").strip() or "—",
                "role": role,
            })

    part2_conditions = []
    for i in range(1, 4):
        cause_raw = st.session_state.get(f"agent_part2_{i}_cause", fd.get(f"part2_{i}_cause", ""))
        interval_raw = st.session_state.get(f"agent_part2_{i}_interval", fd.get(f"part2_{i}_interval", ""))
        cause = clean_cause_input(cause_raw)
        if cause:
            part2_conditions.append({
                "line": f"II-{i}",
                "cause": cause,
                "interval": str(interval_raw or "").strip() or "—",
                "role": "other",
            })
    return part1_chain, part2_conditions

def save_agent_cod_to_form_data(fd: Dict, part1_chain: List[Dict], part2_conditions: List[Dict]) -> None:
    """Persist edited doctor fields back into form_data."""
    for letter in ["a", "b", "c", "d"]:
        fd[f"part1_{letter}_cause"] = ""
        fd[f"part1_{letter}_interval"] = ""
    for i in range(1, 4):
        fd[f"part2_{i}_cause"] = ""
        fd[f"part2_{i}_interval"] = ""

    for x in part1_chain:
        line = str(x.get("line", "")).lower()
        fd[f"part1_{line}_cause"] = x.get("cause", "")
        fd[f"part1_{line}_interval"] = x.get("interval", "—")

    for x in part2_conditions:
        idx = str(x.get("line", "")).replace("II-", "")
        fd[f"part2_{idx}_cause"] = x.get("cause", "")
        fd[f"part2_{idx}_interval"] = x.get("interval", "—")

    narrative_parts = []
    if part1_chain:
        narrative_parts.append(" due to ".join([f"{x['cause']} ({x.get('interval','—')})" for x in part1_chain]))
    if part2_conditions:
        narrative_parts.append("Other significant conditions included " + ", ".join([f"{x['cause']} ({x.get('interval','—')})" for x in part2_conditions]))

    fd["manual_part1_chain"] = part1_chain
    fd["manual_part2_conditions"] = part2_conditions
    fd["free_text"] = ". ".join(narrative_parts) + "." if narrative_parts else ""
    st.session_state.form_data.update(fd)

@st.cache_resource(show_spinner=False)
def load_tabb_rules() -> pd.DataFrame:
    """Load local TABB CSV if available. Returns an empty table when unavailable."""
    for path in TABB_RULES_CSV_PATHS:
        try:
            if path and os.path.exists(path):
                df = pd.read_csv(path).fillna("")
                expected = ["anchor", "rule_type", "modifier", "source_start", "source_end", "target", "raw_body", "page"]
                for col in expected:
                    if col not in df.columns:
                        df[col] = ""
                df["anchor_norm"] = df["anchor"].apply(normalize_icd_for_tabb)
                df["source_start_norm"] = df["source_start"].apply(normalize_icd_for_tabb)
                df["source_end_norm"] = df["source_end"].apply(normalize_icd_for_tabb)
                df["target_norm"] = df["target"].apply(normalize_icd_for_tabb)
                return df
        except Exception:
            continue
    return pd.DataFrame(columns=[
        "anchor", "rule_type", "modifier", "source_start", "source_end", "target",
        "raw_body", "page", "anchor_norm", "source_start_norm", "source_end_norm", "target_norm"
    ])

def normalize_icd_for_tabb(code: str) -> str:
    """Normalize ICD code for TABB comparison: R57.2 -> R572."""
    return re.sub(r"[^A-Z0-9]", "", str(code or "").upper().strip())

def icd_sort_key_for_tabb(code: str) -> Tuple[str, int, str]:
    c = normalize_icd_for_tabb(code)
    if len(c) < 3:
        return ("", -1, "")
    letter = c[0]
    try:
        category = int(c[1:3])
    except Exception:
        category = -1
    suffix = c[3:]
    return (letter, category, suffix)

def code_in_tabb_range(code: str, start: str, end: str) -> bool:
    """Check if normalized ICD code is inside a TABB code/range."""
    c = normalize_icd_for_tabb(code)
    s = normalize_icd_for_tabb(start)
    e = normalize_icd_for_tabb(end) or s
    if not c or not s:
        return False

    if s == e:
        # A three-character category such as B24 should match B24 and B24 subcodes.
        if len(s) == 3:
            return c[:3] == s
        return c == s

    sk = icd_sort_key_for_tabb(s)
    ck = icd_sort_key_for_tabb(c)
    ek = icd_sort_key_for_tabb(e)
    if sk[0] != ck[0] or ek[0] != ck[0]:
        return False

    # For category range checks, tuple comparison is sufficient after normalization.
    return sk <= ck <= ek

def query_tabb(tabb_df: pd.DataFrame, anchor_code: str, other_code: str, max_matches: int = 8) -> List[Dict]:
    """Return TABB rules where anchor_code is the rule anchor and other_code is in source range."""
    if tabb_df is None or tabb_df.empty:
        return []
    anchor = normalize_icd_for_tabb(anchor_code)
    other = normalize_icd_for_tabb(other_code)
    if not anchor or not other:
        return []

    rules = tabb_df[tabb_df["anchor_norm"] == anchor]
    # Fallback to category-level anchor if the exact subcode does not exist.
    if rules.empty and len(anchor) > 3:
        rules = tabb_df[tabb_df["anchor_norm"] == anchor[:3]]

    matches = []
    for _, row in rules.iterrows():
        if code_in_tabb_range(other, row.get("source_start_norm", ""), row.get("source_end_norm", "")):
            matches.append({
                "anchor": str(row.get("anchor", "")),
                "anchor_checked": anchor_code,
                "other_checked": other_code,
                "rule_type": str(row.get("rule_type", "")),
                "modifier": str(row.get("modifier", "")),
                "source_start": str(row.get("source_start", "")),
                "source_end": str(row.get("source_end", "")),
                "target": str(row.get("target", "")),
                "raw_body": str(row.get("raw_body", "")),
                "page": str(row.get("page", "")),
                "direction": "anchor_to_other",
            })
            if len(matches) >= max_matches:
                break
    return matches

def tabb_rule_message(match: Dict) -> str:
    rt = str(match.get("rule_type", "")).upper()
    anchor = match.get("anchor_checked", "")
    other = match.get("other_checked", "")
    target = match.get("target", "")
    meanings = {
        "DS": "Direct sequel rule",
        "DSC": "Direct sequel combination",
        "LMP": "Linkage with mention preference",
        "LMC": "Linkage with mention combination",
        "SMP": "Specificity preference",
        "SMC": "Specificity combination",
        "SDC": "Specificity due-to combination",
        "TRIV": "Trivial condition rule",
    }
    base = meanings.get(rt, f"TABB rule {rt}")
    if target:
        return f"{base}: {anchor} with {other} points to target {target}."
    return f"{base}: relationship found between {anchor} and {other}."

def run_tabb_certificate_check(tabb_df: pd.DataFrame, coded_causes: List[Dict], sp_review: Dict, validation: Dict) -> Dict:
    """Check selected UCOD/start point against other selected ICD codes using TABB."""
    selected_code = (
        sp_review.get("selected_code")
        or validation.get("underlying_cause")
        or ""
    )
    selected_code = str(selected_code or "").strip()
    matches = []
    reverse_matches = []

    if not selected_code:
        return {
            "available": bool(tabb_df is not None and not tabb_df.empty),
            "selected_code": "",
            "matches": [],
            "reverse_matches": [],
            "needs_manual_review": True,
            "summary": "No selected starting-point ICD code was available for TABB checking.",
        }

    if tabb_df is None or tabb_df.empty:
        return {
            "available": False,
            "selected_code": selected_code,
            "matches": [],
            "reverse_matches": [],
            "needs_manual_review": False,
            "summary": "TABB CSV was not found. SP review was applied without TABB table confirmation.",
        }

    for item in coded_causes:
        code = str(item.get("code_formatted", "") or "").strip()
        if not code or normalize_icd_for_tabb(code) == normalize_icd_for_tabb(selected_code):
            continue
        direct = query_tabb(tabb_df, selected_code, code)
        for m in direct:
            m["other_line"] = item.get("line", "")
            m["other_cause"] = item.get("cause", "")
            matches.append(m)
        reverse = query_tabb(tabb_df, code, selected_code)
        for m in reverse:
            m["other_line"] = item.get("line", "")
            m["other_cause"] = item.get("cause", "")
            m["direction"] = "other_to_selected"
            reverse_matches.append(m)

    important_rule_types = {"DS", "DSC", "LMP", "LMC", "SMP", "SMC", "SDC", "TRIV"}
    needs_review = any(str(m.get("rule_type", "")).upper() in important_rule_types for m in matches + reverse_matches)

    if matches or reverse_matches:
        messages = [tabb_rule_message(m) for m in (matches + reverse_matches)[:5]]
        summary = "TABB match detected: " + " ".join(messages)
    else:
        summary = "No TABB rule matched the selected starting point against the other certificate codes."

    return {
        "available": True,
        "selected_code": selected_code,
        "matches": matches[:12],
        "reverse_matches": reverse_matches[:12],
        "needs_manual_review": needs_review,
        "summary": summary,
    }

def apply_tabb_result_to_validation(validation: Dict, tabb_result: Dict) -> Dict:
    out = dict(validation)
    issues = list(out.get("coding_issues", []) or [])
    if tabb_result.get("available") and (tabb_result.get("matches") or tabb_result.get("reverse_matches")):
        for m in (tabb_result.get("matches", []) + tabb_result.get("reverse_matches", []))[:5]:
            msg = "TABB: " + tabb_rule_message(m)
            if msg not in issues:
                issues.append(msg)
    elif not tabb_result.get("available"):
        msg = "TABB rules CSV was not available; mortality sequence was checked using SP logic only."
        if msg not in issues:
            issues.append(msg)

    out["coding_issues"] = issues
    out["tabb_result"] = tabb_result
    if tabb_result.get("needs_manual_review"):
        out["overall_quality"] = "Needs Review"
    return out

def agent1_input_validation_with_llm(api_key: str, part1_chain: List[Dict], part2_conditions: List[Dict]) -> Dict:
    precheck = pre_validate_structured_cod(part1_chain, part2_conditions)
    cross_issues = add_cross_field_cod_issues(precheck.get("part1_chain", []), precheck.get("part2_conditions", []))
    sequence_screen = live_sequence_screen(precheck.get("part1_chain", []))
    sequence_issues = []
    if sequence_screen.get("valid") is False:
        problem_line = sequence_screen.get("problem_line") or "Part I"
        sequence_issues.append({
            "severity": "warning",
            "line": f"Part I ({problem_line})",
            "type": "sequence_not_confirmed",
            "message": sequence_screen.get("message", "The causal sequence needs review."),
            "blocking": False,
        })

    rule_issues = list(precheck.get("issues", [])) + cross_issues + sequence_issues
    blocking = any(x.get("severity") == "error" or x.get("blocking") for x in rule_issues)
    fallback = {
        "status": "block" if blocking else ("warning" if rule_issues else "pass"),
        "summary": "Input validation completed.",
        "issues": [
            {
                "line": str(i.get("line", "")),
                "severity": str(i.get("severity", "warning")),
                "message": str(i.get("message", "")),
            }
            for i in rule_issues
        ],
        "condition_to_continue": "Fix blocking errors before retrieval." if blocking else "Doctor may continue to ICD retrieval.",
    }

    payload = {
        "part1_chain": part1_chain,
        "part2_conditions": part2_conditions,
        "rule_based_issues": fallback["issues"],
        "sequence_screen": sequence_screen,
        "instruction": "Explain the validation result. Do not add diseases or ICD codes.",
    }
    llm = call_claude_json(api_key, AGENT1_SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False, indent=2), max_tokens=700, fallback=fallback)
    if not isinstance(llm, dict):
        llm = fallback

    # Deterministic rule status is authoritative.
    llm["status"] = fallback["status"]
    llm["blocking"] = blocking
    llm["rule_issues"] = rule_issues
    llm["precheck"] = precheck
    llm["condition_to_continue"] = fallback["condition_to_continue"]
    return llm

def agent2_rule_issues(coded_causes: List[Dict], sex_value: str) -> List[Dict]:
    issues = []
    for item in coded_causes:
        line = str(item.get("line", ""))
        cause = str(item.get("cause", ""))
        code = str(item.get("code_formatted", ""))
        if not code:
            issues.append({"line": line, "severity": "error", "message": f"No ICD code was selected for {cause}."})
        if item.get("selection_status") == "manual_review":
            issues.append({"line": line, "severity": "warning", "message": f"{cause} requires manual review."})
        if acceptable_main_bool(item.get("acceptable_main", "")) is False and item.get("role") in {"immediate", "contributing", "underlying"}:
            issues.append({"line": line, "severity": "warning", "message": f"{code} is not acceptable as a main cause."})
        if not is_gender_allowed(item.get("gender_restriction", ""), sex_value):
            issues.append({"line": line, "severity": "error", "message": f"{code} conflicts with the patient sex."})
        if is_excel_ill_defined(item):
            issues.append({"line": line, "severity": "warning", "message": f"{code} may be ill-defined or vague."})
        if is_excel_unlikely_to_cause_death(item):
            issues.append({"line": line, "severity": "warning", "message": f"{code} may be unlikely to cause death by itself."})
    return issues

def agent2_candidate_validation_with_llm(api_key: str, coded_results: Dict, patient_info: Dict) -> Dict:
    coded_causes = coded_results.get("coded_causes", []) or []
    issues = agent2_rule_issues(coded_causes, patient_info.get("sex", ""))
    has_error = any(i.get("severity") == "error" for i in issues)
    status = "block" if has_error else ("warning" if issues else "pass")

    compact = []
    for item in coded_causes:
        compact.append({
            "line": item.get("line", ""),
            "role": item.get("role", ""),
            "cause": item.get("cause", ""),
            "selected_code": item.get("code_formatted", ""),
            "short_desc": item.get("short_desc", ""),
            "acceptable_main": item.get("acceptable_main", ""),
            "gender_restriction": item.get("gender_restriction", ""),
            "selection_status": item.get("selection_status", ""),
            "selection_notes": item.get("selection_notes", ""),
            "top_candidates": [
                {
                    "code": c.get("code_formatted", ""),
                    "short_desc": c.get("short_desc", ""),
                    "acceptable_main": c.get("acceptable_main", ""),
                    "score": c.get("score", 0),
                }
                for c in item.get("candidates", [])[:5]
            ],
        })

    fallback = {
        "status": status,
        "summary": "ICD retrieval and candidate validation completed.",
        "issues": issues,
        "condition_to_continue": "Resolve missing-code errors before mortality sequence review." if has_error else "Doctor may continue to WHO/TABB sequence review.",
    }

    payload = {
        "patient_info": patient_info,
        "coded_causes_and_candidates": compact,
        "rule_based_issues": issues,
        "instruction": "Review selected ICD codes. Do not invent codes. Only discuss retrieved candidates and selected Excel rows.",
    }
    llm = call_claude_json(api_key, AGENT2_SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False, indent=2), max_tokens=900, fallback=fallback)
    if not isinstance(llm, dict):
        llm = fallback

    llm["status"] = status
    llm["blocking"] = has_error
    llm["rule_issues"] = issues
    llm["condition_to_continue"] = fallback["condition_to_continue"]
    return llm

def agent3_actionable_tabb_issues(tabb_result: Dict) -> List[Dict]:
    """Return only TABB findings that should make Agent 3 warn.

    TABB matches are often evidence that two certificate codes are related.
    A match is not automatically a problem. Agent 3 should warn only when
    the TABB rule clearly changes the UCOD decision or marks the selected
    cause as trivial/problematic. General DS/LMP relationship matches are
    stored internally but not shown as Agent 3 REVIEW.
    """
    if not tabb_result or not tabb_result.get("available"):
        return []

    selected_norm = normalize_icd_for_tabb(tabb_result.get("selected_code", ""))
    actionable = []
    rows = list(tabb_result.get("matches", []) or []) + list(tabb_result.get("reverse_matches", []) or [])
    for m in rows:
        rule_type = str(m.get("rule_type", "") or "").upper().strip()
        target_norm = normalize_icd_for_tabb(m.get("target", ""))
        modifier = str(m.get("modifier", "") or "").lower().strip()
        raw_body = str(m.get("raw_body", "") or "").lower().strip()

        selected_is_trivial = (
            rule_type == "TRIV"
            or "trivial" in modifier
            or "trivial" in raw_body
        )

        target_changes_selected_code = bool(
            target_norm
            and selected_norm
            and target_norm != selected_norm
            and target_norm not in {"NAN", "NONE"}
        )

        # Only these should change the compact Agent 3 result.
        is_actionable = selected_is_trivial or (rule_type in {"DSC", "LMC", "SMC", "SDC"} and target_changes_selected_code)

        if is_actionable:
            actionable.append({
                "line": m.get("other_line", ""),
                "severity": "warning",
                "message": "TABB actionable rule: " + tabb_rule_message(m),
            })
    return actionable

def agent3_sequence_status(sp_review: Dict, tabb_result: Dict) -> Tuple[str, List[Dict], str]:
    """Decide Agent 3 status from SP/TABB sequence only.

    Agent 2 owns ICD-code quality warnings. Agent 3 should be PASS when the
    Part I causal sequence supports the selected UCOD and no actionable TABB
    rule changes it.
    """
    issues: List[Dict] = []
    sp_rule = str(sp_review.get("sp_rule", "REVIEW") or "REVIEW").upper()
    selected = str(sp_review.get("selected_cause", "") or "").strip()
    selected_code = str(sp_review.get("selected_code", "") or "").strip()

    sequence_confirmed = (
        sp_rule in {"SP1", "SP2", "SP3", "SP4", "SP6"}
        and bool(selected)
        and not (sp_review.get("full_sequence_valid") is False and sp_rule in {"SP3"})
    )

    # Keep only true sequence warnings. Ignore coding-metadata wording that may
    # be produced by the LLM or older SP refinements.
    for warning in sp_review.get("warnings", []) or []:
        w = str(warning).strip()
        wl = w.lower()
        if not w:
            continue
        if any(term in wl for term in [
            "coding", "metadata", "ill-defined", "ill defined", "vague",
            "acceptablemain", "not acceptable", "manual review", "r-code",
        ]):
            continue
        if sequence_confirmed:
            continue
        issues.append({
            "line": sp_review.get("selected_line", ""),
            "severity": "warning",
            "message": w,
        })

    if not sequence_confirmed:
        issues.append({
            "line": sp_review.get("selected_line", ""),
            "severity": "warning",
            "message": sp_review.get("explanation", "SP/WHO review could not fully confirm the UCOD starting point."),
        })

    issues.extend(agent3_actionable_tabb_issues(tabb_result))

    if not issues:
        code_txt = f" ({selected_code})" if selected_code else ""
        summary = f"UCOD sequence accepted. Selected starting point: {selected}{code_txt}."
        return "pass", [], summary

    return "warning", issues, "UCOD sequence needs review based on SP/WHO or actionable TABB findings."

def agent3_mortality_sequence_with_llm(api_key: str, coded_results: Dict, tabb_df: pd.DataFrame) -> Dict:
    concepts = coded_results.get("concepts", {}) or {}
    coded_causes = coded_results.get("coded_causes", []) or []
    validation = coded_results.get("validation", {}) or {}

    # SP/WHO review selects the starting point / UCOD candidate.
    sp_review = apply_sp_engine(api_key, concepts, coded_causes)
    validation = apply_sp_result_to_validation(validation, sp_review, coded_causes)

    # TABB is checked, but coding-quality warnings from Agent 2 should not make
    # Agent 3 fail. Agent 3 status is based only on sequence/SP/TABB actionability.
    tabb_result = run_tabb_certificate_check(tabb_df, coded_causes, sp_review, validation)
    agent3_status, rule_issues, agent3_summary = agent3_sequence_status(sp_review, tabb_result)

    validation["tabb_result"] = tabb_result
    validation["agent3_sequence_status"] = agent3_status
    validation["agent3_sequence_summary"] = agent3_summary

    # Preserve final certificate quality separately. Coding issues can still make
    # the final certificate need review, but the compact Agent 3 output remains
    # focused on mortality-sequence correctness.
    if agent3_status == "pass":
        validation.setdefault("overall_quality", "Good")
        if not validation.get("coding_issues"):
            validation["overall_quality"] = "Excellent"
    else:
        validation["overall_quality"] = "Needs Review"

    fallback = {
        "status": agent3_status,
        "summary": agent3_summary,
        "issues": rule_issues,
        "condition_to_continue": "Certificate can continue to final preview." if agent3_status == "pass" else "Manual review is recommended before final submission.",
    }

    payload = {
        "part1_chain": concepts.get("part1_chain", []),
        "part2_conditions": concepts.get("part2_conditions", []),
        "coded_causes": [
            {
                "line": x.get("line", ""),
                "role": x.get("role", ""),
                "cause": x.get("cause", ""),
                "code": x.get("code_formatted", ""),
                "short_desc": x.get("short_desc", ""),
                "acceptable_main": x.get("acceptable_main", ""),
            }
            for x in coded_causes
        ],
        "sp_review": sp_review,
        "tabb_result": tabb_result,
        "agent3_rule_issues": rule_issues,
        "instruction": "Explain only the mortality sequence / SP / TABB result. Do not repeat Agent 2 coding-quality warnings unless they directly change UCOD selection.",
    }
    llm = call_claude_json(api_key, AGENT3_SYSTEM_PROMPT, json.dumps(payload, ensure_ascii=False, indent=2), max_tokens=800, fallback=fallback)
    if not isinstance(llm, dict):
        llm = fallback

    # Deterministic sequence status is authoritative. LLM may phrase the summary,
    # but cannot downgrade a valid sequence because of Agent 2 coding issues.
    llm["status"] = agent3_status
    # Deterministic summary is authoritative so Agent 3 does not repeat Agent 2 coding warnings.
    llm["summary"] = agent3_summary
    llm["blocking"] = False
    llm["rule_issues"] = rule_issues
    llm["issues"] = rule_issues
    llm["sp_review"] = sp_review
    llm["tabb_result"] = tabb_result
    llm["validation"] = validation
    llm["condition_to_continue"] = fallback["condition_to_continue"]

    coded_results["validation"] = validation
    return llm

def agent_status_class(status: str) -> str:
    if status == "pass":
        return "agent-status-pass"
    if status == "block":
        return "agent-status-error"
    return "agent-status-warn"

def render_agent_stepper(current_step: int) -> None:
    labels = [
        (1, "Input"),
        (2, "Retrieval"),
        (3, "WHO/TABB"),
    ]
    html_pills = []
    for num, label in labels:
        cls = "agent-step-pill active" if num == current_step else ("agent-step-pill done" if num < current_step else "agent-step-pill")
        html_pills.append(f'<span class="{cls}">Agent {num}: {escape(label)}</span>')
        if num < 3:
            html_pills.append('<span style="color:#7b8d80;font-weight:900">→</span>')
    st.markdown('<div class="agent-mini-stepper">' + "".join(html_pills) + '</div>', unsafe_allow_html=True)

def render_agent_card_header(step: int, title: str, subtitle: str, state: str = "active") -> None:
    """Compact title card only.

    Important: do not leave an open HTML <div> across Streamlit widgets.
    Streamlit renders each element separately, so an open div creates an empty
    square and the output appears outside it. The actual agent output is
    rendered by render_agent_result() as its own bordered square/card.
    """
    state_class = "active" if state == "active" else ("done" if state == "done" else "blocked")
    st.markdown(
        f"""
        <div class="agent-card {state_class}">
          <div class="agent-kicker">AGENT {step}</div>
          <div class="agent-title">{escape(title)}</div>
          <div class="agent-subtitle">{escape(subtitle)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

def close_agent_card() -> None:
    # No-op in compact mode. Cards are closed inside render_agent_card_header().
    return

def render_agent_result(result: Dict) -> None:
    """Compact agent output renderer.
    Shows only the agent result summary and a very short issue count.
    Detailed findings, candidate tables, prompts, and rule internals are intentionally hidden.
    """
    if not result:
        st.markdown(
            '<div class="agent-output-box">Run this agent to see its output.</div>',
            unsafe_allow_html=True,
        )
        return

    status = str(result.get("status", "warning")).lower()
    status_label = {
        "pass": "PASSED",
        "warning": "REVIEW SUGGESTED",
        "block": "BLOCKED",
    }.get(status, status.upper())

    status_class = "block" if status == "block" else ("warn" if status == "warning" else "")
    summary = str(result.get("summary", "Agent completed its review.") or "Agent completed its review.")

    issues = result.get("issues", []) or result.get("rule_issues", []) or []
    errors = [i for i in issues if isinstance(i, dict) and str(i.get("severity", "")).lower() == "error"]
    warnings = [i for i in issues if isinstance(i, dict) and str(i.get("severity", "")).lower() == "warning"]
    infos = [i for i in issues if isinstance(i, dict) and str(i.get("severity", "")).lower() == "info"]

    if errors:
        output_note = f"{len(errors)} blocking issue(s) found. Please correct the doctor-entry fields before continuing."
    elif warnings:
        output_note = f"{len(warnings)} review warning(s) found. You may continue, but review is recommended."
    elif infos:
        output_note = f"{len(infos)} informational note(s). No review warning was detected."
    else:
        output_note = "No blocking issue was detected."

    box_class = "agent-output-box"
    if status == "warning":
        box_class += " warn"
    elif status == "block":
        box_class += " block"

    html_out = (
        f'<div class="{box_class}">'
        f'<div class="agent-output-status {status_class}">Output: {escape(status_label)}</div>'
        f'<div>{escape(summary)}</div>'
        f'<div class="agent-hidden-details-note">{escape(output_note)}</div>'
        '</div>'
    )
    st.markdown(html_out, unsafe_allow_html=True)

def render_agent_prompt_box(prompt_text: str) -> None:
    """Prompt details are hidden in compact UI mode."""
    return

def render_doctor_edit_panel(fd: Dict) -> Tuple[List[Dict], List[Dict]]:
    """Left-side editable doctor panel used on the agent workflow page."""
    st.markdown('<div class="doctor-edit-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Doctor Editable Certificate Fields</div>', unsafe_allow_html=True)
    st.caption("The doctor can modify these fields at any time. After changes, click Save Changes & Reset Agents.")

    st.markdown("**Part I — Direct causal sequence**")
    labels = {
        "a": ("Immediate cause", "e.g., septic shock"),
        "b": ("Due to / as a consequence of", "e.g., generalized peritonitis"),
        "c": ("Due to / as a consequence of", "e.g., perforated sigmoid diverticulitis"),
        "d": ("Due to / as a consequence of", "optional"),
    }
    for letter in ["a", "b", "c", "d"]:
        c0, c1, c2 = st.columns([0.08, 0.67, 0.25])
        with c0:
            st.markdown(f"<div style='padding-top:1.9rem;font-weight:800;color:#006940'>({letter})</div>", unsafe_allow_html=True)
        st.session_state.setdefault(f"agent_part1_{letter}_cause", fd.get(f"part1_{letter}_cause", ""))
        st.session_state.setdefault(f"agent_part1_{letter}_interval", fd.get(f"part1_{letter}_interval", ""))
        with c1:
            st.text_input(
                labels[letter][0],
                key=f"agent_part1_{letter}_cause",
                placeholder=labels[letter][1],
            )
        with c2:
            st.text_input(
                "Interval",
                key=f"agent_part1_{letter}_interval",
                placeholder="e.g., 2 days",
            )

    st.markdown("---")
    st.markdown("**Part II — Other significant conditions**")
    for i in range(1, 4):
        c0, c1, c2 = st.columns([0.08, 0.67, 0.25])
        with c0:
            st.markdown(f"<div style='padding-top:1.9rem;font-weight:800;color:#1a4a7a'>II-{i}</div>", unsafe_allow_html=True)
        st.session_state.setdefault(f"agent_part2_{i}_cause", fd.get(f"part2_{i}_cause", ""))
        st.session_state.setdefault(f"agent_part2_{i}_interval", fd.get(f"part2_{i}_interval", ""))
        with c1:
            st.text_input(
                f"Other significant condition {i}",
                key=f"agent_part2_{i}_cause",
                placeholder="e.g., type 2 diabetes mellitus",
            )
        with c2:
            st.text_input(
                "Interval",
                key=f"agent_part2_{i}_interval",
                placeholder="e.g., 12 years",
            )

    part1_chain, part2_conditions = build_structured_cod_from_form_state(fd)

    b_save, b_back = st.columns([1.4, 1])
    with b_save:
        if st.button("Save Changes & Reset Agents", type="primary", use_container_width=True):
            save_agent_cod_to_form_data(fd, part1_chain, part2_conditions)
            reset_agent_workflow(clear_codes=True)
            st.success("Changes saved. Agent workflow reset to Agent 1.")
            st.rerun()
    with b_back:
        if st.button("Back to Cause Page", use_container_width=True):
            save_agent_cod_to_form_data(fd, part1_chain, part2_conditions)
            st.session_state.icd_results = None
            st.session_state.page = 3
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)
    return part1_chain, part2_conditions

def render_compact_coded_causes(coded_causes: List[Dict]) -> None:
    rows = []
    for item in coded_causes:
        rows.append({
            "Line": item.get("line", ""),
            "Role": item.get("role", ""),
            "Cause": item.get("cause", ""),
            "ICD-10": item.get("code_formatted", ""),
            "Disease Name": item.get("short_desc", ""),
            "Status": item.get("selection_status", ""),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No coded causes yet.")


# =============================================================================
# PAGE 1
# =============================================================================
if st.session_state.page == 1:
    render_steps(1)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Patient Basic Information</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        full_name = st.text_input("Full Name*", placeholder="Mohammed Abdullah Al-Otaibi")
        national_id = st.text_input("National ID / Iqama*", placeholder="1XXXXXXXXX")
        nationality = st.text_input("Nationality", placeholder="Saudi")
        dob = st.date_input(
            "Date of Birth",
            value=datetime.date(1960, 1, 1),
            min_value=datetime.date(1900, 1, 1),
            max_value=datetime.date.today()
        )
    with c2:
        sex = st.selectbox("Sex*", ["Male", "Female"])
        marital_status = st.selectbox("Marital Status", ["Single", "Married", "Divorced", "Widowed"])
        education = st.selectbox("Education", ["Illiterate", "Primary", "Intermediate", "Secondary", "Diploma", "Bachelor", "Postgraduate", "Unknown"])
        occupation = st.text_input("Occupation", placeholder="Engineer")
        address = st.text_input("Address", placeholder="Riyadh")

    st.markdown("---")
    c3, c4 = st.columns(2)
    with c3:
        dod = st.date_input("Date of Death*", value=datetime.date.today())
        time_of_death = st.time_input("Time of Death")
        place_of_death = st.selectbox("Place of Death", ["Hospital", "Emergency", "Home", "Road", "Unknown"])
    with c4:
        cert_number = st.text_input("Certificate Number", placeholder="DC-2026-XXXXX")
        date_issued = st.date_input("Issue Date", value=datetime.date.today())

    st.markdown('</div>', unsafe_allow_html=True)

    age_years = max(0, (dod - dob).days // 365) if dob and dod else 0
    st.info(f"Age at death: {age_years} years")

    if st.button("Next"):
        if not full_name or not national_id:
            st.error("Please enter the patient's full name and ID.")
        else:
            st.session_state.form_data.update({
                "full_name": full_name,
                "national_id": national_id,
                "nationality": nationality,
                "dob": str(dob),
                "dod": str(dod),
                "time_of_death": str(time_of_death),
                "place_of_death": place_of_death,
                "sex": sex,
                "marital_status": marital_status,
                "education": education,
                "occupation": occupation,
                "address": address,
                "age_years": age_years,
                "cert_number": cert_number,
                "date_issued": str(date_issued),
            })
            st.session_state.page = 2
            st.rerun()

# =============================================================================
# PAGE 2
# =============================================================================
elif st.session_state.page == 2:
    render_steps(2)
    fd = st.session_state.form_data

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Medical History</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        had_surgery = st.radio("Surgery within last month?", ["No", "Yes", "Unknown"])
        surgery_details = ""
        if had_surgery == "Yes":
            surgery_details = st.text_area("Surgery Details", placeholder="Procedure, date, hospital")

        autopsy_required = st.radio("Autopsy required?", ["No", "Yes", "Undetermined"])
        autopsy_reason = ""
        if autopsy_required == "Yes":
            autopsy_reason = st.text_input("Reason for Autopsy")

    with c2:
        death_type = st.selectbox("Type of Death", ["Natural", "Accident", "Suicide", "Homicide", "Undetermined"])
        inpatient_days = st.number_input("Hospital Stay (days)", min_value=0, value=0)
        was_pregnant = "N/A"
        if fd.get("sex") == "Female":
            was_pregnant = st.selectbox("Pregnancy Status", ["No", "Pregnant", "During delivery", "Within 42 days postpartum", "N/A"])
        chronic_conditions = st.multiselect(
            "Known Chronic Conditions",
            ["Diabetes", "Hypertension", "Heart disease", "Renal disease", "Liver disease",
             "Cancer", "Pulmonary disease", "Obesity", "Neurological disease", "Other"]
        )

    st.markdown('</div>', unsafe_allow_html=True)

    b1, b2, _ = st.columns([1, 1, 6])
    with b1:
        if st.button("Back", use_container_width=True):
            st.session_state.page = 1
            st.rerun()
    with b2:
        if st.button("Next", use_container_width=True):
            st.session_state.form_data.update({
                "had_surgery": had_surgery,
                "surgery_details": surgery_details,
                "autopsy_required": autopsy_required,
                "autopsy_reason": autopsy_reason,
                "death_type": death_type,
                "inpatient_days": inpatient_days,
                "was_pregnant": was_pregnant,
                "chronic_conditions": chronic_conditions,
            })
            st.session_state.page = 3
            st.rerun()

# =============================================================================
# PAGE 3
# =============================================================================
elif st.session_state.page == 3:
    render_steps(3)
    fd = st.session_state.form_data
    df_source = st.session_state.df_source
    faiss_index = st.session_state.faiss_index
    bm25 = st.session_state.bm25_index

    st.markdown('<div class="section-title">Cause of Death — WHO Structured Form</div>', unsafe_allow_html=True)
    st.caption("Enter one medical condition per line. Guidance appears directly under the line that needs attention.")

    part1_defs = [
        ("a", "Immediate cause", "immediate", "e.g., septic shock"),
        ("b", "Due to / as a consequence of", "contributing", "e.g., generalized peritonitis"),
        ("c", "Due to / as a consequence of", "contributing", "e.g., perforated sigmoid diverticulitis"),
        ("d", "Due to / as a consequence of", "underlying", "optional if line (c) is the underlying cause"),
    ]

    raw_part1, raw_part2 = [], []
    for letter, label, role, placeholder in part1_defs:
        raw_cause = st.session_state.get(f"part1_{letter}_cause", fd.get(f"part1_{letter}_cause", ""))
        raw_interval = st.session_state.get(f"part1_{letter}_interval", fd.get(f"part1_{letter}_interval", ""))
        cause = clean_cause_input(raw_cause)
        if cause:
            raw_part1.append({"line": letter, "cause": cause, "interval": str(raw_interval or "").strip(), "role": role})
    for i in range(1, 4):
        raw_cause = st.session_state.get(f"part2_{i}_cause", fd.get(f"part2_{i}_cause", ""))
        raw_interval = st.session_state.get(f"part2_{i}_interval", fd.get(f"part2_{i}_interval", ""))
        cause = clean_cause_input(raw_cause)
        if cause:
            raw_part2.append({"line": f"II-{i}", "cause": cause, "interval": str(raw_interval or "").strip(), "role": "other"})

    precheck = pre_validate_structured_cod(raw_part1, raw_part2)
    cross_issues = add_cross_field_cod_issues(precheck["part1_chain"], precheck["part2_conditions"])
    sequence_screen = live_sequence_screen(precheck["part1_chain"])
    sequence_issues = []
    if sequence_screen.get("valid") is False:
        problem_line = sequence_screen.get("problem_line") or (precheck["part1_chain"][-1].get("line", "") if precheck["part1_chain"] else "")
        sequence_issues.append({
            "severity": "warning",
            "line": f"Part I ({problem_line})" if problem_line else "Part I",
            "type": "sequence_not_confirmed",
            "message": sequence_screen.get("message", "This causal sequence needs review before SP3 can be applied."),
            "blocking": False,
        })
    all_pre_issues = list(precheck["issues"]) + cross_issues + sequence_issues

    live_excel_issues = []
    live_candidates = {}
    if df_source is not None:
        for x in precheck["part1_chain"]:
            role = "immediate" if x["line"] == "a" else ("underlying" if x["line"] == precheck["part1_chain"][-1]["line"] else "contributing")
            issues, cands = validate_cause_line_from_excel(
                cause_text=x["cause"], line_label=f"Part I ({x['line']})", role=role,
                df_source=df_source, faiss_index=faiss_index, bm25=bm25,
                sex_value=fd.get("sex", ""), age_years=fd.get("age_years", 0), top_k=5,
            )
            live_excel_issues.extend(issues)
            live_candidates[f"Part I ({x['line']})"] = cands
        for x in precheck["part2_conditions"]:
            idx = str(x["line"]).replace("II-", "")
            issues, cands = validate_cause_line_from_excel(
                cause_text=x["cause"], line_label=f"Part II ({idx})", role="other",
                df_source=df_source, faiss_index=faiss_index, bm25=bm25,
                sex_value=fd.get("sex", ""), age_years=fd.get("age_years", 0), top_k=5,
            )
            live_excel_issues.extend(issues)
            live_candidates[f"Part II ({idx})"] = cands

    all_issues = all_pre_issues + live_excel_issues
    issues_by_field = group_issues_by_field(all_issues)
    has_any_cod_input = bool(precheck["part1_chain"] or precheck["part2_conditions"])
    blocking_issues = [x for x in all_pre_issues if x.get("severity") == "error"]
    nonblocking_issues = [x for x in all_issues if x.get("severity") != "error"]
    tentative = precheck.get("tentative_underlying", {})
    sp_info = decide_sp_rule_simple(precheck["part1_chain"], bool(blocking_issues), sequence_screen)

    left, right = st.columns([1.65, 0.95], gap="large")

    with left:
        st.markdown('<div class="section-title">Part I — Direct causal sequence</div>', unsafe_allow_html=True)
        st.caption("The condition on each lower line should explain the line above it.")

        for letter, label, role, placeholder in part1_defs:
            c0, c1, c2 = st.columns([0.08, 0.67, 0.25])
            with c0:
                st.markdown(f"<div style='padding-top:1.9rem;font-weight:800;color:#006940'>({letter})</div>", unsafe_allow_html=True)
            with c1:
                raw_cause = st.text_input(label, value=fd.get(f"part1_{letter}_cause", ""), key=f"part1_{letter}_cause", placeholder=placeholder)
            with c2:
                interval = st.text_input("Interval", value=fd.get(f"part1_{letter}_interval", ""), key=f"part1_{letter}_interval", placeholder="e.g., 2 days")
            field_key = f"part1_{letter}"
            for issue in issues_by_field.get(field_key, [])[:3]:
                inline_note(issue.get("message", "Please review this line."), "error" if issue.get("severity") == "error" else "warning")
            cause_now = clean_cause_input(st.session_state.get(f"part1_{letter}_cause", raw_cause))
            if cause_now and field_key not in issues_by_field:
                inline_note("Line format looks acceptable.", "ok")

        st.markdown("---")
        st.markdown('<div class="section-title">Part II — Other significant conditions</div>', unsafe_allow_html=True)
        st.caption("Use Part II only for conditions that contributed to death but were not part of the direct chain.")

        for i in range(1, 4):
            c0, c1, c2 = st.columns([0.08, 0.67, 0.25])
            with c0:
                st.markdown(f"<div style='padding-top:1.9rem;font-weight:800;color:#1a4a7a'>II-{i}</div>", unsafe_allow_html=True)
            with c1:
                raw_cause = st.text_input(f"Other significant condition {i}", value=fd.get(f"part2_{i}_cause", ""), key=f"part2_{i}_cause", placeholder="e.g., type 2 diabetes mellitus")
            with c2:
                interval = st.text_input("Interval", value=fd.get(f"part2_{i}_interval", ""), key=f"part2_{i}_interval", placeholder="e.g., 12 years")
            field_key = f"part2_{i}"
            for issue in issues_by_field.get(field_key, [])[:3]:
                inline_note(issue.get("message", "Please review this line."), "error" if issue.get("severity") == "error" else "warning")
            cause_now = clean_cause_input(st.session_state.get(f"part2_{i}_cause", raw_cause))
            if cause_now and field_key not in issues_by_field:
                inline_note("Contributing condition recorded.", "ok")

    with right:
        st.markdown('<div class="section-title">Agent 1 — Input Validation Agent</div>', unsafe_allow_html=True)

        # Build a simple doctor-facing Good / Needs Attention preview for Agent 1 only.
        # ICD retrieval warnings are still shown under fields, but this card stays focused on input/form quality.
        input_issues = list(all_pre_issues)
        input_errors = [x for x in input_issues if x.get("severity") == "error" or x.get("blocking")]
        input_warnings = [x for x in input_issues if x.get("severity") != "error" and not x.get("blocking")]

        good_items = []
        if precheck["part1_chain"]:
            good_items.append("Part I has at least one completed cause line.")
        if precheck["part1_chain"] and not any(i.get("type") == "skipped_line" for i in input_issues):
            good_items.append("Completed Part I lines are consecutive; no skipped line detected.")
        if has_any_cod_input and not any(i.get("type") == "multiple_causes" for i in input_issues):
            good_items.append("Each completed line appears to contain one condition.")
        if has_any_cod_input and not any(i.get("type") in {"missing_interval", "ambiguous_interval", "unclear_interval"} for i in input_issues):
            good_items.append("Intervals are present and readable for completed lines.")
        if has_any_cod_input and not input_errors:
            good_items.append("No blocking input/form error is detected.")
        if not good_items:
            good_items.append("Waiting for the doctor to enter Part I line (a).")

        attention_items = []
        for issue in (input_errors + input_warnings)[:6]:
            line = str(issue.get("line", "")).strip()
            msg = str(issue.get("message", "Please review this field.")).strip()
            attention_items.append(f"{line}: {msg}" if line else msg)
        if not attention_items:
            attention_items.append("No bad input/form issue detected by Agent 1.")

        bad_class = "agent-bad-box error" if input_errors else "agent-bad-box"
        status_text = "BLOCKED" if input_errors else ("REVIEW" if input_warnings else "GOOD")
        status_color = "#c0392b" if input_errors else ("#a66a00" if input_warnings else "#006940")

        good_html = "".join([f"<li>{escape(x)}</li>" for x in good_items])
        bad_html = "".join([f"<li>{escape(x)}</li>" for x in attention_items])

        st.markdown(
            f"""
            <div class="agent-preview-card">
              <div class="agent-kicker">AGENT 1</div>
              <div class="agent-preview-title">Input Validation Agent</div>
              <div class="agent-preview-subtitle">
                First step only: checks the doctor-entered form before ICD retrieval. SP/WHO/TABB appears later in Agent 3.
              </div>
              <div style="font-size:.82rem;margin-bottom:.55rem;color:{status_color};font-weight:850">Status: {status_text}</div>
              <div class="agent-goodbad-grid">
                <div class="agent-good-box">
                  <b>Good</b>
                  <ul>{good_html}</ul>
                </div>
                <div class="{bad_class}">
                  <b>Bad / Needs attention</b>
                  <ul>{bad_html}</ul>
                </div>
              </div>
              <div class="agent-condition">
                <b>Condition to continue:</b><br>
                Agent 2 opens only when Agent 1 has no blocking input/form errors.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.caption("The yellow medical/ICD warnings under the fields are suggestions. Full ICD retrieval starts in Agent 2.")

    b1, b2, _ = st.columns([1, 1.8, 5.5])
    with b1:
        if st.button("Back", use_container_width=True):
            st.session_state.page = 2
            st.rerun()
    with b2:
        can_analyze = bool(precheck["part1_chain"]) and not bool(blocking_issues)
        if st.button("Open Agent 1 Workflow", use_container_width=True, type="primary", disabled=(not can_analyze)):
            if not precheck["part1_chain"]:
                st.error("Please enter at least one Part I cause.")
            elif st.session_state.df_source is None:
                st.error("Coding source data failed to load. Please check Admin / data status.")
            elif not API_KEY:
                st.error("ANTHROPIC_API_KEY is missing in Streamlit secrets.")
            else:
                for x in precheck["part1_chain"]:
                    fd[f"part1_{x['line']}_cause"] = x["cause"]
                    fd[f"part1_{x['line']}_interval"] = x.get("interval") or "—"
                for x in precheck["part2_conditions"]:
                    idx = str(x["line"]).replace("II-", "")
                    fd[f"part2_{idx}_cause"] = x["cause"]
                    fd[f"part2_{idx}_interval"] = x.get("interval") or "—"
                narrative_parts = []
                if precheck["part1_chain"]:
                    narrative_parts.append(" due to ".join([f"{x['cause']} ({x['interval']})" for x in precheck["part1_chain"]]))
                if precheck["part2_conditions"]:
                    narrative_parts.append("Other significant conditions included " + ", ".join([f"{x['cause']} ({x['interval']})" for x in precheck["part2_conditions"]]))
                st.session_state.form_data.update(fd)
                st.session_state.form_data["manual_part1_chain"] = precheck["part1_chain"]
                st.session_state.form_data["manual_part2_conditions"] = precheck["part2_conditions"]
                st.session_state.form_data["precheck_issues"] = all_pre_issues
                st.session_state.form_data["sp_preview"] = sp_info
                st.session_state.form_data["free_text"] = ". ".join(narrative_parts) + "."
                st.session_state.icd_results = None
                st.session_state.page = 4
                st.rerun()

# =============================================================================
# PAGE 4 — Sequential LLM Agent Workflow
# =============================================================================
elif st.session_state.page == 4:
    render_steps(4)
    fd = st.session_state.form_data
    df_source = st.session_state.df_source
    faiss_index = st.session_state.faiss_index
    bm25 = st.session_state.bm25_index

    if df_source is None:
        st.error("ICD source data is unavailable. Please check sidebar loading errors and reload ICD data.")
        if st.button("Back"):
            st.session_state.page = 3
            st.rerun()
        st.stop()

    if not API_KEY:
        st.error("ANTHROPIC_API_KEY is missing in Streamlit secrets.")
        st.stop()

    # If the case came from Page 3, initialize editable agent fields once.
    if fd.get("manual_part1_chain"):
        for x in fd.get("manual_part1_chain", []):
            line = str(x.get("line", "")).lower()
            st.session_state.setdefault(f"agent_part1_{line}_cause", x.get("cause", ""))
            st.session_state.setdefault(f"agent_part1_{line}_interval", x.get("interval", "—"))
    if fd.get("manual_part2_conditions"):
        for x in fd.get("manual_part2_conditions", []):
            idx = str(x.get("line", "")).replace("II-", "")
            st.session_state.setdefault(f"agent_part2_{idx}_cause", x.get("cause", ""))
            st.session_state.setdefault(f"agent_part2_{idx}_interval", x.get("interval", "—"))

    if "agent_step" not in st.session_state:
        st.session_state.agent_step = 1

    st.markdown('<div class="section-title">Review & Coding — Sequential LLM Agents</div>', unsafe_allow_html=True)
    st.caption("The doctor edits the certificate on the left. The right side shows one agent at a time with a compact output only.")

    left, right = st.columns([1.35, 1.0], gap="large")

    with left:
        part1_chain, part2_conditions = render_doctor_edit_panel(fd)

    patient_info = {
        "age_years": fd.get("age_years", 0),
        "sex": fd.get("sex", ""),
        "death_type": fd.get("death_type", ""),
        "chronic_conditions": fd.get("chronic_conditions", []),
    }

    with right:
        st.markdown('<div class="agent-workspace-title">Agent Workspace</div>', unsafe_allow_html=True)
        render_agent_stepper(int(st.session_state.get("agent_step", 1)))

        # ------------------------------------------------------------------
        # Agent 1: Input validation
        # ------------------------------------------------------------------
        if st.session_state.agent_step == 1:
            render_agent_card_header(
                1,
                "Input Validation Agent",
                "Checks Part I / Part II structure before retrieval: empty lines, skipped lines, multiple causes, duplicate causes, intervals, and sequence plausibility.",
                state="active",
            )
            st.markdown(
                """
                <div class="agent-checklist">
                <b>This agent validates:</b>
                <ul>
                  <li>Part I is not empty</li>
                  <li>No skipped Part I lines</li>
                  <li>One disease or condition per line</li>
                  <li>Intervals are understandable</li>
                  <li>No duplicated causal-chain entries</li>
                </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="agent-condition"><b>Condition to unlock Agent 2:</b><br>No blocking input/form errors.</div>',
                unsafe_allow_html=True,
            )
            render_agent_prompt_box(AGENT1_SYSTEM_PROMPT)

            if st.button("Run Agent 1 — Validate Input", type="primary", use_container_width=True):
                save_agent_cod_to_form_data(fd, part1_chain, part2_conditions)
                with st.spinner("Agent 1 is reviewing the doctor input..."):
                    st.session_state.agent1_result = agent1_input_validation_with_llm(
                        API_KEY,
                        part1_chain,
                        part2_conditions,
                    )
                st.session_state.agent1_done = True
                st.rerun()

            render_agent_result(st.session_state.get("agent1_result"))

            can_go_next = bool(st.session_state.get("agent1_done")) and not bool((st.session_state.get("agent1_result") or {}).get("blocking"))
            if st.button("Next → Agent 2", use_container_width=True, disabled=not can_go_next):
                st.session_state.agent_step = 2
                st.rerun()

            close_agent_card()

        # ------------------------------------------------------------------
        # Agent 2: ICD retrieval and candidate validation
        # ------------------------------------------------------------------
        elif st.session_state.agent_step == 2:
            if not st.session_state.get("agent1_done"):
                st.warning("Run Agent 1 first.")
                if st.button("Back to Agent 1", use_container_width=True):
                    st.session_state.agent_step = 1
                    st.rerun()
                st.stop()

            render_agent_card_header(
                2,
                "ICD Candidate Validation Agent",
                "Runs Excel-grounded retrieval and LLM code selection. The LLM can choose only from retrieved ICD file candidates.",
                state="active",
            )
            st.markdown(
                """
                <div class="agent-checklist">
                <b>This agent validates:</b>
                <ul>
                  <li>BM25 + FAISS candidate retrieval</li>
                  <li>Selected code exists in the ICD Excel source</li>
                  <li>Claude selected only from retrieved candidates</li>
                  <li>AcceptableMain, gender restriction, vague/R-code flags</li>
                  <li>Missing-code/manual-review conditions</li>
                </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="agent-condition"><b>Condition to unlock Agent 3:</b><br>At least one ICD-coded Part I chain exists and no missing-code error is present.</div>',
                unsafe_allow_html=True,
            )
            render_agent_prompt_box(AGENT2_SYSTEM_PROMPT)

            b_run, b_back = st.columns([1.4, 1])
            with b_run:
                if st.button("Run Agent 2 — Retrieve & Select ICD Codes", type="primary", use_container_width=True):
                    save_agent_cod_to_form_data(fd, part1_chain, part2_conditions)
                    extracted = {
                        "part1_chain": part1_chain,
                        "part2_conditions": part2_conditions,
                    }
                    with st.spinner("Agent 2 is retrieving ICD candidates and selecting file-only codes..."):
                        coded_results = code_extracted_causes_with_claude(
                            api_key=API_KEY,
                            extracted=extracted,
                            df_source=df_source,
                            faiss_index=faiss_index,
                            bm25=bm25,
                            patient_info=patient_info,
                        )
                        st.session_state.icd_results = coded_results
                        st.session_state.agent2_result = agent2_candidate_validation_with_llm(
                            API_KEY,
                            coded_results,
                            patient_info,
                        )
                    st.session_state.agent2_done = True
                    st.session_state.agent3_done = False
                    st.session_state.agent3_result = None
                    st.rerun()
            with b_back:
                if st.button("← Back to Agent 1", use_container_width=True):
                    st.session_state.agent_step = 1
                    st.rerun()

            render_agent_result(st.session_state.get("agent2_result"))

            # Compact UI: ICD candidate tables are hidden here.
            # The selected codes remain stored in st.session_state.icd_results and appear on the final certificate page.

            can_go_next = (
                bool(st.session_state.get("agent2_done"))
                and bool(st.session_state.get("icd_results"))
                and not bool((st.session_state.get("agent2_result") or {}).get("blocking"))
            )
            if st.button("Next → Agent 3", use_container_width=True, disabled=not can_go_next):
                st.session_state.agent_step = 3
                st.rerun()

            close_agent_card()

        # ------------------------------------------------------------------
        # Agent 3: Mortality sequence / WHO / TABB validation
        # ------------------------------------------------------------------
        elif st.session_state.agent_step == 3:
            if not st.session_state.get("agent2_done") or not st.session_state.get("icd_results"):
                st.warning("Run Agent 2 first.")
                if st.button("Back to Agent 2", use_container_width=True):
                    st.session_state.agent_step = 2
                    st.rerun()
                st.stop()

            render_agent_card_header(
                3,
                "Mortality Sequence / WHO Rules Agent",
                "Applies SP1–SP8 starting-point logic and TABB ICD-code relationship checks, then confirms or flags the UCOD decision.",
                state="active",
            )
            st.markdown(
                """
                <div class="agent-checklist">
                <b>This agent validates:</b>
                <ul>
                  <li>SP1–SP8 starting-point logic</li>
                  <li>Part I causal-chain plausibility</li>
                  <li>TABB rules using normalized ICD codes</li>
                  <li>UCOD decision and manual-review status</li>
                </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="agent-condition"><b>Final condition:</b><br>If SP/TABB is uncertain, the certificate remains marked as Needs Review.</div>',
                unsafe_allow_html=True,
            )
            render_agent_prompt_box(AGENT3_SYSTEM_PROMPT)

            b_run, b_back = st.columns([1.4, 1])
            with b_run:
                if st.button("Run Agent 3 — WHO / TABB Review", type="primary", use_container_width=True):
                    with st.spinner("Agent 3 is reviewing SP rules and TABB code relationships..."):
                        tabb_df = load_tabb_rules()
                        st.session_state.agent3_result = agent3_mortality_sequence_with_llm(
                            API_KEY,
                            st.session_state.icd_results,
                            tabb_df,
                        )
                        st.session_state.icd_results["validation"] = st.session_state.agent3_result.get(
                            "validation",
                            st.session_state.icd_results.get("validation", {}),
                        )
                    st.session_state.agent3_done = True
                    st.rerun()
            with b_back:
                if st.button("← Back to Agent 2", use_container_width=True):
                    st.session_state.agent_step = 2
                    st.rerun()

            render_agent_result(st.session_state.get("agent3_result"))

            # Compact UI: SP/TABB internals and final coded-cause tables are hidden here.
            # The final certificate page keeps the complete coded result for review/download.

            b_final, b_new = st.columns([1.4, 1])
            with b_final:
                if st.button("Go to Final Certificate", use_container_width=True, disabled=not bool(st.session_state.get("agent3_done"))):
                    st.session_state.page = 5
                    st.rerun()
            with b_new:
                if st.button("New Certificate", use_container_width=True):
                    keys_to_remove = [k for k in st.session_state.keys() if str(k).startswith("code_edit_") or str(k).startswith("agent_part")]
                    for k in keys_to_remove:
                        del st.session_state[k]
                    st.session_state.page = 1
                    st.session_state.form_data = {}
                    st.session_state.icd_results = None
                    reset_agent_workflow(clear_codes=True)
                    st.rerun()

            close_agent_card()

# =============================================================================
# PAGE 5 — Final Certificate with PDF Download
# =============================================================================
elif st.session_state.page == 5:
    render_steps(5)

    fd = st.session_state.form_data
    results = st.session_state.icd_results

    if results is None:
        st.error("No coded certificate data found.")
        if st.button("Back to Review & Coding"):
            st.session_state.page = 4
            st.rerun()
        st.stop()

    coded_causes = results.get("coded_causes", [])
    validation = results.get("validation", {})
    concepts = results.get("concepts", {})

    part1 = [x for x in coded_causes if x["role"] in {"immediate", "contributing", "underlying"}]
    part2 = [x for x in coded_causes if x["role"] == "other"]

    cert_no = fd.get("cert_number") or f"DC-{datetime.date.today().year}-{fd.get('national_id', '')[-4:]}"
    quality = validation.get("overall_quality", "Needs Review")
    issues = validation.get("coding_issues", [])
    who_notes = validation.get("who_notes", "")
    underlying_code = validation.get("underlying_cause") or "Pending manual review"

    quality_color = {
        "Excellent": "#006940",
        "Good": "#2d7a4f",
        "Needs Review": "#c0392b",
    }.get(quality, "#888")

    # ── PDF download (generate once per session state hash) ──────────────────
    pdf_cache_key = "pdf_bytes_cached"
    if pdf_cache_key not in st.session_state or st.session_state.get("pdf_cert_no") != cert_no:
        try:
            pdf_bytes = generate_certificate_pdf(
                fd=fd,
                coded_causes=coded_causes,
                validation=validation,
                hospital_name=hospital_name,
                hospital_city=hospital_city,
                doctor_name=doctor_name,
            )
            st.session_state[pdf_cache_key] = pdf_bytes
            st.session_state["pdf_cert_no"] = cert_no
        except Exception as e:
            st.session_state[pdf_cache_key] = None
            st.error(f"PDF generation failed: {e}")

    pdf_bytes = st.session_state.get(pdf_cache_key)

    # ── Top action bar ────────────────────────────────────────────────────────
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Final Death Certificate</div>', unsafe_allow_html=True)

    top_left, top_right = st.columns([3, 1])
    with top_left:
        st.markdown(
            f'<div style="background:white;border:2px solid {quality_color};border-radius:8px;'
            f'padding:.7rem 1rem;display:inline-block">'
            f'<b style="color:{quality_color}">Validation: {escape(quality)}</b> &nbsp;|&nbsp; '
            f'Underlying cause: <b style="font-family:monospace">{escape(underlying_code)}</b>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with top_right:
        if pdf_bytes:
            st.download_button(
                label="⬇ Download PDF",
                data=pdf_bytes,
                file_name=f"{sanitize_filename('death_certificate_' + cert_no)}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        else:
            st.warning("PDF unavailable")

    st.markdown("---")

    # ── Patient Information ───────────────────────────────────────────────────
    st.markdown("### Patient Information")
    p1, p2 = st.columns(2)
    with p1:
        st.write(f"**Full Name:** {fd.get('full_name', '—')}")
        st.write(f"**National ID / Iqama:** {fd.get('national_id', '—')}")
        st.write(f"**Nationality:** {fd.get('nationality', '—')}")
        st.write(f"**Sex:** {fd.get('sex', '—')}")
        st.write(f"**Age:** {fd.get('age_years', '—')} years")
        st.write(f"**Date of Birth:** {fd.get('dob', '—')}")
        st.write(f"**Marital Status:** {fd.get('marital_status', '—')}")
        st.write(f"**Occupation:** {fd.get('occupation', '—')}")
        st.write(f"**Address:** {fd.get('address', '—')}")
    with p2:
        st.write(f"**Date of Death:** {fd.get('dod', '—')}")
        st.write(f"**Time of Death:** {fd.get('time_of_death', '—')}")
        st.write(f"**Place of Death:** {fd.get('place_of_death', '—')}")
        st.write(f"**Type of Death:** {fd.get('death_type', '—')}")
        st.write(f"**Issue Date:** {fd.get('date_issued', '—')}")
        st.write(f"**Certificate Number:** {cert_no}")
        st.write(f"**Hospital Stay:** {fd.get('inpatient_days', '—')} days")
        st.write(f"**Autopsy Required:** {fd.get('autopsy_required', '—')}")
        st.write(f"**Recent Surgery:** {fd.get('had_surgery', '—')}")

    st.markdown("---")

    # ── Part I ────────────────────────────────────────────────────────────────
    st.markdown("### Part I — Direct Causal Chain")
    row_names = ["(a)", "(b)", "(c)", "(d)", "(e)"]
    part1_html = ""
    for i, item in enumerate(part1):
        row_label = row_names[i] if i < len(row_names) else f"({i+1})"
        code_display  = item.get("code_formatted") or "Pending manual review"
        short_display = item.get("short_desc") or "Pending manual review"
        long_display  = item.get("long_desc") or "Pending manual review"
        status_display= item.get("selection_status", "—")

        part1_html += f"""
        <div class="final-block">
            <div style="font-weight:700;color:#006940;margin-bottom:.35rem">
                {escape(row_label)} {"Immediate cause" if i == 0 else "Due to"}
            </div>
            <div style="font-size:.95rem;color:#1a2e1a;margin-bottom:.25rem">
                {escape(item.get("cause", "—"))}
            </div>
            <div style="font-size:.82rem;color:#4b5f50;line-height:1.7">
                <b>Interval:</b> {escape(item.get("interval", "—"))}<br>
                <b>ICD-10 Code:</b> {escape(code_display)}<br>
                <b>Disease Name:</b> {escape(short_display)}<br>
                <b>Full Description:</b> {escape(long_display)}<br>
                <b>Status:</b> {escape(status_display)}
            </div>
        </div>
        """

    if part1_html:
        st.markdown(part1_html, unsafe_allow_html=True)
    else:
        st.info("No Part I causes available.")

    # ── Part II ───────────────────────────────────────────────────────────────
    st.markdown("### Part II — Other Significant Conditions")
    part2_html = ""
    for i, item in enumerate(part2, start=1):
        code_display  = item.get("code_formatted") or "Pending manual review"
        short_display = item.get("short_desc") or "Pending manual review"
        long_display  = item.get("long_desc") or "Pending manual review"
        status_display= item.get("selection_status", "—")

        part2_html += f"""
        <div class="final-block-secondary">
            <div style="font-weight:700;color:#355c7d;margin-bottom:.35rem">
                Other condition ({i})
            </div>
            <div style="font-size:.95rem;color:#1a2e1a;margin-bottom:.25rem">
                {escape(item.get("cause", "—"))}
            </div>
            <div style="font-size:.82rem;color:#4b5f50;line-height:1.7">
                <b>Interval:</b> {escape(item.get("interval", "—"))}<br>
                <b>ICD-10 Code:</b> {escape(code_display)}<br>
                <b>Disease Name:</b> {escape(short_display)}<br>
                <b>Full Description:</b> {escape(long_display)}<br>
                <b>Status:</b> {escape(status_display)}
            </div>
        </div>
        """

    if part2_html:
        st.markdown(part2_html, unsafe_allow_html=True)
    else:
        st.info("No Part II conditions available.")

    st.markdown("---")

    # ── Underlying cause highlight ────────────────────────────────────────────
    st.markdown(
        f'<div style="background:#f0f4ff;border:2px solid #1a4a7a;border-radius:8px;'
        f'padding:1rem 1.4rem;margin-bottom:1rem">'
        f'<b style="color:#1a4a7a;font-size:.95rem">Underlying Cause (for mortality statistics):</b> '
        f'<span style="font-family:monospace;font-weight:800;font-size:1.1rem;color:#1a4a7a">{escape(underlying_code)}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Validation Summary ────────────────────────────────────────────────────
    st.markdown("### Validation Summary")
    st.markdown(
        f'<div style="background:white;border:2px solid {quality_color};border-radius:8px;'
        f'padding:1rem 1.2rem;margin-bottom:1rem">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">'
        f'<b style="color:{quality_color};font-size:.95rem">Validation Result — {escape(quality)}</b>'
        f'<span style="background:{quality_color};color:white;border-radius:4px;padding:2px 10px;font-size:.78rem">'
        f'Underlying cause: {escape(underlying_code)}</span></div></div>',
        unsafe_allow_html=True,
    )

    if issues:
        for issue in issues:
            st.error(issue)
    else:
        st.success("No validation issues detected.")

    if who_notes:
        st.info(who_notes)

    st.markdown("---")

    # ── Physician block ───────────────────────────────────────────────────────
    st.markdown("### Physician / Hospital Information")
    d1, d2 = st.columns(2)
    with d1:
        st.write(f"**Hospital Name:** {hospital_name}")
        st.write(f"**City:** {hospital_city}")
        st.write(f"**Certifying Physician:** {doctor_name or '________________________________'}")
    with d2:
        st.write("**Signature:** ______________________________")
        st.write("**Official Stamp:** MOH Draft / Final Review")

    st.markdown("---")

    # ── Original narrative ────────────────────────────────────────────────────
    st.markdown("### Original Narrative")
    st.text_area(
        "Cause Narrative Used for Extraction",
        value=fd.get("free_text", ""),
        height=180,
        disabled=True,
    )

    with st.expander("Show extracted structure (debug)"):
        st.json(concepts)

    # ── Download buttons ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Download")

    dl1, dl2 = st.columns(2)

    if pdf_bytes:
        with dl1:
            st.download_button(
                label="⬇ Download Final Certificate as PDF",
                data=pdf_bytes,
                file_name=f"{sanitize_filename('death_certificate_' + cert_no)}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

    final_lines = [
        "FINAL DEATH CERTIFICATE",
        f"Certificate No: {cert_no}",
        "=" * 80,
        f"Hospital: {hospital_name}",
        f"City: {hospital_city}",
        f"Certifying Physician: {doctor_name}",
        "",
        "PATIENT INFORMATION",
        f"Full Name: {fd.get('full_name', '')}",
        f"National ID / Iqama: {fd.get('national_id', '')}",
        f"Nationality: {fd.get('nationality', '')}",
        f"Sex: {fd.get('sex', '')}",
        f"Age: {fd.get('age_years', '')} years",
        f"Date of Birth: {fd.get('dob', '')}",
        f"Date of Death: {fd.get('dod', '')}",
        f"Time of Death: {fd.get('time_of_death', '')}",
        f"Place of Death: {fd.get('place_of_death', '')}",
        f"Type of Death: {fd.get('death_type', '')}",
        f"Marital Status: {fd.get('marital_status', '')}",
        f"Occupation: {fd.get('occupation', '')}",
        f"Address: {fd.get('address', '')}",
        "",
        "PART I - DIRECT CAUSAL CHAIN",
    ]

    for i, item in enumerate(part1):
        line_label = row_names[i] if i < len(row_names) else str(i + 1)
        final_lines.append(
            f"{line_label} {item.get('cause', '')} | interval: {item.get('interval', '—')} | "
            f"ICD: {item.get('code_formatted') or 'Pending manual review'} | "
            f"{item.get('short_desc') or 'Pending manual review'}"
        )

    final_lines.append("")
    final_lines.append("PART II - OTHER SIGNIFICANT CONDITIONS")
    if part2:
        for item in part2:
            final_lines.append(
                f"- {item.get('cause', '')} | interval: {item.get('interval', '—')} | "
                f"ICD: {item.get('code_formatted') or 'Pending manual review'} | "
                f"{item.get('short_desc') or 'Pending manual review'}"
            )
    else:
        final_lines.append("None documented.")

    final_lines += [
        "",
        "VALIDATION",
        f"Overall Quality: {quality}",
        f"Underlying Cause: {underlying_code}",
        "",
        "ISSUES",
    ]

    if issues:
        for issue in issues:
            final_lines.append(f"- {issue}")
    else:
        final_lines.append("- No issues detected.")

    final_lines += [
        "",
        "WHO NOTE",
        who_notes,
        "",
        "ORIGINAL NARRATIVE",
        fd.get("free_text", ""),
        "",
        f"Issue Date: {fd.get('date_issued', '')}",
        f"Physician: {doctor_name}",
    ]

    with dl2:
        st.download_button(
            label="⬇ Download Summary as Text (.txt)",
            data="\n".join(final_lines).encode("utf-8"),
            file_name=f"{sanitize_filename('death_certificate_' + cert_no)}.txt",
            mime="text/plain",
            use_container_width=True,
        )

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Navigation ────────────────────────────────────────────────────────────
    st.markdown("---")
    b1, b2, b3, _ = st.columns([1, 1, 1.2, 5])

    with b1:
        if st.button("Back to Review", use_container_width=True):
            st.session_state.page = 4
            st.rerun()

    with b2:
        if st.button("Edit Narrative", use_container_width=True):
            st.session_state.page = 3
            st.rerun()

    with b3:
        if st.button("New Certificate", use_container_width=True):
            keys_to_remove = [k for k in st.session_state.keys() if k.startswith("code_edit_")]
            for k in keys_to_remove:
                del st.session_state[k]
            st.session_state.page = 1
            st.session_state.form_data = {}
            st.session_state.icd_results = None
            for k in list(st.session_state.keys()):
                if k.startswith("part1_") or k.startswith("part2_"):
                    del st.session_state[k]
            # clear pdf cache too
            for k in ["pdf_bytes_cached", "pdf_cert_no"]:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()
