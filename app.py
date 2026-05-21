"""
Saudi MOH — Electronic Death Certificate AI Assistant
Streamlit single-file prototype

Design goals
------------
- LEFT: doctor-facing electronic death certificate form.
- RIGHT: live 4-box validation assistant:
  1) Validation Summary
  2) Suggested UCOD
  3) Confidence / Review Status
  4) Explanation / Notes
- AI is assistive only. Claude may extract/normalize/explain, but deterministic
  Python functions apply SP1–SP8 logic and validation.
- ICD code source of truth = loaded ICD Excel/CSV only.
- TABB mortality logic = parsed TABB CSV/SQLite when available.
- No LLM is allowed to invent ICD codes or bypass validation.

Run
---
streamlit run death_certificate_ai_app.py

Optional files in same folder or upload via sidebar:
- ICD10_Enriched_Final.xlsx
- tabb_rules_clean.csv / tabb_rules.csv
"""

from __future__ import annotations

import json
import re
import sqlite3
import tempfile
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

# Optional imports
try:
    import anthropic  # type: ignore
except Exception:
    anthropic = None

try:
    from rank_bm25 import BM25Okapi  # type: ignore
except Exception:
    BM25Okapi = None


# =============================================================================
# Page setup
# =============================================================================

st.set_page_config(
    page_title="Saudi MOH | Electronic Death Certificate",
    page_icon="🟢",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =============================================================================
# CSS
# =============================================================================

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

:root {
  --moh-green:#006940;
  --moh-green-2:#00843D;
  --moh-dark:#003d27;
  --moh-light:#E9F6EF;
  --moh-gold:#C8A951;
  --bg:#F5F8F6;
  --card:#FFFFFF;
  --ink:#17251C;
  --muted:#63756A;
  --border:#D8E4DC;
  --yellow:#B7791F;
  --yellow-bg:#FFF8E8;
  --red:#B42318;
  --red-bg:#FFF1F0;
  --blue:#175CD3;
  --blue-bg:#EFF6FF;
  --green-bg:#ECFDF3;
}

html, body, [class*="css"] {
  font-family: Inter, sans-serif;
  background: var(--bg);
  color: var(--ink);
}

.main .block-container {
  max-width: 1500px;
  padding-top: 1rem;
  padding-bottom: 2rem;
}

.moh-header {
  background: linear-gradient(135deg, var(--moh-green), var(--moh-green-2));
  border-radius: 18px;
  padding: 1.2rem 1.4rem;
  margin: 0.25rem 0 1.0rem 0;
  color: white;
  border-bottom: 4px solid var(--moh-gold);
  box-shadow: 0 10px 30px rgba(0,105,64,0.18);
}
.moh-header h1 { margin: 0; font-size: 1.45rem; font-weight: 900; }
.moh-header p { margin: 0.25rem 0 0 0; opacity: 0.86; font-size: 0.88rem; }

.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 1rem 1.05rem;
  box-shadow: 0 4px 18px rgba(21, 49, 35, 0.05);
  margin-bottom: 0.9rem;
}

.card h3 {
  color: var(--moh-green);
  margin: 0 0 0.75rem 0;
  font-size: 0.98rem;
  font-weight: 850;
  letter-spacing: .01em;
}

.small-muted { color: var(--muted); font-size: 0.82rem; }

.line-label {
  font-weight: 800;
  color: var(--moh-green);
  font-size: 0.86rem;
  margin-top: 0.35rem;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  border-radius: 999px;
  padding: .2rem .55rem;
  font-size: .75rem;
  font-weight: 800;
  margin: .12rem .15rem .12rem 0;
  border: 1px solid transparent;
}
.pill-green { background: var(--green-bg); color: var(--moh-green); border-color:#B7E4C7; }
.pill-yellow { background: var(--yellow-bg); color: var(--yellow); border-color:#FAD894; }
.pill-red { background: var(--red-bg); color: var(--red); border-color:#FDA29B; }
.pill-blue { background: var(--blue-bg); color: var(--blue); border-color:#B2DDFF; }
.pill-gray { background:#F2F4F7; color:#475467; border-color:#EAECF0; }

.right-card {
  background: white;
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 0.95rem;
  margin-bottom: 0.85rem;
  box-shadow: 0 4px 18px rgba(21, 49, 35, 0.05);
}

.right-card h4 {
  margin: 0 0 .55rem 0;
  color: var(--moh-green);
  font-weight: 900;
  font-size: .94rem;
}

.metric-big {
  font-size: 1.1rem;
  font-weight: 900;
  color: var(--ink);
  line-height: 1.25;
}
.ucod-code {
  color: var(--moh-green);
  font-size: 1.25rem;
  font-weight: 900;
}
.warning-box, .error-box, .ok-box, .info-box {
  border-radius: 12px;
  padding: .58rem .68rem;
  margin: .35rem 0;
  font-size: .82rem;
  line-height: 1.35;
}
.warning-box { background: var(--yellow-bg); border-left: 4px solid var(--yellow); color:#6B4700; }
.error-box { background: var(--red-bg); border-left: 4px solid var(--red); color:#7A271A; }
.ok-box { background: var(--green-bg); border-left: 4px solid var(--moh-green); color:#05603A; }
.info-box { background: var(--blue-bg); border-left: 4px solid var(--blue); color:#1849A9; }

.chain {
  background:#F8FBF9;
  border:1px dashed var(--border);
  border-radius:12px;
  padding:.65rem .75rem;
  font-size:.84rem;
  line-height:1.75;
  margin:.4rem 0;
}

.audit-json {
  background:#101828;
  color:#D0D5DD;
  border-radius:14px;
  padding:1rem;
  font-size:.78rem;
  overflow:auto;
  max-height:430px;
}

.stTextInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] {
  border-radius: 11px !important;
}

.stButton button, .stDownloadButton button {
  border-radius: 999px !important;
  font-weight: 850 !important;
  border: none !important;
}

div[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #003D27, #006940);
}

div[data-testid="stSidebar"] * {
  color: white !important;
}

hr { margin: .85rem 0; }
</style>
""",
    unsafe_allow_html=True,
)


# =============================================================================
# Data classes
# =============================================================================

@dataclass
class CauseLine:
    line: str
    part: str
    cause: str = ""
    interval: str = ""
    code: str = ""
    description: str = ""
    role: str = ""
    selected_candidate_index: int = 0


@dataclass
class Issue:
    severity: str  # ok, info, warning, error
    category: str
    line: str
    message: str
    blocking: bool = False


@dataclass
class SPResult:
    starting_point_line: str = ""
    starting_point_condition: str = ""
    starting_point_code: str = ""
    ucod_condition: str = ""
    ucod_code: str = ""
    applied_rule: str = ""
    explanation: str = ""
    rejected_conditions: List[Dict[str, str]] = None
    confidence: str = "Low"
    human_review_required: bool = True

    def __post_init__(self):
        if self.rejected_conditions is None:
            self.rejected_conditions = []


# =============================================================================
# Constants and helpers
# =============================================================================

DEFAULT_ILL_DEFINED_TERMS = {
    "cardiac arrest",
    "heart arrest",
    "respiratory arrest",
    "respiratory failure",
    "multi organ failure",
    "multiorgan failure",
    "multiple organ failure",
    "old age",
    "senility",
    "natural causes",
    "shock",
    "coma",
    "unknown",
    "collapse",
}

DEFAULT_UNLIKELY_TERMS = {
    "mild anemia",
    "dermatitis",
    "eczema",
    "headache",
    "fatigue",
    "minor injury",
    "superficial injury",
    "common cold",
}


def norm(x: Any) -> str:
    s = "" if x is None else str(x)
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    return s


def norm_code(code: Any) -> str:
    if code is None:
        return ""
    s = str(code).strip().upper().replace(".", "").replace(" ", "")
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s


def display_code(code: Any) -> str:
    s = norm_code(code)
    if len(s) > 3 and re.match(r"^[A-Z]\d{2}", s):
        return s[:3] + "." + s[3:]
    return s


def tokenize(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z]+|\d+|[\u0600-\u06FF]+", norm(text))


def html_escape(x: Any) -> str:
    import html
    return html.escape("" if x is None else str(x))


def issue_box(issue: Issue) -> None:
    css = {
        "ok": "ok-box",
        "info": "info-box",
        "warning": "warning-box",
        "error": "error-box",
    }.get(issue.severity, "info-box")
    icon = {
        "ok": "✓",
        "info": "ℹ",
        "warning": "⚠",
        "error": "✕",
    }.get(issue.severity, "•")
    st.markdown(
        f"<div class='{css}'><b>{icon} {html_escape(issue.line or issue.category)}</b><br>{html_escape(issue.message)}</div>",
        unsafe_allow_html=True,
    )


def pill(text: str, kind: str = "gray") -> str:
    cls = {
        "green": "pill-green",
        "yellow": "pill-yellow",
        "red": "pill-red",
        "blue": "pill-blue",
        "gray": "pill-gray",
    }.get(kind, "pill-gray")
    return f"<span class='pill {cls}'>{html_escape(text)}</span>"


def candidate_label(row: pd.Series) -> str:
    code = display_code(row.get("CodeFormatted", row.get("Code", "")))
    desc = str(row.get("ShortDesc", "")) or str(row.get("LongDesc", ""))
    return f"{code} — {desc}".strip(" —")


# =============================================================================
# Data loading
# =============================================================================

ICD_ALIASES = {
    "Code (Formatted)": "CodeFormatted",
    "Code Formatted": "CodeFormatted",
    "Short Description": "ShortDesc",
    "Long Description": "LongDesc",
    "Acceptable as Main Cause": "AcceptableMain",
    "Gender Restriction": "GenderRestriction",
    "Age Restriction": "AgeRestriction",
    "Class": "Classification",
}


def normalize_icd_df(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: ICD_ALIASES.get(c, c) for c in df.columns}).copy()

    if "CodeFormatted" not in df.columns and "Code" in df.columns:
        df["CodeFormatted"] = df["Code"].astype(str)
    if "Code" not in df.columns:
        df["Code"] = df.get("CodeFormatted", "").astype(str)

    for col in [
        "Code", "CodeFormatted", "ShortDesc", "LongDesc", "AcceptableMain",
        "GenderRestriction", "AgeRestriction", "Classification", "Note"
    ]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)

    if "Deleted" in df.columns:
        df = df[df["Deleted"].astype(str).str.lower().str.strip() != "yes"].copy()

    df["lookup_code"] = df["CodeFormatted"].apply(norm_code)
    df["search_text"] = (
        df["CodeFormatted"] + " " + df["ShortDesc"] + " " + df["LongDesc"] + " " +
        df["Classification"] + " " + df["Note"]
    ).fillna("").astype(str)
    df["search_text_norm"] = df["search_text"].apply(norm)
    df = df[df["lookup_code"] != ""].drop_duplicates("lookup_code").reset_index(drop=True)
    return df


def load_icd_from_upload_or_path(uploaded_file, default_paths: List[str]) -> Optional[pd.DataFrame]:
    try:
        if uploaded_file is not None:
            name = uploaded_file.name.lower()
            if name.endswith(".xlsx") or name.endswith(".xls"):
                return normalize_icd_df(pd.read_excel(uploaded_file))
            return normalize_icd_df(pd.read_csv(uploaded_file))

        for p in default_paths:
            path = Path(p)
            if path.exists():
                if path.suffix.lower() in [".xlsx", ".xls"]:
                    return normalize_icd_df(pd.read_excel(path))
                return normalize_icd_df(pd.read_csv(path))
    except Exception as e:
        st.sidebar.error(f"Could not load ICD file: {e}")
    return None


def normalize_tabb_df(df: pd.DataFrame) -> pd.DataFrame:
    expected = ["anchor", "rule_type", "modifier", "source_start", "source_end", "target", "raw_body", "page"]
    for col in expected:
        if col not in df.columns:
            df[col] = ""
    for col in ["anchor", "source_start", "source_end", "target"]:
        df[col] = df[col].apply(norm_code)
    df["rule_type"] = df["rule_type"].fillna("").astype(str).str.upper().str.strip()
    return df[expected].copy()


def load_tabb_from_upload_or_path(uploaded_file, default_paths: List[str]) -> Optional[pd.DataFrame]:
    try:
        if uploaded_file is not None:
            return normalize_tabb_df(pd.read_csv(uploaded_file))
        for p in default_paths:
            path = Path(p)
            if path.exists():
                return normalize_tabb_df(pd.read_csv(path))
    except Exception as e:
        st.sidebar.error(f"Could not load TABB file: {e}")
    return None


@st.cache_resource(show_spinner=False)
def build_bm25_for_icd(search_text: Tuple[str, ...]):
    if BM25Okapi is None:
        return None
    corpus = [tokenize(x) for x in search_text]
    return BM25Okapi(corpus)


# =============================================================================
# ICD RAG matcher
# =============================================================================

def exact_code_lookup(icd_df: pd.DataFrame, query: str) -> List[Tuple[int, float]]:
    q = norm_code(query)
    if not q:
        return []
    hits = icd_df.index[icd_df["lookup_code"] == q].tolist()
    return [(int(i), 100.0) for i in hits]


def simple_keyword_match(icd_df: pd.DataFrame, query: str, top_k: int = 12) -> List[Tuple[int, float]]:
    q = norm(query)
    q_tokens = [t for t in tokenize(q) if len(t) > 1]
    if not q_tokens:
        return []

    scores = []
    for idx, row in icd_df.iterrows():
        txt = row["search_text_norm"]
        score = 0.0
        if q in txt:
            score += 12.0
        for t in set(q_tokens):
            if t in txt:
                score += 1.0
        if score > 0:
            # prefer less vague code descriptions and more specific codes
            score += min(len(row["lookup_code"]), 6) * 0.05
            scores.append((int(idx), float(score)))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:top_k]


def bm25_match(icd_df: pd.DataFrame, bm25, query: str, top_k: int = 12) -> List[Tuple[int, float]]:
    if bm25 is None:
        return []
    toks = tokenize(query)
    if not toks:
        return []
    scores = bm25.get_scores(toks)
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [(int(i), float(scores[i])) for i in order if scores[i] > 0]


def rerank_icd_candidate(row: pd.Series, query: str, patient_sex: str, role: str) -> float:
    score = 0.0
    q = norm(query)
    code = norm_code(row.get("CodeFormatted", ""))
    txt = norm(row.get("search_text", ""))

    if q and q in txt:
        score += 10
    if role == "underlying" and acceptable_as_main(row) is True:
        score += 1.5
    if role == "underlying" and acceptable_as_main(row) is False:
        score -= 2.0
    if is_ill_defined_row(row):
        score -= 2.0
    if is_unlikely_row(row):
        score -= 2.0
    if not gender_ok(row, patient_sex):
        score -= 10.0

    # common preference hints
    if "pneumonia" in q and code.startswith("J18"):
        score += 4
    if "septic shock" in q and code.startswith("R572"):
        score += 4
    if "cardiac arrest" in q and code.startswith("I46"):
        score += 4
    if "diabetes" in q and code.startswith(("E10", "E11", "E14")):
        score += 3
    if "cancer" in q or "malignant" in q:
        if code.startswith("C"):
            score += 3
    return score


def icd_rag_match(
    icd_df: Optional[pd.DataFrame],
    query: str,
    patient_sex: str,
    role: str = "other",
    top_k: int = 8
) -> List[Dict[str, Any]]:
    if icd_df is None or not query.strip():
        return []

    bm25 = build_bm25_for_icd(tuple(icd_df["search_text_norm"].tolist()))
    hits = []
    hits.extend(exact_code_lookup(icd_df, query))
    hits.extend(simple_keyword_match(icd_df, query, top_k=top_k * 3))
    hits.extend(bm25_match(icd_df, bm25, query, top_k=top_k * 3))

    fused: Dict[int, float] = {}
    for rank, (idx, sc) in enumerate(hits):
        fused[idx] = fused.get(idx, 0.0) + sc + 1.0 / (rank + 1)

    results = []
    for idx, sc in fused.items():
        row = icd_df.iloc[idx]
        total = sc + rerank_icd_candidate(row, query, patient_sex, role)
        results.append((idx, total))

    results.sort(key=lambda x: x[1], reverse=True)

    out = []
    seen = set()
    for idx, sc in results:
        row = icd_df.iloc[idx]
        code = norm_code(row["CodeFormatted"])
        if code in seen:
            continue
        seen.add(code)
        out.append({
            "code": code,
            "code_display": display_code(code),
            "description": str(row.get("ShortDesc", "")) or str(row.get("LongDesc", "")),
            "long_desc": str(row.get("LongDesc", "")),
            "acceptable_main": str(row.get("AcceptableMain", "")),
            "classification": str(row.get("Classification", "")),
            "gender_restriction": str(row.get("GenderRestriction", "")),
            "age_restriction": str(row.get("AgeRestriction", "")),
            "note": str(row.get("Note", "")),
            "score": round(float(sc), 3),
        })
        if len(out) >= top_k:
            break
    return out


# =============================================================================
# ICD validation
# =============================================================================

def acceptable_as_main(row_or_dict: Any) -> Optional[bool]:
    val = str(row_or_dict.get("AcceptableMain", row_or_dict.get("acceptable_main", ""))).strip().lower()
    if val in {"yes", "true", "1", "acceptable", "y"}:
        return True
    if val in {"no", "false", "0", "not acceptable", "n"}:
        return False
    if "not acceptable" in val:
        return False
    if "acceptable" in val:
        return True
    return None


def row_text(row_or_dict: Any) -> str:
    fields = ["Classification", "classification", "AcceptableMain", "acceptable_main", "Note", "note", "ShortDesc", "description", "LongDesc", "long_desc"]
    return norm(" ".join(str(row_or_dict.get(f, "")) for f in fields))


def is_ill_defined_row(row_or_dict: Any) -> bool:
    txt = row_text(row_or_dict)
    code = norm_code(row_or_dict.get("CodeFormatted", row_or_dict.get("code", "")))
    return code.startswith("R") or "ill-defined" in txt or "ill defined" in txt or "vague" in txt


def is_unlikely_row(row_or_dict: Any) -> bool:
    txt = row_text(row_or_dict)
    return "unlikely" in txt or "trivial" in txt or "not likely" in txt


def gender_ok(row_or_dict: Any, patient_sex: str) -> bool:
    gr = norm(row_or_dict.get("GenderRestriction", row_or_dict.get("gender_restriction", "")))
    sx = norm(patient_sex)
    if not gr or gr in {"none", "nan", "n/a", "na", "unknown"}:
        return True
    # Avoid male inside female false positive
    if "female" in gr and sx.startswith("m"):
        return False
    if re.search(r"\bmale\b", gr) and sx.startswith("f"):
        return False
    return True


def validate_icd_candidate(candidate: Dict[str, Any], role: str, patient_sex: str, patient_age: int) -> List[Issue]:
    issues: List[Issue] = []
    code = candidate.get("code_display", candidate.get("code", ""))
    label = code or "ICD"

    if not code:
        issues.append(Issue("error", "ICD", label, "No ICD code selected.", True))
        return issues

    if role == "underlying" and acceptable_as_main(candidate) is False:
        issues.append(Issue("warning", "ICD", label, "This code is not marked acceptable as a main underlying cause.", False))

    if is_ill_defined_row(candidate):
        issues.append(Issue("warning", "ICD", label, "This appears ill-defined/vague or symptom-based. Look for a more specific disease or injury.", False))

    if is_unlikely_row(candidate):
        issues.append(Issue("warning", "ICD", label, "This condition is flagged as trivial/unlikely to cause death by itself.", False))

    if not gender_ok(candidate, patient_sex):
        issues.append(Issue("error", "ICD", label, "This code conflicts with patient sex restriction.", True))

    # Age restriction is usually not uniform in source files; keep as soft warning when text indicates mismatch.
    age_note = norm(candidate.get("age_restriction", ""))
    if age_note and patient_age:
        if "neonatal" in age_note and patient_age > 1:
            issues.append(Issue("warning", "ICD", label, "This code may be neonatal/age-restricted; verify age compatibility.", False))

    return issues


# =============================================================================
# TABB query engine
# =============================================================================

def code_to_sort_key(code: str) -> Tuple[str, int]:
    c = norm_code(code)
    if not c:
        return ("", -1)
    m = re.match(r"^([A-Z])(\d+)$", c)
    if not m:
        return (c[:1], -1)
    return (m.group(1), int(m.group(2)))


def code_in_range(code: str, start: str, end: str) -> bool:
    c1, n = code_to_sort_key(code)
    s1, sn = code_to_sort_key(start)
    e1, en = code_to_sort_key(end)
    if c1 == "" or s1 == "" or e1 == "":
        return False
    if c1 != s1 or s1 != e1:
        return False
    return sn <= n <= en


def query_tabb_rules(tabb_df: Optional[pd.DataFrame], anchor_code: str, input_code: Optional[str] = None) -> pd.DataFrame:
    if tabb_df is None or not anchor_code:
        return pd.DataFrame()
    anchor = norm_code(anchor_code)
    rows = tabb_df[tabb_df["anchor"] == anchor].copy()
    if input_code:
        inp = norm_code(input_code)
        mask = rows.apply(lambda r: code_in_range(inp, r["source_start"], r["source_end"]), axis=1)
        rows = rows[mask].copy()
    return rows


def is_trivial_by_tabb(tabb_df: Optional[pd.DataFrame], code: str) -> bool:
    if tabb_df is None or not code:
        return False
    c = norm_code(code)
    rows = tabb_df[(tabb_df["anchor"] == c) & (tabb_df["rule_type"] == "TRIV")]
    return len(rows) > 0


def tabb_relation_exists(tabb_df: Optional[pd.DataFrame], lower_code: str, upper_code: str) -> Tuple[bool, str]:
    """
    Lightweight lookup. This is not a full ACME/MMDS implementation.
    It checks whether TABB has a rule anchored at upper_code that covers lower_code
    or a direct target match involving lower/upper.
    """
    if tabb_df is None or not lower_code or not upper_code:
        return False, "TABB table unavailable or codes missing."

    lower = norm_code(lower_code)
    upper = norm_code(upper_code)

    rows = query_tabb_rules(tabb_df, anchor_code=upper, input_code=lower)
    if len(rows):
        types = ", ".join(sorted(rows["rule_type"].unique()))
        return True, f"TABB rule found under anchor {display_code(upper)} covering {display_code(lower)} ({types})."

    # fallback: target match
    rows2 = tabb_df[(tabb_df["anchor"] == upper) & (tabb_df["target"] == lower)]
    if len(rows2):
        types = ", ".join(sorted(rows2["rule_type"].unique()))
        return True, f"TABB target rule found under anchor {display_code(upper)} targeting {display_code(lower)} ({types})."

    return False, f"No direct TABB relation found for {display_code(lower)} → {display_code(upper)}."


# =============================================================================
# Form extraction and Claude integration
# =============================================================================

def get_claude_client():
    api_key = st.session_state.get("anthropic_api_key") or st.secrets.get("ANTHROPIC_API_KEY", "")
    if not api_key or anthropic is None:
        return None
    return anthropic.Anthropic(api_key=api_key)


def claude_extract_narrative(narrative: str) -> Dict[str, Any]:
    client = get_claude_client()
    if client is None:
        return {"part1": [], "part2": [], "error": "Claude unavailable."}

    system = """You are a clinical death-certificate extraction assistant.
Return ONLY valid JSON. Do not invent causes. Extract concise medical conditions.
Schema:
{
  "part1": [
    {"line":"a","cause":"string","interval":"string"},
    {"line":"b","cause":"string","interval":"string"}
  ],
  "part2": [
    {"cause":"string","interval":"string"}
  ]
}
Part I must be ordered immediate cause first, then due-to causes.
Part II contains contributing conditions only."""
    msg = f"Narrative:\n{narrative}"
    try:
        resp = client.messages.create(
            model=st.session_state.get("claude_model", "claude-sonnet-4-20250514"),
            max_tokens=1000,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": msg}],
        )
        text = "\n".join(getattr(b, "text", "") for b in resp.content if getattr(b, "text", ""))
        m = re.search(r"\{.*\}", text, re.S)
        return json.loads(m.group(0) if m else text)
    except Exception as e:
        return {"part1": [], "part2": [], "error": str(e)}


def claude_explain_result(result: SPResult, issues: List[Issue], chain: List[CauseLine]) -> str:
    client = get_claude_client()
    if client is None:
        return result.explanation

    system = """You explain death-certificate validation results to a doctor.
Do not add medical facts not provided by backend. Keep it concise and clinically clear."""
    payload = {
        "result": asdict(result),
        "issues": [asdict(i) for i in issues],
        "chain": [asdict(c) for c in chain],
    }
    try:
        resp = client.messages.create(
            model=st.session_state.get("claude_model", "claude-sonnet-4-20250514"),
            max_tokens=600,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        return "\n".join(getattr(b, "text", "") for b in resp.content if getattr(b, "text", "")).strip()
    except Exception:
        return result.explanation


# =============================================================================
# SP1–SP8 rule engine
# =============================================================================

def form_validation(part1: List[CauseLine], part2: List[CauseLine]) -> List[Issue]:
    issues: List[Issue] = []

    filled_part1 = [x for x in part1 if x.cause.strip()]
    filled_part2 = [x for x in part2 if x.cause.strip()]

    if not part1[0].cause.strip():
        issues.append(Issue("error", "Form", "Part I-a", "Immediate cause of death is required.", True))

    # no skipped lines
    seen_empty = False
    for x in part1:
        if not x.cause.strip():
            seen_empty = True
        elif seen_empty:
            issues.append(Issue("error", "Form", f"Part I-{x.line}", "Do not skip Part I lines. Fill causes consecutively from line a.", True))

    # duplicate conditions
    seen: Dict[str, str] = {}
    for x in filled_part1 + filled_part2:
        key = norm(x.cause)
        if key in seen:
            issues.append(Issue("warning", "Form", x.line, f"Duplicate condition also appears in {seen[key]}.", False))
        else:
            seen[key] = x.line

    # multiple conditions in one line
    for x in filled_part1 + filled_part2:
        if re.search(r"\s+(and|with|plus)\s+|;|/", norm(x.cause)):
            issues.append(Issue("warning", "Form", x.line, "This line may contain more than one condition. Prefer one disease/condition per line.", False))

    # durations
    for x in filled_part1 + filled_part2:
        if not x.interval.strip():
            issues.append(Issue("info", "Form", x.line, "Approximate interval is missing. Add duration or write 'unknown'.", False))
        elif re.fullmatch(r"\d+", x.interval.strip()):
            issues.append(Issue("warning", "Form", x.line, "Interval has a number but no unit. Use e.g., 2 hours, 5 days, 1 year.", False))

    if not filled_part1 and not filled_part2:
        issues.append(Issue("error", "Form", "Certificate", "No causes have been entered.", True))

    return issues


def select_best_candidate(candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    return candidates[0] if candidates else None


def enrich_lines_with_icd(
    part1: List[CauseLine],
    part2: List[CauseLine],
    icd_df: Optional[pd.DataFrame],
    patient_sex: str,
) -> Tuple[List[CauseLine], Dict[str, List[Dict[str, Any]]], List[Issue]]:
    all_candidates: Dict[str, List[Dict[str, Any]]] = {}
    issues: List[Issue] = []

    new_part1 = []
    for i, line in enumerate(part1):
        role = "immediate" if i == 0 else ("underlying" if line.cause.strip() and i == max([j for j, v in enumerate(part1) if v.cause.strip()] or [i]) else "contributing")
        line.role = role
        if line.cause.strip() and not line.code.strip():
            cands = icd_rag_match(icd_df, line.cause, patient_sex, role=role, top_k=8)
            all_candidates[line.line] = cands
            best = select_best_candidate(cands)
            if best:
                line.code = best["code"]
                line.description = best["description"]
                issues.extend(validate_icd_candidate(best, role, patient_sex, st.session_state.get("patient_age", 0)))
            else:
                issues.append(Issue("warning", "ICD", line.line, "No ICD candidate found from the loaded ICD source.", False))
        elif line.cause.strip() and line.code.strip():
            cands = icd_rag_match(icd_df, line.code, patient_sex, role=role, top_k=3)
            all_candidates[line.line] = cands
            if cands:
                line.description = cands[0]["description"]
                issues.extend(validate_icd_candidate(cands[0], role, patient_sex, st.session_state.get("patient_age", 0)))
            else:
                issues.append(Issue("error", "ICD", line.line, f"Selected ICD code {line.code} was not found in source.", True))
        new_part1.append(line)

    new_part2 = []
    for i, line in enumerate(part2, start=1):
        line.role = "other"
        key = f"II-{i}"
        if line.cause.strip() and not line.code.strip():
            cands = icd_rag_match(icd_df, line.cause, patient_sex, role="other", top_k=8)
            all_candidates[key] = cands
            best = select_best_candidate(cands)
            if best:
                line.code = best["code"]
                line.description = best["description"]
                issues.extend(validate_icd_candidate(best, "other", patient_sex, st.session_state.get("patient_age", 0)))
            else:
                issues.append(Issue("warning", "ICD", key, "No ICD candidate found from the loaded ICD source.", False))
        elif line.cause.strip() and line.code.strip():
            cands = icd_rag_match(icd_df, line.code, patient_sex, role="other", top_k=3)
            all_candidates[key] = cands
            if cands:
                line.description = cands[0]["description"]
                issues.extend(validate_icd_candidate(cands[0], "other", patient_sex, st.session_state.get("patient_age", 0)))
            else:
                issues.append(Issue("error", "ICD", key, f"Selected ICD code {line.code} was not found in source.", True))
        new_part2.append(line)

    return new_part1, new_part2, all_candidates, issues


def evaluate_sequence(part1: List[CauseLine], tabb_df: Optional[pd.DataFrame]) -> Tuple[bool, List[str], List[Issue]]:
    filled = [x for x in part1 if x.cause.strip()]
    messages: List[str] = []
    issues: List[Issue] = []

    if len(filled) <= 1:
        return True, ["Single Part I line; no sequence comparison needed."], issues

    all_valid = True
    # Medical chain: lowest line should cause line above it.
    for upper, lower in zip(reversed(filled[:-1]), reversed(filled[1:])):
        # Actually for filled [a,b,c], compare c→b then b→a
        ok, msg = tabb_relation_exists(tabb_df, lower.code, upper.code)
        messages.append(msg)
        if not ok:
            all_valid = False
            issues.append(Issue("warning", "Sequence", f"{lower.line} → {upper.line}", msg, False))

    return all_valid, messages, issues


def apply_sp_rules(
    part1: List[CauseLine],
    part2: List[CauseLine],
    icd_df: Optional[pd.DataFrame],
    tabb_df: Optional[pd.DataFrame],
    patient_sex: str,
) -> Tuple[SPResult, List[Issue], List[str]]:
    issues: List[Issue] = []
    tabb_messages: List[str] = []

    filled_part1 = [x for x in part1 if x.cause.strip()]
    filled_part2 = [x for x in part2 if x.cause.strip()]
    all_filled = filled_part1 + filled_part2

    if not all_filled:
        return SPResult(applied_rule="None", explanation="No causes entered."), [Issue("error", "SP", "Certificate", "No causes entered.", True)], []

    selected: Optional[CauseLine] = None
    rejected: List[Dict[str, str]] = []

    # SP1
    if len(all_filled) == 1:
        selected = all_filled[0]
        rule = "SP1"
        explanation = "Only one condition is reported on the certificate; it becomes the starting point."

    # SP2
    elif len(filled_part1) == 1:
        selected = filled_part1[0]
        rule = "SP2"
        explanation = "Only one line is used in Part I; that line becomes the starting point."

    else:
        # SP3
        seq_valid, seq_messages, seq_issues = evaluate_sequence(part1, tabb_df)
        tabb_messages.extend(seq_messages)
        issues.extend(seq_issues)

        if seq_valid:
            selected = filled_part1[-1]
            rule = "SP3"
            explanation = "The first cause on the lowest used Part I line explains the conditions above; a valid causal sequence is detected."
        else:
            # SP4: find longest partial chain ending at terminal condition (line a)
            # Simple approximation: choose the lowest line in the longest valid suffix reaching line a.
            selected = None
            for start_idx in range(len(filled_part1) - 1, 0, -1):
                subset = filled_part1[: start_idx + 1]
                ok, msgs, _ = evaluate_sequence(subset, tabb_df)
                if ok:
                    selected = subset[-1]
                    break
            if selected:
                rule = "SP4"
                explanation = "No full sequence explains all entries, but a partial sequence ending with the terminal condition was found."
            else:
                # SP5
                selected = filled_part1[0]
                rule = "SP5"
                explanation = "No causal sequence was established in Part I; first-mentioned condition rule applied."

    if selected is None:
        selected = all_filled[0]
        rule = "SP5"
        explanation = "Fallback: first-mentioned condition selected."

    # SP7: ill-defined selected condition
    selected_text = norm(selected.cause)
    selected_candidate = {
        "code": selected.code,
        "description": selected.description,
        "classification": "",
        "note": "",
        "acceptable_main": "",
    }
    is_ill = (
        selected_text in DEFAULT_ILL_DEFINED_TERMS or
        selected.code.upper().startswith("R") or
        is_ill_defined_row(selected_candidate)
    )
    if is_ill:
        rejected.append({"condition": selected.cause, "reason": "Ill-defined/vague or terminal mechanism."})
        more_specific = None
        # Prefer lower Part I lines, then Part II, with non-ill-defined and acceptable-looking codes.
        for cand in reversed(filled_part1):
            if cand is selected:
                continue
            if norm(cand.cause) not in DEFAULT_ILL_DEFINED_TERMS and not cand.code.upper().startswith("R"):
                more_specific = cand
                break
        if more_specific is None:
            for cand in filled_part2:
                if norm(cand.cause) not in DEFAULT_ILL_DEFINED_TERMS and not cand.code.upper().startswith("R"):
                    more_specific = cand
                    break
        if more_specific:
            selected = more_specific
            rule = f"{rule}+SP7"
            explanation += " SP7 correction applied because the initially selected condition was ill-defined; a more specific condition was selected."
            issues.append(Issue("warning", "SP7", selected.line, "SP7 correction applied to avoid ill-defined UCOD.", False))
        else:
            issues.append(Issue("warning", "SP7", selected.line, "Selected starting point appears ill-defined; coder review required.", False))

    # SP8: trivial/unlikely condition
    if norm(selected.cause) in DEFAULT_UNLIKELY_TERMS or is_trivial_by_tabb(tabb_df, selected.code):
        rejected.append({"condition": selected.cause, "reason": "Trivial/unlikely to cause death."})
        replacement = None
        for cand in filled_part1 + filled_part2:
            if cand is not selected and norm(cand.cause) not in DEFAULT_UNLIKELY_TERMS:
                replacement = cand
                break
        if replacement:
            selected = replacement
            rule = f"{rule}+SP8"
            explanation += " SP8 correction applied because the selected condition was trivial/unlikely to cause death."
        else:
            issues.append(Issue("warning", "SP8", selected.line, "Selected condition may be unlikely to cause death; coder review required.", False))

    # SP6: obvious cause heuristic (use cautiously)
    # If cancer/trauma/sepsis exists elsewhere and current selected is terminal/vague, prefer specific disease/injury.
    obvious_keywords = ["cancer", "malignant", "carcinoma", "trauma", "injury", "sepsis", "pneumonia", "stroke", "myocardial infarction"]
    if norm(selected.cause) in DEFAULT_ILL_DEFINED_TERMS:
        for cand in filled_part1 + filled_part2:
            if any(k in norm(cand.cause) for k in obvious_keywords):
                rejected.append({"condition": selected.cause, "reason": "Replaced by obvious more specific cause."})
                selected = cand
                rule = f"{rule}+SP6"
                explanation += " SP6 correction applied because a medically obvious specific cause was present."
                break

    # Final ICD validation for selected UCOD
    final_candidates = icd_rag_match(icd_df, selected.code or selected.cause, patient_sex, role="underlying", top_k=1)
    if final_candidates:
        issues.extend(validate_icd_candidate(final_candidates[0], "underlying", patient_sex, st.session_state.get("patient_age", 0)))

    blocking = any(i.blocking for i in issues)
    serious = any(i.severity in {"error", "warning"} for i in issues)
    if blocking:
        confidence = "Low"
    elif serious:
        confidence = "Medium"
    else:
        confidence = "High"

    result = SPResult(
        starting_point_line=selected.line,
        starting_point_condition=selected.cause,
        starting_point_code=display_code(selected.code),
        ucod_condition=selected.cause,
        ucod_code=display_code(selected.code),
        applied_rule=rule,
        explanation=explanation,
        rejected_conditions=rejected,
        confidence=confidence,
        human_review_required=confidence != "High",
    )
    return result, issues, tabb_messages


# =============================================================================
# Session state
# =============================================================================

def init_state() -> None:
    defaults = {
        "patient_age": 0,
        "patient_sex": "Unknown",
        "anthropic_api_key": "",
        "claude_model": "claude-sonnet-4-20250514",
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


init_state()


# =============================================================================
# Sidebar
# =============================================================================

with st.sidebar:
    st.markdown("### System Settings")
    st.session_state["anthropic_api_key"] = st.text_input(
        "Claude API key",
        value=st.session_state.get("anthropic_api_key", ""),
        type="password",
        help="Optional. Used only for narrative extraction and explanation."
    )
    st.session_state["claude_model"] = st.text_input("Claude model", value=st.session_state.get("claude_model", "claude-sonnet-4-20250514"))

    st.markdown("---")
    st.markdown("### Data Sources")
    icd_upload = st.file_uploader("Upload ICD Excel/CSV", type=["xlsx", "xls", "csv"])
    tabb_upload = st.file_uploader("Upload parsed TABB CSV", type=["csv"])

    use_tabb = st.checkbox("Enable TABB rule lookup", value=True)
    use_claude_explain = st.checkbox("Use Claude for final explanation", value=False)
    st.caption("Claude does not decide UCOD. It only extracts/explains. Backend rules decide.")

    st.markdown("---")
    st.markdown("### Validation Behavior")
    live_validate = st.checkbox("Run live validation", value=True)
    block_submit = st.checkbox("Block critical errors on submit", value=True)


icd_df = load_icd_from_upload_or_path(
    icd_upload,
    [
        "ICD10_Enriched_Final.xlsx",
        "/mnt/data/ICD10_Enriched_Final(4).xlsx",
        "/mnt/data/ICD10_Enriched_Final.xlsx",
    ],
)
tabb_df = load_tabb_from_upload_or_path(
    tabb_upload,
    [
        "tabb_rules_clean.csv",
        "tabb_rules.csv",
        "/mnt/data/tabb_rules_clean.csv",
        "/mnt/data/tabb_rules.csv",
    ],
) if use_tabb else None


# =============================================================================
# Header
# =============================================================================

st.markdown(
    """
<div class="moh-header">
  <h1>Electronic Death Certificate System</h1>
  <p>Saudi MOH-style workflow · AI-assisted extraction · Deterministic SP1–SP8 validation · ICD/TABB rule support</p>
</div>
""",
    unsafe_allow_html=True,
)

status_bits = []
status_bits.append(pill("ICD loaded" if icd_df is not None else "ICD not loaded", "green" if icd_df is not None else "red"))
status_bits.append(pill("TABB loaded" if tabb_df is not None else "TABB not loaded", "green" if tabb_df is not None else "yellow"))
status_bits.append(pill("Claude available" if get_claude_client() else "Claude optional/off", "blue" if get_claude_client() else "gray"))
st.markdown(" ".join(status_bits), unsafe_allow_html=True)

if icd_df is None:
    st.warning("Load the ICD Excel/CSV file to enable code suggestions and acceptability checks.")
if use_tabb and tabb_df is None:
    st.info("TABB CSV not loaded. SP logic will still run, but causal sequence validation will be weaker.")


# =============================================================================
# Main layout
# =============================================================================

left, right = st.columns([1.62, 0.95], gap="large")


with left:
    st.markdown("<div class='card'><h3>1. Patient and Hospital Information</h3>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    with c1:
        cert_no = st.text_input("Certificate number", value="MOH-DC-0001")
        patient_name = st.text_input("Patient name", value="")
        national_id = st.text_input("National ID / MRN", value="")
    with c2:
        age = st.number_input("Age in years", min_value=0, max_value=130, value=int(st.session_state.get("patient_age", 0)))
        sex = st.selectbox("Sex", ["Unknown", "Male", "Female"], index=["Unknown", "Male", "Female"].index(st.session_state.get("patient_sex", "Unknown")))
        death_date = st.date_input("Date of death")
    with c3:
        hospital = st.text_input("Hospital", value="King Fahad Specialist Hospital")
        city = st.text_input("City", value="Riyadh")
        physician = st.text_input("Certifying physician", value="")
    st.session_state["patient_age"] = int(age)
    st.session_state["patient_sex"] = sex
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='card'><h3>2. Part I — Direct Causal Chain</h3><div class='small-muted'>Enter one disease or condition per line. Line (a) is required and cannot be skipped.</div>", unsafe_allow_html=True)

    part1: List[CauseLine] = []
    labels = [
        ("a", "Immediate cause of death"),
        ("b", "Due to"),
        ("c", "Due to"),
        ("d", "Due to"),
    ]

    for line_id, label in labels:
        st.markdown(f"<div class='line-label'>Part I-{line_id}: {label}</div>", unsafe_allow_html=True)
        cc1, cc2, cc3 = st.columns([2.5, 0.85, 1.05])
        with cc1:
            cause = st.text_input(f"Cause {line_id}", key=f"cause_{line_id}", label_visibility="collapsed", placeholder=label)
        with cc2:
            interval = st.text_input(f"Interval {line_id}", key=f"interval_{line_id}", label_visibility="collapsed", placeholder="e.g., 2 days")
        with cc3:
            code_manual = st.text_input(f"ICD code {line_id}", key=f"code_{line_id}", label_visibility="collapsed", placeholder="Auto / manual")
        part1.append(CauseLine(line=line_id, part="I", cause=cause, interval=interval, code=norm_code(code_manual), role=""))

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='card'><h3>3. Part II — Other Significant Conditions</h3><div class='small-muted'>Conditions that contributed to death but were not part of the direct sequence.</div>", unsafe_allow_html=True)
    part2: List[CauseLine] = []
    for i in range(1, 4):
        cc1, cc2, cc3 = st.columns([2.5, 0.85, 1.05])
        with cc1:
            cause = st.text_input(f"Part II condition {i}", key=f"part2_cause_{i}", placeholder="Other significant condition")
        with cc2:
            interval = st.text_input(f"Part II interval {i}", key=f"part2_interval_{i}", placeholder="Duration")
        with cc3:
            code_manual = st.text_input(f"Part II ICD {i}", key=f"part2_code_{i}", placeholder="Auto / manual")
        part2.append(CauseLine(line=f"II-{i}", part="II", cause=cause, interval=interval, code=norm_code(code_manual), role="other"))
    st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("Optional: paste narrative and let Claude fill structure"):
        narrative = st.text_area("Doctor narrative", height=140, placeholder="Example: The patient died from cardiac arrest due to septic shock due to pneumonia. Diabetes mellitus contributed.")
        if st.button("Extract from narrative using Claude", disabled=get_claude_client() is None):
            extracted = claude_extract_narrative(narrative)
            if extracted.get("error"):
                st.error(extracted["error"])
            else:
                for i, item in enumerate(extracted.get("part1", [])[:4]):
                    line_id = labels[i][0]
                    st.session_state[f"cause_{line_id}"] = item.get("cause", "")
                    st.session_state[f"interval_{line_id}"] = item.get("interval", "")
                    st.session_state[f"code_{line_id}"] = ""
                for i, item in enumerate(extracted.get("part2", [])[:3], start=1):
                    st.session_state[f"part2_cause_{i}"] = item.get("cause", "")
                    st.session_state[f"part2_interval_{i}"] = item.get("interval", "")
                    st.session_state[f"part2_code_{i}"] = ""
                st.rerun()

    submit = st.button("Run Final Validation / Prepare Review", type="primary", use_container_width=True)


# =============================================================================
# Validation computation
# =============================================================================

form_issues = form_validation(part1, part2)
icd_issues: List[Issue] = []
candidate_map: Dict[str, List[Dict[str, Any]]] = {}

enriched_part1 = part1
enriched_part2 = part2

if live_validate or submit:
    enriched_part1, enriched_part2, candidate_map, icd_issues = enrich_lines_with_icd(part1, part2, icd_df, sex)

sp_result, sp_issues, tabb_messages = apply_sp_rules(enriched_part1, enriched_part2, icd_df, tabb_df, sex)
all_issues = form_issues + icd_issues + sp_issues

if use_claude_explain and (submit or st.session_state.get("last_explain", False)):
    sp_result.explanation = claude_explain_result(sp_result, all_issues, enriched_part1 + enriched_part2)


# =============================================================================
# Right panel
# =============================================================================

with right:
    # Box 1
    st.markdown("<div class='right-card'><h4>1. Validation Summary</h4>", unsafe_allow_html=True)
    blocking_count = sum(1 for i in all_issues if i.blocking or i.severity == "error")
    warning_count = sum(1 for i in all_issues if i.severity == "warning")
    info_count = sum(1 for i in all_issues if i.severity == "info")

    summary_pills = [
        pill(f"{blocking_count} critical", "red" if blocking_count else "green"),
        pill(f"{warning_count} warnings", "yellow" if warning_count else "green"),
        pill(f"{info_count} notes", "blue" if info_count else "gray"),
    ]
    st.markdown(" ".join(summary_pills), unsafe_allow_html=True)

    if all_issues:
        for issue in all_issues[:7]:
            issue_box(issue)
        if len(all_issues) > 7:
            st.caption(f"+ {len(all_issues)-7} more issues shown in review section.")
    else:
        st.markdown("<div class='ok-box'><b>✓ No active validation issues</b><br>The form is currently clean.</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # Box 2
    st.markdown("<div class='right-card'><h4>2. Suggested UCOD</h4>", unsafe_allow_html=True)
    if sp_result.ucod_condition:
        st.markdown(f"<div class='metric-big'>{html_escape(sp_result.ucod_condition)}</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='ucod-code'>{html_escape(sp_result.ucod_code or 'No code')}</div>", unsafe_allow_html=True)
        st.markdown(pill(f"Rule: {sp_result.applied_rule}", "blue"), unsafe_allow_html=True)
        st.markdown(
            f"<div class='chain'><b>Part I chain:</b><br>" +
            "<br>↓<br>".join(html_escape(x.cause or "—") for x in reversed([x for x in enriched_part1 if x.cause.strip()])) +
            "</div>",
            unsafe_allow_html=True,
        )
    else:
        st.info("Enter Part I causes to generate a suggested UCOD.")
    st.markdown("</div>", unsafe_allow_html=True)

    # Box 3
    st.markdown("<div class='right-card'><h4>3. Confidence / Review Status</h4>", unsafe_allow_html=True)
    conf_kind = {"High": "green", "Medium": "yellow", "Low": "red"}.get(sp_result.confidence, "gray")
    st.markdown(pill(f"Confidence: {sp_result.confidence}", conf_kind), unsafe_allow_html=True)
    st.markdown(
        pill("Coder review required" if sp_result.human_review_required else "Coder review optional", "yellow" if sp_result.human_review_required else "green"),
        unsafe_allow_html=True,
    )
    if any(i.blocking for i in all_issues):
        st.markdown("<div class='error-box'><b>Submission blocked</b><br>Resolve critical errors first.</div>", unsafe_allow_html=True)
    elif warning_count:
        st.markdown("<div class='warning-box'><b>Needs attention</b><br>Certificate can be reviewed, but warnings should be checked.</div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='ok-box'><b>Ready for review</b><br>No critical warnings detected.</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # Box 4
    st.markdown("<div class='right-card'><h4>4. Explanation / Notes</h4>", unsafe_allow_html=True)
    st.write(sp_result.explanation or "No explanation yet.")
    if sp_result.rejected_conditions:
        st.markdown("**Rejected / corrected causes**")
        for r in sp_result.rejected_conditions:
            st.markdown(f"- **{r.get('condition','')}** — {r.get('reason','')}")
    with st.expander("TABB lookup notes"):
        if tabb_messages:
            for msg in tabb_messages:
                st.caption(msg)
        else:
            st.caption("No TABB notes available.")
    st.markdown("</div>", unsafe_allow_html=True)


# =============================================================================
# Review / candidate details
# =============================================================================

st.markdown("---")
tab1, tab2, tab3, tab4 = st.tabs(["ICD Candidates", "Final Review", "Audit JSON", "Developer Notes"])

with tab1:
    st.subheader("Retrieved ICD candidates")
    if not candidate_map:
        st.info("No candidates yet. Enter causes or load ICD source.")
    for line_key, cands in candidate_map.items():
        st.markdown(f"### {line_key}")
        if not cands:
            st.warning("No candidates retrieved.")
            continue
        df_show = pd.DataFrame(cands)[["code_display", "description", "acceptable_main", "classification", "score"]]
        st.dataframe(df_show, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Final Review")
    if submit and block_submit and any(i.blocking or i.severity == "error" for i in all_issues):
        st.error("Final validation found critical errors. Please correct them before issuing the certificate.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Selected Starting Point / UCOD")
            st.markdown(f"**Starting Point:** {sp_result.starting_point_condition or '—'}")
            st.markdown(f"**Starting Point Code:** {sp_result.starting_point_code or '—'}")
            st.markdown(f"**Suggested UCOD:** {sp_result.ucod_condition or '—'}")
            st.markdown(f"**UCOD Code:** {sp_result.ucod_code or '—'}")
            st.markdown(f"**Applied Rule:** {sp_result.applied_rule or '—'}")
            st.markdown(f"**Confidence:** {sp_result.confidence}")

        with c2:
            st.markdown("#### Confirmation")
            doctor_confirm = st.checkbox("Doctor confirms the suggested UCOD", value=False)
            coder_confirm = st.checkbox("Coder confirms / reviewed", value=False)
            override = st.checkbox("Manual override")
            override_reason = ""
            if override:
                override_code = st.text_input("Override UCOD ICD code")
                override_condition = st.text_input("Override UCOD condition")
                override_reason = st.text_area("Required override reason")
                if not override_reason.strip():
                    st.warning("Override reason is required.")

        st.markdown("#### Issues")
        if all_issues:
            for issue in all_issues:
                issue_box(issue)
        else:
            st.success("No issues detected.")

        audit_payload = {
            "certificate_no": cert_no,
            "patient": {
                "name": patient_name,
                "national_id": national_id,
                "age": int(age),
                "sex": sex,
                "death_date": str(death_date),
            },
            "hospital": {
                "name": hospital,
                "city": city,
                "physician": physician,
            },
            "part1": [asdict(x) for x in enriched_part1],
            "part2": [asdict(x) for x in enriched_part2],
            "sp_result": asdict(sp_result),
            "issues": [asdict(i) for i in all_issues],
            "tabb_messages": tabb_messages,
            "confirmations": {
                "doctor_confirmed": bool(doctor_confirm),
                "coder_confirmed": bool(coder_confirm),
                "manual_override": bool(override),
                "override_reason": override_reason,
            },
            "data_sources": {
                "icd_loaded": icd_df is not None,
                "tabb_loaded": tabb_df is not None,
            },
        }

        st.download_button(
            "Download audit JSON",
            data=json.dumps(audit_payload, ensure_ascii=False, indent=2),
            file_name=f"{cert_no or 'death_certificate'}_audit.json",
            mime="application/json",
            use_container_width=True,
        )

with tab3:
    audit_payload_live = {
        "part1": [asdict(x) for x in enriched_part1],
        "part2": [asdict(x) for x in enriched_part2],
        "sp_result": asdict(sp_result),
        "issues": [asdict(i) for i in all_issues],
        "tabb_messages": tabb_messages,
    }
    st.markdown(f"<pre class='audit-json'>{html_escape(json.dumps(audit_payload_live, ensure_ascii=False, indent=2))}</pre>", unsafe_allow_html=True)

with tab4:
    st.markdown(
        """
### Implementation notes

- **One main Claude agent** is enough. Do not use multiple agents for clinical decisions.
- Claude can extract narrative text and explain backend results.
- Claude must not invent ICD codes or select UCOD without backend validation.
- ICD RAG returns candidates from the loaded ICD file only.
- TABB should be parsed into CSV/SQLite and queried symbolically, not embedded as text.
- SP1–SP8 logic is deterministic and auditable.
- The UI intentionally uses a left form + right validation assistant panel.
- Critical errors should block submission; warnings require review.
"""
    )
