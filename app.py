from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3, os
import re
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "secret123"

UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

users = {
    "Anushree": "123",
    "durgahalady": "halady123",
    "NRkoteshwara": "koteshwara123",
    "chinamayakundapur": "kundapur123",
    "adarshudupi": "udupi123"
}

DAILY_APPOINTMENT_LIMIT = 3

def get_db():
    return sqlite3.connect("hospital.db")

def init_db():
    con = get_db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS hospital(
        username TEXT PRIMARY KEY,
        name TEXT,
        location TEXT,
        image TEXT
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS doctor(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        name TEXT,
        specialization TEXT,
        education TEXT,
        timings TEXT,
        weekly_holiday TEXT,
        emergency_leave TEXT,
        image TEXT
    )""")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS appointment(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        doctor_id INTEGER,
        doctor_name TEXT,
        hospital_name TEXT,
        appointment_date TEXT,
        patient_name TEXT,
        patient_phone TEXT,
        status TEXT DEFAULT 'confirmed'
    )""")

    con.commit()
    con.close()

init_db()

@app.route("/", methods=["GET","POST"])
def home():
    search_query = request.args.get("search", "").strip().lower()
   
    con = get_db()
    cur = con.cursor()
   
    cur.execute("""
        SELECT DISTINCT h.* FROM hospital h
        INNER JOIN doctor d ON h.username = d.username
        WHERE h.name != h.username AND h.location != 'Not Set'
    """)
    hospitals = cur.fetchall()
   
    hospitals_with_doctors = []
    for hospital in hospitals:
        hospital_username = hospital[0]
        cur.execute("SELECT * FROM doctor WHERE username=?", (hospital_username,))
        doctors = cur.fetchall()

        if search_query:
            filtered_doctors = []
            for doctor in doctors:
                if (search_query in doctor[2].lower() or
                    search_query in doctor[3].lower() or
                    search_query in hospital[1].lower()):
                    filtered_doctors.append(doctor)
            doctors = filtered_doctors
            if not doctors:
                continue

        hospitals_with_doctors.append({
            'hospital': hospital,
            'doctors': doctors
        })
   
    con.close()
    return render_template("user.html", hospitals_with_doctors=hospitals_with_doctors, search_query=search_query)

@app.route("/doctor_profile/<int:doctor_id>", methods=["GET"])
def doctor_profile(doctor_id):
    con = get_db()
    cur = con.cursor()
    
    # Get doctor details
    cur.execute("SELECT * FROM doctor WHERE id=?", (doctor_id,))
    doctor = cur.fetchone()
    
    if not doctor:
        con.close()
        return "Doctor not found", 404
    
    # Get hospital details
    cur.execute("SELECT * FROM hospital WHERE username=?", (doctor[1],))
    hospital = cur.fetchone()
    
    # Get all appointments for this doctor
    cur.execute("""
        SELECT id, doctor_name, hospital_name, appointment_date, patient_name, patient_phone, status 
        FROM appointment WHERE doctor_id=? ORDER BY appointment_date DESC, id DESC
    """, (doctor_id,))
    appointments = cur.fetchall()
    
    con.close()
    
    return render_template("doctor_profile.html", 
                         doctor=doctor, 
                         hospital=hospital, 
                         appointments=appointments)

@app.route("/book_appointment/<int:doctor_id>", methods=["GET", "POST"])
def book_appointment_page(doctor_id):
    con = get_db()
    cur = con.cursor()
    
    # Get doctor details
    cur.execute("SELECT * FROM doctor WHERE id=?", (doctor_id,))
    doctor = cur.fetchone()
    
    if not doctor:
        con.close()
        return "Doctor not found", 404
    
    # Get hospital details
    cur.execute("SELECT * FROM hospital WHERE username=?", (doctor[1],))
    hospital = cur.fetchone()
    
    # Get appointment stats
    cur.execute("SELECT COUNT(*) FROM appointment WHERE doctor_id=?", (doctor_id,))
    existing_count = cur.fetchone()[0]
    
    today = datetime.now().strftime('%Y-%m-%d')
    cur.execute("SELECT COUNT(*) FROM appointment WHERE doctor_id=? AND appointment_date=?", (doctor_id, today))
    today_count = cur.fetchone()[0]
    
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM appointment")
    next_number = cur.fetchone()[0]
    
    can_book_today = today_count < DAILY_APPOINTMENT_LIMIT
    
    con.close()
    
    if request.method == "POST":
        # Handle the booking
        appointment_date = request.form.get("appointment_date")
        patient_name = request.form.get("patient_name", "").strip()
        patient_phone = request.form.get("patient_phone", "").strip()

        if not patient_name or len(patient_name) < 2:
            return render_template("book_appointment.html", 
                                 doctor=doctor, 
                                 hospital=hospital,
                                 existing_count=existing_count,
                                 today_count=today_count,
                                 daily_limit=DAILY_APPOINTMENT_LIMIT,
                                 can_book_today=can_book_today,
                                 next_appointment_number=next_number,
                                 error="Patient name is required (minimum 2 characters)")

        phone_digits = re.sub(r'\D', '', patient_phone)
        if len(phone_digits) != 10:
            return render_template("book_appointment.html", 
                                 doctor=doctor, 
                                 hospital=hospital,
                                 existing_count=existing_count,
                                 today_count=today_count,
                                 daily_limit=DAILY_APPOINTMENT_LIMIT,
                                 can_book_today=can_book_today,
                                 next_appointment_number=next_number,
                                 error="Phone number must be exactly 10 digits")

        con = get_db()
        cur = con.cursor()
        
        # Check daily limit again
        cur.execute("SELECT COUNT(*) FROM appointment WHERE doctor_id=? AND appointment_date=?", (doctor_id, appointment_date))
        daily_count = cur.fetchone()[0]
        
        if daily_count >= DAILY_APPOINTMENT_LIMIT:
            con.close()
            return render_template("book_appointment.html", 
                                 doctor=doctor, 
                                 hospital=hospital,
                                 existing_count=existing_count,
                                 today_count=today_count,
                                 daily_limit=DAILY_APPOINTMENT_LIMIT,
                                 can_book_today=False,
                                 next_appointment_number=next_number,
                                 error=f"Daily limit reached! Maximum {DAILY_APPOINTMENT_LIMIT} appointments per day per doctor.")
        
        cur.execute("""
            INSERT INTO appointment (doctor_id, doctor_name, hospital_name, appointment_date, patient_name, patient_phone, status)
            VALUES (?, ?, ?, ?, ?, ?, 'confirmed')""", (doctor_id, doctor[2], hospital[1], appointment_date, patient_name, patient_phone))
        con.commit()
        con.close()

        return render_template("booking_success.html", 
                             doctor=doctor, 
                             hospital=hospital,
                             appointment_date=appointment_date,
                             patient_name=patient_name,
                             patient_phone=patient_phone,
                             appointment_number=next_number)
    
    # Default appointment date
    now = datetime.now()
    appointment_date = now if now.hour < 9 else now + timedelta(days=1)
    default_date = appointment_date.strftime('%Y-%m-%d')
    
    return render_template("book_appointment.html", 
                         doctor=doctor, 
                         hospital=hospital,
                         existing_count=existing_count,
                         today_count=today_count,
                         daily_limit=DAILY_APPOINTMENT_LIMIT,
                         can_book_today=can_book_today,
                         next_appointment_number=next_number,
                         default_date=default_date)

@app.route("/get_appointment_stats/<int:doctor_id>", methods=["GET"])
def get_appointment_stats(doctor_id):
    con = get_db()
    cur = con.cursor()
   
    cur.execute("SELECT COUNT(*) FROM appointment WHERE doctor_id=?", (doctor_id,))
    existing_count = cur.fetchone()[0]
   
    today = datetime.now().strftime('%Y-%m-%d')
    cur.execute("SELECT COUNT(*) FROM appointment WHERE doctor_id=? AND appointment_date=?", (doctor_id, today))
    today_count = cur.fetchone()[0]
   
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM appointment")
    next_number = cur.fetchone()[0]
   
    can_book_today = today_count < DAILY_APPOINTMENT_LIMIT
   
    con.close()
    return jsonify({
        "existing_count": existing_count,
        "today_count": today_count,
        "daily_limit": DAILY_APPOINTMENT_LIMIT,
        "can_book_today": can_book_today,
        "next_appointment_number": next_number
    })

@app.route("/my_appointments/<phone>", methods=["GET"])
def my_appointments(phone):
    clean_phone = re.sub(r'\D', '', phone)
    con = get_db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, doctor_name, hospital_name, appointment_date, patient_name, patient_phone, status 
        FROM appointment 
        WHERE patient_phone LIKE ? OR patient_phone LIKE ?
        ORDER BY appointment_date DESC, id DESC
    """, (f'%{clean_phone}%', f'%{clean_phone}'))
    appointments = cur.fetchall()
    con.close()
    return jsonify([{
        "id": apt[0], "doctor_name": apt[1], "hospital_name": apt[2], 
        "appointment_date": apt[3], "patient_name": apt[4], 
        "patient_phone": apt[5], "status": apt[6]
    } for apt in appointments])

@app.route("/cancel_appointment/<int:appointment_id>", methods=["POST"])
def cancel_appointment(appointment_id):
    patient_phone = request.form.get("patient_phone", "")
    clean_phone = re.sub(r'\D', '', patient_phone)
    
    con = get_db()
    cur = con.cursor()
    
    # Verify patient owns this appointment
    cur.execute("SELECT patient_phone FROM appointment WHERE id=?", (appointment_id,))
    apt = cur.fetchone()
    if not apt or re.sub(r'\D', '', apt[0]) != clean_phone:
        con.close()
        return jsonify({"status": "error", "message": "❌ Unauthorized: You can only cancel your own appointments"}), 403
    
    cur.execute("UPDATE appointment SET status='cancelled' WHERE id=?", (appointment_id,))
    con.commit()
    con.close()
    
    return jsonify({"status": "success", "message": "✅ Appointment cancelled successfully!"})

@app.route("/confirm_appointment/<int:appointment_id>", methods=["POST"])
def confirm_appointment(appointment_id):
    patient_phone = request.form.get("patient_phone", "")
    clean_phone = re.sub(r'\D', '', patient_phone)
    
    con = get_db()
    cur = con.cursor()
    
    # Verify patient owns this appointment
    cur.execute("SELECT patient_phone, status FROM appointment WHERE id=?", (appointment_id,))
    apt = cur.fetchone()
    if not apt or re.sub(r'\D', '', apt[0]) != clean_phone:
        con.close()
        return jsonify({"status": "error", "message": "❌ Unauthorized: You can only confirm your own appointments"}), 403
    
    if apt[1] == 'confirmed':
        con.close()
        return jsonify({"status": "error", "message": "✅ Appointment already confirmed!"}), 400
    
    cur.execute("UPDATE appointment SET status='confirmed' WHERE id=?", (appointment_id,))
    con.commit()
    con.close()
    
    return jsonify({"status": "success", "message": "✅ Appointment confirmed successfully!"})

@app.route("/appointment", methods=["POST"])
def book_appointment():
    doctor_id = request.form.get("doctor_id")
    doctor_name = request.form.get("doctor_name")
    hospital_name = request.form.get("hospital_name")
    appointment_date = request.form.get("appointment_date")
    patient_name = request.form.get("patient_name", "").strip()
    patient_phone = request.form.get("patient_phone", "").strip()

    if not patient_name or len(patient_name) < 2:
        return jsonify({"status": "error", "message": "Patient name is required (minimum 2 characters)"}), 400
    
    phone_digits = re.sub(r'\D', '', patient_phone)
    if len(phone_digits) != 10:
        return jsonify({"status": "error", "message": "Phone number must be exactly 10 digits"}), 400

    con = get_db()
    cur = con.cursor()
   
    today = datetime.now().strftime('%Y-%m-%d')
    cur.execute("SELECT COUNT(*) FROM appointment WHERE doctor_id=? AND appointment_date=?", (doctor_id, appointment_date))
    daily_count = cur.fetchone()[0]
   
    if daily_count >= DAILY_APPOINTMENT_LIMIT:
        con.close()
        return jsonify({
            "status": "error",
            "message": f"❌ Daily limit reached! Maximum {DAILY_APPOINTMENT_LIMIT} appointments per day per doctor."
        }), 400
   
    cur.execute("SELECT COUNT(*) FROM appointment WHERE doctor_id=?", (doctor_id,))
    existing_count = cur.fetchone()[0]
   
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM appointment")
    next_appointment_number = cur.fetchone()[0]
   
    cur.execute("""
        INSERT INTO appointment (doctor_id, doctor_name, hospital_name, appointment_date, patient_name, patient_phone, status)
        VALUES (?, ?, ?, ?, ?, ?, 'confirmed')""", (doctor_id, doctor_name, hospital_name, appointment_date, patient_name, patient_phone))
    con.commit()
    con.close()

    return jsonify({
        "status": "success",
        "message": "✅ Appointment confirmed!",
        "existing_count": existing_count,
        "today_count": daily_count,
        "your_appointment_number": next_appointment_number,
        "patient_name": patient_name,
        "patient_phone": patient_phone
    })

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]
        if u in users and users[u] == p:
            session["user"] = u
            return redirect("/dashboard")
        else:
            return render_template("login.html", error="Invalid username or password")
    return render_template("login.html")

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "user" not in session:
        return redirect("/login")
    
    username = session["user"]
    con = get_db()
    cur = con.cursor()
    
    if request.method == "POST":
        # Handle delete doctor
        delete_doctor_id = request.form.get("delete_doctor_id")
        if delete_doctor_id:
            cur.execute("DELETE FROM doctor WHERE id=? AND username=?", (delete_doctor_id, username))
            con.commit()
            return redirect("/dashboard")
        
        # Handle hospital profile update
        name = request.form.get("name", "").strip()
        location = request.form.get("location", "").strip()
        
        # Handle image upload
        image_filename = None
        if "hospital_image" in request.files:
            file = request.files["hospital_image"]
            if file and file.filename:
                filename = secure_filename(file.filename)
                image_filename = f"{username}_{filename}"
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], image_filename))
        
        # Update or insert hospital data
        cur.execute("SELECT * FROM hospital WHERE username=?", (username,))
        existing = cur.fetchone()
        
        if existing:
            # Update existing record
            if image_filename:
                cur.execute("UPDATE hospital SET name=?, location=?, image=? WHERE username=?", 
                          (name, location, image_filename, username))
            else:
                cur.execute("UPDATE hospital SET name=?, location=? WHERE username=?", 
                          (name, location, username))
        else:
            # Insert new record
            cur.execute("INSERT INTO hospital (username, name, location, image) VALUES (?, ?, ?, ?)", 
                      (username, name, location, image_filename))
        
        con.commit()
        return redirect("/dashboard")  # Redirect to remove edit parameter
    
    # Get updated hospital details
    cur.execute("SELECT * FROM hospital WHERE username=?", (username,))
    hospital = cur.fetchone()
    
    # Get doctors for this hospital
    cur.execute("SELECT * FROM doctor WHERE username=?", (username,))
    doctors = cur.fetchall()
    
    con.close()
    
    # Check if edit mode is requested
    edit_mode = request.args.get("edit") == "1"
    
    return render_template("dashboard.html", hospital=hospital, doctors=doctors, edit_mode=edit_mode)

@app.route("/doctors", methods=["GET", "POST"])
def manage_doctors():
    if "user" not in session:
        return redirect("/login")
    
    username = session["user"]
    doctor_id = request.args.get("id")
    
    if request.method == "POST":
        # Handle image upload
        image_filename = None
        if "photo" in request.files:
            file = request.files["photo"]
            if file and file.filename:
                filename = secure_filename(file.filename)
                image_filename = f"{username}_doctor_{filename}"
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], image_filename))
        
        emergency_leave = ""
        if request.form.get("emergency_date") and request.form.get("emergency_session"):
            emergency_leave = request.form["emergency_date"] + " " + request.form["emergency_session"]
        
        if doctor_id:  # Update existing doctor
            con = get_db()
            cur = con.cursor()
            
            # Get current image if no new image uploaded
            if not image_filename:
                cur.execute("SELECT image FROM doctor WHERE id=? AND username=?", (doctor_id, username))
                current = cur.fetchone()
                if current and current[0]:
                    image_filename = current[0]
            
            cur.execute("""
                UPDATE doctor SET 
                name=?, specialization=?, education=?, timings=?, weekly_holiday=?, 
                emergency_leave=?, image=?
                WHERE id=? AND username=?
            """, (
                request.form["name"], request.form["specialization"], request.form["education"],
                request.form["timings"], request.form["weekly_holiday"], 
                emergency_leave, image_filename,
                doctor_id, username
            ))
            con.commit()
            con.close()
        else:  # Add new doctor
            con = get_db()
            cur = con.cursor()
            cur.execute("""
                INSERT INTO doctor (username, name, specialization, education, timings, weekly_holiday, emergency_leave, image)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                username, request.form["name"], request.form["specialization"], 
                request.form["education"], request.form["timings"], request.form["weekly_holiday"],
                emergency_leave, image_filename
            ))
            con.commit()
            con.close()
        
        return redirect("/dashboard")
    
    # GET request - show form
    doctor = None
    if doctor_id:
        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT * FROM doctor WHERE id=? AND username=?", (doctor_id, username))
        doctor = cur.fetchone()
        con.close()
    
    return render_template("doctor.html", doctor=doctor)

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)