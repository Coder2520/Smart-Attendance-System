import streamlit as st
import time
import sqlite3

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

# -------------------------------
# ROUTING
# -------------------------------
st.set_page_config(page_title="QR Attendance", layout="centered")
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
    </div>

    <script>
    const QR_INTERVAL = {QR_INTERVAL};
    const BASE_URL = window.location.origin;

    function updateQR() {{
        const now = Math.floor(Date.now() / 1000);
        const interval = Math.floor(now / QR_INTERVAL);
        const token = "QR_" + interval;

        const target =
            BASE_URL +
            "/?mode=scan&token=" +
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

    st.components.v1.html(qr_html, height=380)

# -------------------------------
# SCAN VIEW (PHONE)
# -------------------------------
elif mode == "scan":
    st.set_page_config(page_title="Attendance Check-in", layout="centered")
    st.title("Attendance Check-in")

    token = params.get("token", [""])[0]

    # TOKEN PARSE
    try:
        _, interval = token.split("_")
        interval = int(interval)
    except:
        st.error("Invalid or corrupted QR code.")
        st.stop()

    # REGISTRATION NUMBER INPUT
    reg_no = st.text_input(
        "Enter your Registration Number",
        placeholder="e.g. 22BCE1234"
    )

    # SUBMIT
    if st.button("Mark Attendance", use_container_width=True):

        if not reg_no.strip():
            st.warning("Please enter your registration number.")
            st.stop()

        scan_time = now()
        qr_time = interval * QR_INTERVAL

        # TIME VALIDATION
        if abs(scan_time - qr_time) <= QR_INTERVAL:
            status = "PRESENT"
            st.success("Marked as present")
        else:
            status = "EXPIRED"
            st.error("QR expired. Please scan the current QR.")

        # LOG (TEMPORARY)
        cur = DB.cursor()
        cur.execute(
            "INSERT INTO scans (ts, result) VALUES (?, ?)",
            (scan_time, f"{reg_no} | {status}")
        )
        DB.commit()
