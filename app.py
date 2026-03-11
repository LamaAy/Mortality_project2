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

def validate_certificate(coded_causes: List[Dict], sex_value: str) -> Dict:
    issues = []

    part1 = [x for x in coded_causes if x["role"] in {"immediate", "contributing"}]

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

        if is_r_chapter(code) and not (code.startswith("R57") or code.startswith("R65")):
            issues.append(f"{code} is an ill-defined R-chapter code in Part I and should be avoided if a more specific cause is available.")

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
    part1 = [x for x in coded_causes if x["role"] in {"immediate", "contributing"}]
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
    st.markdown("### System Settings")
    st.markdown("---")
    st.markdown("### ICD Data Sources")
    st.markdown(
        '<div style="font-size:.78rem;opacity:.85;padding:.3rem 0;line-height:1.7">'
        'Source of truth: Excel / metadata<br>'
        'Retrieval: FAISS + BM25 + deterministic rules<br>'
        'Extraction: Claude<br>'
        'Coding: file candidates only</div>',
        unsafe_allow_html=True,
    )

    if st.button("Reload ICD Data", use_container_width=True):
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

    st.markdown("---")
    st.markdown("### Hospital Information")
    hospital_name = st.text_input("Hospital Name", value="King Fahad Specialist Hospital")
    hospital_city = st.text_input("City", value="Riyadh")
    doctor_name   = st.text_input("Certifying Physician", value="")

    st.markdown("---")
    if API_KEY:
        st.success("Anthropic API key found.")
    else:
        st.error("ANTHROPIC_API_KEY missing in Streamlit secrets.")

    st.markdown(
        '<div style="font-size:.72rem;opacity:.65;text-align:center;line-height:2;margin-top:.8rem">'
        'Ministry of Health<br>Hybrid ICD-10 Coding v1</div>',
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
        st.sidebar.success(f"Loaded {len(df_excel):,} ICD rows from Excel.")
    except Exception as e:
        load_errors.append(f"Excel load failed: {e}")

    try:
        df_meta = load_metadata(GDRIVE_METADATA_ID)
        st.session_state["df_metadata"] = df_meta
        st.sidebar.success(f"Loaded {len(df_meta):,} metadata rows.")
    except Exception as e:
        load_errors.append(f"Metadata load failed: {e}")

    try:
        faiss_index = load_faiss_resources(GDRIVE_EMBEDDINGS_ID, GDRIVE_FAISS_ID)
        st.session_state["faiss_index"] = faiss_index
        if faiss_index is not None:
            st.sidebar.success("FAISS ready.")
        else:
            st.sidebar.warning("FAISS unavailable. Semantic search disabled.")
    except Exception as e:
        load_errors.append(f"FAISS load failed: {e}")

    try:
        if df_excel is not None:
            bm25 = build_bm25_index(df_excel)
            st.session_state["bm25_index"] = bm25
            if bm25 is not None:
                st.sidebar.success("BM25 ready.")
            else:
                st.sidebar.warning("BM25 unavailable. Using fallback keyword overlap.")
    except Exception as e:
        load_errors.append(f"BM25 load failed: {e}")

    if load_errors:
        for err in load_errors:
            st.sidebar.error(err)

# =============================================================================
# Step bar
# =============================================================================
def render_steps(current: int):
    labels = [
        "Basic Information",
        "Medical History",
        "Cause Narrative",
        "Review & Coding",
        "Final Certificate",
    ]
    html_s = '<div class="step-bar">'
    for i, lbl in enumerate(labels, 1):
        cls = "step active" if i == current else ("step done" if i < current else "step")
        html_s += f'<div class="{cls}">{i}. {escape(lbl)}</div>'
    html_s += "</div>"
    st.markdown(html_s, unsafe_allow_html=True)

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

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Cause of Death Narrative</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="background:#fffbe6;border-left:3px solid #C8A951;padding:9px 14px;'
        'border-radius:5px;margin-bottom:1.1rem;font-size:.87rem;color:#5a4a00">'
        'Write the immediate cause first, then the underlying sequence, then other significant conditions.</div>',
        unsafe_allow_html=True
    )

    free_text = st.text_area(
        "Narrative Description",
        value=fd.get("free_text", ""),
        height=220,
        placeholder=(
            "The patient died from acute respiratory distress syndrome (2 days) due to septic shock (5 days) "
            "due to perforated sigmoid diverticulitis with generalized peritonitis (10 days). "
            "Other significant conditions included type 2 diabetes mellitus with diabetic vasculopathy (12 years) "
            "and chronic obesity with metabolic syndrome (20 years)."
        ),
    )
    st.markdown('</div>', unsafe_allow_html=True)

    b1, b2, _ = st.columns([1, 1.4, 6])
    with b1:
        if st.button("Back", use_container_width=True):
            st.session_state.page = 2
            st.rerun()
    with b2:
        if st.button("Analyze & Find Codes", use_container_width=True, type="primary"):
            if not free_text.strip():
                st.error("Please enter a narrative description.")
            elif st.session_state.df_source is None:
                st.error("ICD source data failed to load. Check the sidebar error messages.")
            elif not API_KEY:
                st.error("ANTHROPIC_API_KEY is missing in Streamlit secrets.")
            else:
                st.session_state.form_data["free_text"] = free_text
                st.session_state.icd_results = None
                st.session_state.page = 4
                st.rerun()

# =============================================================================
# PAGE 4
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

    if not fd.get("free_text", "").strip():
        st.error("No cause narrative found.")
        if st.button("Back"):
            st.session_state.page = 3
            st.rerun()
        st.stop()

    if st.session_state.icd_results is None:
        patient_info = {
            "age_years": fd.get("age_years", 0),
            "sex": fd.get("sex", ""),
            "death_type": fd.get("death_type", ""),
            "chronic_conditions": fd.get("chronic_conditions", []),
        }

        with st.spinner("Extracting causes with Claude and coding from file candidates..."):
            try:
                st.session_state.icd_results = code_causes_hybrid_with_claude(
                    api_key=API_KEY,
                    narrative=fd["free_text"],
                    df_source=df_source,
                    faiss_index=faiss_index,
                    bm25=bm25,
                    patient_info=patient_info,
                )
            except Exception as e:
                st.session_state.icd_results = {
                    "concepts": {"part1_chain": [], "part2_conditions": []},
                    "coded_causes": [],
                    "validation": {
                        "underlying_cause": "",
                        "coding_issues": [f"System error during coding: {type(e).__name__}: {e}"],
                        "who_notes": "",
                        "overall_quality": "Needs Review",
                    },
                }
                st.error(f"System error during coding: {type(e).__name__}: {e}")

    results = st.session_state.icd_results
    coded_causes = results["coded_causes"]
    concepts = results["concepts"]
    validation = results["validation"]

    quality = validation.get("overall_quality", "")
    q_color = {"Excellent": "#006940", "Good": "#2d7a4f", "Needs Review": "#c0392b"}.get(quality, "#888")

    if quality:
        underlying = validation.get("underlying_cause", "—")
        issues = validation.get("coding_issues", [])
        who_notes = validation.get("who_notes", "")

        issues_html = "".join(
            f'<li style="color:#c0392b;font-size:.83rem">{escape(i)}</li>' for i in issues
        ) if issues else '<li style="color:#006940;font-size:.83rem">No issues detected.</li>'

        st.markdown(
            '<div style="background:white;border:2px solid ' + q_color + ';border-radius:8px;'
            'padding:1rem 1.2rem;margin-bottom:1.2rem">'
            '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.5rem;gap:12px;flex-wrap:wrap">'
            '<b style="color:' + q_color + ';font-size:.95rem">Validation Result — ' + escape(quality) + '</b>'
            '<span style="background:' + q_color + ';color:white;border-radius:4px;padding:2px 10px;font-size:.78rem">'
            'Underlying cause for mortality statistics: ' + escape(underlying or "—") + '</span></div>'
            '<ul style="margin:.3rem 0 .3rem 1rem">' + issues_html + '</ul>'
            + ('<div style="font-size:.82rem;color:#444;margin-top:.4rem">' + escape(who_notes) + '</div>' if who_notes else '')
            + '</div>',
            unsafe_allow_html=True,
        )

    tab_res, tab_cert, tab_debug = st.tabs(["ICD-10 Codes", "Certificate Preview", "Extracted Structure"])

    with tab_res:
        role_hdr = {"immediate": "#006940", "contributing": "#2d7a4f", "other": "#5a7060"}

        for idx, item in enumerate(coded_causes):
            acc = item.get("acceptable_main", "")
            acc_bool = acceptable_main_bool(acc)
            bg_acc = "#006940" if acc_bool is True else ("#c0392b" if acc_bool is False else "#888")
            acc_en = (
                "Acceptable as main cause" if acc_bool is True
                else "Not acceptable as main cause" if acc_bool is False
                else "Unknown acceptability"
            )

            rc = role_hdr.get(item["role"], "#555")
            code_val = item.get("code_formatted", "")
            short_val = item.get("short_desc", "")
            long_val = item.get("long_desc", "")
            notes_val = item.get("selection_notes", "")
            source_note = item.get("note", "")
            show_badge = item["role"] in {"immediate", "contributing"}

            badge_html = (
                '<span style="background:' + bg_acc + ';color:white;border-radius:4px;'
                'padding:3px 10px;font-size:.72rem;font-weight:700;display:inline-block;margin-top:4px">'
                + escape(acc_en) + '</span>'
            ) if show_badge else ""

            st.markdown(
                '<div style="border:1.5px solid #c8dece;border-radius:8px;'
                'margin-bottom:1.4rem;overflow:hidden">'
                '<div style="background:' + rc + ';color:white;padding:.5rem 1rem;'
                'font-size:.84rem;font-weight:700">'
                + escape(item["label"]) + ' — ' + escape(item["cause"])
                + ' <span style="opacity:.82;font-weight:400;font-size:.78rem"> | Interval: '
                + escape(item["interval"]) + '</span></div>'
                '<div style="display:grid;grid-template-columns:1fr 1.6fr 2.4fr 2.5fr;gap:0">'

                '<div style="padding:.7rem .9rem;border-right:1px solid #e0ece5">'
                '<div style="font-size:.72rem;font-weight:700;color:#555;margin-bottom:.3rem;text-transform:uppercase;letter-spacing:.04em">ICD-10 Code</div>'
                '<div style="font-size:1.05rem;font-weight:800;color:var(--green);letter-spacing:.03em">'
                + (escape(code_val) if code_val else '<span style="color:#bbb;font-style:italic">—</span>')
                + '</div>' + badge_html + '</div>'

                '<div style="padding:.7rem .9rem;border-right:1px solid #e0ece5">'
                '<div style="font-size:.72rem;font-weight:700;color:#555;margin-bottom:.3rem;text-transform:uppercase;letter-spacing:.04em">Disease Name</div>'
                '<div style="font-size:.85rem;color:#1a2e1a;line-height:1.45">'
                + (escape(short_val) if short_val else '<span style="color:#bbb;font-style:italic">—</span>')
                + '</div></div>'

                '<div style="padding:.7rem .9rem;border-right:1px solid #e0ece5">'
                '<div style="font-size:.72rem;font-weight:700;color:#555;margin-bottom:.3rem;text-transform:uppercase;letter-spacing:.04em">Full Description</div>'
                '<div style="font-size:.82rem;color:#2a3a2a;line-height:1.5">'
                + (escape(long_val) if long_val else '<span style="color:#bbb;font-style:italic">—</span>')
                + '</div></div>'

                '<div style="padding:.7rem .9rem;background:#f7faf8">'
                '<div style="font-size:.72rem;font-weight:700;color:#555;margin-bottom:.3rem;text-transform:uppercase;letter-spacing:.04em">Selection Notes</div>'
                '<div style="font-size:.81rem;color:#1a2e1a;line-height:1.6;border:1px solid #d7e6db;border-radius:5px;padding:.4rem .6rem;background:white">'
                + (escape(notes_val) if notes_val else '<span style="color:#bbb;font-style:italic">—</span>')
                + '</div>'
                + ('<div style="font-size:.76rem;color:#666;margin-top:.45rem"><b>ICD Note:</b> ' + escape(source_note) + '</div>' if source_note else '')
                + '</div>'
                '</div></div>',
                unsafe_allow_html=True,
            )

            widget_key = f"code_edit_{idx}"
            if widget_key not in st.session_state:
                st.session_state[widget_key] = code_val

            new_code = st.text_input(
                f"Edit ICD code for: {item['cause'][:50]}",
                key=widget_key,
                placeholder="e.g. I21.0",
            )

            if new_code != code_val:
                updated = refresh_code_from_manual_edit(df_source, item, new_code, fd.get("sex", ""))
                st.session_state.icd_results["coded_causes"][idx] = updated
                st.session_state.icd_results["validation"] = validate_certificate(
                    st.session_state.icd_results["coded_causes"], fd.get("sex", "")
                )
                st.rerun()

            with st.expander("Top retrieved candidates"):
                cand_rows = []
                for c in item.get("candidates", []):
                    cand_rows.append({
                        "Code": c.get("code_formatted", ""),
                        "ShortDesc": c.get("short_desc", ""),
                        "AcceptableMain": c.get("acceptable_main", ""),
                        "GenderRestriction": c.get("gender_restriction", ""),
                        "Score": round(float(c.get("score", 0.0)), 4),
                        "Why": "; ".join(c.get("reasons", [])),
                    })
                if cand_rows:
                    st.dataframe(pd.DataFrame(cand_rows), use_container_width=True)
                else:
                    st.info("No candidates available.")

    with tab_cert:
        cert_no = fd.get("cert_number") or f"DC-{datetime.date.today().year}-{fd.get('national_id', '')[-4:]}"
        cert_no_safe = sanitize_filename(cert_no)

        part1 = [x for x in coded_causes if x["role"] in {"immediate", "contributing"}]
        part2 = [x for x in coded_causes if x["role"] == "other"]

        row_labels = ["(a)", "(b)", "(c)", "(d)", "(e)"]
        part1_rows = ""
        for i, x in enumerate(part1):
            part1_rows += (
                '<div class="cert-field"><span class="cert-label">'
                + escape(row_labels[i] if i < len(row_labels) else f"({i+1})")
                + (' Immediate cause' if i == 0 else ' Due to')
                + '</span><span>'
                + escape(x["cause"]) + ' — <b>' + escape(x.get("code_formatted", "")) + '</b>'
                + ' <span style="font-size:.78rem;color:#666">(' + escape(x.get("interval", "—")) + ')</span>'
                + '</span></div>'
            )

        part2_rows = "".join(
            '<div class="cert-field"><span class="cert-label">Other significant condition</span>'
            '<span>' + escape(x["cause"]) + ' — <b>' + escape(x.get("code_formatted", "")) + '</b>'
            + (' <span style="font-size:.78rem;color:#666">(' + escape(x.get("interval", "—")) + ')</span>' if x.get("interval", "—") != "—" else '')
            + '</span></div>'
            for x in part2
        )

        underlying_code = validation.get("underlying_cause", "—")

        st.markdown(
            '<div class="cert-preview">'
            '<div style="display:flex;justify-content:space-between;align-items:center;'
            'border-bottom:2px solid var(--green);padding-bottom:1rem;margin-bottom:1.4rem;gap:12px;flex-wrap:wrap">'
            '<div>'
            '<div style="font-size:.95rem;font-weight:700;color:var(--green)">Kingdom of Saudi Arabia</div>'
            '<div style="font-size:.8rem;color:var(--muted)">Ministry of Health</div>'
            '<div style="font-size:.75rem;color:#888">' + escape(hospital_name) + ' — ' + escape(hospital_city) + '</div></div>'
            '<div style="text-align:center">'
            '<div class="cert-title">Death Certificate</div>'
            '<div class="cert-sub">Electronic ICD-10 Coding Preview</div>'
            '<div style="background:var(--green);color:white;border-radius:4px;padding:2px 10px;'
            'font-size:.76rem;margin-top:5px;display:inline-block">No: ' + escape(cert_no) + '</div></div>'
            '<div style="text-align:right">'
            '<div style="font-size:.95rem;font-weight:700;color:var(--green)">Saudi MOH</div>'
            '<div style="font-size:.8rem;color:var(--muted)">Official Draft Preview</div></div></div>'

            '<div style="display:grid;grid-template-columns:1fr 1fr;gap:2rem;margin-bottom:1.4rem">'
            '<div>'
            '<div class="cert-field"><span class="cert-label">Name</span><span>' + escape(fd.get("full_name", "—")) + '</span></div>'
            '<div class="cert-field"><span class="cert-label">ID</span><span>' + escape(fd.get("national_id", "—")) + '</span></div>'
            '<div class="cert-field"><span class="cert-label">Sex</span><span>' + escape(fd.get("sex", "—")) + '</span></div>'
            '<div class="cert-field"><span class="cert-label">Age</span><span>' + escape(str(fd.get("age_years", "—"))) + ' years</span></div>'
            '</div><div>'
            '<div class="cert-field"><span class="cert-label">Date of Death</span><span>' + escape(str(fd.get("dod", "—"))) + '</span></div>'
            '<div class="cert-field"><span class="cert-label">Place of Death</span><span>' + escape(fd.get("place_of_death", "—")) + '</span></div>'
            '<div class="cert-field"><span class="cert-label">Type of Death</span><span>' + escape(fd.get("death_type", "—")) + '</span></div>'
            '</div></div>'

            '<div style="background:var(--green-light);border-radius:6px;padding:1rem 1.2rem;'
            'margin-bottom:1rem;border:1px solid #9ecaad">'
            '<div style="font-weight:700;color:var(--green);margin-bottom:.6rem">Part I — Direct causal sequence</div>'
            + part1_rows +
            '</div>'

            '<div style="background:#f8fafc;border-radius:6px;padding:1rem 1.2rem;'
            'margin-bottom:1rem;border:1px solid #d7e2ea">'
            '<div style="font-weight:700;color:#355c7d;margin-bottom:.6rem">Part II — Other significant conditions</div>'
            + (part2_rows if part2_rows else '<div style="font-size:.85rem;color:#666">None documented.</div>')
            + '</div>'

            '<div style="background:#f0f4ff;border-radius:6px;padding:.7rem 1rem;'
            'margin-bottom:1.4rem;border:1px solid #b0c4de;font-size:.85rem">'
            '<b style="color:#1a4a7a">Underlying Cause (for mortality statistics):</b> '
            '<span style="font-family:monospace;font-weight:800;font-size:.95rem">' + escape(underlying_code or "—") + '</span></div>'

            '<div style="display:flex;justify-content:space-between;padding-top:1.2rem;border-top:1px solid #d0ddd2;gap:12px;flex-wrap:wrap">'
            '<div><div style="font-weight:700;color:var(--green);font-size:.85rem">Certifying Physician</div>'
            '<div>' + escape(doctor_name or "________________________________") + '</div>'
            '<div style="font-size:.75rem;color:#888;margin-top:6px">Signature: _______________________</div></div>'
            '<div class="cert-stamp">MOH<br>Official<br>Draft</div>'
            '<div style="text-align:right"><div style="font-weight:700;color:var(--green);font-size:.85rem">Issue Date</div>'
            '<div>' + escape(str(fd.get("date_issued", datetime.date.today()))) + '</div></div></div></div>',
            unsafe_allow_html=True,
        )

        cert_lines = [
            "DEATH CERTIFICATE",
            f"Certificate No: {cert_no}",
            "=" * 60,
            f"Hospital: {hospital_name} - {hospital_city}",
            "",
            f"Name: {fd.get('full_name', '')}",
            f"ID: {fd.get('national_id', '')}",
            f"Sex: {fd.get('sex', '')}",
            f"Age: {fd.get('age_years', '')} years",
            f"Date of death: {fd.get('dod', '')}",
            f"Place of death: {fd.get('place_of_death', '')}",
            "",
            "PART I - DIRECT CAUSAL SEQUENCE",
        ]
        for i, item in enumerate(part1):
            lbl = row_labels[i] if i < len(row_labels) else f"({i+1})"
            cert_lines.append(
                f"  {lbl} {item['cause']} | {item.get('code_formatted', '')} | {item.get('short_desc', '')} | interval: {item.get('interval', '—')}"
            )

        cert_lines.append("")
        cert_lines.append("PART II - OTHER SIGNIFICANT CONDITIONS")
        if part2:
            for item in part2:
                cert_lines.append(
                    f"  - {item['cause']} | {item.get('code_formatted', '')} | {item.get('short_desc', '')} | interval: {item.get('interval', '—')}"
                )
        else:
            cert_lines.append("  None documented.")

        cert_lines += [
            "",
            f"Underlying cause: {underlying_code}",
            "",
            f"Physician: {doctor_name}",
            f"Issue date: {fd.get('date_issued', '')}",
        ]

        st.download_button(
            "Download Certificate Summary (.txt)",
            data="\n".join(cert_lines).encode("utf-8"),
            file_name=f"{sanitize_filename('death_cert_' + cert_no_safe)}.txt",
            mime="text/plain",
        )

    with tab_debug:
        st.subheader("Claude-extracted structure")
        st.json(concepts)

    st.markdown("---")
    b1, b2, b3, _ = st.columns([1, 1.3, 1.2, 5])

    with b1:
        if st.button("Back", use_container_width=True):
            st.session_state.page = 3
            st.session_state.icd_results = None
            st.rerun()

    with b2:
        if st.button("Go to Final Certificate", use_container_width=True):
            st.session_state.page = 5
            st.rerun()

    with b3:
        if st.button("New Certificate", use_container_width=True):
            keys_to_remove = [k for k in st.session_state.keys() if k.startswith("code_edit_")]
            for k in keys_to_remove:
                del st.session_state[k]
            st.session_state.page = 1
            st.session_state.form_data = {}
            st.session_state.icd_results = None
            st.rerun()

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

    part1 = [x for x in coded_causes if x["role"] in {"immediate", "contributing"}]
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
            # clear pdf cache too
            for k in ["pdf_bytes_cached", "pdf_cert_no"]:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()
