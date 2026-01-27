from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
import sqlite3, os
import re
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import csv
from io import StringIO

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
        image TEXT,
        max_appointments INTEGER DEFAULT 3
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

# **NEW: Function to check if doctor is unavailable TODAY**
def is_doctor_unavailable_today(doctor):
    if not doctor:
        return False, None, None
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    today_weekday = datetime.now().strftime('%A')
    
    # Check WEEKLY HOLIDAY
    weekly_holiday = doctor[6] or ""
    weekly_days = [day.strip() for day in weekly_holiday.split(',') if day.strip()]
    if today_weekday in weekly_days:
        return True, "weekly_holiday", f"{today_weekday} (Weekly Holiday)"
    
    # Check EMERGENCY LEAVE
    emergency_leave = doctor[7] or ""
    if emergency_leave.startswith(today_str + " "):
        session_info = emergency_leave.replace(today_str + " ", "")
        return True, "emergency", f"{today_str} - {session_info}"
    
    return False, None, None

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

        # **ADD AVAILABILITY STATUS TO ALL DOCTORS**
        doctors_with_status = []
        for doctor in doctors:
            unavailable, reason, detail = is_doctor_unavailable_today(doctor)
            doctor_with_status = list(doctor)
            doctor_with_status.extend([unavailable, reason, detail])  # Add status at end
            doctors_with_status.append(doctor_with_status)

        if search_query:
            # Filter available doctors only for search
            filtered_doctors = [d for d in doctors_with_status if not d[-3] and (
                search_query in d[2].lower() or
                search_query in d[3].lower() or
                search_query in hospital[1].lower()
            )]
            if filtered_doctors:
                hospitals_with_doctors.append({
                    'hospital': hospital,
                    'doctors': filtered_doctors
                })
        else:
            hospitals_with_doctors.append({
                'hospital': hospital,
                'doctors': doctors_with_status
            })
   
    con.close()
    return render_template("user.html", hospitals_with_doctors=hospitals_with_doctors, search_query=search_query)

@app.route("/doctor_profile/<int:doctor_id>", methods=["GET"])
def doctor_profile(doctor_id):
    con = get_db()
    cur = con.cursor()
    
    cur.execute("SELECT * FROM doctor WHERE id=?", (doctor_id,))
    doctor = cur.fetchone()
    
    if not doctor:
        con.close()
        return "Doctor not found", 404
    
    is_unavailable, reason, detail = is_doctor_unavailable_today(doctor)
    
    cur.execute("SELECT * FROM hospital WHERE username=?", (doctor[1],))
    hospital = cur.fetchone()
    
    cur.execute("""
        SELECT id, doctor_name, hospital_name, appointment_date, patient_name, patient_phone, status 
        FROM appointment WHERE doctor_id=? ORDER BY appointment_date DESC, id DESC
    """, (doctor_id,))
    appointments = cur.fetchall()
    
    con.close()
    
    return render_template("doctor_profile.html", 
                           doctor=doctor, 
                           hospital=hospital, 
                           appointments=appointments,
                           is_unavailable=is_unavailable,
                           unavailable_reason=reason,
                           unavailable_detail=detail)

@app.route("/book_appointment/<int:doctor_id>", methods=["GET", "POST"])
def book_appointment_page(doctor_id):
    con = get_db()
    cur = con.cursor()
    
    cur.execute("SELECT * FROM doctor WHERE id=?", (doctor_id,))
    doctor = cur.fetchone()
    
    if not doctor:
        con.close()
        return "Doctor not found", 404
    
    # **INLINE UNAVAILABLE MESSAGE - NO SEPARATE TEMPLATE NEEDED**
    is_unavailable, reason, detail = is_doctor_unavailable_today(doctor)
    if is_unavailable:
        cur.execute("SELECT * FROM hospital WHERE username=?", (doctor[1],))
        hospital = cur.fetchone()
        con.close()
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Doctor Unavailable</title>
            <style>
                body {{ font-family: Arial; text-align: center; padding: 50px; background: #f5f5f5; margin: 0; }}
                .msg {{ background: white; padding: 40px; border-radius: 15px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); max-width: 500px; margin: 0 auto; }}
                h1 {{ color: #dc3545; font-size: 32px; margin-bottom: 20px; }}
                .doctor-name {{ font-size: 24px; color: #333; margin: 20px 0; }}
                .reason {{ background: #f8d7da; color: #721c24; padding: 15px; border-radius: 8px; margin: 20px 0; font-size: 16px; }}
                .back {{ padding: 12px 30px; background: #007bff; color: white; text-decoration: none; border-radius: 25px; display: inline-block; margin-top: 20px; }}
                .back:hover {{ background: #0056b3; }}
            </style>
        </head>
        <body>
            <div class='msg'>
                <h1>🚨 Doctor Unavailable Today</h1>
                <div class='reason'>
                    <strong>Reason:</strong> {reason.title() if reason else 'Unknown'}<br>
                    <strong>Details:</strong> {detail or 'No details available'}
                </div>
                <div class='doctor-name'>{doctor[2]}</div>
                <p style='color: #666; font-size: 16px;'>Please try another doctor or check back tomorrow.</p>
                <a href='/' class='back'>🏥 Browse Other Doctors</a>
            </div>
        </body>
        </html>
        """
    
    cur.execute("SELECT * FROM hospital WHERE username=?", (doctor[1],))
    hospital = cur.fetchone()
    
    cur.execute("SELECT COUNT(*) FROM appointment WHERE doctor_id=?", (doctor_id,))
    existing_count = cur.fetchone()[0]
    
    today = datetime.now().strftime('%Y-%m-%d')
    cur.execute("SELECT COUNT(*) FROM appointment WHERE doctor_id=? AND appointment_date=?", (doctor_id, today))
    today_count = cur.fetchone()[0]
    
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM appointment")
    next_number = cur.fetchone()[0]
    
    max_appts = doctor[9] if len(doctor) > 9 and doctor[9] else DAILY_APPOINTMENT_LIMIT
    can_book_today = today_count < max_appts
    
    con.close()
    
    if request.method == "POST":
        appointment_date = request.form.get("appointment_date")
        patient_name = request.form.get("patient_name", "").strip()
        patient_phone = request.form.get("patient_phone", "").strip()

        if not patient_name or len(patient_name) < 2:
            return render_template("book_appointment.html", 
                                   doctor=doctor, 
                                   hospital=hospital,
                                   existing_count=existing_count,
                                   today_count=today_count,
                                   daily_limit=max_appts,
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
                                   daily_limit=max_appts,
                                   can_book_today=can_book_today,
                                   next_appointment_number=next_number,
                                   error="Phone number must be exactly 10 digits")

        con = get_db()
        cur = con.cursor()
        
        cur.execute("SELECT COUNT(*) FROM appointment WHERE doctor_id=? AND appointment_date=?", (doctor_id, appointment_date))
        daily_count = cur.fetchone()[0]
        
        if daily_count >= max_appts:
            con.close()
            return render_template("book_appointment.html", 
                                   doctor=doctor, 
                                   hospital=hospital,
                                   existing_count=existing_count,
                                   today_count=today_count,
                                   daily_limit=max_appts,
                                   can_book_today=False,
                                   next_appointment_number=next_number,
                                   error=f"Daily limit reached! Maximum {max_appts} appointments per day per doctor.")
        
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
    
    now = datetime.now()
    appointment_date = now if now.hour < 9 else now + timedelta(days=1)
    default_date = appointment_date.strftime('%Y-%m-%d')
    
    return render_template("book_appointment.html", 
                           doctor=doctor, 
                           hospital=hospital,
                           existing_count=existing_count,
                           today_count=today_count,
                           daily_limit=max_appts,
                           can_book_today=can_book_today,
                           next_appointment_number=next_number,
                           default_date=default_date)

@app.route("/get_appointment_stats/<int:doctor_id>", methods=["GET"])
def get_appointment_stats(doctor_id):
    con = get_db()
    cur = con.cursor()
    
    cur.execute("SELECT * FROM doctor WHERE id=?", (doctor_id,))
    doctor = cur.fetchone()
    
    is_unavailable, reason, detail = is_doctor_unavailable_today(doctor)
    
    max_appts = doctor[9] if len(doctor) > 9 and doctor[9] else DAILY_APPOINTMENT_LIMIT
    
    cur.execute("SELECT COUNT(*) FROM appointment WHERE doctor_id=?", (doctor_id,))
    existing_count = cur.fetchone()[0]
    
    today = datetime.now().strftime('%Y-%m-%d')
    cur.execute("SELECT COUNT(*) FROM appointment WHERE doctor_id=? AND appointment_date=?", (doctor_id, today))
    today_count = cur.fetchone()[0]
    
    cur.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM appointment")
    next_number = cur.fetchone()[0]
    
    can_book_today = today_count < max_appts and not is_unavailable
    
    con.close()
    return jsonify({
        "existing_count": existing_count,
        "today_count": today_count,
        "daily_limit": max_appts,
        "can_book_today": can_book_today,
        "is_unavailable": is_unavailable,
        "unavailable_reason": reason,
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
    
    cur.execute("SELECT * FROM doctor WHERE id=?", (doctor_id,))
    doctor = cur.fetchone()
    max_appts = doctor[9] if len(doctor) > 9 and doctor[9] else DAILY_APPOINTMENT_LIMIT
    
    # **CHECK DOCTOR AVAILABILITY**
    is_unavailable, reason, detail = is_doctor_unavailable_today(doctor)
    if is_unavailable:
        con.close()
        return jsonify({
            "status": "error",
            "message": f"🚨 Doctor unavailable today: {detail}"
        }), 400
    
    cur.execute("SELECT COUNT(*) FROM appointment WHERE doctor_id=? AND appointment_date=?", (doctor_id, appointment_date))
    daily_count = cur.fetchone()[0]
    
    if daily_count >= max_appts:
        con.close()
        return jsonify({
            "status": "error",
            "message": f"❌ Daily limit reached! Maximum {max_appts} appointments per day per doctor."
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
        delete_doctor_id = request.form.get("delete_doctor_id")
        if delete_doctor_id:
            cur.execute("DELETE FROM doctor WHERE id=? AND username=?", (delete_doctor_id, username))
            con.commit()
            return redirect("/dashboard")
            
        name = request.form.get("name", "").strip()
        location = request.form.get("location", "").strip()
        
        image_filename = None
        if "hospital_image" in request.files:
            file = request.files["hospital_image"]
            if file and file.filename:
                filename = secure_filename(file.filename)
                image_filename = f"{username}_{filename}"
                file.save(os.path.join(app.config["UPLOAD_FOLDER"], image_filename))
        
        cur.execute("SELECT * FROM hospital WHERE username=?", (username,))
        existing = cur.fetchone()
        
        if existing:
            if image_filename:
                cur.execute("UPDATE hospital SET name=?, location=?, image=? WHERE username=?", 
                           (name, location, image_filename, username))
            else:
                cur.execute("UPDATE hospital SET name=?, location=? WHERE username=?", 
                           (name, location, username))
        else:
            cur.execute("INSERT INTO hospital (username, name, location, image) VALUES (?, ?, ?, ?)", 
                       (username, name, location, image_filename))
        
        con.commit()
        return redirect("/dashboard")
    
    cur.execute("SELECT * FROM hospital WHERE username=?", (username,))
    hospital = cur.fetchone()
    
    cur.execute("SELECT * FROM doctor WHERE username=?", (username,))
    doctors = cur.fetchall()
    
    # **MARK DOCTORS UNAVAILABLE TODAY**
    doctors_with_status = []
    for doctor in doctors:
        unavailable, reason, detail = is_doctor_unavailable_today(doctor)
        doctors_with_status.append({
            'doctor': doctor,
            'is_unavailable': unavailable,
            'unavailable_reason': reason,
            'unavailable_detail': detail
        })
    
    con.close()
    
    edit_mode = request.args.get("edit") == "1"
    
    return render_template("dashboard.html", 
                           hospital=hospital, 
                           doctors_with_status=doctors_with_status, 
                           edit_mode=edit_mode)

@app.route("/doctors", methods=["GET", "POST"])
def manage_doctors():
    if "user" not in session:
        return redirect("/login")
    
    username = session["user"]
    doctor_id = request.args.get("id")
    today_date = datetime.now().strftime('%Y-%m-%d')
    
    if request.method == "POST":
        # **PAST DATE VALIDATION**
        emergency_date = request.form.get("emergency_date")
        if emergency_date:
            today = datetime.now().date()
            try:
                input_date = datetime.strptime(emergency_date, '%Y-%m-%d').date()
                if input_date < today:
                    return render_template("doctor.html", 
                                          doctor=None, 
                                          today_date=today_date,
                                          error="past_date")
            except ValueError:
                return render_template("doctor.html", 
                                      doctor=None, 
                                      today_date=today_date,
                                      error="invalid_date")
        
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
        
        if doctor_id:
            con = get_db()
            cur = con.cursor()
            
            if not image_filename:
                cur.execute("SELECT image FROM doctor WHERE id=? AND username=?", (doctor_id, username))
                current = cur.fetchone()
                if current and current[0]:
                    image_filename = current[0]
            
            cur.execute("""
                UPDATE doctor SET 
                name=?, specialization=?, education=?, timings=?, weekly_holiday=?, 
                emergency_leave=?, image=?, max_appointments=?
                WHERE id=? AND username=?
            """, (
                request.form["name"], request.form["specialization"], request.form["education"],
                request.form["timings"], request.form["weekly_holiday"], 
                emergency_leave, image_filename, request.form.get("max_appointments", 3),
                doctor_id, username
            ))
            con.commit()
            con.close()
        else:
            con = get_db()
            cur = con.cursor()
            cur.execute("""
                INSERT INTO doctor (username, name, specialization, education, timings, weekly_holiday, emergency_leave, image, max_appointments)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                username, request.form["name"], request.form["specialization"], 
                request.form["education"], request.form["timings"], request.form["weekly_holiday"],
                emergency_leave, image_filename, request.form.get("max_appointments", 3)
            ))
            con.commit()
            con.close()
        
        return redirect("/dashboard")
    
    doctor = None
    if doctor_id:
        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT * FROM doctor WHERE id=? AND username=?", (doctor_id, username))
        doctor = cur.fetchone()
        con.close()
    
    # **CHECK DOCTOR STATUS FOR TODAY**
    is_unavailable, reason, detail = is_doctor_unavailable_today(doctor)
    
    error = request.args.get("error")
    return render_template("doctor.html", 
                           doctor=doctor, 
                           today_date=today_date, 
                           error=error,
                           is_unavailable=is_unavailable,
                           unavailable_reason=reason,
                           unavailable_detail=detail)

@app.route("/view_appointments/<int:doctor_id>")
def view_appointments(doctor_id):
    if "user" not in session:
        return redirect("/login")
    
    username = session["user"]
    
    con = get_db()
    cur = con.cursor()
    
    cur.execute("SELECT * FROM doctor WHERE id=? AND username=?", (doctor_id, username))
    doctor = cur.fetchone()
    if not doctor:
        con.close()
        return "Doctor not found", 404
    
    cur.execute("SELECT * FROM hospital WHERE username=?", (username,))
    hospital = cur.fetchone()
    
    cur.execute("""
        SELECT id, doctor_name, hospital_name, appointment_date, patient_name, patient_phone, status 
        FROM appointment 
        WHERE doctor_id=? AND status='confirmed'
        ORDER BY appointment_date DESC, id DESC
    """, (doctor_id,))
    appointments = cur.fetchall()
    
    con.close()
    
    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        'Appointment ID', 'Doctor Name', 'Hospital Name', 'Appointment Date', 
        'Patient Name', 'Patient Phone', 'Status'
    ])
    
    for apt in appointments:
        writer.writerow(apt)
    
    csv_data = output.getvalue()
    filename = f"appointments_{doctor[2].replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/")

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
