import streamlit as st
import time
import sqlite3
import qrcode
from io import BytesIO
import urllib.parse
import csv
import os

# ---------------- CONFIG ----------------
# On Streamlit Cloud, the app URL is public, so HOST auto-detect is fine:
HOST = st.secrets.get("HOST", "")  # empty means "use relative paths"

QR_INTERVAL_SECONDS = 2
TOKEN_WINDOW_SECONDS = 30
DB_PATH = "/mount/data/attendance.db"

# ---------------- DB ----------------
def init_db():
    con = sqlite3.connect("attendance.db", check_same_thread=False)
    cur = con.cursor()

    cur.execute("""CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    started INTEGER,
                    ended INTEGER DEFAULT 0
                )""")

    cur.execute("""CREATE TABLE IF NOT EXISTS attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_name TEXT,
                    reg_no TEXT,
                    token TEXT,
                    token_ts INTEGER,
                    submit_ts INTEGER
                )""")

    con.commit()
    return con

DB = init_db()

# ---------------- Helpers ----------------
def current_interval():
    return int(time.time() // QR_INTERVAL_SECONDS)

def make_token(session_name, interval):
    return f"{session_name}|{interval}"

def token_valid(token):
    try:
        parts = token.split("|")
        if len(parts) != 2:
            return False, None, "Malformed token"
        session_name = parts[0]
        interval = int(parts[1])
        token_ts = interval * QR_INTERVAL_SECONDS
        now = time.time()

        if abs(now - token_ts) <= TOKEN_WINDOW_SECONDS:
            cur = DB.cursor()
            cur.execute("SELECT ended FROM sessions WHERE name=?", (session_name,))
            row = cur.fetchone()
            if not row:
                return False, None, "Session not found"
            ended = row[0]
            if ended:
                return False, None, "Session ended"
            return True, token_ts, None
        else:
            return False, None, "Token expired"
    except Exception as e:
        return False, None, str(e)

def generate_qr_image(url):
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def start_session(session_name):
    cur = DB.cursor()
    now = int(time.time())
    cur.execute("""INSERT OR REPLACE INTO sessions
                   (id, name, started, ended)
                   VALUES ((SELECT id FROM sessions WHERE name=?), ?, ?, 0)""",
                (session_name, session_name, now))
    DB.commit()

def end_session(session_name):
    cur = DB.cursor()
    now = int(time.time())
    cur.execute("UPDATE sessions SET ended=? WHERE name=?", (now, session_name))
    DB.commit()

def session_active(session_name):
    cur = DB.cursor()
    cur.execute("SELECT started, ended FROM sessions WHERE name=?", (session_name,))
    row = cur.fetchone()
    if not row:
        return False
    started, ended = row
    return started and not ended

def record_attendance(session_name, reg_no, token, token_ts):
    cur = DB.cursor()
    cur.execute("SELECT id FROM attendance WHERE session_name=? AND reg_no=? LIMIT 1",
                (session_name, reg_no))
    if cur.fetchone():
        return False, "This registration number already submitted."

    now = int(time.time())
    cur.execute("""INSERT INTO attendance
                   (session_name, reg_no, token, token_ts, submit_ts)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_name, reg_no, token, token_ts, now))
    DB.commit()
    return True, "Attendance recorded."

def get_attendance_for_session(session_name):
    cur = DB.cursor()
    cur.execute("SELECT reg_no, datetime(submit_ts, 'unixepoch') 
                 FROM attendance 
                 WHERE session_name=? ORDER BY submit_ts",
                (session_name,))
    return cur.fetchall()

# ---------------- Streamlit UI ----------------
st.set_page_config(page_title="QR Attendance (Simple)", layout="centered")
params = st.experimental_get_query_params()
mode = params.get("mode", ["teacher"])[0]

# ------------ Teacher Dashboard ------------
if mode == "teacher":
    st.title("Teacher — QR Attendance")

    st.sidebar.header("Session Controls")
    session_name = st.sidebar.text_input("Session name:", value="Session1")

    col1, col2 = st.sidebar.columns(2)
    if col1.button("Start Session"):
        if session_name.strip():
            start_session(session_name.strip())
            st.sidebar.success(f"Started '{session_name}'")
    if col2.button("End Session"):
        if session_name.strip():
            end_session(session_name.strip())
            st.sidebar.success(f"Ended '{session_name}'")

    # Show QR if active
    if session_name and session_active(session_name):
        st.success(f"Session '{session_name}' ACTIVE")
        placeholder = st.empty()

        current_int = current_interval()
        token = make_token(session_name, current_int)

        query = {"mode": "mark", "session": session_name, "token": token}
        qr_url = "/?" + urllib.parse.urlencode(query) if HOST == "" else HOST + "/?" + urllib.parse.urlencode(query)

        img_buf = generate_qr_image(qr_url)

        with placeholder.container():
            st.image(img_buf)
            st.write("Scan with phone camera:")
            st.code(qr_url)
            st.caption("QR refreshes every 2 seconds")

        time.sleep(QR_INTERVAL_SECONDS)
        st.experimental_rerun()

    else:
        if session_name:
            st.info(f"Session '{session_name}' not active.")

    # Download CSV
    st.subheader("Download Attendance")
    dl_session = st.text_input("Session name:", value=session_name)

    if st.button("Download CSV"):
        rows = get_attendance_for_session(dl_session.strip())
        if not rows:
            st.warning("No records found.")
        else:
            csv_buf = BytesIO()
            writer = csv.writer(csv_buf)
            writer.writerow(["reg_no", "session_name", "timestamp"])
            for reg_no, ts in rows:
                writer.writerow([reg_no, dl_session.strip(), ts])
            csv_buf.seek(0)

            st.download_button(
                "Download CSV",
                data=csv_buf.getvalue(),
                file_name=f"attendance_{dl_session.strip()}.csv",
                mime="text/csv"
            )

# ------------ Student QR Route ------------
elif mode == "mark":
    st.title("Mark Attendance")
    token = params.get("token", [""])[0]
    session_name = params.get("session", [""])[0]

    if not token or not session_name:
        st.error("Invalid QR link.")
    else:
        valid, token_ts, err = token_valid(token)
        if not valid:
            st.error(err)
        else:
            st.info(f"Session: {session_name}")
            with st.form("form"):
                reg = st.text_input("Registration Number")
                submit = st.form_submit_button("Submit")
            if submit:
                if not reg.strip():
                    st.error("Enter registration number.")
                else:
                    ok, msg = record_attendance(session_name, reg.strip(), token, token_ts)
                    if ok:
                        st.success("Attendance Recorded ✔")
                    else:
                        st.error(msg)
