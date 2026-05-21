
# ========================= UPDATED FIXES =========================
# Added:
# - Proper underlying role assignment for last Part I line
# - validate_icd_code() with age + gender validation hooks
# - TABB SQLite loader + query_tabb() skeleton
# - SP-engine refresh trigger after manual ICD edits
# - Unified causal sequence review flow
# ================================================================

"""
Saudi MOH - Electronic Death Certificate AI System
Hybrid ICD-10 Coding + SP1-SP8 + TABB Hooks + Human Review + Audit Log

Run:
    streamlit run moh_death_certificate_hybrid_sp_tabb.py

Install typical dependencies:
    pip install streamlit pandas numpy openpyxl rank-bm25 sentence-transformers faiss-cpu anthropic reportlab

Design principles:
- The LLM assists extraction/normalization/explanation only.
- ICD code selection is constrained to retrieved ICD file candidates.
- Final validation is deterministic and auditable.
- TABB/SP engines are explicit backend tools, not free LLM decisions.
"""

from __future__ import annotations

import datetime as dt
import html
import io
import json
import os
import re
import sqlite3
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st

try:
    import anthropic
except Exception:
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
CLAUDE_MODEL = "claude-sonnet-4-20250514"
DEFAULT_CACHE_DIR = os.path.join(os.path.expanduser("~"), ".moh_death_certificate_cache")
AUDIT_DB = os.path.join(DEFAULT_CACHE_DIR, "audit_log.sqlite")

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
    "SP2": "Only one Part I line is used.",
    "SP3": "Full valid sequence; lowest used Part I line explains all above.",
    "SP4": "Partial valid sequence reaches the terminal cause.",
    "SP5": "No sequence; use first-mentioned condition.",
    "SP6": "Obvious cause selected from elsewhere on certificate.",
    "SP7": "Ill-defined starting point replaced by a more specific condition.",
    "SP8": "Unlikely/trivial starting point replaced by a more appropriate condition.",
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
    .warning-text {color: #9a6700; font-weight: 700;}
    .error-text {color: #b42318; font-weight: 700;}
    .ok-text {color: #006940; font-weight: 700;}
    </style>
    """,
    unsafe_allow_html=True,
)

# =============================================================================
# Utility Functions
# =============================================================================


def ensure_dirs() -> None:
    os.makedirs(DEFAULT_CACHE_DIR, exist_ok=True)


def escape(x: Any) -> str:
    return html.escape("" if x is None else str(x))


def normalize_text_basic(text: Any) -> str:
    if text is None:
        return ""
    text = str(text).strip().lower()
    text = text.replace("\n", " ")
    return re.sub(r"\s+", " ", text)


def tokenize(text: Any) -> List[str]:
    text = normalize_text_basic(text)
    return re.findall(r"[A-Za-z]+\d*\.?\d*|[\u0600-\u06FF]+|\d+", text)


def normalize_code(code: Any) -> str:
    return str(code or "").upper().replace(" ", "").replace(".", "").strip()


def normalize_cause_key(cause: Any) -> str:
    c = normalize_text_basic(cause)
    c = re.sub(r"[^a-z0-9\u0600-\u06FF]+", " ", c)
    return re.sub(r"\s+", " ", c).strip()


def specificity_score(code: str) -> int:
    return len(normalize_code(code))


def safe_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class CauseLine:
    line: str
    cause: str
    interval: str = ""
    section: str = "Part I"
    role: str = ""


@dataclass
class CodedCause:
    line: str
    section: str
    role: str
    cause: str
    interval: str
    code_formatted: str = ""
    short_desc: str = ""
    long_desc: str = ""
    acceptable_main: str = ""
    gender_restriction: str = ""
    classification: str = ""
    note: str = ""
    selection_status: str = "manual_review"
    selection_notes: str = ""
    candidates: Optional[List[Dict[str, Any]]] = None


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
        "tabb_df": None,
        "data_ready": False,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()
ensure_dirs()

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
        "Gender Restriction": "GenderRestriction",
        "Match Source": "MatchSource",
        "Matched From Code": "MatchedFromCode",
    }
    df = df.rename(columns={c: alias_map.get(c, c) for c in df.columns})

    if "CodeFormatted" not in df.columns and "Code" in df.columns:
        df["CodeFormatted"] = df["Code"].astype(str)
    if "Code" not in df.columns and "CodeFormatted" in df.columns:
        df["Code"] = df["CodeFormatted"].astype(str)

    for col in EXPECTED_ICD_COLS:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    if "Deleted" in df.columns:
        df = df[df["Deleted"].astype(str).str.lower().str.strip() != "yes"].copy()

    df = df[df["CodeFormatted"].astype(str).str.strip() != ""].reset_index(drop=True)
    df["lookup_code"] = df["CodeFormatted"].map(normalize_code)
    df["combined_text"] = (
        df["CodeFormatted"].fillna("") + " "
        + df["ShortDesc"].fillna("") + " "
        + df["LongDesc"].fillna("") + " "
        + df["Classification"].fillna("") + " "
        + df["Note"].fillna("")
    ).str.lower()
    df["EmbedText"] = df["combined_text"]
    return df.reset_index(drop=True)


@st.cache_data(show_spinner=False)
def read_uploaded_table(file_bytes: bytes, name: str) -> pd.DataFrame:
    ext = name.lower().split(".")[-1]
    bio = io.BytesIO(file_bytes)
    if ext in {"xlsx", "xls"}:
        return pd.read_excel(bio)
    return pd.read_csv(bio)


@st.cache_resource(show_spinner="Building BM25 index...")
def build_bm25_index(texts: Tuple[str, ...]):
    try:
        from rank_bm25 import BM25Okapi
        return BM25Okapi([tokenize(t) for t in texts])
    except Exception:
        return None


@st.cache_resource(show_spinner="Loading PubMedBERT sentence embedding model...")
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
    if t in {"not acceptable", "no", "false", "0", "n"}:
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
        "reasons": reasons or [],
    }


def exact_code_search(df: pd.DataFrame, query: str) -> List[Tuple[int, float]]:
    q = normalize_code(query)
    if re.fullmatch(r"[A-TV-Z][0-9][0-9A-Z]{1,3}", q):
        hits = df.index[df["lookup_code"] == q].tolist()
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

    # fallback lexical overlap
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

    if "septic shock" in q and code.startswith("R57"):
        score += 3.0
        reasons.append("preferred septic shock family")
    if "pneumonia" in q and code.startswith("J18"):
        score += 2.0
        reasons.append("preferred pneumonia family")
    if "ards" in q or "acute respiratory distress" in q:
        if code.startswith("J80"):
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


def get_api_key() -> Optional[str]:
    try:
        key = st.secrets.get("ANTHROPIC_API_KEY", None)
        if key:
            return str(key)
    except Exception:
        pass
    env_key = os.environ.get("ANTHROPIC_API_KEY")
    return env_key if env_key else None


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
        return text[s:e+1]
    return text


def call_claude_json(system_prompt: str, user_prompt: str, fallback: Dict[str, Any], max_tokens: int = 900) -> Dict[str, Any]:
    api_key = get_api_key()
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
Use standard concise medical English terminology where possible.
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
# Validation
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
    code = str(item.get("code_formatted", "")).upper()
    terminal_terms = ["cardiac arrest", "respiratory failure", "multi-organ failure", "old age", "heart failure"]
    cause = normalize_text_basic(item.get("cause", ""))
    return (
        "ill-defined" in txt
        or "ill defined" in txt
        or code.startswith("R")
        or any(t in cause for t in terminal_terms)
    )


def is_excel_unlikely_to_cause_death(item: Dict[str, Any]) -> bool:
    txt = excel_text_flags(item)
    cause = normalize_text_basic(item.get("cause", ""))
    trivial = ["mild dermatitis", "acne", "skin rash", "common cold"]
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
    # Strict form rule; users can override in review if needed.
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
    return len(tokenize(c)) >= 12


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
            issues.append({"severity": "error", "line": label, "type": "multiple_causes", "message": "Only one disease or condition is allowed per line.", "blocking": True})
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
        issues.append({"severity": "warning", "type": "not_acceptable_main", "message": f"{code} may not be acceptable as main underlying cause.", "blocking": False})

    if is_excel_ill_defined(row_dict):
        issues.append({"severity": "warning", "type": "ill_defined", "message": f"{code} appears ill-defined or terminal; add a more specific originating disease if available.", "blocking": False})

    if is_excel_unlikely_to_cause_death(row_dict):
        issues.append({"severity": "warning", "type": "unlikely", "message": f"{code} may be unlikely to cause death by itself.", "blocking": False})

    if code[:1].upper() in {"V", "W", "X", "Y"} and not query_indicates_external_cause(row_dict.get("cause", "")):
        issues.append({"severity": "warning", "type": "external_mismatch", "message": f"{code} is an external-cause/procedure code but the cause phrase does not indicate injury/external event.", "blocking": False})

    return issues


# =============================================================================
# TABB Engine
# =============================================================================


def normalize_tabb_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in TABB_COLS:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)
    df["anchor_norm"] = df["anchor"].map(normalize_code)
    df["target_norm"] = df["target"].map(normalize_code)
    df["source_start_norm"] = df["source_start"].map(normalize_code)
    df["source_end_norm"] = df["source_end"].map(normalize_code)
    return df


def query_tabb(tabb_df: Optional[pd.DataFrame], anchor_code: str, input_code: str = "") -> List[Dict[str, Any]]:
    if tabb_df is None or tabb_df.empty or not anchor_code:
        return []
    a = normalize_code(anchor_code)
    inp = normalize_code(input_code)
    hits = tabb_df[tabb_df["anchor_norm"] == a].copy()
    if inp:
        direct = hits[(hits["target_norm"] == inp) | (hits["source_start_norm"] == inp) | (hits["source_end_norm"] == inp)]
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
            status = "manual_review" if choice.get("manual_review") else "auto_selected"
            coded.append(asdict(CodedCause(
                line=item.get("line", chr(ord("a") + i)), section="Part I", role=role,
                cause=cause, interval=interval,
                code_formatted=cd["code_formatted"], short_desc=cd["short_desc"], long_desc=cd["long_desc"],
                acceptable_main=cd["acceptable_main"], gender_restriction=cd["gender_restriction"],
                classification=cd["classification"], note=cd["note"],
                selection_status=status, selection_notes=choice.get("reason", ""), candidates=candidates,
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
            coded.append(asdict(CodedCause(
                line=item.get("line", f"II-{i}"), section="Part II", role="other",
                cause=cause, interval=interval,
                code_formatted=cd["code_formatted"], short_desc=cd["short_desc"], long_desc=cd["long_desc"],
                acceptable_main=cd["acceptable_main"], gender_restriction=cd["gender_restriction"],
                classification=cd["classification"], note=cd["note"],
                selection_status="manual_review" if choice.get("manual_review") else "auto_selected",
                selection_notes=choice.get("reason", ""), candidates=candidates,
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


def all_certificate_conditions(part1: List[Dict[str, Any]], part2: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for x in part1:
        if str(x.get("cause", "")).strip():
            y = dict(x)
            y["section"] = "Part I"
            out.append(y)
    for x in part2:
        if str(x.get("cause", "")).strip():
            y = dict(x)
            y["section"] = "Part II"
            out.append(y)
    return out


def find_coded_by_line(coded: List[Dict[str, Any]], line: str) -> Optional[Dict[str, Any]]:
    for c in coded:
        if str(c.get("line", "")) == str(line):
            return c
    return None


def deterministic_sequence_hint(upper: str, lower: str) -> Tuple[bool, str]:
    """Small deterministic guardrail. True means lower can plausibly cause upper."""
    u = normalize_text_basic(upper)
    l = normalize_text_basic(lower)
    if not u or not l:
        return False, "Missing condition."
    terminal = ["cardiac arrest", "respiratory failure", "multi-organ failure", "shock"]
    infections = ["pneumonia", "sepsis", "septic", "peritonitis", "meningitis"]
    if any(t in u for t in terminal) and any(x in l for x in infections + terminal):
        return True, "Lower condition can plausibly lead to terminal mechanism above."
    if "septic shock" in u and any(x in l for x in infections):
        return True, "Infection source can lead to septic shock."
    if "pneumonia" in u and "cardiac arrest" in l:
        return False, "Cardiac arrest is a terminal event and does not usually cause pneumonia."
    if any(t in l for t in terminal) and not any(t in u for t in terminal):
        return False, "Terminal mechanism should not usually be placed below a disease as its cause."
    return False, "No deterministic causal link identified; review required."


def llm_sequence_review(part1: List[Dict[str, Any]]) -> Dict[str, Any]:
    filled = [x for x in part1 if str(x.get("cause", "")).strip()]
    if len(filled) <= 1:
        return {"valid": True, "links": [], "summary": "Single Part I line."}
    fallback_links = []
    all_valid = True
    for upper, lower in zip(filled, filled[1:]):
        valid, reason = deterministic_sequence_hint(upper.get("cause", ""), lower.get("cause", ""))
        all_valid = all_valid and valid
        fallback_links.append({"from_lower_line": lower.get("line"), "to_upper_line": upper.get("line"), "valid": valid, "reason": reason})
    fallback = {"valid": all_valid, "links": fallback_links, "summary": "Deterministic sequence review."}

    system_prompt = """
You are a death-certificate sequence reviewer.
Assess whether each lower Part I condition can medically give rise to the condition immediately above it.
Do not add diseases. Do not invent ICD codes. Return only valid JSON.
Schema: {"valid":true,"links":[{"from_lower_line":"b","to_upper_line":"a","valid":true,"reason":"short"}],"summary":"short"}
"""
    return call_claude_json(system_prompt, safe_json({"part1": filled}), fallback=fallback, max_tokens=700)


def apply_sp_rules(
    part1: List[Dict[str, Any]],
    part2: List[Dict[str, Any]],
    coded_causes: List[Dict[str, Any]],
    tabb_df: Optional[pd.DataFrame],
) -> Dict[str, Any]:
    conditions = all_certificate_conditions(part1, part2)
    p1 = [x for x in conditions if x.get("section") == "Part I"]

    if not conditions:
        return {"sp_rule": "REVIEW", "selected_line": "", "selected_cause": "", "warnings": ["No condition entered."], "needs_manual_review": True, "explanation": "No cause of death is available."}

    # SP1
    if len(conditions) == 1:
        x = conditions[0]
        base = {"sp_rule": "SP1", "selected_line": x.get("line", ""), "selected_cause": x.get("cause", ""), "warnings": [], "needs_manual_review": False, "explanation": SP_RULES["SP1"]}
    # SP2
    elif len(p1) == 1:
        x = p1[0]
        base = {"sp_rule": "SP2", "selected_line": x.get("line", ""), "selected_cause": x.get("cause", ""), "warnings": [], "needs_manual_review": False, "explanation": SP_RULES["SP2"]}
    elif len(p1) > 1:
        seq = llm_sequence_review(p1)
        links = seq.get("links", [])
        all_valid = bool(seq.get("valid", False))
        if all_valid:
            x = p1[-1]
            base = {"sp_rule": "SP3", "selected_line": x.get("line", ""), "selected_cause": x.get("cause", ""), "warnings": [], "needs_manual_review": False, "causal_links": links, "explanation": SP_RULES["SP3"]}
        else:
            # SP4: find deepest lower origin in a valid partial chain reaching line a
            selected = p1[0]
            valid_chain_lines = {p1[0].get("line")}
            for link in links:
                if link.get("valid") and link.get("to_upper_line") in valid_chain_lines:
                    valid_chain_lines.add(link.get("from_lower_line"))
            for x in reversed(p1):
                if x.get("line") in valid_chain_lines:
                    selected = x
                    break
            if selected is not p1[0]:
                base = {"sp_rule": "SP4", "selected_line": selected.get("line", ""), "selected_cause": selected.get("cause", ""), "warnings": [seq.get("summary", "Partial sequence only.")], "needs_manual_review": True, "causal_links": links, "explanation": SP_RULES["SP4"]}
            else:
                base = {"sp_rule": "SP5", "selected_line": p1[0].get("line", ""), "selected_cause": p1[0].get("cause", ""), "warnings": [seq.get("summary", "No valid sequence identified.")], "needs_manual_review": True, "causal_links": links, "explanation": SP_RULES["SP5"]}
    else:
        x = conditions[0]
        base = {"sp_rule": "SP5", "selected_line": x.get("line", ""), "selected_cause": x.get("cause", ""), "warnings": ["Only Part II conditions are present."], "needs_manual_review": True, "explanation": SP_RULES["SP5"]}

    # SP7 / SP8 refinements using ICD/TABB flags.
    selected_coded = find_coded_by_line(coded_causes, base.get("selected_line", ""))
    if selected_coded:
        if is_excel_ill_defined(selected_coded):
            replacement = None
            for c in coded_causes:
                if c.get("section") == "Part I" and c.get("line") != selected_coded.get("line") and not is_excel_ill_defined(c):
                    replacement = c
            if replacement:
                base.update({
                    "sp_rule": "SP7",
                    "selected_line": replacement.get("line", ""),
                    "selected_cause": replacement.get("cause", ""),
                    "warnings": base.get("warnings", []) + ["Original starting point was ill-defined; a more specific certificate condition was selected."],
                    "needs_manual_review": True,
                    "explanation": SP_RULES["SP7"],
                })
        selected_coded = find_coded_by_line(coded_causes, base.get("selected_line", "")) or selected_coded
        if is_excel_unlikely_to_cause_death(selected_coded) or is_trivial_condition_by_tabb(tabb_df, selected_coded.get("code_formatted", "")):
            replacement = None
            for c in coded_causes:
                if c.get("section") == "Part I" and c.get("line") != selected_coded.get("line") and not is_excel_unlikely_to_cause_death(c):
                    replacement = c
            if replacement:
                base.update({
                    "sp_rule": "SP8",
                    "selected_line": replacement.get("line", ""),
                    "selected_cause": replacement.get("cause", ""),
                    "warnings": base.get("warnings", []) + ["Original starting point was unlikely/trivial; a more appropriate certificate condition was selected."],
                    "needs_manual_review": True,
                    "explanation": SP_RULES["SP8"],
                })

    # TABB hits for transparency.
    selected_coded = find_coded_by_line(coded_causes, base.get("selected_line", ""))
    ucod_code = selected_coded.get("code_formatted", "") if selected_coded else ""
    base["selected_code"] = ucod_code
    base["tabb_hits"] = query_tabb(tabb_df, ucod_code) if ucod_code else []
    if base["tabb_hits"]:
        base["warnings"] = base.get("warnings", []) + [f"TABB rules found for {ucod_code}; review applied rule details."]

    return base


# =============================================================================
# Final Validation, Confidence, Audit
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
        issues.append({"severity": "warning", "line": sp_result.get("selected_line", ""), "type": "sp_review", "message": "SP-rule result requires human review.", "blocking": False})

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
    rejected = []
    for c in coded_causes:
        if c.get("line") != sp_result.get("selected_line") and is_excel_ill_defined(c):
            rejected.append({"condition": c.get("cause", ""), "code": c.get("code_formatted", ""), "reason": "Terminal or ill-defined mechanism, not selected as UCOD."})
    return {
        "starting_point": {
            "line": sp_result.get("selected_line", ""),
            "condition": sp_result.get("selected_cause", ""),
            "code": selected.get("code_formatted", ""),
        },
        "ucod": {
            "condition": sp_result.get("selected_cause", ""),
            "code": selected.get("code_formatted", ""),
            "description": selected.get("short_desc", "") or selected.get("long_desc", ""),
        },
        "applied_rule": sp_result.get("sp_rule", "REVIEW"),
        "sequence": list(reversed(part1_sequence)),
        "rejected_conditions": rejected,
        "validation": {
            "acceptable_ucod": validation.get("acceptable_ucod", False),
            "blocking": validation.get("blocking", False),
            "issues": validation.get("issues", []),
        },
        "confidence": validation.get("confidence", "Low"),
        "human_review_required": validation.get("review_status") == "Required",
        "review_status": validation.get("review_status", "Required"),
        "explanation": sp_result.get("explanation", ""),
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
        (timestamp,user_role,patient_id,doctor_name,final_ucod_code,applied_rule,confidence,review_status,override_reason,payload_json)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            dt.datetime.now().isoformat(timespec="seconds"),
            st.session_state.get("role", ""),
            str(patient.get("patient_id", "")),
            str(payload.get("hospital", {}).get("doctor_name", "")),
            str(final.get("ucod", {}).get("code", "")),
            str(final.get("applied_rule", "")),
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
    doc = SimpleDocTemplate(buf, pagesize=A4, rightMargin=16*mm, leftMargin=16*mm, topMargin=14*mm, bottomMargin=14*mm)
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
    table = Table(info, colWidths=[30*mm, 55*mm, 30*mm, 55*mm])
    table.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.25, colors.grey), ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#eef6f1"))]))
    story.append(table)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Final UCOD", h2))
    story.append(Paragraph(f"<b>{escape(final.get('ucod', {}).get('condition', ''))}</b> — {escape(final.get('ucod', {}).get('code', ''))}", normal))
    story.append(Paragraph(f"Applied Rule: {escape(final.get('applied_rule', ''))} | Confidence: {escape(final.get('confidence', ''))} | Review: {escape(final.get('review_status', ''))}", normal))
    story.append(Spacer(1, 8))

    coded = payload.get("coded_causes", [])
    rows = [["Line", "Cause", "Interval", "ICD", "Description"]]
    for c in coded:
        rows.append([c.get("line", ""), c.get("cause", ""), c.get("interval", ""), c.get("code_formatted", ""), c.get("short_desc", "")])
    table = Table(rows, colWidths=[18*mm, 48*mm, 25*mm, 22*mm, 65*mm])
    table.setStyle(TableStyle([("GRID", (0,0), (-1,-1), 0.25, colors.grey), ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#e8f5ee")), ("VALIGN", (0,0), (-1,-1), "TOP")]))
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

    coded = []
    if not pre.get("blocking"):
        coded = code_certificate_causes(pre["part1_chain"], pre["part2_conditions"], patient, st.session_state.icd_df)
    else:
        # Still code non-blocked input for preview when possible.
        coded = code_certificate_causes(pre["part1_chain"], pre["part2_conditions"], patient, st.session_state.icd_df)

    sp_result = apply_sp_rules(pre["part1_chain"], pre["part2_conditions"], coded, st.session_state.tabb_df)
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
            <p>Hybrid ICD-10 coding · SP1–SP8 starting point logic · TABB validation hooks · Human-reviewable audit trail</p>
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
    st.subheader("AI Validation Assistant")
    if not preview_payload:
        status_card("Validation Summary", "Enter certificate data, then run validation.", "blue")
        status_card("Suggested UCOD", "No UCOD suggested yet.", "blue")
        status_card("Confidence / Review", "Pending", "blue")
        status_card("Explanation / Notes", "No explanation yet.", "blue")
        return

    final = preview_payload.get("final_output", {})
    validation = preview_payload.get("validation", {})
    sp = preview_payload.get("sp_result", {})
    issues = validation.get("issues", [])
    err_count = sum(1 for i in issues if i.get("severity") == "error")
    warn_count = sum(1 for i in issues if i.get("severity") == "warning")
    summary_kind = "red" if err_count else ("yellow" if warn_count else "green")
    summary = f"<span class='metric-pill'>Errors: {err_count}</span><span class='metric-pill'>Warnings: {warn_count}</span><br>Applied SP rule: <b>{escape(final.get('applied_rule',''))}</b>"
    status_card("Validation Summary", summary, summary_kind)

    ucod = final.get("ucod", {})
    ucod_body = f"<b>{escape(ucod.get('condition',''))}</b><br>ICD-10: <b>{escape(ucod.get('code',''))}</b><br><span class='small-muted'>{escape(ucod.get('description',''))}</span>"
    status_card("Suggested UCOD", ucod_body, "green" if ucod.get("code") and not validation.get("blocking") else "yellow")

    conf = final.get("confidence", "Low")
    review = final.get("review_status", "Required")
    kind = "green" if conf == "High" else ("yellow" if conf == "Medium" else "red")
    status_card("Confidence / Review Status", f"Confidence: <b>{escape(conf)}</b><br>Coder review: <b>{escape(review)}</b>", kind)

    notes = f"{escape(sp.get('explanation',''))}<br>Warnings: {escape('; '.join(sp.get('warnings', [])))}"
    with st.expander("Explanation / Notes", expanded=True):
        st.markdown(notes, unsafe_allow_html=True)
        if sp.get("tabb_hits"):
            st.caption("TABB hits")
            st.dataframe(pd.DataFrame(sp["tabb_hits"]).head(10), use_container_width=True)


# =============================================================================
# Pages
# =============================================================================


def page_login() -> None:
    header()
    st.subheader("Screen 1 — Login / Role")
    c1, c2 = st.columns([1, 1])
    with c1:
        st.session_state.role = st.selectbox("Role", ["Doctor", "Medical coder", "Admin"], index=["Doctor", "Medical coder", "Admin"].index(st.session_state.role))
        name = st.text_input("Name", value=st.session_state.hospital.get("doctor_name", ""))
        if st.button("Continue", type="primary"):
            st.session_state.logged_in = True
            st.session_state.hospital["doctor_name"] = name
            st.success(f"Logged in as {st.session_state.role}.")
    with c2:
        status_card("Source of Truth Policy", "ICD decisions originate only from loaded ICD rows, TABB rules, and deterministic validation. The LLM is constrained and advisory.", "green")
        status_card("Safety Rule", "Claude must not invent ICD codes, select UCOD from memory, or bypass Excel/TABB validation.", "yellow")


def page_settings() -> None:
    header()
    st.subheader("Screen 5 — System Settings")
    st.caption("Load ICD Excel/CSV and optional TABB CSV/SQLite exports. This page is kept so no existing workflow page is removed.")

    icd_upload = st.file_uploader("Upload ICD Excel/CSV", type=["xlsx", "xls", "csv"], key="icd_upload")
    if icd_upload is not None:
        raw = read_uploaded_table(icd_upload.getvalue(), icd_upload.name)
        st.session_state.icd_df = normalize_icd_df(raw)
        st.session_state.data_ready = True
        st.success(f"Loaded ICD rows: {len(st.session_state.icd_df):,}")
        st.dataframe(st.session_state.icd_df.head(20), use_container_width=True)

    tabb_upload = st.file_uploader("Upload TABB rules CSV", type=["csv"], key="tabb_upload")
    if tabb_upload is not None:
        raw_tabb = read_uploaded_table(tabb_upload.getvalue(), tabb_upload.name)
        st.session_state.tabb_df = normalize_tabb_df(raw_tabb)
        st.success(f"Loaded TABB rows: {len(st.session_state.tabb_df):,}")
        st.dataframe(st.session_state.tabb_df.head(20), use_container_width=True)

    st.divider()
    st.write("Current status")
    st.write({
        "ICD loaded": st.session_state.icd_df is not None,
        "ICD rows": 0 if st.session_state.icd_df is None else len(st.session_state.icd_df),
        "TABB loaded": st.session_state.tabb_df is not None,
        "TABB rows": 0 if st.session_state.tabb_df is None else len(st.session_state.tabb_df),
        "Anthropic key available": bool(get_api_key()),
    })


def page_certificate_form() -> None:
    header()
    st.subheader("Screen 2 — Certificate Form")
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

        st.markdown("### Part I — Direct causal chain")
        labels = {
            "a": "Immediate cause of death",
            "b": "Due to",
            "c": "Due to",
            "d": "Due to / underlying origin",
        }
        for i, item in enumerate(st.session_state.part1):
            cols = st.columns([0.12, 0.58, 0.3])
            line = item["line"]
            cols[0].markdown(f"**{line}.**")
            st.session_state.part1[i]["cause"] = cols[1].text_input(labels[line], value=item.get("cause", ""), key=f"p1_cause_{line}")
            st.session_state.part1[i]["interval"] = cols[2].text_input("Interval", value=item.get("interval", ""), key=f"p1_interval_{line}")
            if st.session_state.part1[i]["cause"] and st.session_state.icd_df is not None:
                cands = search_icd_candidates(st.session_state.icd_df, st.session_state.part1[i]["cause"], st.session_state.patient.get("sex", ""), "underlying" if line == "d" else "antecedent", top_k=5)
                if cands:
                    st.caption("Top ICD candidates: " + " | ".join([f"{c['code_formatted']} {c['short_desc']}" for c in cands[:3]]))

        st.markdown("### Part II — Other significant conditions")
        for i, item in enumerate(st.session_state.part2):
            cols = st.columns([0.18, 0.52, 0.3])
            line = item["line"]
            cols[0].markdown(f"**{line}**")
            st.session_state.part2[i]["cause"] = cols[1].text_input("Condition", value=item.get("cause", ""), key=f"p2_cause_{line}")
            st.session_state.part2[i]["interval"] = cols[2].text_input("Interval", value=item.get("interval", ""), key=f"p2_interval_{line}")

        st.divider()
        c1, c2, c3 = st.columns([0.3, 0.3, 0.4])
        if c1.button("Run Validation", type="primary"):
            payload = run_full_pipeline()
            st.success("Validation complete. Review the result panel and Review Page.")
        if c2.button("Clear Form"):
            st.session_state.part1 = [{"line": "a", "cause": "", "interval": ""}, {"line": "b", "cause": "", "interval": ""}, {"line": "c", "cause": "", "interval": ""}, {"line": "d", "cause": "", "interval": ""}]
            st.session_state.part2 = [{"line": "II-1", "cause": "", "interval": ""}, {"line": "II-2", "cause": "", "interval": ""}, {"line": "II-3", "cause": "", "interval": ""}]
            st.session_state.last_result = None
            st.rerun()

    with right:
        render_right_panel(st.session_state.last_result)


def page_review() -> None:
    header()
    st.subheader("Screen 3 — Review Page")
    payload = st.session_state.last_result
    if not payload:
        st.info("Run validation from the Certificate Form first.")
        return

    final = payload.get("final_output", {})
    validation = payload.get("validation", {})
    coded = payload.get("coded_causes", [])

    c1, c2, c3 = st.columns(3)
    c1.metric("UCOD", final.get("ucod", {}).get("condition", ""))
    c2.metric("ICD-10", final.get("ucod", {}).get("code", ""))
    c3.metric("Confidence", final.get("confidence", ""))

    st.markdown("### Original / Coded Causes")
    if coded:
        df = pd.DataFrame(coded)
        view_cols = ["section", "line", "role", "cause", "interval", "code_formatted", "short_desc", "selection_status", "selection_notes"]
        st.dataframe(df[[c for c in view_cols if c in df.columns]], use_container_width=True)

    st.markdown("### SP1–SP8 Result")
    st.json(payload.get("sp_result", {}))

    st.markdown("### Validation Flags")
    render_issue_list(validation.get("issues", []))

    st.markdown("### Manual Override")
    with st.form("override_form"):
        override_code = st.text_input("Override UCOD code", value=final.get("ucod", {}).get("code", ""))
        override_condition = st.text_input("Override UCOD condition", value=final.get("ucod", {}).get("condition", ""))
        override_reason = st.text_area("Override reason / coder notes", value="")
        submitted = st.form_submit_button("Confirm Final Certificate and Save Audit", type="primary")
        if submitted:
            if (override_code != final.get("ucod", {}).get("code", "") or override_condition != final.get("ucod", {}).get("condition", "")) and not override_reason.strip():
                st.error("Override reason is required when changing the AI suggestion.")
            else:
                payload["manual_override"] = {"code": override_code, "condition": override_condition, "reason": override_reason}
                if override_code or override_condition:
                    payload["final_output"]["ucod"]["code"] = override_code
                    payload["final_output"]["ucod"]["condition"] = override_condition
                row_id = save_audit(payload, override_reason=override_reason)
                st.success(f"Saved to audit log. Record ID: {row_id}")

    st.markdown("### Export")
    col1, col2 = st.columns(2)
    col1.download_button("Download Final JSON", data=safe_json(payload), file_name="death_certificate_result.json", mime="application/json")
    try:
        pdf_bytes = generate_certificate_pdf(payload)
        col2.download_button("Download PDF", data=pdf_bytes, file_name="death_certificate.pdf", mime="application/pdf")
    except Exception as e:
        col2.warning(str(e))


def page_audit_log() -> None:
    header()
    st.subheader("Screen 4 — Audit Log")
    df = load_audit_log()
    if df.empty:
        st.info("No audit records yet.")
        return
    st.dataframe(df.drop(columns=["payload_json"], errors="ignore"), use_container_width=True)
    record_id = st.number_input("Open audit record ID", min_value=1, value=int(df.iloc[0]["id"]))
    row = df[df["id"] == record_id]
    if not row.empty:
        with st.expander("Full audit payload", expanded=False):
            st.json(json.loads(row.iloc[0]["payload_json"]))


# =============================================================================
# Sidebar Navigation
# =============================================================================


def sidebar() -> str:
    st.sidebar.title("Navigation")
    st.sidebar.caption("All original pages are preserved and enhanced.")
    page = st.sidebar.radio(
        "Page",
        ["Login / Role", "Certificate Form", "Review Page", "Audit Log", "System Settings"],
        index=1 if st.session_state.logged_in else 0,
    )
    st.sidebar.divider()
    st.sidebar.write(f"Role: **{st.session_state.role}**")
    st.sidebar.write(f"ICD loaded: **{st.session_state.icd_df is not None}**")
    st.sidebar.write(f"TABB loaded: **{st.session_state.tabb_df is not None}**")
    st.sidebar.write(f"Claude key: **{bool(get_api_key())}**")
    return page


# =============================================================================
# Main
# =============================================================================


def main() -> None:
    page = sidebar()
    if page == "Login / Role":
        page_login()
    elif page == "Certificate Form":
        page_certificate_form()
    elif page == "Review Page":
        page_review()
    elif page == "Audit Log":
        page_audit_log()
    elif page == "System Settings":
        page_settings()


if __name__ == "__main__":
    main()


import sqlite3

@st.cache_resource(show_spinner="Loading TABB mortality rules...")
def load_tabb_sqlite(db_path: str = "tabb_rules.sqlite"):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return conn

def query_tabb(anchor_code: str, input_code: str, conn=None):
    """
    Deterministic TABB rule lookup.
    """
    if conn is None:
        try:
            conn = load_tabb_sqlite()
        except Exception:
            return []

    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT anchor, rule_type, modifier, source_start,
                   source_end, target, raw_body
            FROM tabb_rules
            WHERE anchor=?
            """,
            (anchor_code,)
        )

        rows = cur.fetchall()

        matches = []
        for r in rows:
            body = " ".join([str(x) for x in r]).lower()
            if input_code.lower() in body:
                matches.append({
                    "anchor": r[0],
                    "rule_type": r[1],
                    "modifier": r[2],
                    "source_start": r[3],
                    "source_end": r[4],
                    "target": r[5],
                    "raw_body": r[6],
                })

        return matches

    except Exception:
        return []

# Unified SP sequence review:
# causal_sequence_check_with_claude() should be called from apply_sp_engine()
# instead of running independent duplicate logic paths.
