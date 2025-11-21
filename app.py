import streamlit as st
import sqlite3
import time
import qrcode
from io import BytesIO, StringIO
import urllib.parse
import csv

HOST = "https://smart-qr-based-attendance-system.streamlit.app"
QR_REFRESH = 1
TOKEN_WINDOW = 30
DB_FILE = "attendance.db"

# ---------------------------
# DATABASE INIT
# ---------------------------
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

def now_int():
    return int(time.time())

def now_ist_struct():
    # Convert current UTC epoch to IST struct_time (UTC +5:30)
    ist_offset = 5 * 3600 + 30 * 60
    return time.localtime(now_int() + ist_offset)

def format_session_unique(base_name):
    """
    Format unique session name as:
      <base>_YYYYMMDD_HHMM  (IST)
    """
    base = base_name.strip() or "Session"
    t = now_ist_struct()
    suffix = time.strftime("%Y%m%d_%H%M", t)
    return f"{base}_{suffix}"

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
    cur = DB.cursor()
    cur.execute("SELECT started, ended FROM sessions WHERE name=?", (name,))
    row = cur.fetchone()
    return bool(row and row[0] and row[1] == 0)

def start_session(unique_name):
    """Insert session row (unique_name already includes date/time)."""
    cur = DB.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO sessions (id, name, started, ended)
        VALUES ((SELECT id FROM sessions WHERE name=?), ?, ?, 0)
    """, (unique_name, unique_name, now_int()))
    DB.commit()

def end_session(name):
    cur = DB.cursor()
    cur.execute("UPDATE sessions SET ended=? WHERE name=?", (now_int(), name))
    DB.commit()

def record_attendance(session_name, reg_no, token, token_ts):
    cur = DB.cursor()
    cur.execute("SELECT id FROM attendance WHERE session_name=? AND reg_no=?", (session_name, reg_no))
    if cur.fetchone():
        return False, "This registration number has already submitted."
    cur.execute("""
        INSERT INTO attendance (session_name, reg_no, token, token_ts, submit_ts)
        VALUES (?, ?, ?, ?, ?)
    """, (session_name, reg_no, token, token_ts, now_int()))
    DB.commit()
    return True, "Attendance marked."

def fetch_attendance(session_name):
    """
    Return rows with IST converted timestamp.
    SQLite datetime(..., 'unixepoch', '+5 hours', '30 minutes') converts UTC->IST.
    """
    cur = DB.cursor()
    cur.execute("""
        SELECT reg_no, datetime(submit_ts, 'unixepoch', '+5 hours', '30 minutes')
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

if "session_started" not in st.session_state:
    st.session_state.session_started = False

if "session_end_ts" not in st.session_state:
    st.session_state.session_end_ts = None

if "running_session_name" not in st.session_state:
    st.session_state.running_session_name = ""  # unique name (with timestamp)

if "running_session_display" not in st.session_state:
    st.session_state.running_session_display = ""  # base name shown in sidebar

if "last_session_name" not in st.session_state:
    st.session_state.last_session_name = ""  # the most recent unique name (ended or running)

# Notification structure: {'msg': str, 'ts': epoch}
if "notification" not in st.session_state:
    st.session_state.notification = None

# Student-side submit lock (per browser)
if "submitted_once" not in st.session_state:
    st.session_state.submitted_once = False


def show_notification(msg, duration_s=3):
    """Set a transient notification to appear top-right for duration_s seconds."""
    st.session_state.notification = {"msg": msg, "ts": now_int(), "dur": duration_s}


def render_notification():
    n = st.session_state.get("notification")
    if not n:
        return
    age = now_int() - n["ts"]
    if age > n.get("dur", 3):
        # expired -> clear
        st.session_state.notification = None
        return
    # render a small top-right fixed box via HTML/CSS
    escaped = n["msg"].replace("'", "\\'")
    html = f"""
    <div style="
        position:fixed; top:20px; right:20px; z-index:9999;
        background:#0f5132; color:white; padding:10px 14px; border-radius:8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.25); font-weight:600;">
        {escaped}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


# ---------------------------
# STREAMLIT ROUTING / UI
# ---------------------------
st.set_page_config(page_title="QR Attendance", layout="centered")
params = st.query_params
mode = get_param(params, "mode", "teacher")

# Render notification at top of page (so it appears on both teacher/student views)
render_notification()

# teacher dashboard
if mode == "teacher":
    st.title("Teacher Dashboard — QR Attendance")

    st.sidebar.header("Session Controls")

    # Sidebar: base name input
    base_session_name = st.sidebar.text_input("Session Name (base)", value=st.session_state.running_session_display or "Session1")

    # Sidebar: label must just say "Timer" with a help tooltip
    timer_minutes = st.sidebar.number_input(
        "Timer",
        min_value=0,
        value=0,
        step=1,
        help="Auto-end after this many minutes. Set 0 for manual end."
    )

    col1, col2 = st.sidebar.columns(2)
    if col1.button("Start"):
        if base_session_name.strip():
            unique_name = format_session_unique(base_session_name)
            start_session(unique_name)
            st.session_state.session_started = True
            st.session_state.running_session_name = unique_name
            st.session_state.running_session_display = base_session_name.strip()
            st.session_state.last_session_name = unique_name
            if timer_minutes and timer_minutes > 0:
                st.session_state.session_end_ts = now_int() + int(timer_minutes) * 60
            else:
                st.session_state.session_end_ts = None

            show_notification("Session started.")

    if col2.button("End"):
        if st.session_state.running_session_name:
            end_session(st.session_state.running_session_name)
            st.session_state.session_started = False
            st.session_state.session_end_ts = None
            st.session_state.last_session_name = st.session_state.running_session_name
            st.session_state.running_session_name = ""
            st.session_state.running_session_display = ""
            show_notification("Session ended.")

    # If timer expired, end the session automatically
    if st.session_state.session_started and st.session_state.session_end_ts:
        if now_int() >= st.session_state.session_end_ts:
            if st.session_state.running_session_name:
                end_session(st.session_state.running_session_name)
                st.session_state.last_session_name = st.session_state.running_session_name
            st.session_state.session_started = False
            st.session_state.session_end_ts = None
            st.session_state.running_session_name = ""
            st.session_state.running_session_display = ""
            show_notification("Session auto-ended (timer).")

    # Check DB active state (in case another tab ended it)
    is_active_db = session_active(st.session_state.running_session_name) if st.session_state.running_session_name else False
    is_active_local = st.session_state.session_started and bool(st.session_state.running_session_name)

    # Active banner (markdown to avoid flashing)
    if is_active_db and is_active_local:
        st.markdown(f"### Session **{st.session_state.running_session_name}** is active")
        if st.session_state.session_end_ts:
            remaining = st.session_state.session_end_ts - now_int()
            if remaining < 0:
                remaining = 0
            mins = remaining // 60
            secs = remaining % 60
            st.markdown(f"**Time left:** {mins}m {secs}s")

        # QR generation using a single placeholder slot
        qr_slot = st.empty()  # placeholder to update/replace in-place

        interval = current_interval()
        token = make_token(st.session_state.running_session_name, interval)
        query = {
            "mode": "mark",
            "session": st.session_state.running_session_name,
            "token": token
        }
        qr_url = HOST + "/?" + urllib.parse.urlencode(query)
        img_buf = generate_qr_image(qr_url)

        with qr_slot:
            st.image(img_buf, caption="Scan to mark attendance")

        time.sleep(QR_REFRESH)
        st.rerun()

    else:
        st.info("Start a session to display the QR.")

    st.subheader("Download Attendance")
    default_dl = st.session_state.last_session_name or ""
    dls = st.text_input("Session to download (exact unique name)", value=default_dl)
    if st.button("Generate CSV"):
        if not dls.strip():
            st.warning("Enter the exact unique session name to generate the CSV (see 'Session started.' popup).")
        else:
            rows = fetch_attendance(dls.strip())
            if not rows:
                st.warning("No data found for this session.")
            else:
                buf = StringIO()
                writer = csv.writer(buf)
                writer.writerow(["reg_no", "session_name", "timestamp (human)"])
                for reg, ts in rows:
                    writer.writerow([reg, dls.strip(), f"'{ts}'"])
                csv_data = buf.getvalue().encode("utf-8")
                st.download_button(
                    "Download CSV",
                    data=csv_data,
                    file_name=f"attendance_{dls.strip()}.csv",
                    mime="text/csv"
                )

# student view
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

    if st.session_state.submitted_once:
        st.success("Your attendance is already recorded ✔")
    else:
        with st.form("attend"):
            reg = st.text_input("Registration Number")
            sub = st.form_submit_button("Submit")

        if sub:
            if not reg.strip():
                st.error("Please enter registration number.")
            else:
                ok, msg = record_attendance(session_name, reg.strip(), token, token_ts)
                if ok:
                    st.session_state.submitted_once = True
                    st.success("Attendance Recorded ✔")
                else:
                    st.error(msg)
