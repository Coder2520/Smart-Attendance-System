import streamlit as st
import sqlite3
import time

QR_INTERVAL = 3
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

st.set_page_config(page_title="QR Attendance")

params = st.query_params
mode = params.get("mode", "teacher")

# -----------------------------
# TEACHER PAGE
# -----------------------------
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
        return window.location.href.split("?")[0];
    }}

    function updateQR() {{

        const interval = Math.floor(Date.now()/1000/INTERVAL);
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

# -----------------------------
# STUDENT PAGE
# -----------------------------
elif mode == "scan":

    st.title("Attendance Check-in")

    token = params.get("token","")

    try:
        scanned_interval = int(token.split("_")[1])
    except:
        st.error("Invalid QR")
        st.stop()

    current_interval = int(time.time() // QR_INTERVAL)

    # Accept current or previous interval
    if current_interval - scanned_interval > 1:
        st.error("QR expired. Please scan again.")
        st.stop()

    reg_no = st.text_input("Registration Number")

    if st.button("Submit Attendance", use_container_width=True):

        if not reg_no.strip():
            st.warning("Enter registration number")
            st.stop()

        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()

        cur.execute(
            "INSERT INTO attendance VALUES (?, ?, ?)",
            (int(time.time()), reg_no.strip(), token)
        )

        con.commit()
        con.close()

        st.success("Attendance marked successfully")

else:
    st.error("Invalid mode")
