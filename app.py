"""
Saudi Ministry of Health – Death Certificate System
شهادة وفاة – وزارة الصحة السعودية
Deployable on Streamlit Cloud
"""

import streamlit as st
import pandas as pd
import numpy as np
import json
import re
import time
import datetime
import io
import base64
from pathlib import Path

# ── Page config (must be first) ────────────────────────────────────────────────
st.set_page_config(
    page_title="شهادة الوفاة | وزارة الصحة",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS – Saudi MOH theme (white + green) ──────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Tajawal:wght@300;400;500;700;800&family=Cairo:wght@400;600;700&display=swap');

:root {
  --green:   #006940;
  --green2:  #00843D;
  --green-light: #e8f5ee;
  --gold:    #C8A951;
  --white:   #ffffff;
  --gray:    #f5f7f5;
  --text:    #1a2e1a;
  --border:  #c5d9c8;
}

html, body, [class*="css"] {
  font-family: 'Tajawal', 'Cairo', sans-serif;
  direction: rtl;
  color: var(--text);
}

/* Sidebar */
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, var(--green) 0%, #004d2e 100%);
  color: white;
}
section[data-testid="stSidebar"] * { color: white !important; }
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stTextInput label { color: #c8e6c9 !important; }

/* Main background */
.main .block-container { background: var(--gray); padding: 1.5rem 2rem; }

/* Header banner */
.moh-header {
  background: linear-gradient(135deg, var(--green) 0%, var(--green2) 60%, #004d2e 100%);
  color: white;
  padding: 1.2rem 2rem;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1.5rem;
  box-shadow: 0 4px 20px rgba(0,105,64,.35);
  border-bottom: 4px solid var(--gold);
}
.moh-header h1 { font-size: 1.6rem; margin: 0; font-weight: 800; }
.moh-header p  { font-size: .85rem; margin: 0; opacity: .85; }
.moh-logo { font-size: 3.5rem; }

/* Section cards */
.section-card {
  background: white;
  border-radius: 10px;
  padding: 1.4rem 1.6rem;
  margin-bottom: 1.2rem;
  border: 1px solid var(--border);
  box-shadow: 0 2px 8px rgba(0,0,0,.06);
}
.section-title {
  color: var(--green);
  font-size: 1.1rem;
  font-weight: 700;
  border-bottom: 2px solid var(--green-light);
  padding-bottom: .5rem;
  margin-bottom: 1rem;
  display: flex;
  align-items: center;
  gap: .5rem;
}

/* Inputs */
.stTextInput>div>div>input,
.stTextArea>div>div>textarea,
.stSelectbox>div>div>div {
  border: 1.5px solid var(--border) !important;
  border-radius: 8px !important;
  font-family: 'Tajawal', sans-serif !important;
  font-size: .95rem !important;
}
.stTextInput>div>div>input:focus,
.stTextArea>div>div>textarea:focus {
  border-color: var(--green) !important;
  box-shadow: 0 0 0 3px rgba(0,105,64,.12) !important;
}

/* Buttons */
.stButton>button {
  background: linear-gradient(135deg, var(--green), var(--green2));
  color: white !important;
  border: none;
  border-radius: 8px;
  font-family: 'Tajawal', sans-serif;
  font-weight: 700;
  font-size: 1rem;
  padding: .6rem 2rem;
  transition: all .2s;
  box-shadow: 0 2px 8px rgba(0,105,64,.3);
}
.stButton>button:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(0,105,64,.4);
}

/* ICD result cards */
.icd-card {
  background: var(--green-light);
  border: 1.5px solid var(--green);
  border-radius: 10px;
  padding: 1rem 1.2rem;
  margin: .6rem 0;
}
.icd-code {
  font-size: 1.2rem;
  font-weight: 800;
  color: var(--green);
  font-family: 'Courier New', monospace;
}
.icd-desc { color: #333; font-size: .95rem; }
.icd-badge {
  display: inline-block;
  background: var(--green);
  color: white;
  border-radius: 20px;
  padding: 2px 12px;
  font-size: .75rem;
  margin-right: 4px;
}

/* Certificate preview */
.cert-preview {
  background: white;
  border: 3px double var(--green);
  border-radius: 12px;
  padding: 2rem;
  font-family: 'Tajawal', sans-serif;
}
.cert-header {
  text-align: center;
  border-bottom: 2px solid var(--green);
  padding-bottom: 1rem;
  margin-bottom: 1.5rem;
}
.cert-title { font-size: 1.8rem; font-weight: 800; color: var(--green); }
.cert-subtitle { color: #555; font-size: .95rem; }
.cert-field {
  display: flex;
  justify-content: space-between;
  border-bottom: 1px dashed #ccc;
  padding: .4rem 0;
  font-size: .95rem;
}
.cert-field-label { font-weight: 700; color: var(--green); }
.cert-stamp {
  border: 3px solid var(--green);
  border-radius: 50%;
  width: 100px; height: 100px;
  display: flex; align-items: center; justify-content: center;
  margin: auto;
  color: var(--green);
  font-weight: 800;
  text-align: center;
  font-size: .75rem;
}

/* Progress steps */
.step-bar {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin-bottom: 1.5rem;
}
.step {
  background: #ccc;
  color: white;
  border-radius: 20px;
  padding: 6px 18px;
  font-size: .85rem;
  font-weight: 600;
}
.step.active { background: var(--green); }
.step.done   { background: var(--gold); }

/* Warning / info */
.stAlert { border-radius: 8px !important; }

/* Radio & checkbox labels */
.stRadio label, .stCheckbox label {
  font-family: 'Tajawal', sans-serif !important;
}

/* Tab styling */
.stTabs [data-baseweb="tab"] {
  font-family: 'Tajawal', sans-serif !important;
  font-weight: 600;
}
.stTabs [aria-selected="true"] {
  color: var(--green) !important;
  border-bottom-color: var(--green) !important;
}
</style>
""", unsafe_allow_html=True)

# ── MOH Header ────────────────────────────────────────────────────────────────
st.markdown("""
<div class="moh-header">
  <div>
    <h1>🏥 نظام شهادة الوفاة الإلكترونية</h1>
    <p>وزارة الصحة – المملكة العربية السعودية &nbsp;|&nbsp; Ministry of Health – Kingdom of Saudi Arabia</p>
    <p style="font-size:.8rem;opacity:.7;">Death Certificate Registration System – ICD-10 Coding with AI Assistance</p>
  </div>
  <div style="text-align:center">
    <div style="font-size:3rem">🇸🇦</div>
    <div style="font-size:.7rem;opacity:.8;">وزارة الصحة</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Sidebar – Configuration ────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ إعدادات النظام")
    st.markdown("---")
    api_key = st.text_input("🔑 Anthropic API Key", type="password",
                            help="Enter your Anthropic API key")
    st.markdown("---")
    st.markdown("### 📁 ملف ICD-10")
    uploaded_excel = st.file_uploader("رفع ملف ICD10_Enriched_Final.xlsx",
                                      type=["xlsx"],
                                      help="Upload the ICD-10 enriched Excel file")
    st.markdown("---")
    st.markdown("### 🏥 بيانات المستشفى")
    hospital_name = st.text_input("اسم المستشفى", value="مستشفى الملك فهد التخصصي")
    hospital_city = st.text_input("المدينة", value="الرياض")
    doctor_name   = st.text_input("اسم الطبيب المُصدر", value="")
    st.markdown("---")
    st.markdown("""
    <div style="font-size:.75rem;opacity:.7;text-align:center">
    نظام شهادة الوفاة الإلكترونية<br>
    وزارة الصحة – 1446هـ<br>
    إصدار 2.0
    </div>
    """, unsafe_allow_html=True)

# ── Session state ──────────────────────────────────────────────────────────────
for key in ["page", "form_data", "icd_results", "cert_ready", "df_icd"]:
    if key not in st.session_state:
        st.session_state[key] = None
if st.session_state.page is None:
    st.session_state.page = 1
if st.session_state.form_data is None:
    st.session_state.form_data = {}

# ── Load ICD-10 data ───────────────────────────────────────────────────────────
@st.cache_data(show_spinner="جارٍ تحميل قاعدة بيانات ICD-10…")
def load_icd_data(file_bytes):
    df = pd.read_excel(io.BytesIO(file_bytes))
    df.columns = ["Id","Code","CodeFormatted","ShortDesc","LongDesc",
                  "HIPPA","Deleted","Classification","AcceptableMain",
                  "GenderRestriction","MatchSource","MatchedFromCode","Note"]
    df = df[df["Deleted"] != "Yes"].copy()
    df = df.dropna(subset=["Code"]).reset_index(drop=True)
    df["EmbedText"] = (df["CodeFormatted"].fillna("") + " | " +
                       df["LongDesc"].fillna("") + " | " +
                       df["ShortDesc"].fillna(""))
    return df

def search_icd_keyword(df, query, top_k=6):
    """Fast keyword search without FAISS (works on Streamlit Cloud)."""
    q_lower = query.lower()
    terms = q_lower.split()
    scores = df["EmbedText"].str.lower().apply(
        lambda x: sum(t in x for t in terms)
    )
    top_idx = scores.nlargest(top_k).index
    results = []
    for idx in top_idx:
        if scores[idx] == 0:
            continue
        row = df.iloc[idx]
        results.append({
            "code":               str(row["Code"]),
            "code_formatted":     str(row["CodeFormatted"]),
            "short_desc":         str(row["ShortDesc"]),
            "long_desc":          str(row["LongDesc"]),
            "acceptable_main":    str(row["AcceptableMain"]),
            "gender_restriction": str(row["GenderRestriction"]),
            "classification":     str(row["Classification"]),
            "similarity":         float(scores[idx]),
        })
    return results

# Load data if uploaded
if uploaded_excel and st.session_state.df_icd is None:
    file_bytes = uploaded_excel.read()
    st.session_state.df_icd = load_icd_data(file_bytes)
    st.sidebar.success(f"✅ تم تحميل {len(st.session_state.df_icd):,} رمز ICD-10")

# ── Claude API calls ───────────────────────────────────────────────────────────
def call_claude(system_prompt, user_content, max_tokens=1500):
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    return resp.content[0].text.strip()

def extract_medical_concepts(free_text, gender, age):
    system = """You are a clinical coding assistant for Saudi Ministry of Health death certificates.
Extract structured medical information from doctor's free-text description.
Return ONLY a valid JSON object with exactly these keys:
{
  "immediate_cause": "single string – direct cause of death",
  "contributing_causes": ["underlying/intermediate causes as list"],
  "other_conditions": ["other significant conditions as list"],
  "intervals": {"immediate_cause": "e.g. minutes/hours", "contributing_causes": ["days","weeks"]},
  "notes": "any relevant clinical notes"
}
Use standard ICD-10 compatible medical terminology. Return ONLY JSON."""
    user = f"Patient: {age} years old, {gender}.\n\nDoctor's description:\n{free_text}"
    raw = call_claude(system, user, max_tokens=800)
    raw = re.sub(r"^```json?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)

def get_ai_suggestion(concepts, candidates, gender, age, extra_info):
    system = """You are a senior clinical coding specialist at Saudi Ministry of Health.
Given extracted causes of death and ICD-10 candidates, provide:
1. Best recommended ICD-10 code for immediate cause of death (with justification)
2. Codes for contributing/underlying causes
3. Any gender/age validity warnings
4. Advice on certificate completeness
5. Any WHO/MOH coding rules that apply

Respond in Arabic with English ICD codes. Be concise and clinically precise."""
    user = f"""Patient: {age} years old, {gender}
{extra_info}

Extracted causes:
{json.dumps(concepts, ensure_ascii=False, indent=2)}

ICD-10 candidates:
{json.dumps(candidates, ensure_ascii=False, indent=2)}

Provide your expert coding recommendation."""
    return call_claude(system, user, max_tokens=1200)

# ── Step indicator ─────────────────────────────────────────────────────────────
def step_bar(current):
    steps = ["1️⃣ البيانات الأساسية", "2️⃣ السيرة المرضية", "3️⃣ أسباب الوفاة", "4️⃣ المراجعة والتوصيات"]
    html = '<div class="step-bar">'
    for i, s in enumerate(steps, 1):
        cls = "active" if i == current else ("done" if i < current else "step")
        html += f'<div class="step {cls}">{s}</div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 1 – Basic Patient Information
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.page == 1:
    step_bar(1)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">👤 البيانات الأساسية للمتوفى – Patient Basic Information</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        full_name_ar = st.text_input("الاسم الكامل (عربي) *", placeholder="محمد بن عبدالله العتيبي")
        full_name_en = st.text_input("Full Name (English)", placeholder="Mohammed Abdullah Al-Otaibi")
        national_id  = st.text_input("رقم الهوية / الإقامة *", placeholder="1XXXXXXXXX")
        nationality  = st.text_input("الجنسية / Nationality", placeholder="سعودي / Saudi")
        dob = st.date_input("تاريخ الميلاد / Date of Birth",
                            value=datetime.date(1960, 1, 1),
                            min_value=datetime.date(1900, 1, 1),
                            max_value=datetime.date.today())
    with col2:
        sex = st.selectbox("الجنس / Sex *", ["ذكر / Male", "أنثى / Female"])
        marital_status = st.selectbox("الحالة الاجتماعية / Marital Status",
                                      ["أعزب / Single", "متزوج / Married", "مطلق / Divorced", "أرمل / Widowed"])
        education = st.selectbox("المستوى التعليمي / Education Level",
                                 ["أمي / Illiterate", "ابتدائي / Primary", "متوسط / Intermediate",
                                  "ثانوي / Secondary", "دبلوم / Diploma", "بكالوريوس / Bachelor",
                                  "دراسات عليا / Postgraduate", "غير معلوم / Unknown"])
        occupation = st.text_input("المهنة / Occupation", placeholder="مهندس / Engineer")
        address    = st.text_input("العنوان / Address", placeholder="الرياض – حي العليا")

    st.markdown("---")
    col3, col4 = st.columns(2)
    with col3:
        dod = st.date_input("تاريخ الوفاة / Date of Death *", value=datetime.date.today())
        time_of_death = st.time_input("وقت الوفاة / Time of Death")
        place_of_death = st.selectbox("مكان الوفاة / Place of Death",
                                      ["المستشفى / Hospital", "الطوارئ / Emergency",
                                       "المنزل / Home", "الطريق / Road", "غير معلوم / Unknown"])
    with col4:
        cert_number = st.text_input("رقم الشهادة / Certificate No.", placeholder="DC-2024-XXXXX")
        date_issued = st.date_input("تاريخ الإصدار / Issue Date", value=datetime.date.today())

    st.markdown('</div>', unsafe_allow_html=True)

    # Age calculation
    if dob and dod:
        age_years = (dod - dob).days // 365
        st.info(f"📅 العمر عند الوفاة / Age at Death: **{age_years} سنة / years**")
    else:
        age_years = 0

    col_btn1, col_btn2 = st.columns([1, 5])
    with col_btn1:
        if st.button("التالي ←", use_container_width=True):
            if not full_name_ar or not national_id:
                st.error("⚠️ يرجى إدخال الاسم الكامل ورقم الهوية")
            else:
                st.session_state.form_data.update({
                    "full_name_ar": full_name_ar, "full_name_en": full_name_en,
                    "national_id": national_id, "nationality": nationality,
                    "dob": str(dob), "dod": str(dod),
                    "time_of_death": str(time_of_death),
                    "place_of_death": place_of_death,
                    "sex": sex, "marital_status": marital_status,
                    "education": education, "occupation": occupation,
                    "address": address, "age_years": age_years,
                    "cert_number": cert_number, "date_issued": str(date_issued),
                })
                st.session_state.page = 2
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 2 – Medical History & Clinical Info
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.page == 2:
    step_bar(2)
    fd = st.session_state.form_data

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🏥 السيرة المرضية – Medical History</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        had_surgery = st.radio(
            "🔪 هل أجرى المريض عملية جراحية خلال آخر شهر؟\nDid the patient undergo surgery in the last month?",
            ["لا / No", "نعم / Yes", "غير معلوم / Unknown"]
        )
        if had_surgery == "نعم / Yes":
            surgery_details = st.text_area("تفاصيل العملية / Surgery Details",
                                           placeholder="نوع العملية، التاريخ، المستشفى")
        else:
            surgery_details = ""

        autopsy_required = st.radio(
            "🔬 هل التشريح مطلوب من وجهة نظر الطبيب؟\nIs autopsy required in the doctor's opinion?",
            ["لا / No", "نعم / Yes", "غير محدد / Not determined"]
        )
        if autopsy_required == "نعم / Yes":
            autopsy_reason = st.text_input("سبب طلب التشريح / Reason for autopsy")
        else:
            autopsy_reason = ""

    with col2:
        death_type = st.selectbox("نوع الوفاة / Type of Death",
                                  ["طبيعية / Natural", "حادث / Accident",
                                   "انتحار / Suicide", "قتل / Homicide", "غير محدد / Undetermined"])
        inpatient_days = st.number_input("مدة الإقامة بالمستشفى (أيام) / Hospital Stay (days)",
                                         min_value=0, value=0)
        was_pregnant = "لا ينطبق"
        if "أنثى" in fd.get("sex", ""):
            was_pregnant = st.selectbox("الحالة أثناء الوفاة (للإناث) / Pregnancy Status",
                                        ["لا / No", "حامل / Pregnant",
                                         "أثناء الولادة / During delivery",
                                         "بعد الولادة (42 يوم) / Within 42 days postpartum",
                                         "لا ينطبق / NA"])

        chronic_conditions = st.multiselect(
            "الأمراض المزمنة المعروفة / Known Chronic Conditions",
            ["داء السكري / Diabetes", "ارتفاع ضغط الدم / Hypertension",
             "أمراض القلب / Heart Disease", "أمراض الكلى / Renal Disease",
             "أمراض الكبد / Liver Disease", "السرطان / Cancer",
             "أمراض الرئة / Pulmonary Disease", "السمنة / Obesity",
             "أمراض عصبية / Neurological", "أخرى / Other"]
        )

    st.markdown('</div>', unsafe_allow_html=True)

    col_b1, col_b2, col_b3 = st.columns([1, 1, 5])
    with col_b1:
        if st.button("→ السابق", use_container_width=True):
            st.session_state.page = 1
            st.rerun()
    with col_b2:
        if st.button("التالي ←", use_container_width=True):
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

# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 3 – Causes of Death & ICD Coding
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.page == 3:
    step_bar(3)
    fd = st.session_state.form_data

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.markdown('<div class="section-title">📋 أسباب الوفاة – Causes of Death (WHO Format)</div>', unsafe_allow_html=True)

    st.markdown("""
    <div style="background:#fff3cd;border-right:4px solid #ffc107;padding:10px 14px;border-radius:6px;margin-bottom:1rem;font-size:.9rem">
    ⚠️ <strong>تعليمات:</strong> يُرجى وصف أسباب الوفاة بالتسلسل الزمني (السبب الفوري أولاً، ثم الأسباب المساهمة)
    </div>
    """, unsafe_allow_html=True)

    free_text = st.text_area(
        "📝 وصف أسباب الوفاة (بالعربية أو الإنجليزية) / Free-text cause of death description",
        height=150,
        placeholder="مثال: توفي المريض إثر احتشاء عضلة القلب الحاد، الذي نتج عن تصلب الشرايين التاجية الناجم عن داء السكري وارتفاع ضغط الدم المزمن.\nExample: Patient died following acute myocardial infarction due to coronary atherosclerosis secondary to diabetes and chronic hypertension."
    )

    st.markdown("---")
    st.markdown("**أو أدخل الأسباب منفردة / Or enter causes separately:**")

    col1, col2 = st.columns(2)
    with col1:
        cause_a = st.text_input("السبب الفوري (أ) / Immediate Cause (a)",
                                placeholder="e.g. Acute myocardial infarction")
        interval_a = st.text_input("الفترة الزمنية (أ) / Time Interval (a)", placeholder="e.g. 2 hours")
        cause_b = st.text_input("السبب المؤدي (ب) / Underlying Cause (b)",
                                placeholder="e.g. Coronary atherosclerosis")
        interval_b = st.text_input("الفترة الزمنية (ب) / Time Interval (b)", placeholder="e.g. 5 years")
    with col2:
        cause_c = st.text_input("سبب آخر (ج) / Other Cause (c)", placeholder="e.g. Diabetes mellitus")
        interval_c = st.text_input("الفترة الزمنية (ج) / Time Interval (c)", placeholder="e.g. 10 years")
        cause_d = st.text_input("سبب آخر (د) / Other Cause (d)", placeholder="e.g. Hypertension")
        interval_d = st.text_input("الفترة الزمنية (د) / Time Interval (d)", placeholder="e.g. 15 years")

    other_conditions_text = st.text_area(
        "حالات أخرى مساهمة / Other Contributing Conditions",
        placeholder="أمراض أخرى ساهمت في الوفاة لكنها ليست السبب المباشر"
    )
    st.markdown('</div>', unsafe_allow_html=True)

    # ICD Search Section
    if st.session_state.df_icd is not None:
        st.markdown('<div class="section-card">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">🔍 بحث ICD-10 يدوي – Manual ICD-10 Search</div>', unsafe_allow_html=True)
        manual_search = st.text_input("ابحث عن رمز ICD-10 / Search ICD-10 code",
                                      placeholder="e.g. myocardial infarction, diabetes, pneumonia")
        if manual_search and len(manual_search) >= 3:
            results = search_icd_keyword(st.session_state.df_icd, manual_search, top_k=8)
            if results:
                st.markdown(f"**نتائج البحث / Search Results ({len(results)}):**")
                for r in results:
                    badge_color = "var(--green)" if r["acceptable_main"] == "Acceptable" else "#dc3545"
                    st.markdown(f"""
                    <div class="icd-card">
                      <span class="icd-code">{r['code_formatted']}</span>
                      <span class="icd-badge" style="background:{badge_color}">{r['acceptable_main']}</span>
                      <span class="icd-badge">{r['gender_restriction']}</span>
                      <div class="icd-desc"><strong>{r['short_desc']}</strong></div>
                      <div class="icd-desc" style="font-size:.85rem;color:#666">{r['long_desc']}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.warning("لم يتم العثور على نتائج / No results found")
        st.markdown('</div>', unsafe_allow_html=True)

    col_b1, col_b2, col_b3 = st.columns([1, 1, 5])
    with col_b1:
        if st.button("→ السابق", use_container_width=True):
            st.session_state.page = 2
            st.rerun()
    with col_b2:
        if st.button("تحليل وتوصيات ←", use_container_width=True):
            if not free_text and not cause_a:
                st.error("⚠️ يرجى إدخال وصف أسباب الوفاة")
            elif not api_key:
                st.error("⚠️ يرجى إدخال مفتاح Anthropic API في الشريط الجانبي")
            elif st.session_state.df_icd is None:
                st.error("⚠️ يرجى رفع ملف ICD-10 Excel في الشريط الجانبي")
            else:
                st.session_state.form_data.update({
                    "free_text": free_text,
                    "cause_a": cause_a, "interval_a": interval_a,
                    "cause_b": cause_b, "interval_b": interval_b,
                    "cause_c": cause_c, "interval_c": interval_c,
                    "cause_d": cause_d, "interval_d": interval_d,
                    "other_conditions_text": other_conditions_text,
                })
                st.session_state.page = 4
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
#  PAGE 4 – AI Analysis, ICD Coding & Certificate Preview
# ══════════════════════════════════════════════════════════════════════════════
elif st.session_state.page == 4:
    step_bar(4)
    fd = st.session_state.form_data

    # Build combined text for AI
    combined_text = fd.get("free_text", "")
    if fd.get("cause_a"):
        combined_text += f"\n\nImmediate cause: {fd['cause_a']} (interval: {fd.get('interval_a','')})"
    if fd.get("cause_b"):
        combined_text += f"\nUnderlying cause: {fd['cause_b']} (interval: {fd.get('interval_b','')})"
    if fd.get("cause_c"):
        combined_text += f"\nOther cause: {fd['cause_c']} (interval: {fd.get('interval_c','')})"
    if fd.get("cause_d"):
        combined_text += f"\nOther cause: {fd['cause_d']} (interval: {fd.get('interval_d','')})"
    if fd.get("other_conditions_text"):
        combined_text += f"\nOther conditions: {fd['other_conditions_text']}"

    gender_str = "Male" if "ذكر" in fd.get("sex","") else "Female"
    age_str    = str(fd.get("age_years", "Unknown"))
    extra_info = f"Surgery last month: {fd.get('had_surgery','No')}\nAutopsy required: {fd.get('autopsy_required','No')}\nChronic conditions: {', '.join(fd.get('chronic_conditions',[]))}"

    # Run AI analysis (cached in session)
    if st.session_state.icd_results is None:
        with st.spinner("🤖 جارٍ تحليل أسباب الوفاة واستخراج رموز ICD-10…"):
            try:
                concepts = extract_medical_concepts(combined_text, gender_str, age_str)
                df = st.session_state.df_icd

                candidates = {}
                if concepts.get("immediate_cause"):
                    candidates["immediate_cause"] = {
                        "query": concepts["immediate_cause"],
                        "candidates": search_icd_keyword(df, concepts["immediate_cause"], top_k=5)
                    }
                contributing = []
                for c in (concepts.get("contributing_causes") or []):
                    contributing.append({"query": c, "candidates": search_icd_keyword(df, c, top_k=4)})
                if contributing:
                    candidates["contributing_causes"] = contributing

                other = []
                for c in (concepts.get("other_conditions") or []):
                    other.append({"query": c, "candidates": search_icd_keyword(df, c, top_k=3)})
                if other:
                    candidates["other_conditions"] = other

                ai_suggestion = get_ai_suggestion(concepts, candidates, gender_str, age_str, extra_info)

                st.session_state.icd_results = {
                    "concepts": concepts,
                    "candidates": candidates,
                    "ai_suggestion": ai_suggestion,
                }
            except Exception as e:
                st.error(f"❌ خطأ في التحليل: {e}")
                st.session_state.icd_results = None

    if st.session_state.icd_results:
        res = st.session_state.icd_results
        concepts   = res["concepts"]
        candidates = res["candidates"]
        ai_suggest = res["ai_suggestion"]

        tab1, tab2, tab3 = st.tabs(["🤖 توصيات الذكاء الاصطناعي", "🔍 مرشحو ICD-10", "📄 معاينة الشهادة"])

        # ── Tab 1: AI Suggestions ─────────────────────────────────────────────
        with tab1:
            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">🧠 المفاهيم الطبية المستخرجة – Extracted Medical Concepts</div>', unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**السبب الفوري:** {concepts.get('immediate_cause','—')}")
                if concepts.get('contributing_causes'):
                    st.markdown("**الأسباب المساهمة:**")
                    for c in concepts['contributing_causes']:
                        st.markdown(f"  • {c}")
            with col2:
                if concepts.get('other_conditions'):
                    st.markdown("**حالات أخرى:**")
                    for c in concepts['other_conditions']:
                        st.markdown(f"  • {c}")
                intervals = concepts.get("intervals", {})
                if intervals:
                    st.markdown(f"**الفترات الزمنية:** {json.dumps(intervals, ensure_ascii=False)}")
            st.markdown('</div>', unsafe_allow_html=True)

            st.markdown('<div class="section-card">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">💡 توصية الطبيب الافتراضي – AI Coding Recommendation</div>', unsafe_allow_html=True)
            st.markdown(ai_suggest)
            st.markdown('</div>', unsafe_allow_html=True)

        # ── Tab 2: ICD Candidates ─────────────────────────────────────────────
        with tab2:
            if candidates.get("immediate_cause"):
                st.markdown("### السبب الفوري / Immediate Cause")
                st.markdown(f"*{candidates['immediate_cause']['query']}*")
                for r in candidates["immediate_cause"]["candidates"]:
                    color = "var(--green)" if r["acceptable_main"] == "Acceptable" else "#dc3545"
                    st.markdown(f"""
                    <div class="icd-card">
                      <span class="icd-code">{r['code_formatted']}</span>
                      <span class="icd-badge" style="background:{color}">{r['acceptable_main']}</span>
                      <span class="icd-badge">{r['gender_restriction']}</span>
                      <span class="icd-badge" style="background:#666">{r['classification']}</span>
                      <div class="icd-desc"><strong>{r['short_desc']}</strong></div>
                      <div style="font-size:.82rem;color:#555">{r['long_desc']}</div>
                    </div>
                    """, unsafe_allow_html=True)

            if candidates.get("contributing_causes"):
                st.markdown("### الأسباب المساهمة / Contributing Causes")
                for item in candidates["contributing_causes"]:
                    st.markdown(f"**{item['query']}**")
                    for r in item["candidates"]:
                        st.markdown(f"""
                        <div class="icd-card" style="border-color:#6aab82;background:#f0faf3">
                          <span class="icd-code" style="color:#2d7a4f">{r['code_formatted']}</span>
                          <span class="icd-badge">{r['acceptable_main']}</span>
                          <div class="icd-desc"><strong>{r['short_desc']}</strong></div>
                        </div>
                        """, unsafe_allow_html=True)

        # ── Tab 3: Certificate Preview ─────────────────────────────────────────
        with tab3:
            cert_no = fd.get("cert_number") or f"DC-{datetime.date.today().year}-{fd['national_id'][-4:]}"
            st.markdown(f"""
            <div class="cert-preview">
              <div class="cert-header">
                <div style="display:flex;justify-content:space-between;align-items:center">
                  <div style="text-align:right">
                    <div style="font-size:1.1rem;color:var(--green);font-weight:700">المملكة العربية السعودية</div>
                    <div style="font-size:.85rem;color:#555">وزارة الصحة</div>
                    <div style="font-size:.8rem;color:#777">{hospital_name} – {hospital_city}</div>
                  </div>
                  <div style="text-align:center">
                    <div style="font-size:2.5rem">🏥</div>
                    <div class="cert-title">شهادة الوفاة</div>
                    <div class="cert-subtitle">DEATH CERTIFICATE</div>
                    <div style="background:var(--green);color:white;border-radius:5px;padding:3px 12px;font-size:.8rem;margin-top:4px">رقم: {cert_no}</div>
                  </div>
                  <div style="text-align:left">
                    <div style="font-size:1.1rem;color:var(--green);font-weight:700">Kingdom of Saudi Arabia</div>
                    <div style="font-size:.85rem;color:#555">Ministry of Health</div>
                    <div style="font-size:.8rem;color:#777">{hospital_name}</div>
                  </div>
                </div>
              </div>

              <div style="display:grid;grid-template-columns:1fr 1fr;gap:1.5rem;margin-bottom:1.5rem">
                <div>
                  <div class="cert-field"><span class="cert-field-label">الاسم الكامل</span><span>{fd.get('full_name_ar','—')}</span></div>
                  <div class="cert-field"><span class="cert-field-label">رقم الهوية</span><span>{fd.get('national_id','—')}</span></div>
                  <div class="cert-field"><span class="cert-field-label">الجنسية</span><span>{fd.get('nationality','—')}</span></div>
                  <div class="cert-field"><span class="cert-field-label">الجنس</span><span>{fd.get('sex','—')}</span></div>
                  <div class="cert-field"><span class="cert-field-label">العمر</span><span>{fd.get('age_years','—')} سنة</span></div>
                  <div class="cert-field"><span class="cert-field-label">المستوى التعليمي</span><span>{fd.get('education','—')}</span></div>
                  <div class="cert-field"><span class="cert-field-label">المهنة</span><span>{fd.get('occupation','—')}</span></div>
                </div>
                <div>
                  <div class="cert-field"><span class="cert-field-label">تاريخ الوفاة</span><span>{fd.get('dod','—')}</span></div>
                  <div class="cert-field"><span class="cert-field-label">وقت الوفاة</span><span>{fd.get('time_of_death','—')}</span></div>
                  <div class="cert-field"><span class="cert-field-label">مكان الوفاة</span><span>{fd.get('place_of_death','—')}</span></div>
                  <div class="cert-field"><span class="cert-field-label">نوع الوفاة</span><span>{fd.get('death_type','—')}</span></div>
                  <div class="cert-field"><span class="cert-field-label">عملية خلال شهر</span><span>{fd.get('had_surgery','لا')}</span></div>
                  <div class="cert-field"><span class="cert-field-label">التشريح مطلوب</span><span>{fd.get('autopsy_required','لا')}</span></div>
                </div>
              </div>

              <div style="background:var(--green-light);border-radius:8px;padding:1rem;margin-bottom:1rem">
                <div style="font-weight:700;color:var(--green);margin-bottom:.5rem">أسباب الوفاة – Causes of Death</div>
                <div class="cert-field"><span class="cert-field-label">(أ) السبب الفوري</span><span>{concepts.get('immediate_cause', fd.get('cause_a','—'))}</span></div>
                {"".join(f'<div class="cert-field"><span class="cert-field-label">(ب/ج) مساهم</span><span>{c}</span></div>' for c in (concepts.get('contributing_causes') or [fd.get('cause_b',''), fd.get('cause_c','')] if any([fd.get('cause_b'), fd.get('cause_c')]) else []))}
                {"<div class='cert-field'><span class='cert-field-label'>حالات أخرى</span><span>" + "; ".join(concepts.get('other_conditions',[])) + "</span></div>" if concepts.get('other_conditions') else ""}
              </div>

              <div style="display:flex;justify-content:space-between;align-items:flex-end;margin-top:2rem;padding-top:1rem;border-top:1px solid #ccc">
                <div>
                  <div style="font-weight:700;color:var(--green)">الطبيب المُصدر / Certifying Doctor</div>
                  <div>{doctor_name or '____________________'}</div>
                  <div style="font-size:.8rem;color:#777">التوقيع / Signature: _________________</div>
                </div>
                <div class="cert-stamp">وزارة<br>الصحة<br>🏥<br>ختم رسمي</div>
                <div style="text-align:left">
                  <div style="font-weight:700;color:var(--green)">تاريخ الإصدار / Issue Date</div>
                  <div>{fd.get('date_issued', str(datetime.date.today()))}</div>
                  <div style="font-size:.8rem;color:#777">{hospital_city}</div>
                </div>
              </div>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("---")
            # Export as text summary
            cert_text = f"""
شهادة وفاة / DEATH CERTIFICATE
رقم / No: {cert_no}
{'='*50}
المستشفى: {hospital_name} – {hospital_city}
وزارة الصحة – المملكة العربية السعودية

البيانات الأساسية:
- الاسم: {fd.get('full_name_ar','')}
- الهوية: {fd.get('national_id','')}
- الجنس: {fd.get('sex','')}
- العمر: {fd.get('age_years','')} سنة
- تاريخ الوفاة: {fd.get('dod','')}
- مكان الوفاة: {fd.get('place_of_death','')}
- نوع الوفاة: {fd.get('death_type','')}

السيرة الطبية:
- عملية جراحية آخر شهر: {fd.get('had_surgery','')}
- التشريح مطلوب: {fd.get('autopsy_required','')}

أسباب الوفاة:
- السبب الفوري: {concepts.get('immediate_cause','')}
- الأسباب المساهمة: {', '.join(concepts.get('contributing_causes',[]))}
- حالات أخرى: {', '.join(concepts.get('other_conditions',[]))}

توصية ICD-10:
{ai_suggest[:500]}...

الطبيب: {doctor_name}
تاريخ الإصدار: {fd.get('date_issued','')}
"""
            st.download_button(
                "⬇️ تحميل ملخص الشهادة / Download Certificate Summary",
                data=cert_text.encode("utf-8"),
                file_name=f"death_cert_{cert_no}_{fd.get('national_id','')}.txt",
                mime="text/plain",
                use_container_width=True,
            )

    # Navigation
    st.markdown("---")
    col_b1, col_b2, col_b3 = st.columns([1, 1, 4])
    with col_b1:
        if st.button("→ السابق", use_container_width=True):
            st.session_state.page = 3
            st.session_state.icd_results = None
            st.rerun()
    with col_b2:
        if st.button("🔄 شهادة جديدة", use_container_width=True):
            for k in ["page","form_data","icd_results","cert_ready"]:
                st.session_state[k] = None
            st.session_state.page = 1
            st.session_state.form_data = {}
            st.rerun()
