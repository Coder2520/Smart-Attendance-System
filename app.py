import streamlit as st
import time
import sqlite3
import urllib.parse

# -------------------------------
# CONFIG
# -------------------------------
QR_INTERVAL = 3   # seconds
DB_FILE = "qr_scan.db"

# -------------------------------
# DATABASE
# -------------------------------
@st.cache_resource
def init_db():
    con = sqlite3.connect(DB_FILE, check_same_thread=False)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            ts INTEGER,
            result TEXT
        )
    """)
    con.commit()
    return con

DB = init_db()

# -------------------------------
# HELPERS
# -------------------------------
def now():
    return int(time.time())

def current_interval():
    return now() // QR_INTERVAL

# -------------------------------
# ROUTING
# -------------------------------
st.set_page_config(page_title="Strict QR Scan Demo", layout="centered")
params = st.query_params
mode = params.get("mode", ["teacher"])[0]

# -------------------------------
# TEACHER VIEW
# -------------------------------
if mode == "teacher":
    st.caption("Scan the QR for attendance.")

    qr_html = f"""
    <div style="text-align:center;">
        <img id="qr_img" width="300">
        <p style="color:gray;">QR refreshes every {QR_INTERVAL} seconds</p>
    </div>

    <script>
    const QR_INTERVAL = {QR_INTERVAL};
    const BASE_URL = window.location.origin;

    function updateQR() {{
        const now = Math.floor(Date.now() / 1000);
        const interval = Math.floor(now / QR_INTERVAL);
        const token = "QR|" + interval;

        const target =
            BASE_URL +
            "/?mode=scan&token=" +
            encodeURIComponent(token);

        const qr_api =
            "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=" +
            encodeURIComponent(target);

        document.getElementById("qr_img").src =
            qr_api + "&t=" + Date.now(); // cache-buster
    }}

    updateQR();
    setInterval(updateQR, QR_INTERVAL * 1000);
    </script>
    """

    st.components.v1.html(qr_html, height=380)

# -------------------------------
# SCAN VIEW
# -------------------------------
elif mode == "scan":
    st.title("QR Scan Result")

    token = params.get("token", [""])[0]

    try:
        _, interval = token.split("|")
        interval = int(interval)
    except:
        st.error("Invalid QR.")
        st.stop()

    scan_time = now()
    qr_time = interval * QR_INTERVAL

    # TIME CHECK
    if abs(scan_time - qr_time) <= QR_INTERVAL:
        result = "VALID (Live Scan)"
        st.success("VALID QR — Live scan detected")
    else:
        result = "INVALID (Photo / Forwarded)"
        st.error("INVALID QR — Photo or forwarded scan")

    cur = DB.cursor()
    cur.execute(
        "INSERT INTO scans (ts, result) VALUES (?, ?)",
        (scan_time, result)
    )
    DB.commit()
