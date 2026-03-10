"""
Saudi Ministry of Health – Electronic Death Certificate System
نظام شهادة الوفاة الإلكترونية – وزارة الصحة السعودية
"""

import streamlit as st
import pandas as pd
import numpy as np
import json
import re
import datetime
import io
import os
import pickle

import anthropic

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="شهادة الوفاة | وزارة الصحة",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@300;400;500;700;800&family=Cairo:wght@400;600;700&display=swap');

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
}

html, body, [class*="css"] {
  font-family: 'Tajawal', 'Cairo', sans-serif;
  direction: rtl;
  color: var(--text);
}

.main .block-container {
  background: var(--gray-bg);
  padding: 1.5rem 2rem;
  max-width: 1200px;
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
.moh-header p  { font-size: .82rem; margin: .2rem 0 0; opacity: .8; }
.moh-emblem {
  width: 70px; height: 70px;
  border: 2px solid rgba(200,169,81,.5);
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
  letter-spacing: .03em;
}

.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div > div {
  border: 1.5px solid var(--border) !important;
  border-radius: 6px !important;
  font-family: 'Tajawal', sans-serif !important;
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
  font-family: 'Tajawal', sans-serif;
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
}
.step { background:#d4ddd6; color:#5a7060; border-radius:20px; padding:5px 16px; font-size:.8rem; font-weight:600; }
.step.active { background:var(--green); color:white; }
.step.done   { background:var(--gold);  color:white; }

.icd-card {
  background: var(--green-light);
  border: 1px solid #9ecaad;
  border-radius: 6px;
  padding: .85rem 1.1rem;
  margin: .45rem 0;
}
.icd-code  { font-size:1.05rem; font-weight:800; color:var(--green); font-family:'Courier New',monospace; letter-spacing:.05em; }
.icd-badge { display:inline-block; background:var(--green); color:white; border-radius:20px; padding:1px 10px; font-size:.7rem; margin:0 2px; font-weight:600; }
.icd-desc  { color:#2a4a2e; font-size:.88rem; margin-top:.2rem; }

.cert-preview {
  background: white;
  border: 2px solid var(--green);
  border-radius: 8px;
  padding: 2.2rem;
  font-family: 'Tajawal', sans-serif;
  box-shadow: 0 4px 20px rgba(0,105,64,.1);
}
.cert-title { font-size:1.6rem; font-weight:800; color:var(--green); }
.cert-sub   { color:var(--muted); font-size:.88rem; }
.cert-field { display:flex; justify-content:space-between; border-bottom:1px solid #e8ede9; padding:.36rem 0; font-size:.88rem; }
.cert-label { font-weight:700; color:var(--green); min-width:155px; }
.cert-stamp {
  border:2px solid var(--green); border-radius:50%;
  width:86px; height:86px;
  display:flex; align-items:center; justify-content:center;
  color:var(--green); font-weight:700; text-align:center; font-size:.65rem; line-height:1.5;
}

.stTabs [data-baseweb="tab"] { font-family:'Tajawal',sans-serif !important; font-weight:600; font-size:.88rem; }
.stTabs [aria-selected="true"] { color:var(--green) !important; border-bottom-color:var(--green) !important; }
</style>
""", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div class="moh-header">
  <div>
    <h1>نظام شهادة الوفاة الإلكترونية</h1>
    <p>وزارة الصحة &nbsp;|&nbsp; المملكة العربية السعودية</p>
    <p style="font-size:.76rem;opacity:.65">Death Certificate Registration System &nbsp;|&nbsp; ICD-10 AI-Assisted Coding</p>
  </div>
  <div class="moh-emblem">وزارة<br>الصحة<br>MOH<br>KSA</div>
</div>
""", unsafe_allow_html=True)

# ── API key from secrets ──────────────────────────────────────────────────────
try:
    API_KEY = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    st.error("مفتاح API غير موجود. يرجى إضافة ANTHROPIC_API_KEY في Streamlit Secrets.")
    st.stop()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### اعدادات النظام")
    st.markdown("---")

    st.markdown("### مصدر بيانات ICD-10")
    data_source = st.radio(
        "اختر مصدر البيانات",
        ["Google Drive", "رفع ملف Excel"],
        label_visibility="collapsed",
    )

    if data_source == "Google Drive":
        drive_meta  = st.text_input(
            "مسار metadata.pkl",
            value="/content/drive/MyDrive/ICD10_RAG/metadata.pkl",
        )
        drive_index = st.text_input(
            "مسار faiss_index.bin",
            value="/content/drive/MyDrive/ICD10_RAG/faiss_index.bin",
        )
        load_btn = st.button("تحميل من Drive", use_container_width=True)
    else:
        uploaded_excel = st.file_uploader("رفع ICD10_Enriched_Final.xlsx", type=["xlsx"])
        load_btn       = False
        drive_meta     = ""
        drive_index    = ""

    st.markdown("---")
    st.markdown("### بيانات المستشفى")
    hospital_name = st.text_input("اسم المستشفى", value="مستشفى الملك فهد التخصصي")
    hospital_city = st.text_input("المدينة", value="الرياض")
    doctor_name   = st.text_input("اسم الطبيب المُصدر", value="")

    st.markdown("---")
    st.markdown(
        '<div style="font-size:.7rem;opacity:.55;text-align:center;line-height:2">'
        'وزارة الصحة – 1446هـ<br>الإصدار 2.1</div>',
        unsafe_allow_html=True,
    )

# ── Session state ──────────────────────────────────────────────────────────────
for k, v in [("page", 1), ("form_data", {}), ("icd_results", None),
             ("df_icd", None), ("faiss_index", None)]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── ICD loaders ───────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="جارٍ تحميل بيانات ICD-10...")
def load_from_excel(file_bytes: bytes) -> pd.DataFrame:
    df = pd.read_excel(io.BytesIO(file_bytes))
    df.columns = ["Id","Code","CodeFormatted","ShortDesc","LongDesc",
                  "HIPPA","Deleted","Classification","AcceptableMain",
                  "GenderRestriction","MatchSource","MatchedFromCode","Note"]
    df = df[df["Deleted"] != "Yes"].dropna(subset=["Code"]).reset_index(drop=True)
    df["EmbedText"] = (df["CodeFormatted"].fillna("") + " | " +
                       df["LongDesc"].fillna("") + " | " +
                       df["ShortDesc"].fillna(""))
    return df

@st.cache_resource(show_spinner="جارٍ تحميل البيانات من Google Drive...")
def load_from_drive(meta_path: str, index_path: str):
    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"الملف غير موجود: {meta_path}")
    with open(meta_path, "rb") as f:
        df = pickle.load(f)
    # Normalise columns if needed
    if "CodeFormatted" not in df.columns and "Code (Formatted)" in df.columns:
        df.columns = ["Id","Code","CodeFormatted","ShortDesc","LongDesc",
                      "HIPPA","Deleted","Classification","AcceptableMain",
                      "GenderRestriction","MatchSource","MatchedFromCode","Note"]
    if "EmbedText" not in df.columns:
        df["EmbedText"] = (df["CodeFormatted"].fillna("") + " | " +
                           df["LongDesc"].fillna("") + " | " +
                           df["ShortDesc"].fillna(""))
    faiss_idx = None
    if index_path and os.path.exists(index_path):
        try:
            import faiss
            faiss_idx = faiss.read_index(index_path)
        except ImportError:
            pass
    return df, faiss_idx

def _row_to_dict(row, score: float) -> dict:
    return {
        "code":               str(row.get("Code", "")),
        "code_formatted":     str(row.get("CodeFormatted", "")),
        "short_desc":         str(row.get("ShortDesc", "")),
        "long_desc":          str(row.get("LongDesc", "")),
        "acceptable_main":    str(row.get("AcceptableMain", "")),
        "gender_restriction": str(row.get("GenderRestriction", "")),
        "classification":     str(row.get("Classification", "")),
        "similarity":         score,
    }

@st.cache_resource(show_spinner="تحميل نموذج التضمين...")
def _embed_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")

def search_icd(df, fidx, query: str, top_k: int = 6) -> list:
    if fidx is not None:
        try:
            model = _embed_model()
            q_vec = model.encode([query], normalize_embeddings=True,
                                 convert_to_numpy=True).astype("float32")
            scores, indices = fidx.search(q_vec, top_k)
            return [_row_to_dict(df.iloc[idx], float(s))
                    for s, idx in zip(scores[0], indices[0]) if idx != -1]
        except Exception:
            pass
    # Keyword fallback
    terms  = query.lower().split()
    scores = df["EmbedText"].str.lower().apply(lambda x: sum(t in x for t in terms))
    top    = scores.nlargest(top_k).index
    return [_row_to_dict(df.iloc[i], float(scores[i])) for i in top if scores[i] > 0]

# ── Trigger loaders ───────────────────────────────────────────────────────────
if data_source == "Google Drive" and load_btn:
    try:
        df, fidx = load_from_drive(drive_meta, drive_index)
        st.session_state.df_icd      = df
        st.session_state.faiss_index = fidx
        mode = "FAISS" if fidx is not None else "keyword"
        st.sidebar.success(f"تم تحميل {len(df):,} رمز  ({mode})")
    except Exception as e:
        st.sidebar.error(f"خطأ: {e}")

elif data_source == "رفع ملف Excel":
    if "uploaded_excel" in dir() and uploaded_excel and st.session_state.df_icd is None:
        df = load_from_excel(uploaded_excel.read())
        st.session_state.df_icd      = df
        st.session_state.faiss_index = None
        st.sidebar.success(f"تم تحميل {len(df):,} رمز ICD-10")

# ── Claude helpers ─────────────────────────────────────────────────────────────
def call_claude(system_prompt: str, user_content: str, max_tokens: int = 1500) -> str:
    client = anthropic.Anthropic(api_key=API_KEY)
    resp   = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    return resp.content[0].text.strip()

def extract_concepts(free_text: str, gender: str, age: str) -> dict:
    sys_p = (
        "You are a clinical coding assistant for Saudi MOH death certificates. "
        "Extract structured medical information. "
        'Return ONLY valid JSON: {"immediate_cause":"string","contributing_causes":["list"],'
        '"other_conditions":["list"],"intervals":{"immediate_cause":"hours/days",'
        '"contributing_causes":["years"]},"notes":"string"}. No markdown, no extra text.'
    )
    raw = call_claude(sys_p, f"Patient: {age}yo, {gender}.\n\n{free_text}", max_tokens=700)
    raw = re.sub(r"^```json?\s*|\s*```$", "", raw).strip()
    return json.loads(raw)

def get_recommendation(concepts: dict, candidates: dict, gender: str, age: str, extra: str) -> str:
    sys_p = (
        "You are a senior clinical coding specialist at Saudi MOH. "
        "Provide: (1) best ICD-10 code for immediate cause with justification, "
        "(2) codes for contributing causes, (3) gender/age validity warnings, "
        "(4) WHO/MOH coding rules, (5) completeness advice. "
        "Respond in Arabic with ICD codes inline. Be concise and clinically precise."
    )
    user = (
        f"Patient: {age}yo, {gender}\n{extra}\n\n"
        f"Concepts:\n{json.dumps(concepts, ensure_ascii=False, indent=2)}\n\n"
        f"Candidates:\n{json.dumps(candidates, ensure_ascii=False, indent=2)}"
    )
    return call_claude(sys_p, user, max_tokens=1200)

# ── Step bar ──────────────────────────────────────────────────────────────────
def render_steps(current: int):
    labels = ["البيانات الأساسية", "السيرة المرضية", "أسباب الوفاة", "المراجعة والتوصيات"]
    html   = '<div class="step-bar">'
    for i, lbl in enumerate(labels, 1):
        cls = "step active" if i == current else ("step done" if i < current else "step")
        html += f'<div class="{cls}">{i}. {lbl}</div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

# =============================================================================
#  PAGE 1 — Patient Basic Information
# =============================================================================
if st.session_state.page == 1:
    render_steps(1)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">البيانات الأساسية للمتوفى / Patient Basic Information</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        full_name_ar = st.text_input("الاسم الكامل (عربي)*", placeholder="محمد بن عبدالله العتيبي")
        full_name_en = st.text_input("Full Name (English)",   placeholder="Mohammed Abdullah Al-Otaibi")
        national_id  = st.text_input("رقم الهوية / الإقامة*", placeholder="1XXXXXXXXX")
        nationality  = st.text_input("الجنسية / Nationality", placeholder="سعودي")
        dob = st.date_input("تاريخ الميلاد / Date of Birth",
                            value=datetime.date(1960, 1, 1),
                            min_value=datetime.date(1900, 1, 1),
                            max_value=datetime.date.today())
    with c2:
        sex            = st.selectbox("الجنس / Sex*", ["ذكر / Male", "أنثى / Female"])
        marital_status = st.selectbox("الحالة الاجتماعية",
                                      ["أعزب / Single","متزوج / Married","مطلق / Divorced","أرمل / Widowed"])
        education      = st.selectbox("المستوى التعليمي / Education",
                                      ["أمي / Illiterate","ابتدائي / Primary","متوسط / Intermediate",
                                       "ثانوي / Secondary","دبلوم / Diploma","بكالوريوس / Bachelor",
                                       "دراسات عليا / Postgraduate","غير معلوم / Unknown"])
        occupation     = st.text_input("المهنة / Occupation", placeholder="مهندس")
        address        = st.text_input("العنوان / Address",   placeholder="الرياض – حي العليا")

    st.markdown("---")
    c3, c4 = st.columns(2)
    with c3:
        dod           = st.date_input("تاريخ الوفاة / Date of Death*", value=datetime.date.today())
        time_of_death = st.time_input("وقت الوفاة / Time of Death")
        place_of_death = st.selectbox("مكان الوفاة / Place of Death",
                                      ["المستشفى / Hospital","الطوارئ / Emergency",
                                       "المنزل / Home","الطريق / Road","غير معلوم / Unknown"])
    with c4:
        cert_number = st.text_input("رقم الشهادة / Certificate No.", placeholder="DC-2025-XXXXX")
        date_issued = st.date_input("تاريخ الإصدار / Issue Date", value=datetime.date.today())

    st.markdown('</div>', unsafe_allow_html=True)

    age_years = max(0, (dod - dob).days // 365) if dob and dod else 0
    st.info(f"العمر عند الوفاة: {age_years} سنة  /  Age at Death: {age_years} years")

    if st.button("التالي"):
        if not full_name_ar or not national_id:
            st.error("يرجى إدخال الاسم الكامل ورقم الهوية.")
        else:
            st.session_state.form_data.update({
                "full_name_ar": full_name_ar, "full_name_en": full_name_en,
                "national_id":  national_id,  "nationality":  nationality,
                "dob": str(dob), "dod": str(dod),
                "time_of_death": str(time_of_death), "place_of_death": place_of_death,
                "sex": sex, "marital_status": marital_status,
                "education": education, "occupation": occupation, "address": address,
                "age_years": age_years, "cert_number": cert_number, "date_issued": str(date_issued),
            })
            st.session_state.page = 2
            st.rerun()

# =============================================================================
#  PAGE 2 — Medical History
# =============================================================================
elif st.session_state.page == 2:
    render_steps(2)
    fd = st.session_state.form_data

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">السيرة المرضية / Medical History</div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        had_surgery = st.radio(
            "هل أجرى المريض عملية جراحية خلال آخر شهر؟ / Surgery within last month?",
            ["لا / No", "نعم / Yes", "غير معلوم / Unknown"],
        )
        surgery_details = ""
        if had_surgery == "نعم / Yes":
            surgery_details = st.text_area("تفاصيل العملية / Surgery Details",
                                           placeholder="نوع العملية، التاريخ، المستشفى")
        autopsy_required = st.radio(
            "هل التشريح مطلوب من وجهة نظر الطبيب؟ / Autopsy required (doctor)?",
            ["لا / No", "نعم / Yes", "غير محدد / Undetermined"],
        )
        autopsy_reason = ""
        if autopsy_required == "نعم / Yes":
            autopsy_reason = st.text_input("سبب طلب التشريح / Reason for autopsy")

    with c2:
        death_type     = st.selectbox("نوع الوفاة / Type of Death",
                                      ["طبيعية / Natural","حادث / Accident",
                                       "انتحار / Suicide","قتل / Homicide","غير محدد / Undetermined"])
        inpatient_days = st.number_input("مدة الإقامة بالمستشفى (أيام) / Hospital Stay (days)",
                                         min_value=0, value=0)
        was_pregnant = "لا ينطبق / N/A"
        if "أنثى" in fd.get("sex", ""):
            was_pregnant = st.selectbox("الحالة أثناء الوفاة / Pregnancy Status",
                                        ["لا / No","حامل / Pregnant",
                                         "أثناء الولادة / During delivery",
                                         "بعد الولادة 42 يوم / Within 42 days postpartum","لا ينطبق / N/A"])
        chronic_conditions = st.multiselect(
            "الأمراض المزمنة المعروفة / Known Chronic Conditions",
            ["داء السكري / Diabetes","ارتفاع ضغط الدم / Hypertension",
             "أمراض القلب / Heart Disease","أمراض الكلى / Renal Disease",
             "أمراض الكبد / Liver Disease","السرطان / Cancer",
             "أمراض الرئة / Pulmonary Disease","السمنة / Obesity",
             "أمراض عصبية / Neurological","أخرى / Other"],
        )

    st.markdown('</div>', unsafe_allow_html=True)

    b1, b2, _ = st.columns([1, 1, 6])
    with b1:
        if st.button("السابق", use_container_width=True):
            st.session_state.page = 1; st.rerun()
    with b2:
        if st.button("التالي", use_container_width=True):
            st.session_state.form_data.update({
                "had_surgery": had_surgery, "surgery_details": surgery_details,
                "autopsy_required": autopsy_required, "autopsy_reason": autopsy_reason,
                "death_type": death_type, "inpatient_days": inpatient_days,
                "was_pregnant": was_pregnant, "chronic_conditions": chronic_conditions,
            })
            st.session_state.page = 3; st.rerun()

# =============================================================================
#  PAGE 3 — Causes of Death
# =============================================================================
elif st.session_state.page == 3:
    render_steps(3)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">أسباب الوفاة / Causes of Death — WHO Format</div>', unsafe_allow_html=True)

    st.markdown("""
    <div style="background:#fffbe6;border-right:3px solid #C8A951;padding:9px 13px;
                border-radius:5px;margin-bottom:1rem;font-size:.86rem;color:#5a4a00">
    يُرجى وصف أسباب الوفاة بالتسلسل الزمني — السبب الفوري أولاً ثم الأسباب الكامنة.
    </div>
    """, unsafe_allow_html=True)

    free_text = st.text_area(
        "وصف حر لأسباب الوفاة / Free-text description (Arabic or English)",
        height=130,
        placeholder="مثال: توفي المريض إثر احتشاء عضلة القلب الحاد الناتج عن تصلب الشرايين التاجية بسبب داء السكري.",
    )

    st.markdown("أو أدخل الأسباب منفردة / Or enter separately:")
    c1, c2 = st.columns(2)
    with c1:
        cause_a    = st.text_input("(أ) السبب الفوري / Immediate Cause",  placeholder="Acute myocardial infarction")
        interval_a = st.text_input("الفترة الزمنية (أ)",                   placeholder="2 hours")
        cause_b    = st.text_input("(ب) السبب المؤدي / Underlying Cause",  placeholder="Coronary atherosclerosis")
        interval_b = st.text_input("الفترة الزمنية (ب)",                   placeholder="5 years")
    with c2:
        cause_c    = st.text_input("(ج) سبب آخر / Other Cause",            placeholder="Diabetes mellitus type 2")
        interval_c = st.text_input("الفترة الزمنية (ج)",                   placeholder="10 years")
        cause_d    = st.text_input("(د) سبب آخر / Other Cause",            placeholder="Hypertension")
        interval_d = st.text_input("الفترة الزمنية (د)",                   placeholder="15 years")

    other_cond = st.text_area(
        "حالات أخرى مساهمة / Other Contributing Conditions",
        placeholder="أمراض أخرى ساهمت في الوفاة لكنها ليست السبب المباشر",
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # Manual search
    if st.session_state.df_icd is not None:
        with st.expander("بحث يدوي في ICD-10 / Manual ICD-10 Search"):
            q = st.text_input("ابحث عن رمز أو تشخيص", placeholder="myocardial infarction, diabetes...")
            if q and len(q) >= 3:
                hits = search_icd(st.session_state.df_icd, st.session_state.faiss_index, q, top_k=8)
                if hits:
                    for r in hits:
                        col = "var(--green)" if r["acceptable_main"] == "Acceptable" else "#c0392b"
                        st.markdown(f"""
                        <div class="icd-card">
                          <span class="icd-code">{r['code_formatted']}</span>
                          <span class="icd-badge" style="background:{col}">{r['acceptable_main']}</span>
                          <span class="icd-badge">{r['gender_restriction']}</span>
                          <div class="icd-desc"><strong>{r['short_desc']}</strong></div>
                          <div style="font-size:.8rem;color:#4a6a4e">{r['long_desc']}</div>
                        </div>""", unsafe_allow_html=True)
                else:
                    st.info("لا توجد نتائج مطابقة.")
    else:
        st.warning("يرجى تحميل بيانات ICD-10 من الشريط الجانبي.")

    b1, b2, _ = st.columns([1, 1, 6])
    with b1:
        if st.button("السابق", use_container_width=True):
            st.session_state.page = 2; st.rerun()
    with b2:
        if st.button("تحليل وتوصيات", use_container_width=True):
            if not free_text and not cause_a:
                st.error("يرجى إدخال وصف أسباب الوفاة.")
            elif st.session_state.df_icd is None:
                st.error("يرجى تحميل بيانات ICD-10 أولاً.")
            else:
                st.session_state.form_data.update({
                    "free_text": free_text,
                    "cause_a": cause_a, "interval_a": interval_a,
                    "cause_b": cause_b, "interval_b": interval_b,
                    "cause_c": cause_c, "interval_c": interval_c,
                    "cause_d": cause_d, "interval_d": interval_d,
                    "other_conditions_text": other_cond,
                })
                st.session_state.page = 4; st.rerun()

# =============================================================================
#  PAGE 4 — AI Analysis & Certificate
# =============================================================================
elif st.session_state.page == 4:
    render_steps(4)
    fd = st.session_state.form_data

    # Compose combined text
    combined = fd.get("free_text", "")
    for label, ck, ik in [("Immediate", "cause_a","interval_a"),("Underlying","cause_b","interval_b"),
                           ("Other",    "cause_c","interval_c"),("Other",     "cause_d","interval_d")]:
        if fd.get(ck):
            combined += f"\n{label} cause: {fd[ck]} (interval: {fd.get(ik,'')})"
    if fd.get("other_conditions_text"):
        combined += f"\nOther conditions: {fd['other_conditions_text']}"

    gender_str = "Male" if "ذكر" in fd.get("sex","") else "Female"
    age_str    = str(fd.get("age_years","Unknown"))
    extra      = (f"Surgery last month: {fd.get('had_surgery','No')}\n"
                  f"Autopsy required: {fd.get('autopsy_required','No')}\n"
                  f"Chronic conditions: {', '.join(fd.get('chronic_conditions',[]))}")

    # Run analysis once
    if st.session_state.icd_results is None:
        with st.spinner("جارٍ تحليل أسباب الوفاة واسترجاع رموز ICD-10..."):
            try:
                concepts   = extract_concepts(combined, gender_str, age_str)
                df         = st.session_state.df_icd
                fidx       = st.session_state.faiss_index
                candidates = {}

                if concepts.get("immediate_cause"):
                    candidates["immediate_cause"] = {
                        "query":      concepts["immediate_cause"],
                        "candidates": search_icd(df, fidx, concepts["immediate_cause"], 5),
                    }
                contrib = [{"query": c, "candidates": search_icd(df, fidx, c, 4)}
                           for c in (concepts.get("contributing_causes") or [])]
                if contrib: candidates["contributing_causes"] = contrib

                other = [{"query": c, "candidates": search_icd(df, fidx, c, 3)}
                         for c in (concepts.get("other_conditions") or [])]
                if other: candidates["other_conditions"] = other

                ai_rec = get_recommendation(concepts, candidates, gender_str, age_str, extra)
                st.session_state.icd_results = {
                    "concepts": concepts, "candidates": candidates, "ai_suggestion": ai_rec,
                }
            except Exception as e:
                st.error(f"خطأ في التحليل: {e}")
                st.session_state.icd_results = None

    if st.session_state.icd_results:
        res        = st.session_state.icd_results
        concepts   = res["concepts"]
        candidates = res["candidates"]
        ai_rec     = res["ai_suggestion"]

        tab1, tab2, tab3 = st.tabs(["توصيات الترميز", "مرشحو ICD-10", "معاينة الشهادة"])

        # ── توصيات الترميز ─────────────────────────────────────────────────
        with tab1:
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">المفاهيم الطبية المستخرجة / Extracted Concepts</div>', unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**السبب الفوري:** {concepts.get('immediate_cause','—')}")
                if concepts.get("contributing_causes"):
                    st.markdown("**الأسباب المساهمة:**")
                    for c in concepts["contributing_causes"]: st.markdown(f"- {c}")
            with col2:
                if concepts.get("other_conditions"):
                    st.markdown("**حالات أخرى:**")
                    for c in concepts["other_conditions"]: st.markdown(f"- {c}")
                ivs = concepts.get("intervals", {})
                if ivs:
                    st.markdown("**الفترات الزمنية:**")
                    st.json(ivs)
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">توصية الترميز / AI Coding Recommendation</div>', unsafe_allow_html=True)
            st.markdown(ai_rec)
            st.markdown('</div>', unsafe_allow_html=True)

        # ── مرشحو ICD-10 ──────────────────────────────────────────────────
        with tab2:
            if candidates.get("immediate_cause"):
                st.markdown("#### السبب الفوري / Immediate Cause")
                st.caption(candidates["immediate_cause"]["query"])
                for r in candidates["immediate_cause"]["candidates"]:
                    col = "var(--green)" if r["acceptable_main"]=="Acceptable" else "#c0392b"
                    st.markdown(f"""
                    <div class="icd-card">
                      <span class="icd-code">{r['code_formatted']}</span>
                      <span class="icd-badge" style="background:{col}">{r['acceptable_main']}</span>
                      <span class="icd-badge">{r['gender_restriction']}</span>
                      <span class="icd-badge" style="background:#5a7060">{r['classification']}</span>
                      <div class="icd-desc"><strong>{r['short_desc']}</strong></div>
                      <div style="font-size:.8rem;color:#4a6a4e">{r['long_desc']}</div>
                    </div>""", unsafe_allow_html=True)

            if candidates.get("contributing_causes"):
                st.markdown("#### الأسباب المساهمة / Contributing Causes")
                for item in candidates["contributing_causes"]:
                    st.markdown(f"**{item['query']}**")
                    for r in item["candidates"]:
                        st.markdown(f"""
                        <div class="icd-card" style="border-color:#9ecaad;background:#f2fbf5">
                          <span class="icd-code" style="color:#2d7a4f">{r['code_formatted']}</span>
                          <span class="icd-badge">{r['acceptable_main']}</span>
                          <div class="icd-desc"><strong>{r['short_desc']}</strong></div>
                        </div>""", unsafe_allow_html=True)

        # ── معاينة الشهادة ─────────────────────────────────────────────────
        with tab3:
            cert_no = fd.get("cert_number") or f"DC-{datetime.date.today().year}-{fd.get('national_id','')[-4:]}"

            contrib_rows = "".join(
                f'<div class="cert-field"><span class="cert-label">(ب/ج) سبب مساهم</span>'
                f'<span>{c}</span></div>'
                for c in (concepts.get("contributing_causes") or [])
            )
            other_row = ""
            if concepts.get("other_conditions"):
                other_row = (
                    f'<div class="cert-field"><span class="cert-label">حالات أخرى</span>'
                    f'<span>{"; ".join(concepts["other_conditions"])}</span></div>'
                )

            st.markdown(f"""
            <div class="cert-preview">
              <div style="display:flex;justify-content:space-between;align-items:center;
                          border-bottom:2px solid var(--green);padding-bottom:1rem;margin-bottom:1.4rem">
                <div>
                  <div style="font-size:.95rem;font-weight:700;color:var(--green)">المملكة العربية السعودية</div>
                  <div style="font-size:.8rem;color:var(--muted)">وزارة الصحة</div>
                  <div style="font-size:.75rem;color:#888">{hospital_name} — {hospital_city}</div>
                </div>
                <div style="text-align:center">
                  <div class="cert-title">شهادة الوفاة</div>
                  <div class="cert-sub">DEATH CERTIFICATE</div>
                  <div style="background:var(--green);color:white;border-radius:4px;
                              padding:2px 10px;font-size:.76rem;margin-top:5px;display:inline-block">
                    رقم: {cert_no}
                  </div>
                </div>
                <div style="text-align:left">
                  <div style="font-size:.95rem;font-weight:700;color:var(--green)">Kingdom of Saudi Arabia</div>
                  <div style="font-size:.8rem;color:var(--muted)">Ministry of Health</div>
                </div>
              </div>

              <div style="display:grid;grid-template-columns:1fr 1fr;gap:2rem;margin-bottom:1.4rem">
                <div>
                  <div class="cert-field"><span class="cert-label">الاسم الكامل</span><span>{fd.get('full_name_ar','—')}</span></div>
                  <div class="cert-field"><span class="cert-label">Full Name</span><span>{fd.get('full_name_en','—')}</span></div>
                  <div class="cert-field"><span class="cert-label">رقم الهوية</span><span>{fd.get('national_id','—')}</span></div>
                  <div class="cert-field"><span class="cert-label">الجنسية</span><span>{fd.get('nationality','—')}</span></div>
                  <div class="cert-field"><span class="cert-label">الجنس</span><span>{fd.get('sex','—')}</span></div>
                  <div class="cert-field"><span class="cert-label">العمر</span><span>{fd.get('age_years','—')} سنة</span></div>
                  <div class="cert-field"><span class="cert-label">المستوى التعليمي</span><span>{fd.get('education','—')}</span></div>
                  <div class="cert-field"><span class="cert-label">المهنة</span><span>{fd.get('occupation','—')}</span></div>
                </div>
                <div>
                  <div class="cert-field"><span class="cert-label">تاريخ الوفاة</span><span>{fd.get('dod','—')}</span></div>
                  <div class="cert-field"><span class="cert-label">وقت الوفاة</span><span>{fd.get('time_of_death','—')}</span></div>
                  <div class="cert-field"><span class="cert-label">مكان الوفاة</span><span>{fd.get('place_of_death','—')}</span></div>
                  <div class="cert-field"><span class="cert-label">نوع الوفاة</span><span>{fd.get('death_type','—')}</span></div>
                  <div class="cert-field"><span class="cert-label">عملية خلال شهر</span><span>{fd.get('had_surgery','لا')}</span></div>
                  <div class="cert-field"><span class="cert-label">التشريح مطلوب</span><span>{fd.get('autopsy_required','لا')}</span></div>
                  <div class="cert-field"><span class="cert-label">إقامة بالمستشفى</span><span>{fd.get('inpatient_days',0)} أيام</span></div>
                </div>
              </div>

              <div style="background:var(--green-light);border-radius:6px;padding:1rem 1.2rem;
                          margin-bottom:1.4rem;border:1px solid #9ecaad">
                <div style="font-weight:700;color:var(--green);margin-bottom:.5rem;font-size:.9rem">
                  أسباب الوفاة / Causes of Death
                </div>
                <div class="cert-field">
                  <span class="cert-label">(أ) السبب الفوري</span>
                  <span>{concepts.get('immediate_cause', fd.get('cause_a','—'))}</span>
                </div>
                {contrib_rows}
                {other_row}
              </div>

              <div style="display:flex;justify-content:space-between;align-items:flex-end;
                          padding-top:1.2rem;border-top:1px solid #d0ddd2">
                <div>
                  <div style="font-weight:700;color:var(--green);font-size:.85rem">الطبيب المُصدر</div>
                  <div style="margin-top:3px">{doctor_name or '________________________________'}</div>
                  <div style="font-size:.75rem;color:#888;margin-top:8px">التوقيع: _______________________</div>
                </div>
                <div class="cert-stamp">وزارة<br>الصحة<br>MOH<br>ختم رسمي</div>
                <div style="text-align:left">
                  <div style="font-weight:700;color:var(--green);font-size:.85rem">تاريخ الإصدار</div>
                  <div style="margin-top:3px">{fd.get('date_issued', str(datetime.date.today()))}</div>
                  <div style="font-size:.75rem;color:#888;margin-top:3px">{hospital_city}</div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("---")
            cert_txt = (
                f"شهادة وفاة / DEATH CERTIFICATE\nرقم: {cert_no}\n{'='*55}\n"
                f"المستشفى: {hospital_name} – {hospital_city}\n"
                f"وزارة الصحة – المملكة العربية السعودية\n\n"
                f"الاسم: {fd.get('full_name_ar','')}\nالهوية: {fd.get('national_id','')}\n"
                f"الجنس: {fd.get('sex','')}\nالعمر: {fd.get('age_years','')} سنة\n"
                f"تاريخ الوفاة: {fd.get('dod','')}\nمكان الوفاة: {fd.get('place_of_death','')}\n"
                f"نوع الوفاة: {fd.get('death_type','')}\n\n"
                f"عملية آخر شهر: {fd.get('had_surgery','')}\n"
                f"التشريح مطلوب: {fd.get('autopsy_required','')}\n\n"
                f"أسباب الوفاة:\n"
                f"  السبب الفوري: {concepts.get('immediate_cause','')}\n"
                f"  الأسباب المساهمة: {', '.join(concepts.get('contributing_causes',[]))}\n"
                f"  حالات أخرى: {', '.join(concepts.get('other_conditions',[]))}\n\n"
                f"توصية ICD-10:\n{ai_rec}\n\n"
                f"الطبيب: {doctor_name}\nتاريخ الإصدار: {fd.get('date_issued','')}\n"
            )
            st.download_button(
                "تحميل ملخص الشهادة / Download Certificate Summary",
                data=cert_txt.encode("utf-8"),
                file_name=f"death_cert_{cert_no}.txt",
                mime="text/plain",
            )

    st.markdown("---")
    b1, b2, _ = st.columns([1, 1, 6])
    with b1:
        if st.button("السابق", use_container_width=True):
            st.session_state.page = 3
            st.session_state.icd_results = None
            st.rerun()
    with b2:
        if st.button("شهادة جديدة", use_container_width=True):
            st.session_state.page        = 1
            st.session_state.form_data   = {}
            st.session_state.icd_results = None
            st.rerun()
