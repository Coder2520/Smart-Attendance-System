import streamlit as st
import sqlite3
import time

# -----------------------------
# CONFIG
# -----------------------------
QR_VALID_SECONDS = 3
SUBMIT_WINDOW = 30
DB_FILE = "attendance.db"

# -----------------------------
# DATABASE
# -----------------------------
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

# -----------------------------
# PAGE SETUP
# -----------------------------
st.set_page_config(page_title="QR Attendance", layout="centered")

params = st.query_params
mode = params.get("mode", "teacher")

# -----------------------------
# TEACHER VIEW
# -----------------------------
if mode == "teacher":

    st.title("QR Attendance")
    st.caption("QR rotates every 3 seconds")

    qr_html = f"""
    <div style="text-align:center;">
        <img id="qr_img" width="300">
    </div>

    <script>

    const VALID = {QR_VALID_SECONDS};

    function baseURL() {{
        return window.top.location.href.split("?")[0];
    }}

    function updateQR() {{

        const issued = Math.floor(Date.now() / 1000);
        const token = "QR_" + issued;

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
    setInterval(updateQR, VALID * 1000);

    </script>
    """

    st.components.v1.html(qr_html, height=360)

# -----------------------------
# SCAN VIEW
# -----------------------------
elif mode == "scan":

    st.title("Attendance Check-in")

    token = params.get("token", "")

    try:
        issue_time = int(token.split("_")[1])
    except:
        st.error("Invalid QR code")
        st.stop()

    # capture scan time ONCE
    if "scan_time" not in st.session_state:
        st.session_state.scan_time = int(time.time())

    scan_time = st.session_state.scan_time
    server_time = int(time.time())

    # rule 1: must scan within 3 seconds of issue
    if scan_time - issue_time > QR_VALID_SECONDS:
        st.error("QR expired (scan too late)")
        st.stop()

    # rule 2: submission must happen within 30 seconds of scan
    if server_time - scan_time > SUBMIT_WINDOW:
        st.error("Submission window expired")
        st.stop()

    reg_no = st.text_input("Enter Registration Number")

    if st.button("Mark Attendance", use_container_width=True):

        if not reg_no.strip():
            st.warning("Enter registration number")
            st.stop()

        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()

        cur.execute(
            "INSERT INTO attendance VALUES (?, ?, ?)",
            (server_time, reg_no.strip(), token)
        )

        con.commit()
        con.close()

        st.success("Attendance marked successfully")

# -----------------------------
# INVALID MODE
# -----------------------------
else:
    st.error("Invalid mode")
