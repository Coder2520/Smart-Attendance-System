import streamlit as st
import sqlite3
import time

QR_INTERVAL = 3
DB_FILE = "attendance.db"

# ---------------------
# DATABASE
# ---------------------
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

# ---------------------
# TEACHER PAGE
# ---------------------
if mode == "teacher":

    st.title("QR Attendance")

    qr_html = f"""
    <div style="text-align:center;">
        <img id="qr_img" width="300">
    </div>

    <script>

    const INTERVAL = {QR_INTERVAL};

    function updateQR() {{

        const issued = Math.floor(Date.now()/1000);
        const token = "QR_" + issued;

        const qr =
        "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=" +
        encodeURIComponent(token);

        document.getElementById("qr_img").src =
        qr + "&t=" + Date.now();
    }}

    updateQR();
    setInterval(updateQR, INTERVAL*1000);

    </script>
    """

    st.components.v1.html(qr_html, height=350)

# ---------------------
# SCAN PAGE
# ---------------------
elif mode == "scan":

    st.title("Scan QR Code")

    scan_html = """
    <div id="reader" style="width:300px"></div>

    <script src="https://unpkg.com/html5-qrcode"></script>

    <script>

    function onScanSuccess(decodedText) {

        document.getElementById("qr_token").value = decodedText;

        document.getElementById("scan_time").value =
            Math.floor(Date.now()/1000);

    }

    const html5QrCode = new Html5Qrcode("reader");

    Html5Qrcode.getCameras().then(devices => {

        html5QrCode.start(
            devices[0].id,
            {fps:10, qrbox:250},
            onScanSuccess
        );

    });

    </script>
    """

    st.components.v1.html(scan_html, height=400)

    # hidden fields populated by JS
    qr_token = st.text_input("QR Token")
    scan_time = st.text_input("Scan Time")

    reg_no = st.text_input("Registration Number")

    if st.button("Mark Attendance"):

        if not qr_token or not scan_time:
            st.error("Scan the QR first")
            st.stop()

        issue_time = int(qr_token.split("_")[1])
        scan_time = int(scan_time)

        if scan_time - issue_time > 3:
            st.error("QR expired")
            st.stop()

        con = sqlite3.connect(DB_FILE)
        cur = con.cursor()

        cur.execute(
            "INSERT INTO attendance VALUES (?, ?, ?)",
            (int(time.time()), reg_no, qr_token)
        )

        con.commit()
        con.close()

        st.success("Attendance marked")

else:
    st.error("Invalid mode")
