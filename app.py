import streamlit as st
import sqlite3
import time

DB = "attendance.db"

def init_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS attendance(
            ts INTEGER,
            reg TEXT
        )
    """)
    con.commit()
    con.close()

init_db()

st.set_page_config(page_title="QR Attendance")

params = st.query_params
mode = params.get("mode", "teacher")

# -----------------------
# TEACHER PAGE
# -----------------------
if mode == "teacher":

    st.title("QR Attendance")

    # IMPORTANT:
    # Replace this with your actual server IP
    # Example: http://192.168.1.15:8501
    SERVER_URL = "http://192.168.1.15:8501"

    target = SERVER_URL + "/?mode=scan"

    qr_html = f"""
    <div style="text-align:center;">
        <img src="https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={target}">
    </div>
    """

    st.components.v1.html(qr_html, height=350)

    st.write("Students scan the QR to open the attendance form.")

# -----------------------
# STUDENT PAGE
# -----------------------
elif mode == "scan":

    st.title("Attendance Form")

    reg = st.text_input("Registration Number")

    if st.button("Submit Attendance"):

        if not reg.strip():
            st.warning("Enter registration number")
            st.stop()

        con = sqlite3.connect(DB)
        cur = con.cursor()

        cur.execute(
            "INSERT INTO attendance VALUES (?,?)",
            (int(time.time()), reg.strip())
        )

        con.commit()
        con.close()

        st.success("Attendance recorded")

else:
    st.error("Invalid mode")
