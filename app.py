import streamlit as st
import sqlite3
import time
import qrcode
from io import BytesIO, StringIO
import urllib.parse
import csv

# ---------------------------------------------
# CONFIG (DEPLOYMENT ONLY)
# ---------------------------------------------
HOST = "https://smart-qr-based-attendance-system.streamlit.app"  # YOUR DEPLOYED URL
QR_REFRESH = 2       # seconds: how often QR token interval changes
TOKEN_WINDOW = 30    # seconds: allowed clock drift / validity window
DB_FILE = "attendance.db"


# ---------------------------------------------
# DATABASE INIT
# ---------------------------------------------
@st.cache_resource
def init_db():
    con = sqlite3.connect(DB_FILE, check_same_thread=False)
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            started INTEGER,
            ended INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_name TEXT,
            reg_no TEXT,
            token TEXT,
            token_ts INTEGER,
            submit_ts INTEGER
        )
    """)

    con.commit()
    return con

DB = init_db()


# ---------------------------------------------
# HELPERS
# ---------------------------------------------
def now_int():
    return int(time.time())

def current_interval():
    return now_int() // QR_REFRESH

def make_token(session_name, interval):
    return f"{session_name}|{interval}"

def token_valid(token):
    try:
        parts = token.split("|")
        if len(parts) != 2:
            return False, None, "Invalid token format."

        session_name = parts[0]
        interval = int(parts[1])
        token_ts = interval * QR_REFRESH
        now = now_int()

        if abs(now - token_ts) > TOKEN_WINDOW:
            return False, None, "QR expired, please scan a fresh one."

        cur = DB.cursor()
        cur.execute("SELECT ended FROM sessions WHERE name=?", (session_name,))
        row = cur.fetchone()
        if not row:
            return False, None, "Session not found."
        if row[0] != 0:
            return False, None, "Session has ended."

        return True, token_ts, None

    except Exception as e:
        return False, None, str(e)


def generate_qr_image(url):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=6,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image()

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def session_active(name):
    """Return True if session exists and is not ended (ended == 0)."""
    cur = DB.cursor()
    cur.execute("SELECT started, ended FROM sessions WHERE name=?", (name,))
    row = cur.fetchone()
    return bool(row and row[0] and row[1] == 0)


def start_session(name):
    cur = DB.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO sessions (id, name, started, ended)
        VALUES ((SELECT id FROM sessions WHERE name=?), ?, ?, 0)
    """, (name, name, now_int()))
    DB.commit()


def end_session(name):
    cur = DB.cursor()
    cur.execute("UPDATE sessions SET ended=? WHERE name=?", (now_int(), name))
    DB.commit()


def record_attendance(session_name, reg_no, token, token_ts):
    cur = DB.cursor()

    cur.execute("SELECT id FROM attendance WHERE session_name=? AND reg_no=?", 
                (session_name, reg_no))
    if cur.fetchone():
        return False, "This registration number has already submitted."

    cur.execute("""
        INSERT INTO attendance (session_name, reg_no, token, token_ts, submit_ts)
        VALUES (?, ?, ?, ?, ?)
    """, (session_name, reg_no, token, token_ts, now_int()))
    DB.commit()
    return True, "Attendance marked."


def fetch_attendance(session_name):
    cur = DB.cursor()
    cur.execute("""
        SELECT reg_no, datetime(submit_ts, 'unixepoch')
        FROM attendance
        WHERE session_name=?
        ORDER BY submit_ts
    """, (session_name,))
    return cur.fetchall()


# Helper to unwrap st.query_params values (Streamlit returns lists)
def get_param(params, name, default=""):
    val = params.get(name, default)
    if isinstance(val, list):
        if len(val) == 0:
            return default
        return val[0]
    return val


# ---------------------------------------------
# SESSION STATE SETUP
# ---------------------------------------------
if "session_started" not in st.session_state:
    st.session_state.session_started = False

if "session_end_ts" not in st.session_state:
    st.session_state.session_end_ts = None

if "running_session_name" not in st.session_state:
    st.session_state.running_session_name = ""


# ---------------------------------------------
# STREAMLIT ROUTING / UI
# ---------------------------------------------
st.set_page_config(page_title="QR Attendance", layout="centered")
params = st.query_params
mode = get_param(params, "mode", "teacher")


# ---------------------------------------------
# TEACHER VIEW
# ---------------------------------------------
if mode == "teacher":
    st.title("Teacher Dashboard — QR Attendance")

    st.sidebar.header("Session Controls")

    session_name = st.sidebar.text_input("Session Name", value=st.session_state.running_session_name or "Session1")

    timer_minutes = st.sidebar.number_input(
        "Auto-end after (minutes, 0 = manual end)",
        min_value=0,
        value=0,
        step=1,
        help="If > 0, session will automatically end after this many minutes."
    )

    col1, col2 = st.sidebar.columns(2)
    if col1.button("Start"):
        if session_name.strip():
            start_session(session_name.strip())
            st.session_state.session_started = True
            st.session_state.running_session_name = session_name.strip()
            if timer_minutes and timer_minutes > 0:
                st.session_state.session_end_ts = now_int() + int(timer_minutes) * 60
            else:
                st.session_state.session_end_ts = None
            st.sidebar.success(f"Session '{session_name}' started.")

    if col2.button("End"):
        if session_name.strip():
            end_session(session_name.strip())
            st.session_state.session_started = False
            st.session_state.session_end_ts = None
            st.sidebar.success(f"Session '{session_name}' ended.")

    # If timer expired, end the session
    if st.session_state.session_started and st.session_state.session_end_ts:
        if now_int() >= st.session_state.session_end_ts:
            if st.session_state.running_session_name:
                end_session(st.session_state.running_session_name)
            st.session_state.session_started = False
            st.session_state.session_end_ts = None
            st.sidebar.info("Session auto-ended (timer reached).")

    # Check DB active state (in case another tab ended it)
    is_active_db = session_active(session_name) if session_name else False
    is_active_local = st.session_state.session_started and st.session_state.running_session_name == session_name

    # Stable active banner using markdown (no flashing)
    if session_name and is_active_db and is_active_local:
        st.markdown(f"### 🟢 Session **{session_name}** is active")

        if st.session_state.session_end_ts:
            remaining = st.session_state.session_end_ts - now_int()
            if remaining < 0:
                remaining = 0
            mins = remaining // 60
            secs = remaining % 60
            st.markdown(f"**Time left:** {mins}m {secs}s")

        # QR image and token
        interval = current_interval()
        token = make_token(session_name, interval)
        query = {
            "mode": "mark",
            "session": session_name,
            "token": token
        }
        qr_url = HOST + "/?" + urllib.parse.urlencode(query)
        img_buf = generate_qr_image(qr_url)
        st.image(img_buf, caption="Scan to mark attendance")
        st.caption("QR updates every few seconds while the session is active.")

        # Update QR / countdown
        time.sleep(QR_REFRESH)
        st.rerun()

    else:
        st.info("Start a session to display the QR.")

    # CSV section: only when session is not active in DB
    if session_name and session_active(session_name):
        st.info("CSV will be available once the session ends.")
    else:
        st.subheader("Download Attendance")
        dls = st.text_input("Session to download", value=session_name)
        if st.button("Generate CSV"):
            rows = fetch_attendance(dls.strip())
            if not rows:
                st.warning("No data found for this session.")
            else:
                buf = StringIO()
                writer = csv.writer(buf)
                writer.writerow(["reg_no", "session_name", "timestamp (human)"])
                # Prefix timestamp with apostrophe to force Excel to treat it as text
                for reg, ts in rows:
                    writer.writerow([reg, dls.strip(), f"'{ts}'"])

                csv_data = buf.getvalue().encode("utf-8")

                st.download_button(
                    "Download CSV",
                    data=csv_data,
                    file_name=f"attendance_{dls.strip()}.csv",
                    mime="text/csv"
                )


# ---------------------------------------------
# STUDENT VIEW (QR ONLY)
# ---------------------------------------------
elif mode == "mark":
    st.title("Mark Attendance")

    token = get_param(params, "token", "")
    session_name = get_param(params, "session", "")

    if not token or not session_name:
        st.error("Invalid or incomplete QR link.")
        st.stop()

    valid, token_ts, err = token_valid(token)
    if not valid:
        st.error(err)
        st.stop()

    st.info(f"Session: {session_name}")

    with st.form("attend"):
        reg = st.text_input("Registration Number")
        sub = st.form_submit_button("Submit")

    if sub:
        if not reg.strip():
            st.error("Please enter registration number.")
        else:
            ok, msg = record_attendance(session_name, reg.strip(), token, token_ts)
            if ok:
                st.success("Attendance Recorded ✔")
            else:
                st.error(msg)
