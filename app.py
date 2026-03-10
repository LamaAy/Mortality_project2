"""
Saudi MOH - Electronic Death Certificate System
English UI
Deterministic ICD-10 coding using:
- Excel / metadata as source of truth
- Optional prebuilt FAISS index
- Optional embeddings
- BM25 keyword retrieval
- Reciprocal Rank Fusion (RRF)
- Rule-based validation

No LLMs are used.
"""

import streamlit as st
import pandas as pd
import numpy as np
import re
import datetime
import io
import os
import pickle
import html
from typing import List, Dict, Tuple, Optional

# =============================================================================
# Page Config
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

.stButton > button {
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
.stButton > button:hover {
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
    <p style="font-size:.76rem;opacity:.72">Deterministic ICD-10 Coding | Excel + Metadata + FAISS + BM25</p>
  </div>
  <div class="moh-emblem">MOH<br>KSA<br>Death<br>Cert</div>
</div>
""", unsafe_allow_html=True)

# =============================================================================
# Updated Resource IDs
# =============================================================================
GDRIVE_EMBEDDINGS_ID = "1CxCGihYnqyaIc-F0IJwHNUTpLRHGmy8Y"
GDRIVE_FAISS_ID      = "17F5rDFoT3iDbRKKiHCMiSB9ZrH0ecVTP"
GDRIVE_METADATA_ID   = "1nUUdhivH1XIPGXkvWjrapxzuKfbM445B"
GDRIVE_EXCEL_ID      = "1h54uBVeae8r6xC0MJI1-G3uRJwLc7K-y"

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".icd10_det_cache_v2")
EMBED_MODEL_NAME = "pritamdeka/S-PubMedBert-MS-MARCO"

# =============================================================================
# Utilities
# =============================================================================
def escape(x) -> str:
    return html.escape("" if x is None else str(x))

def sanitize_filename(s: str) -> str:
    s = re.sub(r"[^\w\-\.]+", "_", s.strip(), flags=re.UNICODE)
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
    code = code.strip().upper()
    return len(code.replace(".", ""))

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

# =============================================================================
# Deterministic dictionaries
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
}

AMBIGUOUS_TERMS = {
    "shock", "failure", "stroke", "cancer", "infection", "sepsis", "respiratory failure"
}

STOPWORDS = {
    "the", "and", "or", "with", "without", "due", "to", "secondary", "of", "in",
    "acute", "chronic", "history", "known", "generalized", "severe", "mild"
}

# =============================================================================
# Cause / interval parsing
# =============================================================================
INTERVAL_PATTERNS = [
    r"\(([^()]{1,40})\)",
    r"\bfor\s+([a-z0-9\-\s]{1,40})\b",
    r"\bover\s+([a-z0-9\-\s]{1,40})\b",
    r"\blasting\s+([a-z0-9\-\s]{1,40})\b",
    r"\bpresent\s+for\s+([a-z0-9\-\s]{1,40})\b",
]

OTHER_CONDITION_HINTS = [
    "diabetes", "hypertension", "obesity", "metabolic syndrome", "dementia",
    "chronic kidney disease", "coronary artery disease", "copd", "cancer",
    "renal disease", "liver disease"
]

def clean_interval(s: str) -> str:
    if not s:
        return "—"
    s = s.strip(" .;:,")
    s = re.sub(r"\s+", " ", s)
    return s if s else "—"

def split_narrative_into_segments(text: str) -> List[str]:
    t = text.replace("\n", " ")
    chunks = re.split(r"\s*(?:;|\.|\n)\s*", t)
    final = []
    for ch in chunks:
        ch = ch.strip()
        if not ch:
            continue
        parts = re.split(r"\b(?:due to|because of|resulting from|caused by|secondary to)\b", ch, flags=re.I)
        parts = [p.strip(" ,.-") for p in parts if p.strip(" ,.-")]
        if len(parts) > 1:
            final.extend(parts)
        else:
            final.append(ch)
    return [x for x in final if x]

def extract_interval_from_segment(seg: str) -> Tuple[str, str]:
    for pat in INTERVAL_PATTERNS:
        m = re.search(pat, seg, flags=re.I)
        if m:
            interval = clean_interval(m.group(1))
            cleaned = re.sub(pat, "", seg, flags=re.I).strip(" ,.-")
            return cleaned, interval
    return seg.strip(" ,.-"), "—"

def classify_segment(seg: str) -> str:
    s = normalize_text_basic(seg)
    for h in OTHER_CONDITION_HINTS:
        if h in s:
            return "other"
    return "chain"

def parse_death_narrative(text: str) -> Dict:
    segments = split_narrative_into_segments(text)
    parsed = []

    for seg in segments:
        cause, interval = extract_interval_from_segment(seg)
        if cause:
            parsed.append({
                "raw": seg,
                "cause": cause,
                "interval": interval,
                "kind": classify_segment(cause),
            })

    chain = [x for x in parsed if x["kind"] == "chain"]
    others = [x for x in parsed if x["kind"] == "other"]

    immediate = chain[0]["cause"] if len(chain) >= 1 else ""
    immediate_interval = chain[0]["interval"] if len(chain) >= 1 else "—"
    contributing = [x["cause"] for x in chain[1:]]
    contributing_intervals = [x["interval"] for x in chain[1:]]

    return {
        "immediate_cause": immediate,
        "contributing_causes": contributing,
        "other_conditions": [x["cause"] for x in others],
        "intervals": {
            "immediate_cause": immediate_interval,
            "contributing_causes": contributing_intervals,
            "other_conditions": [x["interval"] for x in others],
        },
        "segments_debug": parsed,
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
            raise ValueError(
                f"Unexpected schema. Expected {len(EXPECTED_COLS)} columns, got {len(df.columns)}."
            )

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
    """
    Tries in this order:
    1) Load a prebuilt FAISS index from Drive
    2) Otherwise build FAISS from embeddings.npy
    """
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
# Search and candidate selection
# =============================================================================
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

def expand_query(query: str) -> str:
    q = normalize_text_basic(query)
    expansions = []
    for key, vals in LAY_QUERY_EXPANSIONS.items():
        if key in q:
            expansions.extend(vals)
    return (query + " " + " ".join(expansions)).strip() if expansions else query

def diabetes_type_hint(query: str) -> Optional[str]:
    q = normalize_text_basic(query)
    if re.search(r"\b(type\s*2|type\s*ii|non[-\s]?insulin[-\s]?dependent)\b", q):
        return "type2"
    if re.search(r"\b(type\s*1|type\s*i|insulin[-\s]?dependent)\b", q):
        return "type1"
    return None

def detect_ambiguous_query(query: str) -> bool:
    q = normalize_text_basic(query)
    return q in AMBIGUOUS_TERMS or len(tokenize(q)) <= 1

def exact_code_search(df: pd.DataFrame, query: str) -> List[Tuple[int, float]]:
    q = query.strip().upper().replace(" ", "")
    if re.fullmatch(r"[A-TV-Z][0-9][0-9](?:\.[0-9A-Z]+)?", q):
        mask = df["lookup_code"] == q
        hits = df.index[mask].tolist()
        return [(int(i), 1.0) for i in hits]
    return []

def semantic_search(df: pd.DataFrame, faiss_index, query: str, top_k: int = 40) -> List[Tuple[int, float]]:
    if faiss_index is None:
        return []

    try:
        model = get_embed_model()
        q_vec = model.encode([expand_query(query)], normalize_embeddings=True, convert_to_numpy=True).astype("float32")
        scores, indices = faiss_index.search(q_vec, top_k)
        out = []
        for score, idx in zip(scores[0], indices[0]):
            if idx != -1 and 0 <= idx < len(df):
                out.append((int(idx), float(score)))
        return out
    except Exception:
        return []

def bm25_search(df: pd.DataFrame, bm25, query: str, top_k: int = 40) -> List[Tuple[int, float]]:
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
    code = str(row["CodeFormatted"])
    acc = acceptable_main_bool(row["AcceptableMain"])
    gender_ok = is_gender_allowed(row["GenderRestriction"], sex_value)

    if q and q in text:
        score += 3.0
        reasons.append("query phrase found in ICD text")

    q_tokens = [t for t in tokenize(q) if t not in STOPWORDS]
    row_tokens = set(tokenize(text))
    overlap = len(set(q_tokens) & row_tokens)
    score += min(overlap, 6) * 0.35
    if overlap:
        reasons.append(f"token overlap={overlap}")

    spec = specificity_score(code)
    score += spec * 0.03
    reasons.append(f"specificity={spec}")

    if role in {"immediate", "contributing"}:
        if acc is True:
            score += 0.5
            reasons.append("acceptable as main cause")
        elif acc is False:
            score -= 0.8
            reasons.append("not acceptable as main cause")

    if not gender_ok:
        score -= 3.0
        reasons.append("gender restriction conflict")

    # Safer septic shock handling: only when explicitly septic shock
    if "septic shock" in q:
        if code.upper().startswith("R57.2"):
            score += 1.0
            reasons.append("preferred septic shock code")
        if code.upper().startswith("T81.12"):
            score -= 2.5
            reasons.append("postprocedural septic shock penalized")

    d_hint = diabetes_type_hint(q)
    if d_hint == "type2":
        if code.upper().startswith("E11"):
            score += 1.0
            reasons.append("matches type 2 diabetes")
        if code.upper().startswith("E10"):
            score -= 1.2
            reasons.append("type 1 diabetes penalized")
    elif d_hint == "type1":
        if code.upper().startswith("E10"):
            score += 1.0
            reasons.append("matches type 1 diabetes")
        if code.upper().startswith("E11"):
            score -= 1.2
            reasons.append("type 2 diabetes penalized")

    if detect_ambiguous_query(q) and overlap < 2:
        score -= 0.7
        reasons.append("ambiguous query")

    return score, reasons

def search_icd_candidates(
    df: pd.DataFrame,
    faiss_index,
    bm25,
    query: str,
    sex_value: str,
    role: str,
    top_k: int = 12
) -> List[Dict]:
    exact_hits = exact_code_search(df, query)
    sem_hits = semantic_search(df, faiss_index, query, top_k=40)
    bm_hits = bm25_search(df, bm25, query, top_k=40)

    fused = reciprocal_rank_fusion([exact_hits, sem_hits, bm_hits], k=60)

    candidates = []
    for idx, rrf_score in fused.items():
        row = df.iloc[idx]
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

def choose_best_candidate(cands: List[Dict], role: str) -> Dict:
    if not cands:
        return {
            "code_formatted": "",
            "short_desc": "",
            "long_desc": "",
            "acceptable_main": "Unknown",
            "gender_restriction": "",
            "classification": "",
            "note": "",
            "score": 0.0,
            "selection_status": "manual_review",
            "selection_notes": "No candidate found in indexed data. Manual review required.",
        }

    best = cands[0].copy()

    if best["score"] < 0.15:
        best["selection_status"] = "manual_review"
        best["selection_notes"] = "Low-confidence retrieval. Manual review required."
        return best

    if role in {"immediate", "contributing"}:
        acc = acceptable_main_bool(best.get("acceptable_main", ""))
        if acc is False:
            acceptable_alts = [x for x in cands[1:] if acceptable_main_bool(x.get("acceptable_main", "")) is True]
            if acceptable_alts:
                alt = acceptable_alts[0].copy()
                alt["selection_status"] = "auto_selected"
                alt["selection_notes"] = "Top candidate was not acceptable as a main cause; selected best acceptable alternative."
                return alt
            best["selection_status"] = "manual_review"
            best["selection_notes"] = "Top candidate is not acceptable as a main cause and no strong acceptable alternative was found."
            return best

    best["selection_status"] = "auto_selected"
    best["selection_notes"] = "Best deterministic match from indexed ICD data."
    return best

# =============================================================================
# Validation
# =============================================================================
def is_r_chapter(code: str) -> bool:
    code = (code or "").strip().upper()
    return code.startswith("R")

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
        if is_r_chapter(code) and not (code.startswith("R57") or code.startswith("R65")):
            issues.append(f"{code} is an ill-defined R-chapter code in Part I and should be avoided if a more specific cause is available.")

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
# Coding pipeline
# =============================================================================
def code_causes_from_narrative(
    narrative: str,
    df_source: pd.DataFrame,
    faiss_index,
    bm25,
    sex_value: str,
) -> Dict:
    concepts = parse_death_narrative(narrative)
    coded_causes = []

    immediate = concepts.get("immediate_cause", "").strip()
    if immediate:
        cands = search_icd_candidates(df_source, faiss_index, bm25, immediate, sex_value, role="immediate", top_k=10)
        chosen = choose_best_candidate(cands, role="immediate")
        chosen.update({
            "role": "immediate",
            "label": "Immediate cause",
            "cause": immediate,
            "interval": concepts["intervals"].get("immediate_cause", "—"),
            "candidates": cands,
        })
        coded_causes.append(chosen)

    for i, c in enumerate(concepts.get("contributing_causes", [])):
        cands = search_icd_candidates(df_source, faiss_index, bm25, c, sex_value, role="contributing", top_k=10)
        chosen = choose_best_candidate(cands, role="contributing")
        chosen.update({
            "role": "contributing",
            "label": f"Due to ({i+1})",
            "cause": c,
            "interval": concepts["intervals"].get("contributing_causes", ["—"] * 50)[i] if i < len(concepts["intervals"].get("contributing_causes", [])) else "—",
            "candidates": cands,
        })
        coded_causes.append(chosen)

    other_intervals = concepts["intervals"].get("other_conditions", [])
    for i, c in enumerate(concepts.get("other_conditions", [])):
        cands = search_icd_candidates(df_source, faiss_index, bm25, c, sex_value, role="other", top_k=10)
        chosen = choose_best_candidate(cands, role="other")
        chosen.update({
            "role": "other",
            "label": f"Other condition ({i+1})",
            "cause": c,
            "interval": other_intervals[i] if i < len(other_intervals) else "—",
            "candidates": cands,
        })
        coded_causes.append(chosen)

    validation = validate_certificate(coded_causes, sex_value)
    return {
        "concepts": concepts,
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
        updated["score"] = 0.0
        updated["reasons"] = ["manual edit"]
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
    updated["score"] = updated.get("score", 0.0)
    updated["reasons"] = ["manual edit refresh"]

    if not is_gender_allowed(updated["gender_restriction"], sex_value):
        updated["selection_status"] = "manual_review"
        updated["selection_notes"] = "Manual code conflicts with sex restriction."

    return updated

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
        'No LLM usage</div>',
        unsafe_allow_html=True,
    )

    if st.button("Reload ICD Data", use_container_width=True):
        import shutil
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
        st.cache_resource.clear()
        for k in list(st.session_state.keys()):
            if k.startswith("code_edit_"):
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
    st.markdown(
        '<div style="font-size:.72rem;opacity:.65;text-align:center;line-height:2">'
        'Ministry of Health<br>Deterministic ICD-10 Coding v2</div>',
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
# Safe auto-load resources
# =============================================================================
if st.session_state["df_source"] is None:
    df_excel = None
    df_meta = None
    faiss_index = None
    bm25 = None
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
    labels = ["Basic Information", "Medical History", "Cause Narrative", "Review & Coding"]
    html_s = '<div class="step-bar">'
    for i, lbl in enumerate(labels, 1):
        cls = "step active" if i == current else ("step done" if i < current else "step")
        html_s += f'<div class="{cls}">{i}. {escape(lbl)}</div>'
    html_s += "</div>"
    st.markdown(html_s, unsafe_allow_html=True)

# =============================================================================
# PAGE 1 - Basic Information
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
        education = st.selectbox(
            "Education",
            ["Illiterate", "Primary", "Intermediate", "Secondary", "Diploma", "Bachelor", "Postgraduate", "Unknown"]
        )
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
# PAGE 2 - Medical History
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
            was_pregnant = st.selectbox(
                "Pregnancy Status",
                ["No", "Pregnant", "During delivery", "Within 42 days postpartum", "N/A"]
            )
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
# PAGE 3 - Cause Narrative
# =============================================================================
elif st.session_state.page == 3:
    render_steps(3)
    fd = st.session_state.form_data

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">Cause of Death Narrative</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="background:#fffbe6;border-left:3px solid #C8A951;padding:9px 14px;'
        'border-radius:5px;margin-bottom:1.1rem;font-size:.87rem;color:#5a4a00">'
        'Write a single paragraph in plain language or medical language. '
        'For best results, write the immediate cause first, then the underlying sequence, then other significant conditions.</div>',
        unsafe_allow_html=True
    )

    free_text = st.text_area(
        "Narrative Description",
        value=fd.get("free_text", ""),
        height=220,
        placeholder=(
            "Example: The patient died from acute respiratory distress syndrome (2 days) "
            "due to septic shock (5 days) due to perforated sigmoid diverticulitis with generalized peritonitis (10 days). "
            "Other significant conditions included type 2 diabetes mellitus with vasculopathy (12 years) and obesity (20 years)."
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
            else:
                st.session_state.form_data["free_text"] = free_text
                st.session_state.icd_results = None
                st.session_state.page = 4
                st.rerun()

# =============================================================================
# PAGE 4 - Review & Coding
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

    if not fd.get("free_text", "").strip():
        st.error("No cause narrative found.")
        if st.button("Back"):
            st.session_state.page = 3
            st.rerun()
        st.stop()

    if st.session_state.icd_results is None:
        with st.spinner("Parsing narrative and coding against ICD source..."):
            st.session_state.icd_results = code_causes_from_narrative(
                narrative=fd["free_text"],
                df_source=df_source,
                faiss_index=faiss_index,
                bm25=bm25,
                sex_value=fd.get("sex", ""),
            )

        for i, item in enumerate(st.session_state.icd_results["coded_causes"]):
            st.session_state[f"code_edit_{i}"] = item.get("code_formatted", "")

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

    tab_res, tab_cert, tab_debug = st.tabs(["ICD-10 Codes", "Certificate Preview", "Parsed Structure"])

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

            new_code = st.text_input(
                f"Edit ICD code for: {item['cause'][:50]}",
                value=st.session_state.get(f"code_edit_{idx}", code_val),
                key=f"code_edit_{idx}",
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

        part1_rows = ""
        row_labels = ["(a)", "(b)", "(c)", "(d)", "(e)"]
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

        st.markdown("---")

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
            "Download Certificate Summary",
            data="\n".join(cert_lines).encode("utf-8"),
            file_name=f"{sanitize_filename('death_cert_' + cert_no_safe)}.txt",
            mime="text/plain",
        )

    with tab_debug:
        st.subheader("Parsed Narrative")
        st.json({
            "immediate_cause": concepts.get("immediate_cause", ""),
            "contributing_causes": concepts.get("contributing_causes", []),
            "other_conditions": concepts.get("other_conditions", []),
            "intervals": concepts.get("intervals", {}),
        })

        if "segments_debug" in concepts:
            st.subheader("Detected Segments")
            st.dataframe(pd.DataFrame(concepts["segments_debug"]), use_container_width=True)

    st.markdown("---")
    b1, b2, _ = st.columns([1, 1, 6])
    with b1:
        if st.button("Back", use_container_width=True):
            st.session_state.page = 3
            st.session_state.icd_results = None
            st.rerun()
    with b2:
        if st.button("New Certificate", use_container_width=True):
            keys_to_remove = [k for k in st.session_state.keys() if k.startswith("code_edit_")]
            for k in keys_to_remove:
                del st.session_state[k]
            st.session_state.page = 1
            st.session_state.form_data = {}
            st.session_state.icd_results = None
            st.rerun()
