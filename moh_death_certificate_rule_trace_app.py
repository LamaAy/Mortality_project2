"""
Saudi MOH Electronic Death Certificate AI System
Rule-grounded ICD-10 coding + Table A/B SP1-SP8 + WHO ICD API verification + audit trace.

Run:
    streamlit run moh_death_certificate_rule_trace_app.py

Install typical dependencies:
    pip install streamlit pandas numpy openpyxl rank-bm25 sentence-transformers faiss-cpu anthropic requests reportlab

Core design:
- Local ICD file is used for free-text disease-name search and mortality-specific flags.
- WHO ICD API is optional and used only for official selected-code verification/metadata.
- Table A is used deterministically for SP3-SP5 sequence-only logic.
- Table B is used deterministically for SP6 direct-sequel / obvious-cause logic.
- SP7/SP8 are quality blocks/checks based on local mortality flags and TABB TRIV rules.
- LLM is optional and constrained to normalization and candidate-only ICD selection/explanation.
- UI uses clinical module names, not "Agent 1/2/3" labels.
"""

from __future__ import annotations

import datetime as dt
import html
import io
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests
import streamlit as st

try:
    import anthropic
except Exception:  # optional dependency
    anthropic = None


# =============================================================================
# Page Config
# =============================================================================

st.set_page_config(
    page_title="Death Certificate | Saudi MOH",
    page_icon="⚕️",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =============================================================================
# Constants
# =============================================================================

APP_TITLE = "Saudi MOH Electronic Death Certificate System"
APP_SUBTITLE = "ICD-10 coding · Table A/B rule trace · SP1–SP8 · WHO ICD API verification · Audit log"
CLAUDE_MODEL = "claude-sonnet-4-20250514"

DEFAULT_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".moh_death_certificate_cache")
AUDIT_DB = os.path.join(DEFAULT_CACHE_DIR, "audit_log.sqlite")
WHO_CACHE_DB = os.path.join(DEFAULT_CACHE_DIR, "who_icd_cache.sqlite")

TOKEN_ENDPOINT = "https://icdaccessmanagement.who.int/connect/token"
WHO_BASE_URL = "https://id.who.int"
WHO_API_VERSION = "v2"
DEFAULT_WHO_RELEASE_ID = "2019"

EXPECTED_ICD_COLS = [
    "Code",
    "CodeFormatted",
    "ShortDesc",
    "LongDesc",
    "AcceptableMain",
    "GenderRestriction",
    "Classification",
    "Note",
]

TABA_COLS = [
    "anchor_start",
    "anchor_end",
    "cause_start",
    "cause_end",
    "modifier",
    "raw_line",
]

TABB_COLS = [
    "anchor",
    "rule_type",
    "modifier",
    "source_start",
    "source_end",
    "target",
    "raw_body",
    "page",
]

SP_RULES = {
    "SP1": "Single condition reported anywhere on the certificate.",
    "SP2": "Only one Part I line is used, or multiple conditions are placed on one line; select first-mentioned as tentative starting point and continue checks.",
    "SP3": "Full valid sequence; lowest used Part I line explains all above using Table A.",
    "SP4": "Partial valid sequence reaches the terminal cause using Table A.",
    "SP5": "No acceptable sequence reaches the terminal cause; use first-mentioned terminal condition.",
    "SP6": "Obvious cause selected from elsewhere on the certificate using Table B direct sequel rules.",
    "SP7": "Ill-defined starting point requires query/reselection.",
    "SP8": "Unlikely or trivial starting point requires query/reselection.",
    "REVIEW": "Manual coder review required.",
}


# =============================================================================
# CSS
# =============================================================================

st.markdown(
    """
    <style>
    .main .block-container {padding-top: 1.1rem; padding-bottom: 2rem;}
    .moh-header {
        background: linear-gradient(90deg, #006940 0%, #0f5132 55%, #C8A951 100%);
        color: white; padding: 18px 24px; border-radius: 18px; margin-bottom: 18px;
        box-shadow: 0 8px 22px rgba(0,0,0,0.08);
    }
    .moh-header h1 {font-size: 25px; margin: 0; font-weight: 800;}
    .moh-header p {margin: 6px 0 0 0; opacity: 0.95;}
    .card {
        border: 1px solid #d9e7df; border-radius: 16px; padding: 16px 18px;
        background: #ffffff; box-shadow: 0 3px 12px rgba(0,0,0,0.04); margin-bottom: 12px;
    }
    .card h3 {font-size: 17px; margin: 0 0 8px 0; color: #006940;}
    .green-card {border-left: 6px solid #198754; background: #f3fbf6;}
    .yellow-card {border-left: 6px solid #ffc107; background: #fffaf0;}
    .red-card {border-left: 6px solid #dc3545; background: #fff5f5;}
    .blue-card {border-left: 6px solid #0d6efd; background: #f4f8ff;}
    .metric-pill {
        display: inline-block; padding: 4px 10px; margin: 2px 4px 2px 0;
        border-radius: 999px; background: #eef6f1; color: #005c3a; font-size: 12px; font-weight: 700;
    }
    .small-muted {font-size: 12px; color: #5f6f67;}
    .ok-text {color: #006940; font-weight: 700;}
    .warning-text {color: #9a6700; font-weight: 700;}
    .error-text {color: #b42318; font-weight: 700;}
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# Basic Utilities
# =============================================================================


def ensure_dirs() -> None:
    os.makedirs(DEFAULT_CACHE_DIR, exist_ok=True)


def escape(x: Any) -> str:
    return html.escape("" if x is None else str(x))


def normalize_text_basic(text: Any) -> str:
    if text is None:
        return ""
    text = str(text).strip().lower().replace("\n", " ")
    return re.sub(r"\s+", " ", text)


def tokenize(text: Any) -> List[str]:
    text = normalize_text_basic(text)
    return re.findall(r"[A-Za-z]+\d*\.?\d*|[\u0600-\u06FF]+|\d+", text)


def normalize_code(code: Any) -> str:
    """I50.9 -> I509; E11.9 -> E119; C78.7 -> C787."""
    return str(code or "").upper().replace(" ", "").replace(".", "").strip()


def dot_code_from_norm(code_norm: Any) -> str:
    """I509 -> I50.9, E119 -> E11.9. Keeps I10 unchanged."""
    c = normalize_code(code_norm)
    if len(c) > 3:
        return f"{c[:3]}.{c[3:]}"
    return c


def parent_code(code: Any) -> str:
    """I50.9/I509 -> I50; E11.9/E119 -> E11."""
    return normalize_code(code)[:3]


def normalize_cause_key(cause: Any) -> str:
    c = normalize_text_basic(cause)
    c = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", c)
    return re.sub(r"\s+", " ", c).strip()


def safe_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


def specificity_score(code: str) -> int:
    return len(normalize_code(code))


def code_between(code: Any, start: Any, end: Any) -> bool:
    """
    Deterministic ICD range check used by Table A/B.
    The provided WHO mortality table exports use normalized ICD-like lexical ranges.
    """
    c = normalize_code(code)
    s = normalize_code(start)
    e = normalize_code(end)
    if not c or not s or not e:
        return False
    return s <= c <= e


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass
class CodedCause:
    line: str
    section: str
    role: str
    cause: str
    interval: str
    code_formatted: str = ""
    code_norm: str = ""
    parent_code: str = ""
    short_desc: str = ""
    long_desc: str = ""
    acceptable_main: str = ""
    gender_restriction: str = ""
    classification: str = ""
    note: str = ""
    selection_status: str = "manual_review"
    selection_notes: str = ""
    candidates: Optional[List[Dict[str, Any]]] = None
    who_verification: Optional[Dict[str, Any]] = None


# =============================================================================
# Session State
# =============================================================================


def init_state() -> None:
    defaults = {
        "role": "Doctor",
        "logged_in": False,
        "patient": {},
        "hospital": {},
        "part1": [
            {"line": "a", "cause": "", "interval": ""},
            {"line": "b", "cause": "", "interval": ""},
            {"line": "c", "cause": "", "interval": ""},
            {"line": "d", "cause": "", "interval": ""},
        ],
        "part2": [
            {"line": "II-1", "cause": "", "interval": ""},
            {"line": "II-2", "cause": "", "interval": ""},
            {"line": "II-3", "cause": "", "interval": ""},
        ],
        "last_result": None,
        "manual_override": {},
        "icd_df": None,
        "taba_df": None,
        "tabb_df": None,
        "data_ready": False,
        "use_who_api": False,
        "who_release_id": DEFAULT_WHO_RELEASE_ID,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


ensure_dirs()
init_state()


# =============================================================================
# Data Loading and Normalization
# =============================================================================


def normalize_icd_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    alias_map = {
        "Code (Formatted)": "CodeFormatted",
        "Code Formatted": "CodeFormatted",
        "Short Description": "ShortDesc",
        "Long Description": "LongDesc",
        "Acceptable as Main Cause": "AcceptableMain",
        "Acceptable as Main": "AcceptableMain",
        "Gender Restriction": "GenderRestriction",
        "Match Source": "MatchSource",
        "Matched From Code": "MatchedFromCode",
    }
    df = df.rename(columns={c: alias_map.get(c, c) for c in df.columns})

    if "CodeFormatted" not in df.columns and "Code" in df.columns:
        df["CodeFormatted"] = df["Code"].astype(str).map(dot_code_from_norm)
    if "Code" not in df.columns and "CodeFormatted" in df.columns:
        df["Code"] = df["CodeFormatted"].astype(str).map(normalize_code)

    for col in EXPECTED_ICD_COLS:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    if "Deleted" in df.columns:
        df = df[df["Deleted"].astype(str).str.lower().str.strip() != "yes"].copy()

    df = df[df["CodeFormatted"].astype(str).str.strip() != ""].reset_index(drop=True)
    df["lookup_code"] = df["CodeFormatted"].map(normalize_code)
    df["parent_code"] = df["lookup_code"].map(parent_code)
    df["combined_text"] = (
        df["CodeFormatted"].fillna("") + " "
        + df["Code"].fillna("") + " "
        + df["ShortDesc"].fillna("") + " "
        + df["LongDesc"].fillna("") + " "
        + df["Classification"].fillna("") + " "
        + df["Note"].fillna("")
    ).str.lower()
    df["EmbedText"] = df["combined_text"]
    return df.reset_index(drop=True)


def normalize_taba_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in TABA_COLS:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)
    for col in ["anchor_start", "anchor_end", "cause_start", "cause_end"]:
        df[col] = df[col].map(normalize_code)
    return df


def normalize_tabb_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in TABB_COLS:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)
    df["anchor_norm"] = df["anchor"].map(normalize_code)
    df["source_start_norm"] = df["source_start"].map(normalize_code)
    df["source_end_norm"] = df["source_end"].map(normalize_code)
    df["target_norm"] = df["target"].map(normalize_code)
    df["rule_type_norm"] = df["rule_type"].astype(str).str.upper().str.strip()
    return df


@st.cache_data(show_spinner=False)
def read_uploaded_table(file_bytes: bytes, name: str) -> pd.DataFrame:
    ext = name.lower().split(".")[-1]
    bio = io.BytesIO(file_bytes)
    if ext in {"xlsx", "xls"}:
        return pd.read_excel(bio)
    return pd.read_csv(bio)


@st.cache_data(show_spinner=False)
def read_local_table(path: str) -> pd.DataFrame:
    ext = path.lower().split(".")[-1]
    if ext in {"xlsx", "xls"}:
        return pd.read_excel(path)
    return pd.read_csv(path)


@st.cache_resource(show_spinner="Building BM25 index...")
def build_bm25_index(texts: Tuple[str, ...]):
    try:
        from rank_bm25 import BM25Okapi
        return BM25Okapi([tokenize(t) for t in texts])
    except Exception:
        return None


@st.cache_resource(show_spinner="Loading sentence embedding model...")
def get_embed_model(model_name: str = "pritamdeka/S-PubMedBert-MS-MARCO"):
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer(model_name)


@st.cache_resource(show_spinner="Building FAISS index...")
def build_faiss_index(texts: Tuple[str, ...], model_name: str = "pritamdeka/S-PubMedBert-MS-MARCO"):
    try:
        import faiss
        model = get_embed_model(model_name)
        emb = model.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True).astype("float32")
        index = faiss.IndexFlatIP(emb.shape[1])
        index.add(emb)
        return index
    except Exception:
        return None


# =============================================================================
# Optional WHO ICD API Client
# =============================================================================


class WHOICDClient:
    def __init__(self, client_id: str, client_secret: str, language: str = "en"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.language = language
        self._token: Optional[str] = None
        self._token_expiry = 0.0

    def get_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expiry:
            return self._token

        payload = {"grant_type": "client_credentials", "scope": "icdapi_access"}
        response = requests.post(
            TOKEN_ENDPOINT,
            data=payload,
            auth=(self.client_id, self.client_secret),
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        self._token = data["access_token"]
        self._token_expiry = now + int(data.get("expires_in", 3600)) - 300
        return self._token

    def headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.get_token()}",
            "Accept": "application/json",
            "Accept-Language": self.language,
            "API-Version": WHO_API_VERSION,
        }

    def get_icd10_code(self, code: str, release_id: str = DEFAULT_WHO_RELEASE_ID) -> Dict[str, Any]:
        url = f"{WHO_BASE_URL}/icd/release/10/{release_id}/{code.strip().upper()}"
        response = requests.get(url, headers=self.headers(), timeout=20)
        response.raise_for_status()
        return response.json()

    def get_icd10_releases(self) -> Dict[str, Any]:
        url = f"{WHO_BASE_URL}/icd/release/10"
        response = requests.get(url, headers=self.headers(), timeout=20)
        response.raise_for_status()
        return response.json()


def get_secret_or_env(name: str) -> Optional[str]:
    try:
        val = st.secrets.get(name, None)
        if val:
            return str(val)
    except Exception:
        pass
    val = os.environ.get(name)
    return val if val else None


@st.cache_resource(show_spinner=False)
def get_who_client_cached(client_id: str, client_secret: str, language: str = "en") -> WHOICDClient:
    return WHOICDClient(client_id=client_id, client_secret=client_secret, language=language)


def get_who_client() -> Optional[WHOICDClient]:
    client_id = get_secret_or_env("WHO_ICD_CLIENT_ID")
    client_secret = get_secret_or_env("WHO_ICD_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None
    return get_who_client_cached(client_id, client_secret, "en")


def init_who_cache() -> None:
    ensure_dirs()
    con = sqlite3.connect(WHO_CACHE_DB)
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS who_cache (
            cache_key TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )
    con.commit()
    con.close()


def get_cached_who(cache_key: str) -> Optional[Dict[str, Any]]:
    init_who_cache()
    con = sqlite3.connect(WHO_CACHE_DB)
    cur = con.cursor()
    cur.execute("SELECT payload_json FROM who_cache WHERE cache_key=?", (cache_key,))
    row = cur.fetchone()
    con.close()
    if row:
        try:
            return json.loads(row[0])
        except Exception:
            return None
    return None


def set_cached_who(cache_key: str, status: str, payload: Dict[str, Any]) -> None:
    init_who_cache()
    con = sqlite3.connect(WHO_CACHE_DB)
    cur = con.cursor()
    cur.execute(
        """
        INSERT OR REPLACE INTO who_cache(cache_key,timestamp,status,payload_json)
        VALUES(?,?,?,?)
        """,
        (cache_key, dt.datetime.now().isoformat(timespec="seconds"), status, safe_json(payload)),
    )
    con.commit()
    con.close()


def verify_code_with_who(selected_code: str, release_id: str = DEFAULT_WHO_RELEASE_ID) -> Dict[str, Any]:
    """
    Verify selected local ICD-10 code against WHO API.
    Tries detailed dotted code, no-dot code, and parent category.
    Keeps local detailed code as final even if only parent verifies.
    """
    if not st.session_state.get("use_who_api", False):
        return {"enabled": False, "status": "not_used", "message": "WHO ICD API verification disabled."}

    client = get_who_client()
    if client is None:
        return {"enabled": True, "status": "missing_credentials", "message": "WHO API credentials are not configured."}

    code_norm = normalize_code(selected_code)
    attempts = []
    for c in [dot_code_from_norm(code_norm), code_norm, parent_code(code_norm)]:
        if c and c not in attempts:
            attempts.append(c)

    cache_key = f"icd10:{release_id}:{code_norm}"
    cached = get_cached_who(cache_key)
    if cached is not None:
        cached["cached"] = True
        return cached

    errors = []
    for attempt in attempts:
        try:
            info = client.get_icd10_code(attempt, release_id=release_id)
            payload = {
                "enabled": True,
                "cached": False,
                "status": "verified",
                "selected_code": selected_code,
                "selected_code_norm": code_norm,
                "verified_code": attempt,
                "release_id": release_id,
                "who_info": info,
                "message": f"WHO ICD API verified {attempt}.",
            }
            set_cached_who(cache_key, "verified", payload)
            return payload
        except Exception as e:
            errors.append({"attempt": attempt, "error": f"{type(e).__name__}: {e}"})

    payload = {
        "enabled": True,
        "cached": False,
        "status": "not_verified",
        "selected_code": selected_code,
        "selected_code_norm": code_norm,
        "release_id": release_id,
        "errors": errors,
        "message": "WHO ICD API could not verify the detailed or parent code; local code retained with manual review.",
    }
    set_cached_who(cache_key, "not_verified", payload)
    return payload


# =============================================================================
# ICD Retrieval
# =============================================================================


LAY_QUERY_EXPANSIONS = {
    "heart attack": ["acute myocardial infarction", "myocardial infarction", "coronary thrombosis"],
    "stroke": ["cerebral infarction", "cerebrovascular accident", "intracranial hemorrhage"],
    "kidney failure": ["renal failure", "chronic kidney disease", "acute kidney failure"],
    "high blood pressure": ["hypertension", "essential hypertension"],
    "diabetes": ["diabetes mellitus"],
    "type 2 diabetes": ["type 2 diabetes mellitus", "non insulin dependent diabetes mellitus"],
    "type 1 diabetes": ["type 1 diabetes mellitus", "insulin dependent diabetes mellitus"],
    "fluid in lungs": ["pulmonary edema", "acute pulmonary edema"],
    "lung infection": ["pneumonia", "lower respiratory infection"],
    "brain bleed": ["intracranial hemorrhage", "cerebral hemorrhage"],
    "blood clot in lung": ["pulmonary embolism"],
    "cancer spread": ["metastatic malignant neoplasm", "secondary malignant neoplasm"],
    "ards": ["acute respiratory distress syndrome"],
    "septic shock": ["septic shock", "sepsis"],
    "التهاب رئوي": ["pneumonia"],
    "سكري": ["diabetes mellitus"],
    "جلطة": ["infarction", "thrombosis", "stroke"],
}

STOPWORDS = {
    "the", "and", "or", "with", "without", "due", "to", "secondary", "of", "in",
    "acute", "chronic", "history", "known", "generalized", "severe", "mild",
    "patient", "died", "from", "which", "developed", "resulted", "occurred",
}


def expand_query(query: str) -> str:
    q = normalize_text_basic(query)
    expansions: List[str] = []
    for key, vals in LAY_QUERY_EXPANSIONS.items():
        if key in q:
            expansions.extend(vals)
    return (query + " " + " ".join(expansions)).strip() if expansions else query


def acceptable_main_bool(x: Any) -> Optional[bool]:
    t = normalize_text_basic(x)
    if t in {"acceptable", "yes", "true", "1", "y"}:
        return True
    if t in {"not acceptable", "no", "false", "0", "n", "unacceptable"}:
        return False
    return None


def is_gender_allowed(gender_restriction: Any, sex_value: Any) -> bool:
    gr = normalize_text_basic(gender_restriction)
    sx = normalize_text_basic(sex_value)
    if not gr or gr in {"none", "n/a", "nan", "unknown"}:
        return True
    if "female" in gr and "male" in sx and "female" not in sx:
        return False
    if "male" in gr and "female" in sx:
        return False
    return True


def query_indicates_external_cause(query: str) -> bool:
    q = normalize_text_basic(query)
    triggers = [
        "accident", "injury", "collision", "fall", "burn", "poisoning", "vehicle",
        "road traffic", "assault", "homicide", "suicide", "gunshot", "stab", "trauma",
    ]
    return any(t in q for t in triggers)


def row_to_dict(row: pd.Series, score: float = 0.0, reasons: Optional[List[str]] = None) -> Dict[str, Any]:
    code_fmt = str(row.get("CodeFormatted", ""))
    return {
        "code": str(row.get("Code", "")),
        "code_formatted": code_fmt,
        "code_norm": normalize_code(code_fmt),
        "parent_code": parent_code(code_fmt),
        "short_desc": str(row.get("ShortDesc", "")),
        "long_desc": str(row.get("LongDesc", "")),
        "acceptable_main": str(row.get("AcceptableMain", "")),
        "gender_restriction": str(row.get("GenderRestriction", "")),
        "classification": str(row.get("Classification", "")),
        "note": str(row.get("Note", "")),
        "score": float(score),
        "reasons": reasons or [],
    }


def exact_code_search(df: pd.DataFrame, query: str) -> List[Tuple[int, float]]:
    q = normalize_code(query)
    if re.fullmatch(r"[A-TV-Z][0-9][0-9A-Z]{1,4}", q):
        hits = df.index[df["lookup_code"] == q].tolist()
        if not hits:
            hits = df.index[df["parent_code"] == parent_code(q)].tolist()
        return [(int(i), 1.0) for i in hits]
    return []


def bm25_search(df: pd.DataFrame, query: str, top_k: int = 50) -> List[Tuple[int, float]]:
    toks = [t for t in tokenize(expand_query(query)) if t not in STOPWORDS]
    if not toks or df.empty:
        return []
    bm25 = build_bm25_index(tuple(df["EmbedText"].tolist()))
    if bm25 is not None:
        try:
            scores = bm25.get_scores(toks)
            order = np.argsort(scores)[::-1][:top_k]
            mx = float(scores[order[0]]) if len(order) and scores[order[0]] > 0 else 1.0
            return [(int(i), float(scores[i]) / (mx + 1e-9)) for i in order if scores[i] > 0]
        except Exception:
            pass

    # Fallback lexical overlap.
    scored = []
    tokset = set(toks)
    for i, txt in enumerate(df["combined_text"].tolist()):
        overlap = len(tokset & set(tokenize(txt)))
        if overlap:
            scored.append((i, float(overlap)))
    scored = sorted(scored, key=lambda x: x[1], reverse=True)[:top_k]
    mx = scored[0][1] if scored else 1.0
    return [(i, s / (mx + 1e-9)) for i, s in scored]


def semantic_search(df: pd.DataFrame, query: str, top_k: int = 50) -> List[Tuple[int, float]]:
    if df.empty:
        return []
    index = build_faiss_index(tuple(df["EmbedText"].tolist()))
    if index is None:
        return []
    try:
        model = get_embed_model()
        q_vec = model.encode([expand_query(query)], normalize_embeddings=True, convert_to_numpy=True).astype("float32")
        scores, indices = index.search(q_vec, top_k)
        return [(int(idx), float(score)) for score, idx in zip(scores[0], indices[0]) if idx != -1]
    except Exception:
        return []


def reciprocal_rank_fusion(rank_lists: List[List[Tuple[int, float]]], k: int = 60) -> Dict[int, float]:
    fused: Dict[int, float] = {}
    for lst in rank_lists:
        for rank, (idx, _) in enumerate(lst, start=1):
            fused[idx] = fused.get(idx, 0.0) + 1.0 / (k + rank)
    return fused


def candidate_adjustment_score(row: pd.Series, query: str, sex_value: str, role: str) -> Tuple[float, List[str]]:
    reasons: List[str] = []
    score = 0.0
    q = normalize_text_basic(query)
    text = normalize_text_basic(row.get("combined_text", ""))
    code = str(row.get("CodeFormatted", "")).upper()
    acc = acceptable_main_bool(row.get("AcceptableMain", ""))

    if q and q in text:
        score += 4.0
        reasons.append("query phrase found in ICD text")

    q_tokens = [t for t in tokenize(q) if t not in STOPWORDS]
    overlap = len(set(q_tokens) & set(tokenize(text)))
    if overlap:
        score += min(overlap, 8) * 0.5
        reasons.append(f"token overlap={overlap}")

    score += specificity_score(code) * 0.03

    if role in {"immediate", "antecedent", "underlying", "other"}:
        if acc is True:
            score += 0.5
        elif acc is False:
            score -= 0.9
            reasons.append("not acceptable as main cause")

    if not is_gender_allowed(row.get("GenderRestriction", ""), sex_value):
        score -= 3.0
        reasons.append("gender restriction conflict")

    if code[:1] in {"V", "W", "X", "Y"} and not query_indicates_external_cause(query):
        score -= 5.0
        reasons.append("external/procedure code penalized")

    if "septic shock" in q and normalize_code(code).startswith("R57"):
        score += 3.0
        reasons.append("preferred septic shock family")
    if "pneumonia" in q and normalize_code(code).startswith("J18"):
        score += 2.0
        reasons.append("preferred pneumonia family")
    if "ards" in q or "acute respiratory distress" in q:
        if normalize_code(code).startswith("J80"):
            score += 3.0
            reasons.append("preferred ARDS code")

    return score, reasons


def search_icd_candidates(
    df_source: Optional[pd.DataFrame],
    query: str,
    sex_value: str,
    role: str,
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    if df_source is None or df_source.empty or not str(query).strip():
        return []

    exact_hits = exact_code_search(df_source, query)
    bm_hits = bm25_search(df_source, query, top_k=50)
    sem_hits = semantic_search(df_source, query, top_k=50)
    fused = reciprocal_rank_fusion([exact_hits, bm_hits, sem_hits], k=60)

    candidates: List[Dict[str, Any]] = []
    for idx, rrf_score in fused.items():
        if idx < 0 or idx >= len(df_source):
            continue
        row = df_source.iloc[idx]
        adj, reasons = candidate_adjustment_score(row, query, sex_value, role)
        candidates.append(row_to_dict(row, score=rrf_score + adj, reasons=reasons))

    candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)
    seen = set()
    unique: List[Dict[str, Any]] = []
    for c in candidates:
        code = normalize_code(c.get("code_formatted"))
        if not code or code in seen:
            continue
        seen.add(code)
        unique.append(c)
        if len(unique) >= top_k:
            break
    return unique


def get_row_by_code(df: Optional[pd.DataFrame], code: str) -> Optional[pd.Series]:
    if df is None or df.empty or not code:
        return None
    c = normalize_code(code)
    hits = df[df["lookup_code"] == c]
    return None if hits.empty else hits.iloc[0]


# =============================================================================
# LLM Helpers
# =============================================================================


def get_anthropic_api_key() -> Optional[str]:
    return get_secret_or_env("ANTHROPIC_API_KEY")


def extract_text_from_claude_response(resp: Any) -> str:
    parts = []
    for block in getattr(resp, "content", []):
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def extract_json_candidate(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```json\s*", "", text, flags=re.I)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    if text.startswith("{") and text.endswith("}"):
        return text
    s, e = text.find("{"), text.rfind("}")
    if s != -1 and e != -1 and e > s:
        return text[s:e + 1]
    return text


def call_claude_json(system_prompt: str, user_prompt: str, fallback: Dict[str, Any], max_tokens: int = 900) -> Dict[str, Any]:
    api_key = get_anthropic_api_key()
    if not api_key or anthropic is None:
        return fallback
    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=max_tokens,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = extract_text_from_claude_response(resp)
        return json.loads(extract_json_candidate(raw))
    except Exception as e:
        out = dict(fallback)
        out["_error"] = f"{type(e).__name__}: {e}"
        return out


def normalize_causes_with_claude(part1: List[Dict[str, str]], part2: List[Dict[str, str]], patient: Dict[str, Any]) -> Dict[str, Any]:
    fallback = {"part1_chain": part1, "part2_conditions": part2}
    system_prompt = """
You are a clinical death-certificate normalization assistant.
Return only valid JSON.
Use concise standard medical English terminology where possible.
Do not invent causes. Preserve Part I line order and Part II conditions.
Return exactly:
{"part1_chain":[{"line":"a","cause":"string","interval":"string"}],"part2_conditions":[{"line":"II-1","cause":"string","interval":"string"}]}
"""
    payload = {"patient": patient, "part1": part1, "part2": part2}
    return call_claude_json(system_prompt, safe_json(payload), fallback=fallback, max_tokens=900)


def select_code_from_candidates_with_claude(
    cause_text: str,
    role: str,
    interval: str,
    sex_value: str,
    age_years: int,
    candidates: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not candidates:
        return {"selected_code": "", "reason": "No retrieved ICD candidates available.", "manual_review": True}

    fallback = {
        "selected_code": candidates[0].get("code_formatted", ""),
        "reason": "Fallback selected top retrieved candidate; coder review recommended.",
        "manual_review": True,
    }
    slim = [
        {
            "CodeFormatted": c.get("code_formatted", ""),
            "ShortDesc": c.get("short_desc", ""),
            "LongDesc": c.get("long_desc", ""),
            "AcceptableMain": c.get("acceptable_main", ""),
            "GenderRestriction": c.get("gender_restriction", ""),
            "Classification": c.get("classification", ""),
            "Note": c.get("note", ""),
        }
        for c in candidates
    ]
    system_prompt = """
You are an ICD-10 coding assistant.
You MUST choose only from the candidate rows provided.
Do NOT invent codes. Do NOT use outside memory to create a code.
If none is adequate, return selected_code="" and manual_review=true.
Return only valid JSON exactly:
{"selected_code":"string","reason":"string","manual_review":true}
"""
    user_prompt = safe_json({
        "cause_text": cause_text,
        "role": role,
        "interval": interval,
        "patient_sex": sex_value,
        "patient_age": age_years,
        "candidate_icd_rows": slim,
    })
    out = call_claude_json(system_prompt, user_prompt, fallback=fallback, max_tokens=800)
    code = str(out.get("selected_code", "") or "").strip()
    valid_codes = {normalize_code(c.get("code_formatted", "")) for c in candidates}
    if code and normalize_code(code) not in valid_codes:
        return {"selected_code": "", "reason": "LLM selected a code outside retrieved candidates; rejected.", "manual_review": True}
    return {
        "selected_code": code,
        "reason": str(out.get("reason", "")),
        "manual_review": bool(out.get("manual_review", True)),
    }


# =============================================================================
# Structure and ICD Validation
# =============================================================================


def excel_text_flags(item: Dict[str, Any]) -> str:
    return normalize_text_basic(" ".join([
        str(item.get("classification", "")),
        str(item.get("acceptable_main", "")),
        str(item.get("note", "")),
        str(item.get("short_desc", "")),
        str(item.get("long_desc", "")),
    ]))


def is_excel_ill_defined(item: Dict[str, Any]) -> bool:
    txt = excel_text_flags(item)
    code = normalize_code(item.get("code_formatted", ""))
    cause = normalize_text_basic(item.get("cause", ""))
    terminal_terms = ["cardiac arrest", "respiratory failure", "multi-organ failure", "multi organ failure", "old age", "heart failure"]
    return (
        "ill-defined" in txt
        or "ill defined" in txt
        or "terminal" in txt
        or code.startswith("R")
        or any(t in cause for t in terminal_terms)
    )


def is_excel_unlikely_to_cause_death(item: Dict[str, Any]) -> bool:
    txt = excel_text_flags(item)
    cause = normalize_text_basic(item.get("cause", ""))
    trivial = ["mild dermatitis", "acne", "skin rash", "common cold", "ingrown toenail", "toenail"]
    return "unlikely" in txt or "trivial" in txt or "not likely" in txt or any(t in cause for t in trivial)


def has_multiple_causes_in_one_line(cause: str) -> bool:
    c = normalize_text_basic(cause)
    if not c:
        return False
    markers = [";", "/", " plus ", " along with "]
    if any(m in c for m in markers):
        return True
    if "," in c:
        return True
    if re.search(r"\b(and|with)\b", c):
        return True
    return False


def looks_like_narrative(cause: str) -> bool:
    c = normalize_text_basic(cause)
    if not c:
        return False
    bad = [
        "patient died", "passed away", "was admitted", "was brought", "found dead",
        "condition deteriorated", "complained of", "because of unknown", "unknown reason",
    ]
    if any(p in c for p in bad):
        return True
    return len(tokenize(c)) >= 16


def validate_interval_text(interval: str, line_label: str) -> List[Dict[str, Any]]:
    t = normalize_text_basic(interval)
    if not t:
        return [{"severity": "warning", "line": line_label, "type": "missing_interval", "message": "Add approximate interval or write unknown.", "blocking": False}]
    if t in {"unknown", "unk", "not known", "n/a", "na", "-", "—"}:
        return []
    if re.fullmatch(r"\d+(?:\.\d+)?", t):
        return [{"severity": "warning", "line": line_label, "type": "ambiguous_interval", "message": "Interval needs a time unit, e.g., 2 days.", "blocking": False}]
    units = r"(minute|minutes|min|hour|hours|hr|hrs|day|days|week|weeks|month|months|year|years|yr|yrs)"
    if re.search(r"\b\d+(?:\.\d+)?\s*" + units + r"\b", t):
        return []
    return [{"severity": "warning", "line": line_label, "type": "unclear_interval", "message": "Interval format is unclear. Use e.g., 2 days or unknown.", "blocking": False}]


def clean_cause_input(cause: str) -> str:
    c = str(cause or "").strip()
    c = re.sub(r"^\(?[a-dA-D]\)?[\.:\-\s]+", "", c).strip()
    c = re.sub(r"^(part\s*i\s*)?\(?[a-dA-D]\)?[\.:\-\s]+", "", c, flags=re.I).strip()
    c = re.sub(r"^(ii[-\s]*\d+|part\s*ii[-\s]*\d)[\.:\-\s]+", "", c, flags=re.I).strip()
    return re.sub(r"\s+", " ", c)


def pre_validate_structured_cod(part1: List[Dict[str, Any]], part2: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Structural validation. Multiple causes on one line is now a soft warning for SP2,
    not a hard block, following the doctor-facing workflow.
    """
    issues: List[Dict[str, Any]] = []
    cleaned_part1: List[Dict[str, Any]] = []
    cleaned_part2: List[Dict[str, Any]] = []

    for x in part1:
        cx = dict(x)
        cx["cause"] = clean_cause_input(cx.get("cause", ""))
        if cx["cause"]:
            cleaned_part1.append(cx)
    for x in part2:
        cx = dict(x)
        cx["cause"] = clean_cause_input(cx.get("cause", ""))
        if cx["cause"]:
            cleaned_part2.append(cx)

    if not cleaned_part1:
        issues.append({"severity": "error", "line": "Part I", "type": "empty_part_i", "message": "Part I cannot be empty. Enter immediate cause of death.", "blocking": True})

    filled = {str(x.get("line", "")).lower() for x in cleaned_part1}
    order = ["a", "b", "c", "d"]
    for i, letter in enumerate(order):
        later_filled = any(l in filled for l in order[i + 1:])
        if letter not in filled and later_filled:
            issues.append({"severity": "error", "line": f"Part I ({letter})", "type": "skipped_line", "message": "Do not skip Part I lines. Fill from (a) downward.", "blocking": True})

    all_lines = [(f"Part I ({x.get('line','')})", x) for x in cleaned_part1] + [(str(x.get("line", "Part II")), x) for x in cleaned_part2]
    for label, x in all_lines:
        cause = x.get("cause", "")
        if has_multiple_causes_in_one_line(cause):
            issues.append({
                "severity": "warning",
                "line": label,
                "type": "multiple_causes_soft_sp2",
                "message": "Multiple conditions appear on one line. One condition per line is recommended; SP2 can proceed with first-mentioned condition if not corrected.",
                "blocking": False,
            })
        if looks_like_narrative(cause):
            issues.append({"severity": "error", "line": label, "type": "narrative_text", "message": "Use a concise medical condition, not a narrative sentence.", "blocking": True})
        issues.extend(validate_interval_text(x.get("interval", ""), label))

    seen: Dict[str, str] = {}
    for x in cleaned_part1:
        key = normalize_cause_key(x.get("cause", ""))
        line = str(x.get("line", "")).lower()
        if key in seen:
            issues.append({"severity": "error", "line": f"Part I ({line})", "type": "duplicate_cause", "message": f"This repeats Part I ({seen[key]}). Each line should contain the next cause in the chain.", "blocking": True})
        elif key:
            seen[key] = line

    return {
        "part1_chain": cleaned_part1,
        "part2_conditions": cleaned_part2,
        "issues": issues,
        "blocking": any(i.get("blocking") for i in issues),
    }


def validate_icd_code(row_dict: Dict[str, Any], patient_age: int, patient_gender: str, role: str) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    code = str(row_dict.get("code_formatted", ""))
    if not code:
        issues.append({"severity": "error", "type": "missing_code", "message": "No ICD code selected.", "blocking": True})
        return issues

    if not is_gender_allowed(row_dict.get("gender_restriction", ""), patient_gender):
        issues.append({"severity": "error", "type": "gender_conflict", "message": f"{code} conflicts with patient sex.", "blocking": True})

    if role == "underlying" and acceptable_main_bool(row_dict.get("acceptable_main", "")) is False:
        issues.append({"severity": "error", "type": "not_acceptable_main", "message": f"{code} is not acceptable as the underlying cause based on the local mortality file.", "blocking": True})

    if normalize_code(code)[:1] in {"V", "W", "X", "Y"} and not query_indicates_external_cause(row_dict.get("cause", "")):
        issues.append({"severity": "warning", "type": "external_mismatch", "message": f"{code} is an external-cause code but the cause phrase does not indicate injury/external event.", "blocking": False})

    who = row_dict.get("who_verification") or {}
    if who.get("enabled") and who.get("status") == "not_verified":
        issues.append({"severity": "warning", "type": "who_not_verified", "message": f"{code} was not verified by WHO ICD API; local code retained for coder review.", "blocking": False})

    return issues


# =============================================================================
# Table A / Table B Rule Engines
# =============================================================================


def table_a_allows(taba_df: Optional[pd.DataFrame], effect_code: str, cause_code: str) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Table A sequence rule:
    - effect_code = upper-line condition / address
    - cause_code = lower-line condition searched underneath
    """
    if taba_df is None or taba_df.empty or not effect_code or not cause_code:
        return False, []
    effect = normalize_code(effect_code)
    cause = normalize_code(cause_code)
    hits = taba_df[
        (taba_df["anchor_start"] <= effect)
        & (taba_df["anchor_end"] >= effect)
        & (taba_df["cause_start"] <= cause)
        & (taba_df["cause_end"] >= cause)
    ].copy()
    return not hits.empty, hits.head(20).to_dict("records")


def build_table_a_trace_for_sp3(p1_coded: List[Dict[str, Any]], taba_df: Optional[pd.DataFrame]) -> Tuple[bool, List[Dict[str, Any]]]:
    trace: List[Dict[str, Any]] = []
    if len(p1_coded) <= 1:
        return True, trace
    bottom = p1_coded[-1]
    bottom_code = bottom.get("code_formatted", "")
    all_found = True
    for upper in p1_coded[:-1]:
        found, hits = table_a_allows(taba_df, upper.get("code_formatted", ""), bottom_code)
        all_found = all_found and found
        trace.append({
            "check_type": "SP3 bottom-explains-upper",
            "upper_line": upper.get("line", ""),
            "upper_effect": upper.get("cause", ""),
            "upper_code": upper.get("code_formatted", ""),
            "lower_line": bottom.get("line", ""),
            "lower_cause": bottom.get("cause", ""),
            "lower_code": bottom_code,
            "table_a_found": found,
            "matched_rows": hits[:3],
        })
    return all_found, trace


def build_table_a_trace_for_adjacent_path(p1_coded: List[Dict[str, Any]], taba_df: Optional[pd.DataFrame]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    SP4 simplified structured-certificate logic:
    Find the deepest contiguous valid sequence reaching line (a).
    For complex multi-condition same-line certificates, coder review remains required.
    """
    trace: List[Dict[str, Any]] = []
    valid_path: List[Dict[str, Any]] = []
    if not p1_coded:
        return valid_path, trace
    valid_path = [p1_coded[0]]
    for upper, lower in zip(p1_coded, p1_coded[1:]):
        found, hits = table_a_allows(taba_df, upper.get("code_formatted", ""), lower.get("code_formatted", ""))
        trace.append({
            "check_type": "SP4 adjacent-link-to-terminal",
            "upper_line": upper.get("line", ""),
            "upper_effect": upper.get("cause", ""),
            "upper_code": upper.get("code_formatted", ""),
            "lower_line": lower.get("line", ""),
            "lower_cause": lower.get("cause", ""),
            "lower_code": lower.get("code_formatted", ""),
            "table_a_found": found,
            "matched_rows": hits[:3],
        })
        if found:
            valid_path.append(lower)
        else:
            break
    return valid_path, trace


def table_b_find_ds(
    tabb_df: Optional[pd.DataFrame],
    address_code: str,
    candidate_codes: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    SP6 Table B direct-sequel lookup:
    current TSP = address. Search other certificate conditions as source/target DS under this address.
    """
    if tabb_df is None or tabb_df.empty or not address_code:
        return []
    address = normalize_code(address_code)
    hits = tabb_df[(tabb_df["anchor_norm"] == address) & (tabb_df["rule_type_norm"].isin(["DS", "DSC"]))].copy()
    if hits.empty:
        return []

    out: List[Dict[str, Any]] = []
    for cand in candidate_codes:
        ccode = normalize_code(cand.get("code_formatted", ""))
        if not ccode or ccode == address:
            continue
        for _, row in hits.iterrows():
            source_match = code_between(ccode, row.get("source_start_norm", ""), row.get("source_end_norm", ""))
            target = normalize_code(row.get("target_norm", ""))
            target_match = bool(target and ccode == target)
            if source_match or target_match:
                out.append({
                    "old_tsp_code": address_code,
                    "new_tsp_line": cand.get("line", ""),
                    "new_tsp_cause": cand.get("cause", ""),
                    "new_tsp_code": cand.get("code_formatted", ""),
                    "rule_type": row.get("rule_type", ""),
                    "table_b_row": row.to_dict(),
                    "reason": "Direct sequel / obvious cause found in Table B.",
                })
                break
    return out


def apply_sp6_table_b(
    base: Dict[str, Any],
    coded_causes: List[Dict[str, Any]],
    tabb_df: Optional[pd.DataFrame],
) -> Dict[str, Any]:
    trace: List[Dict[str, Any]] = []
    current_line = base.get("selected_line", "")
    current = find_coded_by_line(coded_causes, current_line)
    if not current:
        base["sp6_trace"] = trace
        base["sp6_changed"] = False
        return base

    visited = set()
    while current and current.get("code_formatted") and normalize_code(current.get("code_formatted")) not in visited:
        visited.add(normalize_code(current.get("code_formatted")))
        ds_hits = table_b_find_ds(tabb_df, current.get("code_formatted", ""), coded_causes)
        if not ds_hits:
            break
        chosen = ds_hits[0]
        trace.append(chosen)
        current_line = chosen.get("new_tsp_line", current_line)
        current = find_coded_by_line(coded_causes, current_line)

    if trace and current:
        base.update({
            "sp6_changed": True,
            "sp_rule_path": base.get("sp_rule_path", [base.get("sp_rule", "")]) + ["SP6"],
            "selected_line": current.get("line", ""),
            "selected_cause": current.get("cause", ""),
            "selected_code": current.get("code_formatted", ""),
            "warnings": base.get("warnings", []) + ["SP6 changed the tentative starting point based on Table B direct sequel logic."],
            "needs_manual_review": True,
        })
    else:
        base["sp6_changed"] = False
    base["sp6_trace"] = trace
    return base


def query_tabb(tabb_df: Optional[pd.DataFrame], anchor_code: str, input_code: str = "") -> List[Dict[str, Any]]:
    if tabb_df is None or tabb_df.empty or not anchor_code:
        return []
    a = normalize_code(anchor_code)
    inp = normalize_code(input_code)
    hits = tabb_df[tabb_df["anchor_norm"] == a].copy()
    if inp:
        direct = hits[
            hits.apply(lambda r: code_between(inp, r.get("source_start_norm", ""), r.get("source_end_norm", "")) or inp == normalize_code(r.get("target_norm", "")), axis=1)
        ]
        if not direct.empty:
            hits = direct
    return hits.head(20).to_dict("records")


def is_trivial_condition_by_tabb(tabb_df: Optional[pd.DataFrame], code: str) -> bool:
    hits = query_tabb(tabb_df, code)
    for h in hits:
        if str(h.get("rule_type", "")).upper() == "TRIV":
            return True
        if "triv" in normalize_text_basic(h.get("raw_body", "")):
            return True
    return False


# =============================================================================
# Coding Pipeline
# =============================================================================


def role_for_part1(index: int, total: int) -> str:
    if index == 0:
        return "immediate"
    if index == total - 1:
        return "underlying"
    return "antecedent"


def code_certificate_causes(
    part1: List[Dict[str, Any]],
    part2: List[Dict[str, Any]],
    patient: Dict[str, Any],
    icd_df: Optional[pd.DataFrame],
) -> List[Dict[str, Any]]:
    coded: List[Dict[str, Any]] = []
    p1_filled = [x for x in part1 if str(x.get("cause", "")).strip()]
    p2_filled = [x for x in part2 if str(x.get("cause", "")).strip()]

    for i, item in enumerate(p1_filled):
        role = role_for_part1(i, len(p1_filled))
        cause = item.get("cause", "")
        interval = item.get("interval", "")
        candidates = search_icd_candidates(icd_df, cause, patient.get("sex", ""), role, top_k=10)
        manual_key = f"{item.get('line','')}_override"
        if st.session_state.manual_override.get(manual_key):
            choice = {"selected_code": st.session_state.manual_override[manual_key], "reason": "Manual override selected by user.", "manual_review": True}
        else:
            choice = select_code_from_candidates_with_claude(
                cause_text=cause,
                role=role,
                interval=interval,
                sex_value=patient.get("sex", ""),
                age_years=int(patient.get("age_years", 0) or 0),
                candidates=candidates,
            )
        row = get_row_by_code(icd_df, choice.get("selected_code", ""))
        if row is not None:
            cd = row_to_dict(row)
            who = verify_code_with_who(cd["code_formatted"], release_id=st.session_state.get("who_release_id", DEFAULT_WHO_RELEASE_ID))
            status = "manual_review" if choice.get("manual_review") else "auto_selected"
            coded.append(asdict(CodedCause(
                line=item.get("line", chr(ord("a") + i)), section="Part I", role=role,
                cause=cause, interval=interval,
                code_formatted=cd["code_formatted"], code_norm=cd["code_norm"], parent_code=cd["parent_code"],
                short_desc=cd["short_desc"], long_desc=cd["long_desc"], acceptable_main=cd["acceptable_main"],
                gender_restriction=cd["gender_restriction"], classification=cd["classification"], note=cd["note"],
                selection_status=status, selection_notes=choice.get("reason", ""), candidates=candidates,
                who_verification=who,
            )))
        else:
            coded.append(asdict(CodedCause(
                line=item.get("line", chr(ord("a") + i)), section="Part I", role=role,
                cause=cause, interval=interval,
                selection_status="manual_review", selection_notes=choice.get("reason", "No valid ICD row selected."), candidates=candidates,
            )))

    for i, item in enumerate(p2_filled, start=1):
        cause = item.get("cause", "")
        interval = item.get("interval", "")
        candidates = search_icd_candidates(icd_df, cause, patient.get("sex", ""), "other", top_k=10)
        manual_key = f"{item.get('line','')}_override"
        if st.session_state.manual_override.get(manual_key):
            choice = {"selected_code": st.session_state.manual_override[manual_key], "reason": "Manual override selected by user.", "manual_review": True}
        else:
            choice = select_code_from_candidates_with_claude(
                cause_text=cause,
                role="other",
                interval=interval,
                sex_value=patient.get("sex", ""),
                age_years=int(patient.get("age_years", 0) or 0),
                candidates=candidates,
            )
        row = get_row_by_code(icd_df, choice.get("selected_code", ""))
        if row is not None:
            cd = row_to_dict(row)
            who = verify_code_with_who(cd["code_formatted"], release_id=st.session_state.get("who_release_id", DEFAULT_WHO_RELEASE_ID))
            coded.append(asdict(CodedCause(
                line=item.get("line", f"II-{i}"), section="Part II", role="other",
                cause=cause, interval=interval,
                code_formatted=cd["code_formatted"], code_norm=cd["code_norm"], parent_code=cd["parent_code"],
                short_desc=cd["short_desc"], long_desc=cd["long_desc"], acceptable_main=cd["acceptable_main"],
                gender_restriction=cd["gender_restriction"], classification=cd["classification"], note=cd["note"],
                selection_status="manual_review" if choice.get("manual_review") else "auto_selected",
                selection_notes=choice.get("reason", ""), candidates=candidates, who_verification=who,
            )))
        else:
            coded.append(asdict(CodedCause(
                line=item.get("line", f"II-{i}"), section="Part II", role="other",
                cause=cause, interval=interval, selection_status="manual_review",
                selection_notes=choice.get("reason", "No valid ICD row selected."), candidates=candidates,
            )))
    return coded


# =============================================================================
# SP1-SP8 Engine
# =============================================================================


def find_coded_by_line(coded: List[Dict[str, Any]], line: str) -> Optional[Dict[str, Any]]:
    for c in coded:
        if str(c.get("line", "")) == str(line):
            return c
    return None


def first_part_i_coded(coded: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    order = {"a": 0, "b": 1, "c": 2, "d": 3}
    p1 = [c for c in coded if c.get("section") == "Part I" and c.get("cause")]
    return sorted(p1, key=lambda x: order.get(str(x.get("line", "")), 99))


def apply_sp_rules(
    part1: List[Dict[str, Any]],
    part2: List[Dict[str, Any]],
    coded_causes: List[Dict[str, Any]],
    taba_df: Optional[pd.DataFrame],
    tabb_df: Optional[pd.DataFrame],
    pre_issues: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    warnings: List[str] = []
    pre_issues = pre_issues or []
    if any(i.get("type") == "multiple_causes_soft_sp2" for i in pre_issues):
        warnings.append("Multiple conditions detected on one line. Prefer separating them before final certification.")

    coded_nonempty = [c for c in coded_causes if c.get("cause")]
    p1 = first_part_i_coded(coded_causes)

    if not coded_nonempty:
        return {
            "sp_rule": "REVIEW", "sp_rule_path": ["REVIEW"], "selected_line": "", "selected_cause": "", "selected_code": "",
            "warnings": ["No condition entered."], "needs_manual_review": True, "explanation": "No cause of death is available.",
            "table_a_sp3_trace": [], "table_a_sp4_trace": [], "sp6_trace": [],
        }

    # SP1: one condition anywhere.
    if len(coded_nonempty) == 1:
        x = coded_nonempty[0]
        base = {
            "sp_rule": "SP1",
            "sp_rule_path": ["SP1"],
            "selected_line": x.get("line", ""),
            "selected_cause": x.get("cause", ""),
            "selected_code": x.get("code_formatted", ""),
            "warnings": warnings,
            "needs_manual_review": False,
            "explanation": SP_RULES["SP1"],
            "table_a_sp3_trace": [],
            "table_a_sp4_trace": [],
        }
    # SP2: only one used Part I line; no Table A needed.
    elif len(p1) == 1:
        x = p1[0]
        base = {
            "sp_rule": "SP2",
            "sp_rule_path": ["SP2"],
            "selected_line": x.get("line", ""),
            "selected_cause": x.get("cause", ""),
            "selected_code": x.get("code_formatted", ""),
            "warnings": warnings,
            "needs_manual_review": bool(warnings),
            "explanation": SP_RULES["SP2"],
            "table_a_sp3_trace": [],
            "table_a_sp4_trace": [],
        }
    elif len(p1) > 1:
        sp3_ok, sp3_trace = build_table_a_trace_for_sp3(p1, taba_df)
        if sp3_ok:
            x = p1[-1]
            base = {
                "sp_rule": "SP3",
                "sp_rule_path": ["SP3"],
                "selected_line": x.get("line", ""),
                "selected_cause": x.get("cause", ""),
                "selected_code": x.get("code_formatted", ""),
                "warnings": warnings,
                "needs_manual_review": False,
                "explanation": SP_RULES["SP3"],
                "table_a_sp3_trace": sp3_trace,
                "table_a_sp4_trace": [],
            }
        else:
            valid_path, sp4_trace = build_table_a_trace_for_adjacent_path(p1, taba_df)
            if len(valid_path) > 1:
                x = valid_path[-1]
                base = {
                    "sp_rule": "SP4",
                    "sp_rule_path": ["SP4"],
                    "selected_line": x.get("line", ""),
                    "selected_cause": x.get("cause", ""),
                    "selected_code": x.get("code_formatted", ""),
                    "warnings": warnings + ["SP3 failed; SP4 selected the deepest valid sequence reaching the terminal condition."],
                    "needs_manual_review": True,
                    "explanation": SP_RULES["SP4"],
                    "table_a_sp3_trace": sp3_trace,
                    "table_a_sp4_trace": sp4_trace,
                }
            else:
                x = p1[0]
                base = {
                    "sp_rule": "SP5",
                    "sp_rule_path": ["SP5"],
                    "selected_line": x.get("line", ""),
                    "selected_cause": x.get("cause", ""),
                    "selected_code": x.get("code_formatted", ""),
                    "warnings": warnings + ["No acceptable Table A sequence reaches the terminal condition."],
                    "needs_manual_review": True,
                    "explanation": SP_RULES["SP5"],
                    "table_a_sp3_trace": sp3_trace,
                    "table_a_sp4_trace": sp4_trace,
                }
    else:
        x = coded_nonempty[0]
        base = {
            "sp_rule": "SP5",
            "sp_rule_path": ["SP5"],
            "selected_line": x.get("line", ""),
            "selected_cause": x.get("cause", ""),
            "selected_code": x.get("code_formatted", ""),
            "warnings": warnings + ["Only Part II conditions are present."],
            "needs_manual_review": True,
            "explanation": SP_RULES["SP5"],
            "table_a_sp3_trace": [],
            "table_a_sp4_trace": [],
        }

    # SP6: Table B direct sequel / obvious cause check.
    base = apply_sp6_table_b(base, coded_causes, tabb_df)

    # SP7/SP8: quality checks after TSP is chosen.
    selected_coded = find_coded_by_line(coded_causes, base.get("selected_line", ""))
    base["sp7_failed"] = False
    base["sp8_failed"] = False
    if selected_coded:
        if is_excel_ill_defined(selected_coded):
            base["sp7_failed"] = True
            base["needs_manual_review"] = True
            base["sp_rule_path"] = base.get("sp_rule_path", []) + ["SP7"]
            base["warnings"] = base.get("warnings", []) + [
                "SP7: selected starting point appears ill-defined or terminal; query certifier for the disease that led to it."
            ]
        if is_excel_unlikely_to_cause_death(selected_coded) or is_trivial_condition_by_tabb(tabb_df, selected_coded.get("code_formatted", "")):
            base["sp8_failed"] = True
            base["needs_manual_review"] = True
            base["sp_rule_path"] = base.get("sp_rule_path", []) + ["SP8"]
            base["warnings"] = base.get("warnings", []) + [
                "SP8: selected starting point appears trivial/unlikely to cause death; review or query certifier."
            ]

    base["tabb_hits"] = query_tabb(tabb_df, base.get("selected_code", "")) if base.get("selected_code") else []
    return base


# =============================================================================
# Final Validation, Output, Audit
# =============================================================================


def final_validation(
    coded_causes: List[Dict[str, Any]],
    sp_result: Dict[str, Any],
    pre_issues: List[Dict[str, Any]],
    patient: Dict[str, Any],
) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = list(pre_issues)
    for c in coded_causes:
        role = "underlying" if c.get("line") == sp_result.get("selected_line") else c.get("role", "")
        icd_issues = validate_icd_code(c, int(patient.get("age_years", 0) or 0), patient.get("sex", ""), role)
        for i in icd_issues:
            i["line"] = c.get("line", "")
            issues.append(i)
        if c.get("selection_status") == "manual_review":
            issues.append({"severity": "warning", "line": c.get("line", ""), "type": "manual_review", "message": f"{c.get('cause')} requires coder review.", "blocking": False})

    if sp_result.get("needs_manual_review"):
        issues.append({"severity": "warning", "line": sp_result.get("selected_line", ""), "type": "sp_review", "message": "SP-rule result requires human/coder review.", "blocking": False})

    if sp_result.get("sp7_failed"):
        issues.append({"severity": "error", "line": sp_result.get("selected_line", ""), "type": "sp7_ill_defined", "message": "SP7 failed: selected UCOD is ill-defined/terminal. Query certifier.", "blocking": True})

    if sp_result.get("sp8_failed"):
        issues.append({"severity": "error", "line": sp_result.get("selected_line", ""), "type": "sp8_unlikely", "message": "SP8 failed: selected UCOD is trivial/unlikely. Query certifier.", "blocking": True})

    if not sp_result.get("selected_code"):
        issues.append({"severity": "error", "line": sp_result.get("selected_line", ""), "type": "missing_ucod_code", "message": "Suggested UCOD has no validated ICD code.", "blocking": True})

    has_blocking = any(i.get("blocking") for i in issues)
    warning_count = sum(1 for i in issues if i.get("severity") == "warning")
    if has_blocking:
        confidence = "Low"
        review = "Required"
    elif sp_result.get("needs_manual_review") or warning_count >= 3:
        confidence = "Medium"
        review = "Required"
    elif warning_count:
        confidence = "Medium"
        review = "Recommended"
    else:
        confidence = "High"
        review = "Optional"

    return {
        "issues": issues,
        "blocking": has_blocking,
        "confidence": confidence,
        "review_status": review,
        "acceptable_ucod": not has_blocking,
    }


def build_final_output(coded_causes: List[Dict[str, Any]], sp_result: Dict[str, Any], validation: Dict[str, Any]) -> Dict[str, Any]:
    selected = find_coded_by_line(coded_causes, sp_result.get("selected_line", "")) or {}
    part1_sequence = [c.get("cause", "") for c in coded_causes if c.get("section") == "Part I"]
    return {
        "starting_point": {
            "line": sp_result.get("selected_line", ""),
            "condition": sp_result.get("selected_cause", ""),
            "code": selected.get("code_formatted", ""),
        },
        "ucod": {
            "condition": sp_result.get("selected_cause", ""),
            "code": selected.get("code_formatted", ""),
            "code_norm": selected.get("code_norm", normalize_code(selected.get("code_formatted", ""))),
            "parent_code": selected.get("parent_code", parent_code(selected.get("code_formatted", ""))),
            "description": selected.get("short_desc", "") or selected.get("long_desc", ""),
        },
        "applied_rule": sp_result.get("sp_rule", "REVIEW"),
        "rule_path": sp_result.get("sp_rule_path", [sp_result.get("sp_rule", "REVIEW")]),
        "sequence": list(reversed(part1_sequence)),
        "validation": {
            "acceptable_ucod": validation.get("acceptable_ucod", False),
            "blocking": validation.get("blocking", False),
            "issues": validation.get("issues", []),
        },
        "confidence": validation.get("confidence", "Low"),
        "human_review_required": validation.get("review_status") == "Required",
        "review_status": validation.get("review_status", "Required"),
        "explanation": sp_result.get("explanation", ""),
        "table_a_sp3_trace": sp_result.get("table_a_sp3_trace", []),
        "table_a_sp4_trace": sp_result.get("table_a_sp4_trace", []),
        "sp6_trace": sp_result.get("sp6_trace", []),
        "tabb_hits": sp_result.get("tabb_hits", []),
    }


def init_audit_db() -> None:
    ensure_dirs()
    con = sqlite3.connect(AUDIT_DB)
    cur = con.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            user_role TEXT,
            patient_id TEXT,
            doctor_name TEXT,
            final_ucod_code TEXT,
            applied_rule TEXT,
            rule_path TEXT,
            confidence TEXT,
            review_status TEXT,
            override_reason TEXT,
            payload_json TEXT NOT NULL
        )
        """
    )
    con.commit()
    con.close()


def save_audit(payload: Dict[str, Any], override_reason: str = "") -> int:
    init_audit_db()
    con = sqlite3.connect(AUDIT_DB)
    cur = con.cursor()
    patient = payload.get("patient", {})
    final = payload.get("final_output", {})
    cur.execute(
        """
        INSERT INTO audit_log
        (timestamp,user_role,patient_id,doctor_name,final_ucod_code,applied_rule,rule_path,confidence,review_status,override_reason,payload_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            dt.datetime.now().isoformat(timespec="seconds"),
            st.session_state.get("role", ""),
            str(patient.get("patient_id", "")),
            str(payload.get("hospital", {}).get("doctor_name", "")),
            str(final.get("ucod", {}).get("code", "")),
            str(final.get("applied_rule", "")),
            " → ".join(final.get("rule_path", [])),
            str(final.get("confidence", "")),
            str(final.get("review_status", "")),
            override_reason,
            safe_json(payload),
        ),
    )
    con.commit()
    row_id = int(cur.lastrowid)
    con.close()
    return row_id


def load_audit_log(limit: int = 200) -> pd.DataFrame:
    init_audit_db()
    con = sqlite3.connect(AUDIT_DB)
    df = pd.read_sql_query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", con, params=(limit,))
    con.close()
    return df


# =============================================================================
# PDF Generation
# =============================================================================


def generate_certificate_pdf(payload: Dict[str, Any]) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    except Exception as e:
        raise RuntimeError("reportlab is required for PDF generation. Install: pip install reportlab") from e

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=16 * mm, leftMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("title", parent=styles["Title"], textColor=colors.HexColor("#006940"), fontSize=16)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=colors.HexColor("#006940"), fontSize=12)
    normal = styles["Normal"]
    story = []
    final = payload.get("final_output", {})
    patient = payload.get("patient", {})
    hospital = payload.get("hospital", {})

    story.append(Paragraph("Saudi MOH Electronic Death Certificate", title))
    story.append(Paragraph(f"Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}", normal))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Patient / Hospital", h2))
    info = [
        ["Patient ID", patient.get("patient_id", ""), "Age", patient.get("age_years", "")],
        ["Sex", patient.get("sex", ""), "Death Type", patient.get("death_type", "")],
        ["Hospital", hospital.get("hospital_name", ""), "City", hospital.get("hospital_city", "")],
        ["Physician", hospital.get("doctor_name", ""), "Role", st.session_state.get("role", "")],
    ]
    table = Table(info, colWidths=[30 * mm, 55 * mm, 30 * mm, 55 * mm])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef6f1"))]))
    story.append(table)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Final UCOD", h2))
    story.append(Paragraph(f"<b>{escape(final.get('ucod', {}).get('condition', ''))}</b> — {escape(final.get('ucod', {}).get('code', ''))}", normal))
    story.append(Paragraph(f"Rule Path: {escape(' → '.join(final.get('rule_path', [])))}", normal))
    story.append(Paragraph(f"Confidence: {escape(final.get('confidence', ''))} | Review: {escape(final.get('review_status', ''))}", normal))
    story.append(Spacer(1, 8))

    coded = payload.get("coded_causes", [])
    rows = [["Line", "Cause", "Interval", "ICD", "Description"]]
    for c in coded:
        rows.append([c.get("line", ""), c.get("cause", ""), c.get("interval", ""), c.get("code_formatted", ""), c.get("short_desc", "")])
    table = Table(rows, colWidths=[18 * mm, 48 * mm, 25 * mm, 22 * mm, 65 * mm])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f5ee")), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(Paragraph("Coded Causes", h2))
    story.append(table)
    story.append(Spacer(1, 8))
    story.append(Paragraph("Explanation", h2))
    story.append(Paragraph(escape(final.get("explanation", "")), normal))
    doc.build(story)
    return buf.getvalue()


# =============================================================================
# Main Processing
# =============================================================================


def run_full_pipeline() -> Dict[str, Any]:
    patient = st.session_state.patient
    hospital = st.session_state.hospital
    raw_part1 = st.session_state.part1
    raw_part2 = st.session_state.part2

    normalized = normalize_causes_with_claude(raw_part1, raw_part2, patient)
    part1 = normalized.get("part1_chain", raw_part1)
    part2 = normalized.get("part2_conditions", raw_part2)
    pre = pre_validate_structured_cod(part1, part2)

    # Code even if pre-validation has blocking errors, so the UI can preview what failed.
    coded = code_certificate_causes(pre["part1_chain"], pre["part2_conditions"], patient, st.session_state.icd_df)

    sp_result = apply_sp_rules(
        pre["part1_chain"],
        pre["part2_conditions"],
        coded,
        st.session_state.taba_df,
        st.session_state.tabb_df,
        pre_issues=pre.get("issues", []),
    )
    validation = final_validation(coded, sp_result, pre.get("issues", []), patient)
    final = build_final_output(coded, sp_result, validation)

    payload = {
        "patient": patient,
        "hospital": hospital,
        "raw_part1": raw_part1,
        "raw_part2": raw_part2,
        "normalized": normalized,
        "pre_validation": pre,
        "coded_causes": coded,
        "sp_result": sp_result,
        "validation": validation,
        "final_output": final,
        "system_config": {
            "who_api_enabled": st.session_state.get("use_who_api", False),
            "who_release_id": st.session_state.get("who_release_id", DEFAULT_WHO_RELEASE_ID),
            "icd_rows": 0 if st.session_state.icd_df is None else len(st.session_state.icd_df),
            "taba_rows": 0 if st.session_state.taba_df is None else len(st.session_state.taba_df),
            "tabb_rows": 0 if st.session_state.tabb_df is None else len(st.session_state.tabb_df),
        },
    }
    st.session_state.last_result = payload
    return payload


# =============================================================================
# UI Components
# =============================================================================


def header() -> None:
    st.markdown(
        f"""
        <div class="moh-header">
            <h1>{APP_TITLE}</h1>
            <p>{APP_SUBTITLE}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_card(title: str, body: str, kind: str = "blue") -> None:
    cls = {"green": "green-card", "yellow": "yellow-card", "red": "red-card", "blue": "blue-card"}.get(kind, "blue-card")
    st.markdown(f"<div class='card {cls}'><h3>{escape(title)}</h3><div>{body}</div></div>", unsafe_allow_html=True)


def render_issue_list(issues: List[Dict[str, Any]]) -> None:
    if not issues:
        st.success("No validation issues detected.")
        return
    for issue in issues:
        msg = f"{issue.get('line','')}: {issue.get('message','')}"
        if issue.get("severity") == "error":
            st.error(msg)
        else:
            st.warning(msg)


def render_right_panel(preview_payload: Optional[Dict[str, Any]]) -> None:
    st.subheader("Live Rule Assistant")
    if not preview_payload:
        status_card("Validation Summary", "Enter certificate data, then run coding and rule check.", "blue")
        status_card("Suggested UCOD", "No UCOD suggested yet.", "blue")
        status_card("Rule Path", "Pending", "blue")
        return

    final = preview_payload.get("final_output", {})
    validation = preview_payload.get("validation", {})
    issues = validation.get("issues", [])
    err_count = sum(1 for i in issues if i.get("severity") == "error")
    warn_count = sum(1 for i in issues if i.get("severity") == "warning")
    summary_kind = "red" if err_count else ("yellow" if warn_count else "green")
    summary = f"<span class='metric-pill'>Errors: {err_count}</span><span class='metric-pill'>Warnings: {warn_count}</span><br>Applied rule: <b>{escape(final.get('applied_rule',''))}</b>"
    status_card("Validation Summary", summary, summary_kind)

    ucod = final.get("ucod", {})
    ucod_body = f"<b>{escape(ucod.get('condition',''))}</b><br>ICD-10: <b>{escape(ucod.get('code',''))}</b><br><span class='small-muted'>{escape(ucod.get('description',''))}</span>"
    status_card("Suggested UCOD", ucod_body, "green" if ucod.get("code") and not validation.get("blocking") else "yellow")

    path = " → ".join(final.get("rule_path", [])) or "Pending"
    conf = final.get("confidence", "Low")
    review = final.get("review_status", "Required")
    kind = "green" if conf == "High" else ("yellow" if conf == "Medium" else "red")
    status_card("Rule Path / Review", f"{escape(path)}<br>Confidence: <b>{escape(conf)}</b><br>Coder review: <b>{escape(review)}</b>", kind)


# =============================================================================
# Pages
# =============================================================================


def page_login() -> None:
    header()
    st.subheader("Login / Role")
    c1, c2 = st.columns([1, 1])
    with c1:
        st.session_state.role = st.selectbox("Role", ["Doctor", "Medical coder", "Admin"], index=["Doctor", "Medical coder", "Admin"].index(st.session_state.role))
        name = st.text_input("Name", value=st.session_state.hospital.get("doctor_name", ""))
        if st.button("Continue", type="primary"):
            st.session_state.logged_in = True
            st.session_state.hospital["doctor_name"] = name
            st.success(f"Logged in as {st.session_state.role}.")
    with c2:
        status_card("Source of Truth", "Normal disease names are searched in the local ICD file. WHO ICD API verifies selected codes only. Table A/B rules decide SP logic.", "green")
        status_card("Safety Policy", "LLM can normalize wording and choose only from retrieved candidates. It cannot decide SP3-SP6 or invent codes.", "yellow")


def page_settings() -> None:
    header()
    st.subheader("System Settings / Data Sources")
    st.caption("Load ICD Excel/CSV, Table A CSV, and Table B CSV. Optional WHO API credentials can be set through Streamlit secrets or environment variables.")

    with st.expander("Auto-load local files from current folder", expanded=False):
        folder = st.text_input("Folder path", value=str(Path.cwd()))
        if st.button("Auto-load files"):
            candidates = {
                "icd": ["ICD10_Enriched_Final.xlsx", "ICD10_Enriched_Final(6).xlsx"],
                "taba": ["taba_rules.csv", "taba_rules(1).csv"],
                "tabb": ["tabb_rules.csv", "tabb_rules(3).csv"],
            }
            loaded = []
            for kind, names in candidates.items():
                for name in names:
                    path = Path(folder) / name
                    if path.exists():
                        raw = read_local_table(str(path))
                        if kind == "icd":
                            st.session_state.icd_df = normalize_icd_df(raw)
                        elif kind == "taba":
                            st.session_state.taba_df = normalize_taba_df(raw)
                        elif kind == "tabb":
                            st.session_state.tabb_df = normalize_tabb_df(raw)
                        loaded.append(str(path))
                        break
            st.session_state.data_ready = st.session_state.icd_df is not None and st.session_state.taba_df is not None and st.session_state.tabb_df is not None
            st.success("Loaded: " + ", ".join(loaded) if loaded else "No matching files found.")

    c1, c2, c3 = st.columns(3)
    with c1:
        icd_upload = st.file_uploader("Upload ICD Excel/CSV", type=["xlsx", "xls", "csv"], key="icd_upload")
        if icd_upload is not None:
            raw = read_uploaded_table(icd_upload.getvalue(), icd_upload.name)
            st.session_state.icd_df = normalize_icd_df(raw)
            st.success(f"Loaded ICD rows: {len(st.session_state.icd_df):,}")
    with c2:
        taba_upload = st.file_uploader("Upload Table A rules CSV", type=["csv"], key="taba_upload")
        if taba_upload is not None:
            raw_taba = read_uploaded_table(taba_upload.getvalue(), taba_upload.name)
            st.session_state.taba_df = normalize_taba_df(raw_taba)
            st.success(f"Loaded Table A rows: {len(st.session_state.taba_df):,}")
    with c3:
        tabb_upload = st.file_uploader("Upload Table B rules CSV", type=["csv"], key="tabb_upload")
        if tabb_upload is not None:
            raw_tabb = read_uploaded_table(tabb_upload.getvalue(), tabb_upload.name)
            st.session_state.tabb_df = normalize_tabb_df(raw_tabb)
            st.success(f"Loaded Table B rows: {len(st.session_state.tabb_df):,}")

    st.divider()
    st.session_state.use_who_api = st.checkbox("Use WHO ICD API verification when possible", value=st.session_state.get("use_who_api", False))
    st.session_state.who_release_id = st.text_input("WHO ICD-10 release ID", value=st.session_state.get("who_release_id", DEFAULT_WHO_RELEASE_ID))

    who_client = get_who_client()
    st.write({
        "ICD loaded": st.session_state.icd_df is not None,
        "ICD rows": 0 if st.session_state.icd_df is None else len(st.session_state.icd_df),
        "Table A loaded": st.session_state.taba_df is not None,
        "Table A rows": 0 if st.session_state.taba_df is None else len(st.session_state.taba_df),
        "Table B loaded": st.session_state.tabb_df is not None,
        "Table B rows": 0 if st.session_state.tabb_df is None else len(st.session_state.tabb_df),
        "Anthropic key available": bool(get_anthropic_api_key()),
        "WHO credentials available": who_client is not None,
    })

    if st.session_state.icd_df is not None:
        with st.expander("Preview ICD file"):
            st.dataframe(st.session_state.icd_df.head(20), use_container_width=True)
    if st.session_state.taba_df is not None:
        with st.expander("Preview Table A"):
            st.dataframe(st.session_state.taba_df.head(20), use_container_width=True)
    if st.session_state.tabb_df is not None:
        with st.expander("Preview Table B"):
            st.dataframe(st.session_state.tabb_df.head(20), use_container_width=True)


def page_certificate_form() -> None:
    header()
    st.subheader("Cause of Death Entry")
    if st.session_state.icd_df is None:
        st.info("Upload ICD data in System Settings first. You can still fill the form, but ICD suggestions will be unavailable.")

    left, right = st.columns([1.45, 1], gap="large")
    with left:
        with st.expander("Hospital Information", expanded=True):
            c1, c2, c3 = st.columns(3)
            st.session_state.hospital["hospital_name"] = c1.text_input("Hospital Name", value=st.session_state.hospital.get("hospital_name", "King Fahad Specialist Hospital"))
            st.session_state.hospital["hospital_city"] = c2.text_input("City", value=st.session_state.hospital.get("hospital_city", "Riyadh"))
            st.session_state.hospital["doctor_name"] = c3.text_input("Certifying Physician", value=st.session_state.hospital.get("doctor_name", ""))

        with st.expander("Patient Information", expanded=True):
            c1, c2, c3, c4 = st.columns(4)
            st.session_state.patient["patient_id"] = c1.text_input("Patient ID", value=st.session_state.patient.get("patient_id", ""))
            st.session_state.patient["age_years"] = c2.number_input("Age", min_value=0, max_value=130, value=int(st.session_state.patient.get("age_years", 60) or 60))
            st.session_state.patient["sex"] = c3.selectbox("Sex", ["Unknown", "Male", "Female"], index=["Unknown", "Male", "Female"].index(st.session_state.patient.get("sex", "Unknown")))
            st.session_state.patient["death_type"] = c4.selectbox("Death Type", ["Natural", "Accident", "Suicide", "Homicide", "Pending investigation", "Unknown"], index=0)

        st.markdown("### Part I — Direct causal sequence")
        labels = {
            "a": "Immediate cause",
            "b": "Due to / as a consequence of",
            "c": "Due to / as a consequence of",
            "d": "Due to / underlying origin",
        }
        for i, item in enumerate(st.session_state.part1):
            with st.container(border=True):
                line = item["line"]
                st.markdown(f"**Part I ({line}) — {labels[line]}**")
                cols = st.columns([0.68, 0.22, 0.10])
                st.session_state.part1[i]["cause"] = cols[0].text_input("Cause", value=item.get("cause", ""), key=f"p1_cause_{line}")
                st.session_state.part1[i]["interval"] = cols[1].text_input("Interval", value=item.get("interval", ""), key=f"p1_interval_{line}", placeholder="e.g., 2 days")
                cols[2].markdown("&nbsp;")
                if st.session_state.part1[i]["cause"] and st.session_state.icd_df is not None:
                    cands = search_icd_candidates(st.session_state.icd_df, st.session_state.part1[i]["cause"], st.session_state.patient.get("sex", ""), "underlying" if line == "d" else "antecedent", top_k=5)
                    if cands:
                        st.caption("Top ICD candidates: " + " | ".join([f"{c['code_formatted']} {c['short_desc']}" for c in cands[:3]]))

        st.markdown("### Part II — Other significant conditions")
        for i, item in enumerate(st.session_state.part2):
            with st.container(border=True):
                line = item["line"]
                cols = st.columns([0.68, 0.32])
                st.session_state.part2[i]["cause"] = cols[0].text_input(f"{line} cause", value=item.get("cause", ""), key=f"p2_cause_{line}")
                st.session_state.part2[i]["interval"] = cols[1].text_input("Interval", value=item.get("interval", ""), key=f"p2_interval_{line}", placeholder="e.g., 10 years")
                if st.session_state.part2[i]["cause"] and st.session_state.icd_df is not None:
                    cands = search_icd_candidates(st.session_state.icd_df, st.session_state.part2[i]["cause"], st.session_state.patient.get("sex", ""), "other", top_k=5)
                    if cands:
                        st.caption("Top ICD candidates: " + " | ".join([f"{c['code_formatted']} {c['short_desc']}" for c in cands[:3]]))

        c1, c2 = st.columns([0.25, 0.75])
        with c1:
            if st.button("Run Coding & Rule Check", type="primary", use_container_width=True):
                if st.session_state.icd_df is None:
                    st.error("Please upload ICD data first.")
                elif st.session_state.taba_df is None:
                    st.error("Please upload Table A data first.")
                elif st.session_state.tabb_df is None:
                    st.error("Please upload Table B data first.")
                else:
                    payload = run_full_pipeline()
                    st.success("Coding and rule check completed.")
        with c2:
            st.caption("The system searches local ICD terms first, then optionally verifies selected codes with WHO ICD API, then applies Table A/B rule logic.")

    with right:
        render_right_panel(st.session_state.last_result)


def dataframe_from_trace(trace: List[Dict[str, Any]]) -> pd.DataFrame:
    if not trace:
        return pd.DataFrame()
    rows = []
    for t in trace:
        rows.append({
            "Check": t.get("check_type", ""),
            "Upper line": t.get("upper_line", ""),
            "Upper/effect": f"{t.get('upper_effect','')} ({t.get('upper_code','')})",
            "Lower line": t.get("lower_line", ""),
            "Lower/cause": f"{t.get('lower_cause','')} ({t.get('lower_code','')})",
            "Table A found": t.get("table_a_found", False),
        })
    return pd.DataFrame(rows)


def page_review_coding() -> None:
    header()
    st.subheader("Review & Coding — Rule Trace")
    payload = st.session_state.last_result
    if not payload:
        st.info("Run Coding & Rule Check from the Cause of Death page first.")
        return

    final = payload.get("final_output", {})
    validation = payload.get("validation", {})
    ucod = final.get("ucod", {})

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        status_card("Suggested UCOD", f"<b>{escape(ucod.get('condition',''))}</b><br>{escape(ucod.get('code',''))}", "green" if not validation.get("blocking") else "red")
    with c2:
        status_card("Rule Path", escape(" → ".join(final.get("rule_path", []))), "blue")
    with c3:
        kind = "green" if final.get("confidence") == "High" else ("yellow" if final.get("confidence") == "Medium" else "red")
        status_card("Confidence", escape(final.get("confidence", "Low")), kind)
    with c4:
        kind = "green" if final.get("review_status") == "Optional" else "yellow"
        status_card("Review Status", escape(final.get("review_status", "Required")), kind)

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "ICD Coding",
        "Table A Sequence",
        "Table B Obvious Cause",
        "Quality Check",
        "Audit Trace",
    ])

    with tab1:
        coded = payload.get("coded_causes", [])
        rows = []
        for c in coded:
            who = c.get("who_verification") or {}
            rows.append({
                "Line": c.get("line", ""),
                "Section": c.get("section", ""),
                "Cause": c.get("cause", ""),
                "Selected ICD": c.get("code_formatted", ""),
                "Internal code": c.get("code_norm", ""),
                "Parent": c.get("parent_code", ""),
                "Description": c.get("short_desc", ""),
                "Status": c.get("selection_status", ""),
                "WHO API": who.get("status", "not_used"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

        with st.expander("Manual code override"):
            st.caption("Choose a code from the top retrieved candidates, then rerun Coding & Rule Check.")
            for c in coded:
                cands = c.get("candidates") or []
                if not cands:
                    continue
                options = [""] + [cand.get("code_formatted", "") for cand in cands]
                labels = {cand.get("code_formatted", ""): f"{cand.get('code_formatted','')} — {cand.get('short_desc','')}" for cand in cands}
                key = f"{c.get('line','')}_override"
                selected = st.selectbox(
                    f"Override line {c.get('line','')} ({c.get('cause','')})",
                    options=options,
                    format_func=lambda x, labels=labels: "No override" if x == "" else labels.get(x, x),
                    key=f"override_select_{key}",
                )
                st.session_state.manual_override[key] = selected
            if st.button("Rerun with overrides"):
                run_full_pipeline()
                st.rerun()

    with tab2:
        sp = payload.get("sp_result", {})
        st.markdown("#### SP3 — Bottom line explains all above")
        df_sp3 = dataframe_from_trace(sp.get("table_a_sp3_trace", []))
        if df_sp3.empty:
            st.info("SP3 Table A trace is not applicable for this certificate.")
        else:
            st.dataframe(df_sp3, use_container_width=True)
            with st.expander("Show raw SP3 matched Table A rows"):
                st.json(sp.get("table_a_sp3_trace", []))

        st.markdown("#### SP4 — Valid path reaching terminal condition")
        df_sp4 = dataframe_from_trace(sp.get("table_a_sp4_trace", []))
        if df_sp4.empty:
            st.info("SP4 Table A trace is not applicable or was not needed.")
        else:
            st.dataframe(df_sp4, use_container_width=True)
            with st.expander("Show raw SP4 matched Table A rows"):
                st.json(sp.get("table_a_sp4_trace", []))

    with tab3:
        sp6 = payload.get("sp_result", {}).get("sp6_trace", [])
        if not sp6:
            st.success("No Table B direct-sequel change found. TSP unchanged after SP6.")
        else:
            rows = []
            for t in sp6:
                rows.append({
                    "Old TSP": t.get("old_tsp_code", ""),
                    "New TSP line": t.get("new_tsp_line", ""),
                    "New TSP cause": t.get("new_tsp_cause", ""),
                    "New TSP code": t.get("new_tsp_code", ""),
                    "Rule type": t.get("rule_type", ""),
                    "Reason": t.get("reason", ""),
                })
            st.warning("SP6 changed the tentative starting point.")
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
            with st.expander("Show raw Table B rows"):
                st.json(sp6)

    with tab4:
        st.markdown("#### Validation issues")
        render_issue_list(validation.get("issues", []))
        sp = payload.get("sp_result", {})
        checks = pd.DataFrame([
            {"Rule": "SP7", "Check": "Ill-defined / terminal starting point", "Failed": bool(sp.get("sp7_failed"))},
            {"Rule": "SP8", "Check": "Trivial / unlikely starting point", "Failed": bool(sp.get("sp8_failed"))},
            {"Rule": "Acceptability", "Check": "Acceptable as UCOD", "Failed": any(i.get("type") == "not_acceptable_main" for i in validation.get("issues", []))},
        ])
        st.dataframe(checks, use_container_width=True)

    with tab5:
        st.json(payload)


def page_final_certificate() -> None:
    header()
    st.subheader("Final Certificate")
    payload = st.session_state.last_result
    if not payload:
        st.info("Run Coding & Rule Check first.")
        return

    final = payload.get("final_output", {})
    ucod = final.get("ucod", {})
    validation = payload.get("validation", {})
    kind = "green" if not validation.get("blocking") else "red"
    status_card("Final UCOD", f"<b>{escape(ucod.get('condition',''))}</b><br>ICD-10: <b>{escape(ucod.get('code',''))}</b><br>Rule path: {escape(' → '.join(final.get('rule_path', [])))}", kind)

    st.markdown("### Coded Causes")
    coded = payload.get("coded_causes", [])
    st.dataframe(pd.DataFrame([
        {
            "Line": c.get("line", ""),
            "Section": c.get("section", ""),
            "Cause": c.get("cause", ""),
            "Interval": c.get("interval", ""),
            "ICD": c.get("code_formatted", ""),
            "Description": c.get("short_desc", ""),
        }
        for c in coded
    ]), use_container_width=True)

    st.markdown("### Save / Export")
    c1, c2 = st.columns(2)
    with c1:
        override_reason = st.text_input("Override / review note", value="")
        if st.button("Save audit record", type="primary"):
            row_id = save_audit(payload, override_reason=override_reason)
            st.success(f"Audit record saved with ID {row_id}.")
    with c2:
        try:
            pdf_bytes = generate_certificate_pdf(payload)
            st.download_button("Download certificate PDF", data=pdf_bytes, file_name="death_certificate_rule_trace.pdf", mime="application/pdf")
        except Exception as e:
            st.warning(f"PDF unavailable: {e}")


def page_audit_log() -> None:
    header()
    st.subheader("Audit Log")
    df = load_audit_log()
    if df.empty:
        st.info("No audit records yet.")
        return
    st.dataframe(df.drop(columns=["payload_json"], errors="ignore"), use_container_width=True)
    selected_id = st.selectbox("Open audit record", options=df["id"].tolist())
    row = df[df["id"] == selected_id].iloc[0]
    with st.expander("Payload JSON", expanded=False):
        try:
            st.json(json.loads(row["payload_json"]))
        except Exception:
            st.code(row["payload_json"])


# =============================================================================
# App Router
# =============================================================================


def main() -> None:
    with st.sidebar:
        st.image("https://www.moh.gov.sa/_layouts/15/MOH/Internet/New/images/logo.png", width=120)
        st.markdown("### Navigation")
        page = st.radio(
            "Go to",
            [
                "Login / Role",
                "System Settings",
                "Cause of Death",
                "Review & Coding",
                "Final Certificate",
                "Audit Log",
            ],
            label_visibility="collapsed",
        )
        st.divider()
        st.caption("Visible workflow names: Structure Check, ICD Coding, Table A Sequence, Table B Obvious Cause, Quality Check, Final UCOD Decision.")

    if page == "Login / Role":
        page_login()
    elif page == "System Settings":
        page_settings()
    elif page == "Cause of Death":
        page_certificate_form()
    elif page == "Review & Coding":
        page_review_coding()
    elif page == "Final Certificate":
        page_final_certificate()
    elif page == "Audit Log":
        page_audit_log()


if __name__ == "__main__":
    main()
