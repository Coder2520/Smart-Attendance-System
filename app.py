import streamlit as st
import sqlite3
import time
import json

QR_INTERVAL = 3
DB_FILE = "attendance.db"

# -------------------------
# DB
# -------------------------
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

st.set_page_config(page_title="QR Attendance", layout="centered")

params = st.query_params
mode = params.get("mode", "teacher")

# -------------------------
# TEACHER PAGE
# -------------------------
if mode == "teacher":

    st.title("QR Attendance")

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

        const issued = Math.floor(Date.now()/1000);
        const token = "QR_" + issued;

        const target =
            baseURL() +
            "?mode=scan";

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

# -------------------------
# SCAN PAGE
# -------------------------
elif mode == "scan":

    st.title("Scan QR Code")

    scanner_html = """
    <div id="reader" style="width:300px"></div>

    <script src="https://unpkg.com/html5-qrcode"></script>

    <script>

    function sendResult(qrText){

        const scanTime = Math.floor(Date.now()/1000);

        const payload = {
            qr_token: qrText,
            scan_time: scanTime
        };

        window.parent.postMessage(
            {type:"qr_result",data:payload},
            "*"
        );
    }

    function onScanSuccess(decodedText){

        sendResult(decodedText);
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

    st.components.v1.html(scanner_html, height=400)

    result = st.text_input("Paste scan result JSON")

    if result:

        data = json.loads(result)

        token = data["qr_token"]
        scan_time = data["scan_time"]

        issue_time = int(token.split("_")[1])

        if scan_time - issue_time > 3:
            st.error("QR expired")
            st.stop()

        reg_no = st.text_input("Registration Number")

        if st.button("Submit"):

            con = sqlite3.connect(DB_FILE)
            cur = con.cursor()

            cur.execute(
                "INSERT INTO attendance VALUES (?, ?, ?)",
                (int(time.time()), reg_no, token)
            )

            con.commit()
            con.close()

            st.success("Attendance marked")

else:
    st.error("Invalid mode")
