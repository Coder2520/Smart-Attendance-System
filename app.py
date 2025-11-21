import streamlit as st
import sqlite3
import time
import qrcode
from io import BytesIO, StringIO
import urllib.parse
import csv

# ---------------------------
# CONFIG (Deployment only)
# ---------------------------
HOST = "https://smart-qr-based-attendance-system.streamlit.app"
QR_REFRESH = 1        # seconds per QR refresh
TOKEN_WINDOW = 30     # seconds token validity window
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

# ---------------------------
# HELPERS
# ---------------------------
def now_int():
    return int(time.time())

def now_ist_struct():
    # IST = UTC + 5:30
    ist_offset = 5 * 3600 + 30 * 60
    return time.localtime(now_int() + ist_offset)

def format_session_unique(base):
    """
    Create unique:   <base>_YYYYMMDD_HHMM   (IST)
    """
    base = base.strip() or "Session"
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
            return False, None, "QR expired, scan a fresh one."

        cur = DB.cursor()
        cur.execute("SELECT ended FROM sessions WHERE name=?", (session_name,))
        row = cur.fetchone()

        if not row:
            return False, None, "Session not found."
        if row[0] != 0:
            return False, None, "Session has ended."

        return True, token_ts, None
    except:
        return False, None, "Invalid token."

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
    if not name:
        return False
    cur = DB.cursor()
    cur.execute("SELECT started, ended FROM sessions WHERE name=?", (name,))
    r = cur.fetchone()
    return bool(r and r[0] and r[1] == 0)

def start_session(unique):
    cur = DB.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO sessions (id, name, started, ended)
        VALUES ((SELECT id FROM sessions WHERE name=?), ?, ?, 0)
    """, (unique, unique, now_int()))
    DB.commit()

def end_session(name):
    cur = DB.cursor()
    cur.execute("UPDATE sessions SET ended=? WHERE name=?", (now_int(), name))
    DB.commit()

def record_attendance(sess, reg, token, token_ts):
    cur = DB.cursor()
    cur.execute("SELECT id FROM attendance WHERE session_name=? AND reg_no=?", (sess, reg))
    if cur.fetchone():
        return False, "This registration number has already submitted."

    cur.execute("""
        INSERT INTO attendance (session_name, reg_no, token, token_ts, submit_ts)
        VALUES (?, ?, ?, ?, ?)
    """, (sess, reg, token, token_ts, now_int()))
    DB.commit()
    return True, "Attendance Recorded."

def fetch_attendance(session_name):
    cur = DB.cursor()
    cur.execute("""
        SELECT reg_no, datetime(submit_ts, 'unixepoch', '+5 hours', '30 minutes')
        FROM attendance
        WHERE session_name=?
        ORDER BY submit_ts
    """, (session_name,))
    return cur.fetchall()

def get_param(params, key, default=""):
    v = params.get(key, default)
    if isinstance(v, list):
        return v[0] if v else default
    return v

# ---------------------------
# SESSION STATE
# ---------------------------
if "running_session_name" not in st.session_state:
    st.session_state.running_session_name = ""
if "running_session_display" not in st.session_state:
    st.session_state.running_session_display = ""
if "last_session_name" not in st.session_state:
    st.session_state.last_session_name = ""
if "notification" not in st.session_state:
    st.session_state.notification = None

def show_notification(msg, duration=3):
    st.session_state.notification = {"msg": msg, "ts": now_int(), "dur": duration}

def render_notification():
    n = st.session_state.notification
    if not n:
        return
    if now_int() - n["ts"] > n["dur"]:
        st.session_state.notification = None
        return
    escaped = n["msg"].replace("'", "\\'")
    st.markdown(
        f"""
        <div style="
            position:fixed; top:20px; right:20px; z-index:9999;
            background:#0f5132; color:white;
            padding:10px 14px; border-radius:8px;
            box-shadow:0 4px 12px rgba(0,0,0,0.25);
            font-weight:600;">
            {escaped}
        </div>
        """,
        unsafe_allow_html=True
    )

# ---------------------------
# ROUTE
# ---------------------------
st.set_page_config(page_title="QR Attendance", layout="centered")
params = st.query_params
mode = get_param(params, "mode", "teacher")

render_notification()

# ---------------------------
# TEACHER VIEW
# ---------------------------
if mode == "teacher":
    st.title("Teacher Dashboard — QR Attendance")

    st.sidebar.header("Session Controls")
    base = st.sidebar.text_input("Session Name (base)", value=st.session_state.running_session_display or "Session1")

    col1, col2 = st.sidebar.columns(2)

    if col1.button("Start"):
        if base.strip():
            unique = format_session_unique(base)
            start_session(unique)

            st.session_state.running_session_name = unique
            st.session_state.running_session_display = base.strip()
            st.session_state.last_session_name = unique

            show_notification("Session started.")

    if col2.button("End"):
        rn = st.session_state.running_session_name
        if rn:
            end_session(rn)
            st.session_state.last_session_name = rn
            st.session_state.running_session_name = ""
            st.session_state.running_session_display = ""
            show_notification("Session ended.")

    rn = st.session_state.running_session_name
    active = session_active(rn)

    if active:
        st.markdown(f"### 🟢 Session **{rn}** is active")

        # ----------------------
        # QR Refresh Block
        # ----------------------
        qr_slot = st.empty()

        interval = current_interval()
        token = make_token(rn, interval)
        query = {
            "mode": "mark",
            "session": rn,
            "token": token
        }
        qr_url = HOST + "/?" + urllib.parse.urlencode(query)
        img = generate_qr_image(qr_url)

        qr_slot.image(img, caption="Scan to mark attendance")
        st.caption("QR updates every second.")

        time.sleep(QR_REFRESH)
        st.rerun()

    else:
        st.info("Start a session to display the QR.")

    st.subheader("Download Attendance")
    dls = st.text_input("Session to download", value=st.session_state.last_session_name)

    if st.button("Generate CSV"):
        if not dls.strip():
            st.warning("Enter the session name.")
        else:
            rows = fetch_attendance(dls.strip())
            if not rows:
                st.warning("No data found for this session.")
            else:
                buf = StringIO()
                w = csv.writer(buf)
                w.writerow(["reg_no", "session_name", "timestamp (IST)"])
                for reg, ts in rows:
                    w.writerow([reg, dls.strip(), f"'{ts}'"])
                csv_data = buf.getvalue().encode("utf-8")
                st.download_button(
                    "Download CSV",
                    data=csv_data,
                    file_name=f"attendance_{dls.strip()}.csv",
                    mime="text/csv"
                )

# ---------------------------
# STUDENT VIEW
# ---------------------------
elif mode == "mark":
    st.title("Mark Attendance")

    token = get_param(params, "token", "")
    session_name = get_param(params, "session", "")

    if not token or not session_name:
        st.error("Invalid or incomplete QR.")
        st.stop()

    valid, token_ts, err = token_valid(token)
    if not valid:
        st.error(err)
        st.stop()

    st.info(f"Session: {session_name}")

    lock_key = f"submitted_{session_name}"
    if lock_key not in st.session_state:
        st.session_state[lock_key] = False

    if st.session_state[lock_key]:
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
                    st.session_state[lock_key] = True
                    st.success("Attendance Recorded ✔")
                else:
                    st.error(msg)
