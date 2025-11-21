import streamlit as st
import sqlite3
import time
import urllib.parse
import csv
from io import StringIO

# ---------------------------------------------------
# CONFIG
# ---------------------------------------------------
HOST = "https://smart-qr-based-attendance-system.streamlit.app"
QR_REFRESH = 1            # seconds (client-side in JS)
TOKEN_WINDOW = 30         # seconds
DB_FILE = "attendance.db"

# ---------------------------------------------------
# DATABASE INIT
# ---------------------------------------------------
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

# ---------------------------------------------------
# HELPERS
# ---------------------------------------------------
def now_int():
    return int(time.time())

def now_ist_struct():
    # IST = UTC + 5:30
    offset = 5 * 3600 + 30 * 60
    return time.localtime(now_int() + offset)

def format_session_unique(base_name):
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
            return False, None, "Invalid token."

        session_name = parts[0]
        interval = int(parts[1])
        token_ts = interval * QR_REFRESH
        now = now_int()

        if abs(now - token_ts) > TOKEN_WINDOW:
            return False, None, "QR expired."

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

def session_active(session_name):
    if not session_name:
        return False
    cur = DB.cursor()
    cur.execute("SELECT started, ended FROM sessions WHERE name=?", (session_name,))
    row = cur.fetchone()
    return bool(row and row[0] and row[1] == 0)

def start_session(unique_name):
    cur = DB.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO sessions (id, name, started, ended)
        VALUES ((SELECT id FROM sessions WHERE name=?), ?, ?, 0)
    """, (unique_name, unique_name, now_int()))
    DB.commit()

def end_session(session_name):
    cur = DB.cursor()
    cur.execute("UPDATE sessions SET ended=? WHERE name=?", (now_int(), session_name))
    DB.commit()

def record_attendance(session, reg, token, token_ts):
    cur = DB.cursor()
    cur.execute("SELECT id FROM attendance WHERE session_name=? AND reg_no=?", (session, reg))
    if cur.fetchone():
        return False, "Already submitted."

    cur.execute("""
        INSERT INTO attendance (session_name, reg_no, token, token_ts, submit_ts)
        VALUES (?, ?, ?, ?, ?)
    """, (session, reg, token, token_ts, now_int()))
    DB.commit()
    return True, "Attendance Recorded."

def fetch_attendance(session):
    cur = DB.cursor()
    cur.execute("""
        SELECT reg_no, datetime(submit_ts,'unixepoch','+5 hours','30 minutes')
        FROM attendance
        WHERE session_name=?
        ORDER BY submit_ts
    """, (session,))
    return cur.fetchall()

def get_param(params, key, default=""):
    v = params.get(key, default)
    if isinstance(v, list):
        return v[0] if v else default
    return v

# ---------------------------------------------------
# SESSION STATE
# ---------------------------------------------------
if "running_session" not in st.session_state:
    st.session_state.running_session = ""

if "running_display" not in st.session_state:
    st.session_state.running_display = ""

if "last_session" not in st.session_state:
    st.session_state.last_session = ""

if "notification" not in st.session_state:
    st.session_state.notification = None

# Notification functions
def notify(msg, dur=3):
    st.session_state.notification = {"msg": msg, "ts": now_int(), "dur": dur}

def render_notify():
    n = st.session_state.notification
    if not n:
        return
    if now_int() - n["ts"] > n["dur"]:
        st.session_state.notification = None
        return

    msg = n["msg"].replace("'", "\\'")
    st.markdown(
        f"""
        <div style="
            position:fixed; top:20px; right:20px; z-index:9999;
            background:#0f5132; color:white;
            padding:10px 15px; border-radius:8px;
            box-shadow:0 4px 10px rgba(0,0,0,0.3);">
            {msg}
        </div>
        """,
        unsafe_allow_html=True
    )

# ---------------------------------------------------
# ROUTING
# ---------------------------------------------------
st.set_page_config(page_title="QR Attendance", layout="centered")
params = st.query_params
mode = get_param(params, "mode", "teacher")

render_notify()

# ---------------------------------------------------
# TEACHER VIEW
# ---------------------------------------------------
if mode == "teacher":
    st.title("Teacher Dashboard — QR Attendance")

    st.sidebar.header("Session Controls")

    base = st.sidebar.text_input(
        "Session Name (base)",
        value=st.session_state.running_display or "Session1"
    )

    c1, c2 = st.sidebar.columns(2)

    # START session
    if c1.button("Start"):
        unique = format_session_unique(base)
        start_session(unique)
        st.session_state.running_session = unique
        st.session_state.running_display = base
        st.session_state.last_session = unique
        notify("Session started.")

    # END session
    if c2.button("End"):
        rn = st.session_state.running_session
        if rn:
            end_session(rn)
            st.session_state.last_session = rn
            st.session_state.running_session = ""
            st.session_state.running_display = ""
            notify("Session ended.")

    rn = st.session_state.running_session

    # ACTIVE SESSION
    if session_active(rn):
        st.markdown(f"### Session **{rn}** is active")

        # ---------------------------------------------------
        # NON-FLICKERING QR VIA JS IN st.components.html
        # ---------------------------------------------------
        qr_html = f"""
        <div id="qr_area" style="text-align:center;">
            <img id="qr_img" src="" style="width:260px;border-radius:8px;">
            <div style="color:#6c757d;margin-top:6px;">Scan to mark attendance</div>
        </div>

        <script>
        const host = "{HOST}";
        const session = "{rn}";
        const refresh = {QR_REFRESH} * 1000;

        function updateQR() {{
            const unix = Math.floor(Date.now()/1000);
            const interval = Math.floor(unix / {QR_REFRESH});
            const token = session + "|" + interval;

            const url = host + "/?mode=mark&session="
                       + encodeURIComponent(session)
                       + "&token=" + encodeURIComponent(token);

            const apiURL = "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data="
                           + encodeURIComponent(url);

            const img = document.getElementById("qr_img");
            if (img) {{
                img.src = apiURL + "&t=" + Date.now();
            }}
        }}

        updateQR();
        if (window.qrInterval) clearInterval(window.qrInterval);
        window.qrInterval = setInterval(updateQR, refresh);
        </script>
        """

        st.components.v1.html(qr_html, height=350)

    else:
        st.info("Start a session to display the QR.")

    # ---------------------------------------------------
    # CSV SECTION
    # ---------------------------------------------------
    st.subheader("Download Attendance")

    dls = st.text_input("Session to download", value=st.session_state.last_session)

    if st.button("Generate CSV"):
        rows = fetch_attendance(dls.strip())
        if not rows:
            st.warning("No data found.")
        else:
            buf = StringIO()
            w = csv.writer(buf)
            w.writerow(["reg_no", "session", "timestamp (IST)"])
            for reg, ts in rows:
                w.writerow([reg, dls.strip(), f"'{ts}'"])

            st.download_button(
                "Download CSV",
                buf.getvalue().encode(),
                file_name=f"attendance_{dls.strip()}.csv",
                mime="text/csv"
            )

# ---------------------------------------------------
# STUDENT VIEW
# ---------------------------------------------------
elif mode == "mark":
    st.title("Mark Attendance")

    token = get_param(params, "token", "")
    session = get_param(params, "session", "")

    if not token or not session:
        st.error("Invalid QR.")
        st.stop()

    valid, token_ts, err = token_valid(token)
    if not valid:
        st.error(err)
        st.stop()

    st.info(f"Session: {session}")

    lock_key = f"submitted_{session}"
    if lock_key not in st.session_state:
        st.session_state[lock_key] = False

    if st.session_state[lock_key]:
        st.error("Attendance already recorded for this session.")
    else:
        with st.form("attend"):
            reg = st.text_input("Registration Number")
            submit = st.form_submit_button("Submit")

        if submit:
            if not reg.strip():
                st.error("Enter registration number.")
            else:
                ok, msg = record_attendance(session, reg.strip(), token, token_ts)
                if ok:
                    st.session_state[lock_key] = True
                    st.success("Attendance Recorded ✔")
                else:
                    st.error(msg)
