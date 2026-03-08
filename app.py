import streamlit as st
import mysql.connector  # MySQL connector
import time
import pandas as pd
import face_recognition
import numpy as np
import os
from PIL import Image, ImageDraw
from io import BytesIO
import math

# -----------------------------
# CONFIG
# -----------------------------
QR_INTERVAL = 3
MAX_INTERVAL_DRIFT = 5

DB_HOST = os.environ.get("MYSQLHOST")
DB_USER = os.environ.get("MYSQLUSER")
DB_PASSWORD = os.environ.get("MYSQLPASSWORD")
DB_NAME = os.environ.get("MYSQLDATABASE")
DB_PORT = os.environ.get("MYSQLPORT")

APP_URL = "https://smart-qr-based-attendance-system.streamlit.app"

# Slots
SLOTS = ["A1","A2","B1","B2","C1","C2","D1","D2","E1","E2","F1","F2","G1","G2"]

# -----------------------------
# DATABASE
# -----------------------------
def init_db():
    con = get_db_connection()
    cur = con.cursor()

    # Create one table for each slot
    for slot in SLOTS:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS attendance_{slot} (
                ts BIGINT,
                reg_no VARCHAR(50),
                qr_token VARCHAR(100),
                date VARCHAR(20)
            )
        """)

    st.write("Connection successful.")
    con.commit()
    cur.close()
    con.close()

init_db()

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

# -----------------------------
# PAGE SETUP
# -----------------------------
st.set_page_config(
    page_title="Smart QR Attendance",
    page_icon="📷",
    layout="centered"
)

st.markdown(
"""
<h1 style='text-align:center;'>Smart QR Attendance System</h1>
<p style='text-align:center;color:gray;'>Fast • Secure • Contactless Attendance</p>
<hr>
""",
unsafe_allow_html=True
)

params = st.query_params
mode = params.get("mode", "teacher")

# -----------------------------
# UTILITY FUNCTIONS
# -----------------------------
def load_image(uploaded_file):
    bytes_data = uploaded_file.getvalue()
    pil_img = Image.open(BytesIO(bytes_data)).convert("RGB")
    return pil_img, np.array(pil_img, dtype=np.uint8)

def euclidean(p1, p2):
    return math.sqrt((p1[0]-p2[0])**2 + (p1[1]-p2[1])**2)

def eye_aspect_ratio(eye):
    A = euclidean(eye[1], eye[5])
    B = euclidean(eye[2], eye[4])
    C = euclidean(eye[0], eye[3])
    return (A + B) / (2.0 * C)

def detect_blink(image_file):
    pil_img = Image.open(BytesIO(image_file.getvalue())).convert("RGB")
    img_np = np.array(pil_img)
    face_landmarks = face_recognition.face_landmarks(img_np)
    if len(face_landmarks) == 0:
        return False
    landmarks = face_landmarks[0]
    leftEAR = eye_aspect_ratio(landmarks['left_eye'])
    rightEAR = eye_aspect_ratio(landmarks['right_eye'])
    ear = (leftEAR + rightEAR)/2
    return ear < 0.20

def face_movement(img_a, img_b):
    pil_a = Image.open(BytesIO(img_a.getvalue())).convert("RGB")
    pil_b = Image.open(BytesIO(img_b.getvalue())).convert("RGB")
    arr_a = np.array(pil_a)
    arr_b = np.array(pil_b)
    faces_a = face_recognition.face_locations(arr_a)
    faces_b = face_recognition.face_locations(arr_b)
    if len(faces_a) == 0 or len(faces_b) == 0:
        return 0
    top1, right1, bottom1, left1 = faces_a[0]
    top2, right2, bottom2, left2 = faces_b[0]
    center1 = ((left1 + right1)/2, (top1 + bottom1)/2)
    center2 = ((left2 + right2)/2, (top2 + bottom2)/2)
    return np.sqrt((center1[0]-center2[0])**2 + (center1[1]-center2[1])**2)

# -----------------------------
# TEACHER PAGE
# -----------------------------
if mode == "teacher":
    st.subheader("Attendance")
    st.info("Scan the QR for attendance")

    # Teacher enters date + slot
    date_input = st.date_input("Select Date")
    slot_input = st.selectbox("Select Slot", SLOTS)

    if date_input and slot_input:
        st.session_state["date"] = str(date_input)
        st.session_state["slot"] = slot_input

    # Display QR (with date + slot)
    if "date" in st.session_state and "slot" in st.session_state:
        qr_html = f"""
        <div style="text-align:center;padding:20px;">
            <img id="qr_img" width="300">
        </div>
        <script>
        const INTERVAL = {QR_INTERVAL};
        const BASE = "{APP_URL}";
        const DATE = "{st.session_state['date']}";
        const SLOT = "{st.session_state['slot']}";
        function updateQR(){{
            const interval = Math.floor(Date.now()/1000/INTERVAL);
            const token = "QR_" + interval;
            const target = BASE + "/?mode=scan&token=" + encodeURIComponent(token)
                           + "&date=" + encodeURIComponent(DATE)
                           + "&slot=" + encodeURIComponent(SLOT);
            const qr = "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=" + encodeURIComponent(target);
            document.getElementById("qr_img").src = qr + "&t=" + Date.now();
        }}
        updateQR();
        setInterval(updateQR, INTERVAL*1000);
        </script>
        """
        st.components.v1.html(qr_html, height=340)

    # Download CSV filtered by slot
    st.markdown("---")
    st.subheader("Download Attendance")
    if "slot" in st.session_state and st.session_state["slot"] in SLOTS:
        slot_table = f"attendance_{st.session_state['slot']}"
        con = get_db_connection()
        cur = con.cursor(dictionary=True)
        cur.execute(f"SELECT * FROM {slot_table} WHERE date=%s", (st.session_state["date"],))
        rows = cur.fetchall()
        df = pd.DataFrame(rows)
        if not df.empty:
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Download CSV", csv, f"attendance_{st.session_state['slot']}.csv", "text/csv")
            # Delete records after download
            cur.execute(f"DELETE FROM {slot_table} WHERE date=%s", (st.session_state["date"],))
            con.commit()
        else:
            st.info("No attendance recorded yet.")
        cur.close()
        con.close()
    else:
        st.info("Select a valid slot to download attendance.")

# -----------------------------
# STUDENT SCAN PAGE
# -----------------------------
elif mode == "scan":
    st.subheader("Student Attendance Check-in")
    token = params.get("token", "")
    date_val = params.get("date", "unknown")
    slot_val = params.get("slot", "unknown")  # <-- read from QR

    # QR token validation
    try:
        scanned_interval = int(token.split("_")[1])
    except:
        st.error("Invalid QR")
        st.stop()

    current_interval = int(time.time() // QR_INTERVAL)
    if current_interval - scanned_interval > MAX_INTERVAL_DRIFT:
        st.error("QR expired")
        st.stop()

    # Student details
    reg_no = st.text_input("Enter Registration Number")
    st.markdown("### Capture 3 Images for Verification")
    img1 = st.camera_input("Capture Image 1", key="img1")
    img2 = st.camera_input("Capture Image 2", key="img2")
    img3 = st.camera_input("Capture Image 3", key="img3")

    if st.button("Verify Attendance"):

        if not reg_no:
            st.error("Enter Registration Number")
            st.stop()

        if not (img1 and img2 and img3):
            st.error("Capture all 3 images")
            st.stop()

        # Head movement check
        diff1 = face_movement(img1, img2)
        diff2 = face_movement(img2, img3)
        if diff1 < 20 and diff2 < 20:
            st.error("Move your head slightly during capture")
            st.stop()

        # Blink detection
        blink1 = detect_blink(img1)
        blink2 = detect_blink(img2)
        blink3 = detect_blink(img3)
        if not (blink1 or blink2 or blink3):
            st.error("Blink your eyes during capture")
            st.stop()

        # Reference image
        ref_path = f"ref_imgs/{reg_no}.jpg"
        if not os.path.exists(ref_path):
            st.error("Student not registered")
            st.stop()

        ref_image = face_recognition.load_image_file(ref_path)
        ref_encodings = face_recognition.face_encodings(ref_image)
        if len(ref_encodings) == 0:
            st.error("No face detected in reference image")
            st.stop()
        ref_enc = ref_encodings[0]

        # Face recognition with last captured image
        pil_img, captured_np = load_image(img3)
        face_locations = face_recognition.face_locations(captured_np)

        if len(face_locations) == 0:
            st.error("No face detected in captured image")
            st.stop()

        # -----------------------------
        # IGNORE SMALL FACES 
        # -----------------------------
        img_h, img_w, _ = captured_np.shape
        valid_faces = []

        for (top, right, bottom, left) in face_locations:
            width = right - left
            height = bottom - top
            # Ignore faces smaller than 50px or <5% of image dimensions
            if width >= max(50, img_w * 0.05) and height >= max(50, img_h * 0.05):
                valid_faces.append((top, right, bottom, left))

        if len(valid_faces) == 0:
            st.error("No large face detected for verification")
            st.stop()

        # Sort faces by area (largest first) for prioritizing likely student face
        valid_faces.sort(key=lambda f: (f[2]-f[0])*(f[1]-f[3]), reverse=True)

        # Check all valid faces against reference
        matched = False
        min_distance = 1.0
        for face in valid_faces:
            cap_encodings = face_recognition.face_encodings(captured_np, known_face_locations=[face])
            if len(cap_encodings) == 0:
                continue
            cap_enc = cap_encodings[0]
            distance = face_recognition.face_distance([ref_enc], cap_enc)[0]

            if distance < min_distance:
                min_distance = distance

            if distance < 0.45:
                matched = True
                # Draw rectangle around the first matched face
                draw = ImageDraw.Draw(pil_img)
                top, right, bottom, left = face
                draw.rectangle([(left, top), (right, bottom)], outline="lime", width=4)
                break  # stop once a valid face is found

        st.image(pil_img, caption="Face used for verification", use_container_width=True)
        st.subheader("Verification Result")
        st.write(f"Distance Score: {round(float(min_distance), 3)}")


        if matched:
            if slot_val not in SLOTS:
                st.error("Invalid slot detected from QR")
                st.stop()
            # Save attendance with date + slot into the correct table
            con = get_db_connection()
            cur = con.cursor()
            slot_table = f"attendance_{slot_val}"
            cur.execute(
                f"INSERT INTO {slot_table} (ts, reg_no, qr_token, date) VALUES (%s, %s, %s, %s)",
                (int(time.time()), reg_no, token,  date_val)
            )
            con.commit()
            cur.close()
            con.close()
            st.success(f"Attendance Marked for {reg_no}")
        else:
            st.error("Registered face not found in frame / Proxy detected")

else:
    st.error("Invalid mode")
