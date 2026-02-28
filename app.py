import streamlit as st
import time
import sqlite3

# -------------------------------
# CONFIG
# -------------------------------
QR_VALID_SECONDS = 5          # how long a QR is valid
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
# PAGE CONFIG
# -------------------------------
st.set_page_config(page_title="QR Attendance", layout="centered")

mode = st.query_params.get("mode", "teacher")

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
    const QR_VALID_SECONDS = {QR_VALID_SECONDS};

    function baseURL() {{
        return window.top.location.href.split("?")[0];
    }}

    function updateQR() {{
        // exact issue timestamp (seconds)
        const issuedAt = Math.floor(Date.now() / 1000);
        const token = "QR_" + issuedAt;

        const target =
            baseURL() +
            "?mode=scan&token=" +
            encodeURIComponent(token);

        const qr_api =
            "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=" +
            encodeURIComponent(target);

        document.getElementById("qr_img").src =
            qr_api + "&t=" + Date.now();
    }}

    updateQR();
    setInterval(updateQR, QR_VALID_SECONDS * 1000);
    </script>
    """

    st.components.v1.html(qr_html, height=360)

# -------------------------------
# SCAN VIEW (PHONE)
# -------------------------------
elif mode == "scan":
    st.set_page_config(page_title="Attendance Check-in", layout="centered")
    st.title("Attendance Check-in")

    # capture scan event time ONCE
    if "scan_time" not in st.session_state:
        st.session_state.scan_time = int(time.time())

    scan_time = st.session_state.scan_time

    token = st.query_params.get("token", "")

    try:
        issued_at = int(token.split("_")[1])
    except:
        st.error("Invalid QR code")
        st.stop()

    reg_no = st.text_input(
        "Enter Registration Number",
        placeholder="e.g. 22BCE1234"
    )

    if st.button("Mark Attendance", use_container_width=True):

        if not reg_no.strip():
            st.warning("Please enter your registration number")
            st.stop()

        if 0 <= (scan_time - issued_at) <= QR_VALID_SECONDS:
            status = "PRESENT"
            st.success("Attendance marked")
        else:
            status = "EXPIRED"
            st.error("QR expired")

        try:
            cur = DB.cursor()
            cur.execute(
                "INSERT INTO scans (ts, reg_no, status) VALUES (?, ?, ?)",
                (scan_time, reg_no.strip(), status)
            )
            DB.commit()
        except:
            st.error("Database error while saving attendance")
            st.stop()

# -------------------------------
# FALLBACK
# -------------------------------
else:
    st.error("Invalid mode")
