import streamlit as st
import sqlite3
import time
from collections import deque

# -------------------------------
# CONFIG
# -------------------------------
QR_INTERVAL = 3
QR_QUEUE_SIZE = 10
DB_FILE = "attendance.db"

# -------------------------------
# DATABASE
# -------------------------------
def init_db():
    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            ts INTEGER,
            reg_no TEXT,
            qr_token TEXT
        )
    """)
    con.commit()
    con.close()

init_db()

# -------------------------------
# QR TOKEN QUEUE
# -------------------------------
if "qr_queue" not in st.session_state:
    st.session_state.qr_queue = deque(maxlen=QR_QUEUE_SIZE)

# generate current QR token
current_interval = int(time.time() // QR_INTERVAL)
current_qr = f"QR_{current_interval}"

# update queue
if not st.session_state.qr_queue or st.session_state.qr_queue[-1] != current_qr:
    st.session_state.qr_queue.append(current_qr)

# -------------------------------
# ROUTING
# -------------------------------
params = st.query_params
mode = params.get("mode", "teacher")

# -------------------------------
# TEACHER VIEW
# -------------------------------
if mode == "teacher":

    st.title("QR Attendance")
    st.caption("QR rotates every 3 seconds")

    qr_html = f"""
    <div style="text-align:center;">
        <img id="qr_img" width="300">
    </div>

    <script>
    const INTERVAL = {QR_INTERVAL};

    function baseURL() {{
        return window.top.location.href.split("?")[0];
    }}

    function updateQR() {{
        const interval = Math.floor(Date.now()/1000/{QR_INTERVAL});
        const token = "QR_" + interval;

        const target =
            baseURL() +
            "?mode=scan&token=" +
            encodeURIComponent(token);

        const qr =
        "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=" +
        encodeURIComponent(target);

        document.getElementById("qr_img").src =
        qr + "&t=" + Date.now();
    }}

    updateQR();
    setInterval(updateQR, INTERVAL*1000);
    </script>
    """

    st.components.v1.html(qr_html, height=360)

# -------------------------------
# STUDENT SCAN VIEW
# -------------------------------
elif mode == "scan":

    st.title("Attendance Check-in")

    token = params.get("token", "")

    if token not in st.session_state.qr_queue:
        st.error("QR expired. Please scan again.")
        st.stop()

    reg_no = st.text_input("Enter Registration Number")

    if st.button("Mark Attendance", use_container_width=True):

        if not reg_no.strip():
            st.warning("Enter registration number")
            st.stop()

        try:
            con = sqlite3.connect(DB_FILE)
            cur = con.cursor()
            cur.execute(
                "INSERT INTO attendance (ts, reg_no, qr_token) VALUES (?, ?, ?)",
                (int(time.time()), reg_no.strip(), token)
            )
            con.commit()
            con.close()

            st.success("Attendance marked")

        except:
            st.error("Database error")

# -------------------------------
# INVALID MODE
# -------------------------------
else:
    st.error("Invalid mode")
