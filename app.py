import streamlit as st
import google.generativeai as genai
import pandas as pd
import io
import os
import json
from datetime import datetime
import csv
import time
from dotenv import load_dotenv

# ==================================================
# ================== AUTH SESSION ==================
# ==================================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if "user_email" not in st.session_state:
    st.session_state.user_email = None

if "usage_count" not in st.session_state:
    st.session_state.usage_count = 0

if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_mode" not in st.session_state:
    st.session_state.last_mode = None

# Excel states
if "combined_df" not in st.session_state:
    st.session_state.combined_df = None

if "reco_result" not in st.session_state:
    st.session_state.reco_result = None

FREE_USAGE_LIMIT = 5

# ==================================================
# ================== ENV SETUP =====================
# ==================================================

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    st.error("❌ GEMINI_API_KEY not set. Please configure it in deployment secrets.")
    st.stop()

genai.configure(api_key=api_key)

# ==================================================
# ================== PAGE SETUP ===================
# ==================================================
st.set_page_config(
    page_title="Finance AI Assistant",
    layout="centered"
)

st.title("💼 Finance AI Assistant")
st.caption("Talk to an experienced finance professional")

# ==================================================
# ================== LOGIN =========================
# ==================================================

LOG_FILE = "user_activity_log.csv"

def log_login(email):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    file_exists = os.path.exists(LOG_FILE)

    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow(["email", "login_time", "logout_time", "session_minutes"])

        writer.writerow([email, now, "", ""])


def log_logout(email):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if not os.path.exists(LOG_FILE):
        return

    df = pd.read_csv(LOG_FILE)

    # last open session for this email
    mask = (df["email"] == email) & (df["logout_time"].isna() | (df["logout_time"] == ""))

    if mask.any():
        idx = df[mask].index[-1]

        login_time = datetime.strptime(df.loc[idx, "login_time"], "%Y-%m-%d %H:%M:%S")
        logout_time = datetime.strptime(now, "%Y-%m-%d %H:%M:%S")

        duration = round((logout_time - login_time).total_seconds() / 60, 2)

        df.loc[idx, "logout_time"] = now
        df.loc[idx, "session_minutes"] = duration

        df.to_csv(LOG_FILE, index=False)

def load_allowed_users():
    try:
        with open("allowed_users.json", "r") as f:
            data = json.load(f)
            return set(email.lower() for email in data.get("allowed_emails", []))
    except FileNotFoundError:
        return set()

def login_ui():

    st.subheader("🔐 Login to Finance AI")
    email = st.text_input("Email")

    allowed_users = load_allowed_users()

    if st.button("Login / Continue"):

        if not email or "@" not in email:
            st.error("Please enter a valid email")
            return

        email_clean = email.strip().lower()

        if email_clean not in allowed_users:
            st.error("🚫 Access denied. Please contact the app developer for access.")
            return

        st.session_state.logged_in = True
        st.session_state.user_email = email_clean
        log_login(email_clean)
        st.success("✅ Logged in successfully")
        st.rerun()

if not st.session_state.logged_in:
    login_ui()
    st.stop()

# ==================================================
# ================== SIDEBAR ======================
# ==================================================
with st.sidebar:
    st.markdown("### 👤 Account")
    st.write(st.session_state.user_email)
    st.write(f"Usage: {st.session_state.usage_count}/{FREE_USAGE_LIMIT}")

    if st.button("Logout"):
        log_logout(st.session_state.user_email)

        st.session_state.logged_in = False
        st.session_state.user_email = None
        st.session_state.messages = []
        st.session_state.reco_result = None
        st.session_state.combined_df = None
        st.rerun()


# ==================================================
# ================== MODE =========================
# ==================================================
mode = st.selectbox(
    "Choose Mode",
    ["Finance Research", "Career Guide", "Excel AI"]
)

if st.session_state.last_mode != mode:
    st.session_state.messages = []
    st.session_state.last_mode = mode

# ==================================================
# ================== PROMPTS ======================
# ==================================================
def build_prompt(mode, conversation):
    if mode == "Finance Research":
        return (
            "You are a senior finance research analyst with 20+ years of experience in India. "
            "Analyse company professionally with structure.\n\n"
            + conversation
        )
    if mode == "Career Guide":
        return (
            "You are a senior finance career mentor from India. "
            "Guide step by step with a 6–12 month roadmap.\n\n"
            + conversation
        )
    return conversation

# ==================================================
# ================== CHAT UI =======================
# ==================================================

if mode in ["Finance Research", "Career Guide"]:

    # --- Render existing chat history ---
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # --- Chat input ---
    user_input = st.chat_input("Type your message...")

    if user_input:

        # --- Add & immediately show user message ---
        st.session_state.messages.append(
            {"role": "user", "content": user_input}
        )

        with st.chat_message("user"):
            st.write(user_input)

        # --- Build conversation text ---
        conversation = ""
        for msg in st.session_state.messages:
            role = "User" if msg["role"] == "user" else "AI"
            conversation += f"{role}: {msg['content']}\n"

        full_prompt = build_prompt(mode, conversation)

        # --- AI response with typing effect ---
        with st.chat_message("assistant"):

            placeholder = st.empty()

            try:
                model = genai.GenerativeModel("gemini-3-flash-preview")
                response = model.generate_content(full_prompt)
                reply = response.text

                typed_text = ""

                for char in reply:
                    typed_text += char
                    placeholder.markdown(typed_text)
                    time.sleep(0.005)   # typing speed control

                # --- Save assistant reply ---
                st.session_state.messages.append(
                    {"role": "assistant", "content": reply}
                )

            except Exception as e:
                st.error("AI service temporarily unavailable")
                st.code(str(e))

	# ==================================================
# ================== EXCEL AI =====================
# ==================================================
if mode == "Excel AI":

    st.header("📊 Excel AI Tools")

    excel_task = st.selectbox(
        "Choose Task",
        ["Select", "Combine Files", "Bank Reconciliation"]
    )

    # ==================================================
    # ================= COMBINE FILES ==================
    # ==================================================
    if excel_task == "Combine Files":

        uploaded_files = st.file_uploader(
            "Upload Excel files (same headers)",
            type=["xlsx"],
            accept_multiple_files=True
        )

        if uploaded_files and len(uploaded_files) >= 2:

            dfs = []
            ref_cols = None

            for f in uploaded_files:
                df = pd.read_excel(f)
                if ref_cols is None:
                    ref_cols = list(df.columns)
                if list(df.columns) != ref_cols:
                    st.error("❌ Header mismatch")
                    st.stop()
                dfs.append(df)

            if st.button("🔄 Combine Files"):

                if st.session_state.usage_count >= FREE_USAGE_LIMIT:
                    st.error("🚫 Free usage limit reached.")
                    st.stop()

                st.session_state.combined_df = pd.concat(dfs, ignore_index=True)
                st.session_state.usage_count += 1

        if st.session_state.combined_df is not None:
            st.subheader("📄 Preview")
            st.dataframe(st.session_state.combined_df.head(50))

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                st.session_state.combined_df.to_excel(
                    writer, index=False, sheet_name="Combined"
                )

            st.download_button(
                "⬇️ Download Combined Excel",
                data=output.getvalue(),
                file_name="combined_excel.xlsx"
            )

    # ==================================================
    # ================ BANK RECONCILIATION =============
    # ==================================================
    if excel_task == "Bank Reconciliation":

        bank_file = st.file_uploader("Upload Bank Statement", type=["xlsx"])
        books_file = st.file_uploader("Upload Books Ledger", type=["xlsx"])

        if bank_file and books_file:

            bank = pd.read_excel(bank_file)
            books = pd.read_excel(books_file)

            st.markdown("### Column Mapping")

            bank_amt = st.selectbox("Bank Amount", [""] + list(bank.columns))
            bank_date = st.selectbox("Bank Date (Optional)", [""] + list(bank.columns))
            bank_narr = st.selectbox("Bank Narration (Optional)", [""] + list(bank.columns))

            books_amt = st.selectbox("Books Amount", [""] + list(books.columns))
            books_date = st.selectbox("Books Date (Optional)", [""] + list(books.columns))
            books_narr = st.selectbox("Books Narration (Optional)", [""] + list(books.columns))

            if st.button("🔄 Run Reconciliation"):

                if st.session_state.usage_count >= FREE_USAGE_LIMIT:
                    st.error("🚫 Free usage limit reached.")
                    st.stop()

                def norm_amt(x):
                    try: return abs(float(x))
                    except: return None

                def norm_date(x):
                    try: return pd.to_datetime(x).date()
                    except: return None

                def norm_text(x):
                    return "" if pd.isna(x) else str(x).lower().strip()

                bank["__amt__"] = bank[bank_amt].apply(norm_amt)
                books["__amt__"] = books[books_amt].apply(norm_amt)

                keys = ["__amt__"]

                if bank_date and books_date:
                    bank["__date__"] = bank[bank_date].apply(norm_date)
                    books["__date__"] = books[books_date].apply(norm_date)
                    keys.append("__date__")

                if bank_narr and books_narr:
                    bank["__narr__"] = bank[bank_narr].apply(norm_text)
                    books["__narr__"] = books[books_narr].apply(norm_text)
                    keys.append("__narr__")

                reco = bank.merge(
                    books,
                    how="outer",
                    left_on=keys,
                    right_on=keys,
                    indicator=True,
                    suffixes=("_bank", "_books")
                )

                matched = reco[reco["_merge"] == "both"].copy()
                bank_only = reco[reco["_merge"] == "left_only"].copy()
                books_only = reco[reco["_merge"] == "right_only"].copy()

                st.session_state.reco_result = {
                    "matched": matched,
                    "bank_only": bank_only,
                    "books_only": books_only
                }

                st.session_state.usage_count += 1

        if st.session_state.reco_result:

            st.subheader("📊 Reconciliation Summary")
            st.write({
                "Matched": len(st.session_state.reco_result["matched"]),
                "Bank Only": len(st.session_state.reco_result["bank_only"]),
                "Books Only": len(st.session_state.reco_result["books_only"])
            })

            with st.expander("✅ Matched"):
                st.dataframe(st.session_state.reco_result["matched"].head(50))

            with st.expander("❌ Bank Only"):
                st.dataframe(st.session_state.reco_result["bank_only"].head(50))

            with st.expander("❌ Books Only"):
                st.dataframe(st.session_state.reco_result["books_only"].head(50))

            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                st.session_state.reco_result["matched"].to_excel(writer, sheet_name="Matched", index=False)
                st.session_state.reco_result["bank_only"].to_excel(writer, sheet_name="Bank_Only", index=False)
                st.session_state.reco_result["books_only"].to_excel(writer, sheet_name="Books_Only", index=False)

            st.download_button(
                "⬇️ Download Reconciliation Excel",
                data=output.getvalue(),
                file_name="bank_reconciliation.xlsx"
            )
