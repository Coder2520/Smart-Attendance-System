import streamlit as st
import time
import sqlite3

# -------------------------------
# CONFIG
# -------------------------------
QR_INTERVAL = 3
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
            reg_no TEXT,
            status TEXT
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

# -------------------------------
# PAGE CONFIG
# -------------------------------
st.set_page_config(page_title="QR Attendance", layout="centered")

params = st.query_params
mode = params.get("mode", ["teacher"])[0]

# -------------------------------
# TEACHER VIEW
# -------------------------------
if mode == "teacher":
    st.title("QR Attendance")
    st.caption("Scan the QR code to mark attendance")

    qr_html = f"""
    <div style="text-align:center;">
        <img id="qr_img" width="300"/>
    </div>

    <script>
    const QR_INTERVAL = {QR_INTERVAL};

    function getBaseURL() {{
        // Break out of Streamlit iframe safely
        const url = window.top.location.href;
        return url.split("?")[0];
    }}

    function updateQR() {{
        const now = Math.floor(Date.now() / 1000);
        const interval = Math.floor(now / QR_INTERVAL);
        const token = "QR_" + interval;

        const target =
            getBaseURL() +
            "?mode=scan&token=" +
            encodeURIComponent(token);

        const qr_api =
            "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=" +
            encodeURIComponent(target);

        document.getElementById("qr_img").src =
            qr_api + "&t=" + Date.now();
    }}

    updateQR();
    setInterval(updateQR, QR_INTERVAL * 1000);
    </script>
    """

    st.components.v1.html(qr_html, height=360)

# -------------------------------
# SCAN VIEW
# -------------------------------
elif mode == "scan":
    st.set_page_config(page_title="Attendance Check-in", layout="centered")
    st.title("Attendance Check-in")

    token = params.get("token", [""])[0]

    try:
        _, interval = token.split("_")
        interval = int(interval)
    except:
        st.error("Invalid QR code")
        st.stop()

    reg_no = st.text_input("Enter Registration Number")

    if st.button("Mark Attendance", use_container_width=True):

        if not reg_no.strip():
            st.warning("Enter registration number")
            st.stop()

        scan_time = now()
        qr_time = interval * QR_INTERVAL

        if abs(scan_time - qr_time) <= QR_INTERVAL:
            status = "PRESENT"
            st.success("Attendance marked")
        else:
            status = "EXPIRED"
            st.error("QR expired")

        cur = DB.cursor()
        cur.execute(
            "INSERT INTO scans (ts, reg_no, status) VALUES (?, ?, ?)",
            (scan_time, reg_no.strip(), status)
        )
        DB.commit()

else:
    st.error("Invalid mode")
