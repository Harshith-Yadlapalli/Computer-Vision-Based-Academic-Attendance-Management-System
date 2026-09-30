from flask import Flask, render_template, request, redirect, session, send_file, jsonify
import sqlite3
import os
import uuid
import database
from datetime import datetime, timedelta
import database as dbmod
from database import PERIODS
import io
from collections import OrderedDict
from werkzeug.utils import secure_filename
from flask import send_from_directory

# Map HOD username prefix → department code used in student IDs
# Any <prefix>hod username is valid; prefix must match a key below.
HOD_DEPT_MAP = {
    'cs': 'CSE',
    'cse': 'CSE',
    'ece': 'ECE',
    'ec': 'ECE',
    'eee': 'EEE',
    'ee': 'EE',
    'mech': 'MECH',
    'me': 'MECH',
    'civil': 'CIVIL',
    'cl': 'CIVIL',
    'ce': 'CIVIL',
    'aiml': 'AIML',
    'ai': 'AIML',
    'it': 'IT',
    'ds': 'DS',
    'csd': 'CSD',
    'csm': 'CSM',
    'csbs': 'CSBS',
    'cyber': 'CYBER',
    'cy': 'CYBER',
    'cs(cyber)': 'CYBER',
    'eie': 'EIE',
    'ei': 'EIE',
    'iem': 'IEM',
    'aero': 'AERO',
    'ae': 'AERO',
    'biotech': 'BIOTECH',
    'bt': 'BIOTECH',
    'chem': 'CHEM',
    'mines': 'MINES',
    'mining': 'MINES',
    'pharma': 'PHARMA',
    'csit': 'CSIT',
    'agri': 'AGRI',
    'pete': 'PETE',
}

# All B.Tech specializations offered at Bapatla Engineering College
ALL_BRANCHES = [
    ('CIVIL',  'civil',  'Civil Engineering'),
    ('CYBER',  'cyber',  'Cyber Security'),
    ('CSE',    'cs',     'Computer Science & Engineering'),
    ('CSM',    'csm',    'CSE - AI & ML'),
    ('DS',     'ds',     'Data Science'),
    ('ECE',    'ece',    'Electronics & Communication Engineering'),
    ('EEE',    'eee',    'Electrical & Electronics Engineering'),
    ('EIE',    'eie',    'Electronics & Instrumentation Engineering'),
    ('IT',     'it',     'Information Technology'),
    ('MECH',   'mech',   'Mechanical Engineering'),
]

def get_hod_department(hod_user_id):
    """Extract department code from HOD username. e.g. 'cshod' → 'CSE', 'ithod' → 'IT'."""
    uid = hod_user_id.lower().strip()
    if uid.endswith('hod'):
        prefix = uid[:-3]  # strip trailing 'hod'
    else:
        prefix = uid
    return HOD_DEPT_MAP.get(prefix)

app = Flask(__name__)
app.secret_key = "attendance_secret"
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

# Initialize DB on startup
database.init_db()

DB = "attendance.db"
FACE_DATASET_DIR = os.environ.get(
    "FACE_DATASET_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "clean_faces")
)
ENCODINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "encodings.pickle")

def get_db():
    return sqlite3.connect(DB)


def get_faculty_classes(cursor, faculty_id):
    cursor.execute(
        "SELECT fc.id, fc.branch, fc.year, fc.section FROM faculty_classes fc "
        "JOIN users u ON lower(u.user_id)=lower(fc.faculty_id) "
        "WHERE lower(fc.faculty_id)=lower(?) AND u.role='faculty' AND u.faculty_approved=1 "
        "ORDER BY upper(fc.branch), fc.year, upper(fc.section)",
        (faculty_id,),
    )
    return cursor.fetchall()


def choose_faculty_class(classes, requested_id):
    if not classes:
        return None
    try:
        requested_id = int(requested_id)
    except (TypeError, ValueError):
        requested_id = None
    return next((class_row for class_row in classes if class_row[0] == requested_id), classes[0])


def get_requester_leave_requests(cursor, requester_id):
    cursor.execute(
        "SELECT id, start_date, end_date, reason, status, decision_note, created_at "
        "FROM leave_requests WHERE lower(requester_id)=lower(?) ORDER BY created_at DESC, id DESC",
        (requester_id,),
    )
    return cursor.fetchall()


@app.route("/home")
def role_home():
    home_routes = {"hod": "/hod", "faculty": "/faculty", "student": "/student"}
    return redirect(home_routes.get(session.get("role"), "/"))


@app.route("/login")
def sign_in_page():
    session.clear()
    return redirect("/")

# ---------- LOGIN ----------
@app.route("/", methods=["GET", "POST"])
@app.route("/student/login", methods=["GET", "POST"])
def login():
    student_login = request.path == "/student/login"
    if request.method == "POST":
        user_id = request.form.get("user_id")
        password = request.form.get("password")
        role = request.form.get("role")
        expected_role = "student" if student_login else role

        if expected_role not in ("student", "hod", "faculty"):
            return render_template(
                "login.html",
                error="Select Student or HOD sign-in before entering your details.",
                student_login=student_login,
            )

        con = sqlite3.connect(DB)
        cur = con.cursor()

        query = "SELECT user_id, role, faculty_approved, faculty_status FROM users WHERE lower(user_id)=lower(?) AND password=? AND role=?"
        cur.execute(query, (user_id, password, expected_role))
        row = cur.fetchone()

        if row:
            con.close()
            if row[1] == "faculty" and row[3] != "approved":
                status_message = (
                    "Your faculty signup request was rejected. Contact your HOD for details."
                    if row[3] == "rejected"
                    else "Your faculty signup is waiting for HOD approval."
                )
                return render_template(
                    "login.html",
                    error=status_message,
                    student_login=student_login,
                )
            session["user_id"] = row[0]
            session["role"] = row[1]

            if row[1] == "student":
                return redirect("/student")
            elif row[1] == "hod":
                return redirect("/hod")
            elif row[1] == "faculty":
                return redirect("/faculty")

        cur.execute(
            "SELECT role FROM users WHERE lower(user_id)=lower(?) AND password=?",
            (user_id, password),
        )
        account = cur.fetchone()
        con.close()
        if account and account[0] in ("student", "hod"):
            account_label = "Student" if account[0] == "student" else "HOD"
            error = f"This is a {account_label} account. Please use {account_label} Sign In."
        else:
            error = "Invalid credentials"
        return render_template("login.html", error=error, student_login=student_login)

    return render_template(
        "login.html", student_login=student_login, signup_role=request.args.get("signup")
    )


# ---------- LOGOUT ----------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------- FORGOT PASSWORD ROUTES ----------

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        user_id = request.form.get("reg_no")
        dob = request.form.get("dob")

        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT user_id FROM users WHERE lower(user_id)=lower(?) AND dob=? AND role='student'", (user_id, dob))
        user = cur.fetchone()
        con.close()

        if user:
            session["reset_user_id"] = user_id
            return redirect("/reset-password")
        else:
            return render_template("forget_password_student.html", error="Invalid Register Number or DOB")

    return render_template("forget_password_student.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if "reset_user_id" not in session:
        return redirect("/forgot-password")

    if request.method == "POST":
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        if new_password != confirm_password:
            return render_template("rest_password_student.html", error="Passwords do not match")

        user_id = session["reset_user_id"]
        con = get_db()
        cur = con.cursor()
        cur.execute("UPDATE users SET password=? WHERE user_id=?", (new_password, user_id))
        con.commit()
        con.close()

        session.pop("reset_user_id", None)
        return render_template("reset_success.html")

    return render_template("rest_password_student.html")


# ---------- HOD DASHBOARD ----------
@app.route("/hod")
def hod():
    if session.get("role") != "hod":
        return redirect("/")

    hod_uid = session["user_id"]
    hod_dept = get_hod_department(hod_uid)  # e.g. 'EE', 'CSE', or None for 'hod1'

    time_filter = request.args.get("filter", "all")
    year_filter = request.args.get("year")
    branch_filter = request.args.get("branch")
    section_filter = request.args.get("section")
    q_filter = request.args.get("q")
    date_filter = request.args.get("date")
    con = get_db()
    cur = con.cursor()
    pending_query = "SELECT user_id, name, branch, year, section FROM users WHERE role='faculty' AND faculty_status='pending'"
    pending_params = []
    if hod_dept:
        pending_query += " AND lower(branch)=lower(?)"
        pending_params.append(hod_dept)
    pending_query += " ORDER BY user_id"
    cur.execute(pending_query, pending_params)
    pending_faculty = cur.fetchall()

    approved_query = "SELECT user_id, name, branch, year, section FROM users WHERE role='faculty' AND faculty_status='approved'"
    approved_params = []
    if hod_dept:
        approved_query += " AND lower(branch)=lower(?)"
        approved_params.append(hod_dept)
    approved_query += " ORDER BY user_id"
    cur.execute(approved_query, approved_params)
    approved_faculty = cur.fetchall()

    rejected_query = "SELECT user_id, name, branch, year, section FROM users WHERE role='faculty' AND faculty_status='rejected'"
    rejected_params = []
    if hod_dept:
        rejected_query += " AND lower(branch)=lower(?)"
        rejected_params.append(hod_dept)
    rejected_query += " ORDER BY user_id"
    cur.execute(rejected_query, rejected_params)
    rejected_faculty = cur.fetchall()

    cur.execute("SELECT user_id FROM users WHERE role='student'")
    students_seed = [r[0] for r in cur.fetchall()]
    today_str = dbmod.now_ist().strftime("%Y-%m-%d")
    if students_seed and dbmod.is_working_day(today_str):
        database.init_today(students_seed)
        database.init_today_periods(students_seed)

    # Backfill any missing past working days for all students
    database.backfill_all_students()

    # --- Build common WHERE clause with department auto-filter ---
    def build_where(table_alias):
        clauses = []
        params = []
        # Auto-filter by HOD department: use branch column when set, fallback to student_id substring
        if hod_dept:
            clauses.append(f"(lower(u.branch) = lower(?) OR (u.branch IS NULL AND lower({table_alias}.student_id) LIKE '%' || lower(?) || '%'))")
            params.extend([hod_dept, hod_dept])
        if time_filter == 'today':
            clauses.append(f"{table_alias}.date = ?")
            params.append(today_str)
        elif time_filter != 'all':
            days = {'7days': 7, '15days': 15, '30days': 30}.get(time_filter, 7)
            start_date = (dbmod.now_ist() - timedelta(days=days)).strftime("%Y-%m-%d")
            clauses.append(f"{table_alias}.date >= ?")
            params.append(start_date)
        if year_filter:
            clauses.append(f"(u.year = ? OR (CASE WHEN substr({table_alias}.student_id,1,2) IN ('21','22') THEN '4' WHEN substr({table_alias}.student_id,1,2) = '23' THEN '3' WHEN substr({table_alias}.student_id,1,2) = '24' THEN '2' WHEN substr({table_alias}.student_id,1,2) = '25' THEN '1' ELSE NULL END) = ?)")
            params.extend([year_filter, year_filter])
        if branch_filter:
            clauses.append(f"(lower(u.branch) = lower(?) OR lower({table_alias}.student_id) LIKE '%' || lower(?) || '%')")
            params.extend([branch_filter, branch_filter])
        if section_filter:
            clauses.append("lower(u.section) = lower(?)")
            params.append(section_filter)
        if q_filter:
            clauses.append(f"lower({table_alias}.student_id) LIKE '%' || lower(?) || '%'")
            params.append(q_filter)
        if date_filter:
            clauses.append(f"{table_alias}.date = ?")
            params.append(date_filter)
        return clauses, params

    # Period-wise attendance percentage
    w1, p1 = build_where('pa')
    query = "SELECT pa.student_id, ROUND(SUM(pa.value)*100.0/COUNT(*),2) AS percent FROM period_attendance pa LEFT JOIN users u ON u.user_id = pa.student_id"
    if w1:
        query += " WHERE " + " AND ".join(w1)
    query += " GROUP BY pa.student_id"
    cur.execute(query, p1)
    data = cur.fetchall()
    
    # Period-wise master list
    w2, p2 = build_where('pa')
    list_query = "SELECT pa.student_id, pa.date, pa.period, pa.status, pa.value, pa.first_seen_time FROM period_attendance pa LEFT JOIN users u ON u.user_id = pa.student_id"
    if w2:
        list_query += " WHERE " + " AND ".join(w2)
    list_query += " ORDER BY pa.date DESC, pa.student_id ASC, pa.period ASC"
    cur.execute(list_query, p2)
    master_list = cur.fetchall()

    cur.execute("SELECT student_id, ROUND(SUM(value)*100.0/COUNT(*),2) FROM period_attendance GROUP BY student_id")
    overall_percentages = {s: float(p) for s, p in cur.fetchall()}
    filtered_percentages = {d[0]: float(d[1]) for d in data}

    leave_query = (
        "SELECT id, requester_id, requester_role, branch, start_date, end_date, reason, status, decision_note, created_at "
        "FROM leave_requests"
    )
    leave_params = []
    if hod_dept:
        leave_query += " WHERE upper(branch)=upper(?)"
        leave_params.append(hod_dept)
    leave_query += " ORDER BY CASE status WHEN 'pending' THEN 0 ELSE 1 END, created_at DESC, id DESC"
    cur.execute(leave_query, leave_params)
    leave_requests = cur.fetchall()

    review_query = (
        "SELECT f.student_id, COALESCE(u.name, ''), u.branch, f.date, f.period, "
        "f.flag_type, f.details, f.created_at FROM attendance_review_flags f "
        "LEFT JOIN users u ON u.user_id=f.student_id"
    )
    review_params = []
    if hod_dept:
        review_query += " WHERE lower(u.branch)=lower(?) OR lower(f.student_id) LIKE '%' || lower(?) || '%'"
        review_params.extend([hod_dept, hod_dept])
    review_query += " ORDER BY f.created_at DESC, f.id DESC LIMIT 100"
    cur.execute(review_query, review_params)
    attendance_review_flags = cur.fetchall()

    audit_date = request.args.get("attendance_date", today_str)
    try:
        audit_date = datetime.strptime(audit_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        audit_date = today_str
    audit_weekday = datetime.strptime(audit_date, "%Y-%m-%d").weekday()
    audit_query = (
        "SELECT s.branch, s.year, s.section, s.subject, s.period, s.room, s.faculty_id, "
        "COALESCE(f.name, s.faculty_id), u.user_id, COALESCE(u.name, ''), pa.status, "
        "ca.first_seen_time, cc.completed_at FROM class_schedules s "
        "JOIN users u ON upper(u.branch)=upper(s.branch) AND u.year=s.year "
        "AND upper(u.section)=upper(s.section) AND u.role='student' "
        "LEFT JOIN users f ON lower(f.user_id)=lower(s.faculty_id) "
        "LEFT JOIN period_attendance pa ON pa.student_id=u.user_id AND pa.date=? AND pa.period=s.period "
        "LEFT JOIN cctv_attendance ca ON ca.student_id=u.user_id AND ca.date=? "
        "AND ca.period=s.period AND lower(ca.room)=lower(s.room) "
        "LEFT JOIN cctv_completed_periods cc ON cc.date=? AND cc.period=s.period "
        "AND lower(cc.room)=lower(s.room) WHERE s.weekday=?"
    )
    audit_params = [audit_date, audit_date, audit_date, audit_weekday]
    if hod_dept:
        audit_query += " AND lower(s.branch)=lower(?)"
        audit_params.append(hod_dept)
    audit_query += " ORDER BY s.period, lower(s.room), s.branch, s.year, s.section, lower(u.user_id)"
    cur.execute(audit_query, audit_params)
    cctv_audit_rows = []
    for row in cur.fetchall():
        if row[11]:
            camera_status = "Seen"
        elif row[12]:
            camera_status = "Not seen"
        else:
            camera_status = "Not verified"
        cctv_audit_rows.append({
            "branch": row[0], "year": row[1], "section": row[2], "subject": row[3],
            "period": row[4], "room": row[5], "faculty": row[7], "student_id": row[8],
            "student_name": row[9], "portal_status": row[10] or "not posted",
            "camera_status": camera_status, "camera_time": row[11] or "",
        })

    con.close()

    eligible = [d for d in data if d[1] >= 75]
    condonation = [d for d in data if 65 <= d[1] < 75]
    detained = [d for d in data if d[1] < 65]

    # Build period schedule for template
    period_schedule = {k: f"{v[0]:02d}:{v[1]:02d}\u2013{v[2]:02d}:{v[3]:02d}" for k, v in PERIODS.items()}

    # Group master_list by date for day-wise accordion view
    days_data = OrderedDict()
    for row in master_list:
        sid, dt, period, status, value, time_in = row
        if dt not in days_data:
            days_data[dt] = {'students': {}}
        if sid not in days_data[dt]['students']:
            days_data[dt]['students'][sid] = {'periods': {}}
        days_data[dt]['students'][sid]['periods'][period] = {
            'status': status, 'value': float(value), 'time': time_in or ""
        }

    return render_template(
        "hod_dashboard.html",
        eligible=eligible,
        condonation=condonation,
        detained=detained,
        master_list=master_list,
        days_data=days_data,
        overall_percentages=overall_percentages,
        filtered_percentages=filtered_percentages,
        current_filter=time_filter,
        is_today_working=dbmod.is_working_day(today_str),
        period_schedule=period_schedule,
        current_year=year_filter or "",
        current_branch=branch_filter or "",
        current_section=section_filter or "",
        current_q=q_filter or "",
        hod_dept=hod_dept or 'ALL',
        today_date=today_str,
        pending_faculty=pending_faculty,
        approved_faculty=approved_faculty,
        rejected_faculty=rejected_faculty,
        leave_requests=leave_requests,
        attendance_review_flags=attendance_review_flags,
        cctv_audit_rows=cctv_audit_rows,
        audit_date=audit_date,
    )


# ---------- STUDENT DASHBOARD ----------
@app.route("/student")
def student():
    if session.get("role") != "student":
        return redirect("/")

    sid = session["user_id"]
    today_str = dbmod.now_ist().strftime("%Y-%m-%d")
    if dbmod.is_working_day(today_str):
        database.init_today([sid])
        database.init_today_periods([sid])

    # Backfill any missing past working days for this student
    database.backfill_student_periods(sid)

    con = get_db()
    cur = con.cursor()

    # Period-wise records
    cur.execute(
        "SELECT date, period, status, value, first_seen_time FROM period_attendance WHERE student_id=? ORDER BY date DESC, period ASC",
        (sid,)
    )
    period_rows = cur.fetchall()

    # Today's period breakdown
    cur.execute(
        "SELECT period, status, value, first_seen_time FROM period_attendance WHERE student_id=? AND date=? ORDER BY period",
        (sid, today_str)
    )
    today_periods = cur.fetchall()

    # Period-wise overall stats
    total_periods = len(period_rows)
    total_value = sum(r[3] for r in period_rows)
    percent = round((total_value / total_periods) * 100, 2) if total_periods else 0

    # Count stats
    present_count = sum(1 for r in period_rows if r[2] == 'present')
    absent_count = sum(1 for r in period_rows if r[2] == 'absent')

    cur.execute("SELECT name, year, section, branch FROM users WHERE user_id=?", (sid,))
    student_profile = cur.fetchone() or (None, None, None, None)
    leave_requests = get_requester_leave_requests(cur, sid)

    con.close()

    period_schedule = {k: f"{v[0]:02d}:{v[1]:02d}–{v[2]:02d}:{v[3]:02d}" for k, v in PERIODS.items()}

    # Group period records by date for day-wise view
    from collections import OrderedDict
    days_attendance = OrderedDict()
    for r in period_rows:  # already sorted date DESC, period ASC
        date_str_key = r[0]
        if date_str_key not in days_attendance:
            days_attendance[date_str_key] = []
        days_attendance[date_str_key].append({
            'period': r[1],
            'status': r[2],
            'value': r[3],
            'time_in': r[4] if r[4] else '--'
        })

    return render_template(
        "student_dashboard.html",
        student_id=sid,
        student_name=student_profile[0],
        student_year=student_profile[1],
        student_section=student_profile[2],
        student_branch=student_profile[3],
        percent=percent,
        period_records=period_rows,
        today_periods=today_periods,
        total_periods=total_periods,
        present_count=present_count,
        absent_count=absent_count,
        is_today_working=dbmod.is_working_day(today_str),
        period_schedule=period_schedule,
        days_attendance=days_attendance,
        today_date=today_str,
        leave_requests=leave_requests,
        leave_saved=request.args.get("leave") == "saved",
    )

@app.route("/api/hod-data")
def api_hod_data():
    if session.get("role") != "hod":
        return {"error": "unauthorized"}, 401
    hod_uid = session["user_id"]
    hod_dept = get_hod_department(hod_uid)

    time_filter = request.args.get("filter", "all")
    year_filter = request.args.get("year")
    branch_filter = request.args.get("branch")
    section_filter = request.args.get("section")
    section_filter = request.args.get("section")
    q_filter = request.args.get("q")
    date_filter = request.args.get("date")
    derive_toggle = request.args.get("derive") == "1"

    con = get_db()
    cur = con.cursor()

    def build_where(table_alias):
        clauses = []
        params = []
        if hod_dept:
            clauses.append(f"(lower(u.branch) = lower(?) OR (u.branch IS NULL AND lower({table_alias}.student_id) LIKE '%' || lower(?) || '%'))")
            params.extend([hod_dept, hod_dept])
        if time_filter == 'today':
            today_api = dbmod.now_ist().strftime("%Y-%m-%d")
            clauses.append(f"{table_alias}.date = ?")
            params.append(today_api)
        elif time_filter != 'all':
            days = {'7days': 7, '15days': 15, '30days': 30}.get(time_filter, 7)
            start_date = (dbmod.now_ist() - timedelta(days=days)).strftime("%Y-%m-%d")
            clauses.append(f"{table_alias}.date >= ?")
            params.append(start_date)
        if year_filter:
            if derive_toggle:
                clauses.append(f"(u.year = ? OR (CASE WHEN substr({table_alias}.student_id,1,1)='L' AND substr({table_alias}.student_id,2,2)='23' THEN '4' WHEN substr({table_alias}.student_id,1,2)='22' THEN '2' WHEN substr({table_alias}.student_id,1,2)='21' THEN '4' WHEN substr({table_alias}.student_id,1,2)='23' THEN '3' WHEN substr({table_alias}.student_id,1,2)='24' THEN '2' WHEN substr({table_alias}.student_id,1,2)='25' THEN '1' WHEN substr({table_alias}.student_id,1,2)='20' THEN '5' ELSE NULL END) = ?)")
            else:
                clauses.append(f"(u.year = ? OR (CASE WHEN substr({table_alias}.student_id,1,2) IN ('21','22') THEN '4' WHEN substr({table_alias}.student_id,1,2) = '23' THEN '3' WHEN substr({table_alias}.student_id,1,2) = '24' THEN '2' WHEN substr({table_alias}.student_id,1,2) = '25' THEN '1' ELSE NULL END) = ?)")
            params.extend([year_filter, year_filter])
        if branch_filter:
            clauses.append(f"(lower(u.branch) = lower(?) OR lower({table_alias}.student_id) LIKE '%' || lower(?) || '%')")
            params.extend([branch_filter, branch_filter])
        if section_filter:
            clauses.append("lower(u.section) = lower(?)")
            params.append(section_filter)
        if q_filter:
            clauses.append(f"lower({table_alias}.student_id) LIKE '%' || lower(?) || '%'")
            params.append(q_filter)
        if date_filter:
            clauses.append(f"{table_alias}.date = ?")
            params.append(date_filter)
        return clauses, params

    w1, p1 = build_where('pa')
    query = "SELECT pa.student_id, ROUND(SUM(pa.value)*100.0/COUNT(*),2) AS percent FROM period_attendance pa LEFT JOIN users u ON u.user_id = pa.student_id"
    if w1:
        query += " WHERE " + " AND ".join(w1)
    query += " GROUP BY pa.student_id"
    cur.execute(query, p1)
    data = cur.fetchall()

    filtered_percentages = {s: float(p) for s, p in data}
    eligible = [ {"id": s, "percent": float(p)} for s, p in data if p >= 75 ]
    condonation = [ {"id": s, "percent": float(p)} for s, p in data if 65 <= p < 75 ]
    detained = [ {"id": s, "percent": float(p)} for s, p in data if p < 65 ]

    cur.execute("SELECT student_id, ROUND(SUM(value)*100.0/COUNT(*),2) FROM period_attendance GROUP BY student_id")
    overall_percentages = {s: float(p) for s, p in cur.fetchall()}

    w2, p2 = build_where('pa')
    list_query = "SELECT pa.student_id, pa.date, pa.period, pa.status, pa.value, pa.first_seen_time FROM period_attendance pa LEFT JOIN users u ON u.user_id = pa.student_id"
    if w2:
        list_query += " WHERE " + " AND ".join(w2)
    list_query += " ORDER BY pa.date DESC, pa.student_id ASC, pa.period ASC"
    cur.execute(list_query, p2)
    
    from collections import OrderedDict
    days_data = OrderedDict()
    for row in cur.fetchall():
        sid, dt, period, status, value, time_in = row
        if dt not in days_data:
            days_data[dt] = {'students': {}}
        
        if sid not in days_data[dt]['students']:
            days_data[dt]['students'][sid] = {'periods': {}}
        
        days_data[dt]['students'][sid]['periods'][period] = {
            'status': status, 'value': float(value), 'time': time_in or ""
        }

    con.close()

    return {
        "eligible": eligible,
        "condonation": condonation,
        "detained": detained,
        "days_data": days_data,
        "overall_percentages": overall_percentages,
        "filtered_percentages": filtered_percentages
    }
@app.route("/api/check-username")
def api_check_username():
    user_id = request.args.get("user_id","").lower()
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT 1 FROM users WHERE lower(user_id)=?", (user_id,))
    exists = cur.fetchone() is not None
    con.close()
    return {"exists": exists}
@app.route("/hod/approve-faculty", methods=["POST"])
def hod_approve_faculty():
    if session.get("role") != "hod":
        return redirect("/")

    faculty_id = request.form.get("user_id", "").strip()
    hod_dept = get_hod_department(session.get("user_id", ""))
    con = get_db()
    cur = con.cursor()
    cur.execute(
        "SELECT branch FROM users WHERE lower(user_id)=lower(?) AND role='faculty' AND faculty_status='pending'",
        (faculty_id,),
    )
    faculty = cur.fetchone()
    if not faculty:
        con.close()
        return redirect("/hod")
    if hod_dept and (not faculty[0] or faculty[0].lower() != hod_dept.lower()):
        con.close()
        return "Forbidden", 403

    cur.execute(
        "UPDATE users SET faculty_approved=1, faculty_status='approved' "
        "WHERE lower(user_id)=lower(?) AND role='faculty' AND faculty_status='pending'",
        (faculty_id,),
    )
    cur.execute(
        "INSERT OR IGNORE INTO faculty_classes (faculty_id, branch, year, section) "
        "SELECT user_id, branch, year, section FROM users WHERE lower(user_id)=lower(?) AND role='faculty'",
        (faculty_id,),
    )
    con.commit()
    con.close()
    return redirect("/hod")


@app.route("/hod/reject-faculty", methods=["POST"])
def hod_reject_faculty():
    if session.get("role") != "hod":
        return redirect("/")
    faculty_id = request.form.get("user_id", "").strip()
    hod_dept = get_hod_department(session.get("user_id", ""))
    con = get_db()
    cur = con.cursor()
    cur.execute(
        "SELECT branch FROM users WHERE lower(user_id)=lower(?) AND role='faculty' AND faculty_status='pending'",
        (faculty_id,),
    )
    faculty = cur.fetchone()
    if not faculty:
        con.close()
        return redirect("/hod")
    if hod_dept and (not faculty[0] or faculty[0].lower() != hod_dept.lower()):
        con.close()
        return "Forbidden", 403
    cur.execute(
        "UPDATE users SET faculty_approved=0, faculty_status='rejected' "
        "WHERE lower(user_id)=lower(?) AND role='faculty' AND faculty_status='pending'",
        (faculty_id,),
    )
    con.commit()
    con.close()
    return redirect("/hod")


@app.route("/leave-request", methods=["POST"])
def submit_leave_request():
    requester_role = session.get("role")
    requester_id = session.get("user_id")
    if requester_role not in {"student", "faculty"} or not requester_id:
        return redirect("/")

    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()
    reason = request.form.get("reason", "").strip()
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError:
        return redirect(f"/{requester_role}?leave=invalid")
    if end < start or not reason or len(reason) > 2000:
        return redirect(f"/{requester_role}?leave=invalid")

    con = get_db()
    cur = con.cursor()
    cur.execute(
        "SELECT branch FROM users WHERE lower(user_id)=lower(?) AND role=?",
        (requester_id, requester_role),
    )
    requester = cur.fetchone()
    if not requester or not requester[0]:
        con.close()
        return redirect("/")
    cur.execute(
        "INSERT INTO leave_requests (requester_id, requester_role, branch, start_date, end_date, reason, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (requester_id, requester_role, requester[0], start_date, end_date, reason, dbmod.now_ist().isoformat(timespec="seconds")),
    )
    con.commit()
    con.close()
    return redirect(f"/{requester_role}?leave=saved")


@app.route("/hod/leave-requests/<int:request_id>/decision", methods=["POST"])
def decide_leave_request(request_id):
    if session.get("role") != "hod":
        return redirect("/")
    decision = request.form.get("decision", "").strip().lower()
    if decision not in {"approved", "rejected"}:
        return redirect("/hod")
    hod_department = get_hod_department(session.get("user_id", ""))
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT branch, status FROM leave_requests WHERE id=?", (request_id,))
    leave_request = cur.fetchone()
    if not leave_request or leave_request[1] != "pending":
        con.close()
        return redirect("/hod")
    if hod_department and leave_request[0].lower() != hod_department.lower():
        con.close()
        return "Forbidden", 403
    decision_note = request.form.get("decision_note", "").strip()[:500]
    cur.execute(
        "UPDATE leave_requests SET status=?, decision_note=?, reviewed_by=?, reviewed_at=? "
        "WHERE id=? AND status='pending'",
        (decision, decision_note or None, session["user_id"], dbmod.now_ist().isoformat(timespec="seconds"), request_id),
    )
    con.commit()
    con.close()
    return redirect("/hod")


@app.route("/hod/manual-attendance", methods=["GET","POST"])
def hod_manual_attendance():
    if session.get("role") != "hod":
        return redirect("/")
    if request.method == "POST":
        reg_no = request.form.get("reg_no")
        date_str = request.form.get("date")
        time_str = request.form.get("time")
        year = request.form.get("year")
        period_val = request.form.get("period", "all")  # 1-6 or 'all'
        status_val = request.form.get("status", "present")  # present, late, od
        # Use a connection with a timeout to avoid 'database is locked'
        con = sqlite3.connect(DB, timeout=10)
        cur = con.cursor()
        try:
            cur.execute("SELECT 1 FROM users WHERE lower(user_id)=lower(?)", (reg_no,))
            exists = cur.fetchone()
            if not exists:
                con.close()
                return render_template("hod_manual_attendance.html", error="Student not found", preset_id=reg_no, period_schedule=PERIODS)
            if year:
                cur.execute("UPDATE users SET year=? WHERE lower(user_id)=lower(?)", (year, reg_no))
            # Legacy attendance table
            cur.execute("INSERT OR REPLACE INTO attendance (student_id, date, first_seen_time, present) VALUES (?, ?, ?, 1)", (reg_no, date_str, time_str))
            # Period attendance table
            status_map = {'present': ('present', 1.0), 'od': ('present', 1.0)}
            st, val = status_map.get(status_val, ('present', 1.0))
            if period_val == 'all':
                periods_to_mark = list(PERIODS.keys())
            else:
                periods_to_mark = [int(period_val)]
            for p in periods_to_mark:
                cur.execute("INSERT OR REPLACE INTO period_attendance (student_id, date, period, status, value, first_seen_time) VALUES (?, ?, ?, ?, ?, ?)",
                            (reg_no, date_str, p, st, val, time_str))
            con.commit()
        except sqlite3.OperationalError as e:
            con.rollback()
            con.close()
            return render_template("hod_manual_attendance.html", error="Database is busy. Please retry in a moment.", preset_id=reg_no, period_schedule=PERIODS)
        con.close()
        return redirect("/hod")
    return render_template("hod_manual_attendance.html", period_schedule=PERIODS)


@app.route("/hod/faculty-attendance", methods=["GET", "POST"])
def hod_faculty_attendance():
    if session.get("role") != "hod":
        return redirect("/")
    hod_department = get_hod_department(session.get("user_id", ""))
    selected_date = request.values.get("date", dbmod.now_ist().strftime("%Y-%m-%d"))
    try:
        selected_date = datetime.strptime(selected_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        selected_date = dbmod.now_ist().strftime("%Y-%m-%d")

    con = get_db()
    cur = con.cursor()
    if request.method == "POST":
        faculty_id = request.form.get("faculty_id", "").strip()
        status = request.form.get("status", "").strip().lower()
        note = request.form.get("note", "").strip()[:500]
        cur.execute(
            "SELECT branch FROM users WHERE lower(user_id)=lower(?) AND role='faculty' AND faculty_status='approved'",
            (faculty_id,),
        )
        faculty = cur.fetchone()
        if not faculty or status not in {"present", "absent"}:
            con.close()
            return redirect(f"/hod/faculty-attendance?date={selected_date}&error=invalid")
        if hod_department and faculty[0].lower() != hod_department.lower():
            con.close()
            return "Forbidden", 403
        cur.execute(
            "INSERT INTO faculty_attendance (faculty_id, branch, attendance_date, status, note, marked_by, marked_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(faculty_id, attendance_date) DO UPDATE SET "
            "status=excluded.status, note=excluded.note, marked_by=excluded.marked_by, marked_at=excluded.marked_at",
            (faculty_id, faculty[0], selected_date, status, note or None, session["user_id"], dbmod.now_ist().isoformat(timespec="seconds")),
        )
        con.commit()
        con.close()
        return redirect(f"/hod/faculty-attendance?date={selected_date}&saved=1")

    attendance_query = (
        "SELECT u.user_id, u.name, u.branch, fa.status, fa.note, fa.marked_at "
        "FROM users u LEFT JOIN faculty_attendance fa ON lower(fa.faculty_id)=lower(u.user_id) "
        "AND fa.attendance_date=? WHERE u.role='faculty' AND u.faculty_status='approved'"
    )
    attendance_params = [selected_date]
    if hod_department:
        attendance_query += " AND lower(u.branch)=lower(?)"
        attendance_params.append(hod_department)
    attendance_query += " ORDER BY lower(u.name), lower(u.user_id)"
    cur.execute(attendance_query, attendance_params)
    faculty_rows = cur.fetchall()
    con.close()
    return render_template(
        "hod_faculty_attendance.html", faculty_rows=faculty_rows, selected_date=selected_date,
        error=request.args.get("error"), saved=request.args.get("saved") == "1",
        hod_department=hod_department or "ALL",
    )

@app.route("/hod/signup", methods=["GET","POST"])
def hod_signup():
    import re
    branches = ALL_BRANCHES
    if request.method == "POST":
        branch_code = request.form.get("branch_code", "").strip()  # e.g. 'cs', 'it'
        password = request.form.get("password", "")
        # Build username automatically: e.g. cshod, ithod
        uid_lower = branch_code.lower() + "hod"

        ok = (len(password) >= 10 and re.search(r"[A-Z]", password) and re.search(r"[a-z]", password) and re.search(r"\d", password) and re.search(r"[^A-Za-z0-9]", password))
        if not ok:
            return render_template("hod_signup.html", error="Password must be 10+ chars with uppercase, lowercase, number, and special character.", branches=branches)
        if branch_code not in [b[1] for b in ALL_BRANCHES]:
            return render_template("hod_signup.html", error="Invalid branch selected.", branches=branches)
        hod_dept = HOD_DEPT_MAP.get(branch_code)
        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT 1 FROM users WHERE lower(user_id)=lower(?)", (uid_lower,))
        if cur.fetchone():
            con.close()
            return render_template("hod_signup.html", error=f"HOD account '{uid_lower}' already exists. Please log in.", branches=branches)
        cur.execute("INSERT INTO users (user_id, password, role, dob, branch) VALUES (?, ?, 'hod', NULL, ?)", (uid_lower, password, hod_dept))
        con.commit()
        con.close()
        return redirect("/?signup=hod")
    return render_template("hod_signup.html", branches=branches)


@app.route("/faculty/signup", methods=["GET", "POST"])
def faculty_signup():
    import re

    branches = ALL_BRANCHES
    if request.method == "POST":
        user_id = request.form.get("user_id", "").strip()
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        branch = request.form.get("branch", "").strip().upper()
        year = request.form.get("year", "").strip()
        section = request.form.get("section", "").strip().upper()

        branch_codes = {branch_data[0] for branch_data in branches}
        if not user_id or not name or branch not in branch_codes or year not in {"1", "2", "3", "4"} or section not in {"A", "B", "C", "D"}:
            return render_template("faculty_signup.html", error="Enter your details and select a valid branch, year, and section.", branches=branches)

        password_is_valid = (
            len(password) >= 10
            and re.search(r"[A-Z]", password)
            and re.search(r"[a-z]", password)
            and re.search(r"\d", password)
            and re.search(r"[^A-Za-z0-9]", password)
        )
        if not password_is_valid:
            return render_template(
                "faculty_signup.html",
                error="Password must be 10+ characters with uppercase, lowercase, number, and special character.",
                branches=branches,
            )

        con = get_db()
        cur = con.cursor()
        cur.execute("SELECT 1 FROM users WHERE lower(user_id)=lower(?)", (user_id,))
        if cur.fetchone():
            con.close()
            return render_template("faculty_signup.html", error="That user ID is already registered.", branches=branches)

        cur.execute(
            "INSERT INTO users (user_id, password, role, dob, branch, name, year, section, faculty_approved, faculty_status) "
            "VALUES (?, ?, 'faculty', NULL, ?, ?, ?, ?, 0, 'pending')",
            (user_id, password, branch, name, year, section),
        )
        con.commit()
        con.close()
        return redirect("/?signup=faculty")

    return render_template("faculty_signup.html", branches=branches)


@app.route("/faculty", methods=["GET", "POST"])
def faculty_dashboard():
    if session.get("role") != "faculty":
        return redirect("/")

    con = get_db()
    cur = con.cursor()
    class_options = get_faculty_classes(cur, session["user_id"])
    selected_class = choose_faculty_class(class_options, request.values.get("class_id"))
    if not selected_class:
        con.close()
        session.clear()
        return redirect("/")

    class_id, branch, year, section = selected_class
    cur.execute(
        "SELECT user_id, name FROM users WHERE role='student' AND upper(branch)=? AND year=? AND upper(section)=? ORDER BY lower(name), lower(user_id)",
        (branch.upper(), year, section.upper()),
    )
    students = cur.fetchall()
    today = dbmod.now_ist().strftime("%Y-%m-%d")

    if request.method == "POST":
        date_value = request.form.get("date", "")
        period_value = request.form.get("period", "")
        try:
            selected_date = datetime.strptime(date_value, "%Y-%m-%d").strftime("%Y-%m-%d")
            period = int(period_value)
        except (TypeError, ValueError):
            con.close()
            return render_template(
                "faculty_dashboard.html",
                error="Select a valid date and period.",
                class_options=class_options,
                selected_class_id=class_id,
                branch=branch,
                year=year,
                section=section,
                students=[],
                selected_date=today,
                selected_period=1,
                periods=PERIODS,
            )
        if period not in PERIODS:
            con.close()
            return redirect(f"/faculty?class_id={class_id}")

        submitted_statuses = {
            student_id: request.form.get(f"attendance_{student_id}", "absent")
            for student_id, _ in students
        }
        marked_time = dbmod.now_ist().strftime("%H:%M:%S")
        submitted_at = dbmod.now_ist().isoformat(timespec="seconds")
        scheduled_weekday = datetime.strptime(selected_date, "%Y-%m-%d").weekday()
        cur.execute(
            "SELECT DISTINCT room FROM class_schedules WHERE lower(faculty_id)=lower(?) "
            "AND upper(branch)=upper(?) AND year=? AND upper(section)=upper(?) "
            "AND weekday=? AND period=?",
            (session["user_id"], branch, year, section, scheduled_weekday, period),
        )
        scheduled_rooms = [row[0] for row in cur.fetchall()]
        cctv_room = scheduled_rooms[0] if len(scheduled_rooms) == 1 else None
        if cctv_room:
            cur.execute(
                "SELECT 1 FROM cctv_completed_periods WHERE date=? AND period=? AND lower(room)=lower(?)",
                (selected_date, period, cctv_room),
            )
            cctv_period_complete = cur.fetchone() is not None
        else:
            cctv_period_complete = False
        try:
            for student_id, _ in students:
                status_value = submitted_statuses[student_id]
                is_credited = status_value in ("present", "od")
                faculty_status = "present" if is_credited else "absent"
                cur.execute(
                    "SELECT COUNT(*) FROM faculty_attendance_submissions "
                    "WHERE faculty_id=? AND class_id=? AND student_id=? AND date=? AND period=? AND status='present'",
                    (session["user_id"], class_id, student_id, selected_date, period),
                )
                previous_present_submissions = cur.fetchone()[0]
                if is_credited and previous_present_submissions:
                    cur.execute(
                        "INSERT OR IGNORE INTO attendance_review_flags "
                        "(student_id, date, period, flag_type, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            student_id, selected_date, period, "duplicate_submission",
                            "Student was marked present in more than one faculty submission; review for possible proxy attendance.",
                            submitted_at,
                        ),
                    )
                cur.execute(
                    "INSERT INTO faculty_attendance_submissions "
                    "(faculty_id, class_id, student_id, date, period, status, submitted_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (session["user_id"], class_id, student_id, selected_date, period, faculty_status, submitted_at),
                )

                final_status = faculty_status
                final_time = marked_time if is_credited else None
                if cctv_period_complete:
                    cur.execute(
                        "SELECT first_seen_time FROM cctv_attendance "
                        "WHERE student_id=? AND date=? AND period=? AND lower(room)=lower(?)",
                        (student_id, selected_date, period, cctv_room),
                    )
                    cctv_row = cur.fetchone()
                    cctv_status = "present" if cctv_row else "absent"
                    if faculty_status != cctv_status:
                        cur.execute(
                            "INSERT OR IGNORE INTO attendance_review_flags "
                            "(student_id, date, period, flag_type, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                            (
                                student_id, selected_date, period, "cctv_mismatch",
                                f"Faculty marked {faculty_status}; verified CCTV marked {cctv_status}.",
                                submitted_at,
                            ),
                        )
                    final_status = cctv_status
                    final_time = cctv_row[0] if cctv_row else None
                cur.execute(
                    "INSERT INTO period_attendance (student_id, date, period, status, value, first_seen_time) "
                    "VALUES (?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(student_id, date, period) DO UPDATE SET "
                    "status=excluded.status, value=excluded.value, first_seen_time=excluded.first_seen_time",
                    (
                        student_id,
                        selected_date,
                        period,
                        final_status,
                        1.0 if final_status == "present" else 0.0,
                        final_time,
                    ),
                )
            con.commit()
        except sqlite3.OperationalError:
            con.rollback()
            con.close()
            return render_template(
                "faculty_dashboard.html",
                error="Attendance could not be saved. Please retry.",
                class_options=class_options,
                selected_class_id=class_id,
                branch=branch,
                year=year,
                section=section,
                students=[],
                selected_date=selected_date,
                selected_period=period,
                periods=PERIODS,
            )

        con.close()
        return redirect(f"/faculty?class_id={class_id}&date={selected_date}&period={period}&saved=1")

    selected_date = request.args.get("date", today)
    try:
        selected_date = datetime.strptime(selected_date, "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        selected_date = today
    try:
        selected_period = int(request.args.get("period", "1"))
    except ValueError:
        selected_period = 1
    if selected_period not in PERIODS:
        selected_period = 1

    student_ids = [student_id for student_id, _ in students]
    attendance_by_student = {}
    if student_ids:
        placeholders = ",".join("?" for _ in student_ids)
        cur.execute(
            f"SELECT student_id, status FROM period_attendance WHERE date=? AND period=? AND student_id IN ({placeholders})",
            [selected_date, selected_period, *student_ids],
        )
        attendance_by_student = dict(cur.fetchall())
    leave_requests = get_requester_leave_requests(cur, session["user_id"])
    con.close()

    roster = [
        {"user_id": student_id, "name": name, "status": attendance_by_student.get(student_id, "absent")}
        for student_id, name in students
    ]
    return render_template(
        "faculty_dashboard.html",
        class_options=class_options,
        selected_class_id=class_id,
        branch=branch,
        year=year,
        section=section,
        students=roster,
        selected_date=selected_date,
        selected_period=selected_period,
        periods=PERIODS,
        saved=request.args.get("saved") == "1",
        leave_requests=leave_requests,
        leave_saved=request.args.get("leave") == "saved",
    )


@app.route("/faculty/profile", methods=["GET", "POST"])
def faculty_profile():
    if session.get("role") != "faculty":
        return redirect("/")

    con = get_db()
    cur = con.cursor()
    cur.execute(
        "SELECT user_id, name, branch, year, section, email, phone, password "
        "FROM users WHERE lower(user_id)=lower(?) AND role='faculty' AND faculty_approved=1",
        (session["user_id"],),
    )
    faculty = cur.fetchone()
    if not faculty:
        con.close()
        session.clear()
        return redirect("/")

    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        new_password = request.form.get("new_password", "")
        if not name:
            error = "Enter your name."
        elif new_password and request.form.get("current_password") != faculty[7]:
            error = "Current password is incorrect."
        elif new_password and len(new_password) < 8:
            error = "New password must be at least 8 characters."
        else:
            cur.execute(
                "UPDATE users SET name=?, email=?, phone=? WHERE user_id=?",
                (name, email or None, phone or None, faculty[0]),
            )
            if new_password:
                cur.execute("UPDATE users SET password=? WHERE user_id=?", (new_password, faculty[0]))
            con.commit()
            con.close()
            return redirect("/faculty/profile?saved=1")

    cur.execute(
        "SELECT user_id, name, branch, year, section, email, phone "
        "FROM users WHERE lower(user_id)=lower(?)",
        (session["user_id"],),
    )
    profile = cur.fetchone()
    con.close()
    return render_template("faculty_profile.html", faculty=profile, error=error, saved=request.args.get("saved") == "1")


@app.route("/faculty/students")
def faculty_students():
    if session.get("role") != "faculty":
        return redirect("/")

    con = get_db()
    cur = con.cursor()
    class_options = get_faculty_classes(cur, session["user_id"])
    selected_class = choose_faculty_class(class_options, request.args.get("class_id"))
    if not selected_class:
        con.close()
        session.clear()
        return redirect("/")
    branch, year, section = selected_class[1:]
    cur.execute(
        "SELECT u.user_id, u.name, u.branch, u.year, u.section, "
        "CASE WHEN COUNT(pa.id)=0 THEN 0 ELSE ROUND(SUM(pa.value)*100.0/COUNT(pa.id), 2) END, "
        "ROUND(COALESCE(SUM(pa.value), 0), 0), COUNT(pa.id) "
        "FROM users u LEFT JOIN period_attendance pa ON pa.student_id=u.user_id "
        "WHERE u.role='student' AND upper(u.branch)=upper(?) AND u.year=? AND upper(u.section)=upper(?) "
        "GROUP BY u.user_id ORDER BY lower(u.name), lower(u.user_id)",
        (branch, year, section),
    )
    students = cur.fetchall()
    con.close()
    return render_template(
        "faculty_students.html", students=students, branch=branch, year=year, section=section,
        class_options=class_options, selected_class_id=selected_class[0],
    )


@app.route("/faculty/export-excel")
def faculty_export_excel():
    if session.get("role") != "faculty":
        return redirect("/")
    con = get_db()
    cur = con.cursor()
    class_options = get_faculty_classes(cur, session["user_id"])
    assignment = choose_faculty_class(class_options, request.args.get("class_id"))
    if not assignment:
        con.close()
        session.clear()
        return redirect("/")
    cur.execute(
        "SELECT u.user_id, u.name, u.branch, u.year, u.section, "
        "CASE WHEN COUNT(pa.id)=0 THEN 0 ELSE ROUND(SUM(pa.value)*100.0/COUNT(pa.id), 2) END, "
        "ROUND(COALESCE(SUM(pa.value), 0), 0), COUNT(pa.id) "
        "FROM users u LEFT JOIN period_attendance pa ON pa.student_id=u.user_id "
        "WHERE u.role='student' AND upper(u.branch)=upper(?) AND u.year=? AND upper(u.section)=upper(?) "
        "GROUP BY u.user_id ORDER BY lower(u.name), lower(u.user_id)",
        assignment[1:],
    )
    students = cur.fetchall()
    con.close()

    from openpyxl import Workbook
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Class Attendance"
    sheet.append(["Student ID", "Name", "Branch", "Year", "Section", "Overall Attendance (%)", "Present Periods", "Total Periods"])
    for student in students:
        sheet.append(student)
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=f"{assignment[1]}_Year{assignment[2]}_Section{assignment[3]}_attendance.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/faculty/schedule")
def faculty_schedule():
    if session.get("role") != "faculty":
        return redirect("/")
    con = get_db()
    cur = con.cursor()
    class_options = get_faculty_classes(cur, session["user_id"])
    selected_class = choose_faculty_class(class_options, request.args.get("class_id"))
    if not selected_class:
        con.close()
        session.clear()
        return redirect("/")
    assignment = selected_class[1:]
    cur.execute(
        "SELECT subject, weekday, period, room FROM class_schedules "
        "WHERE upper(branch)=upper(?) AND year=? AND upper(section)=upper(?) "
        "ORDER BY weekday, period, subject",
        assignment,
    )
    schedules = cur.fetchall()
    con.close()
    weekday_names = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday"}
    return render_template(
        "faculty_schedule.html", schedules=schedules, assignment=assignment,
        weekdays=weekday_names, periods=PERIODS, class_options=class_options,
        selected_class_id=selected_class[0],
    )


@app.route("/faculty/coursework", methods=["GET", "POST"])
def faculty_coursework():
    if session.get("role") != "faculty":
        return redirect("/")
    con = get_db()
    cur = con.cursor()
    class_options = get_faculty_classes(cur, session["user_id"])
    selected_class = choose_faculty_class(class_options, request.values.get("class_id"))
    if not selected_class:
        con.close()
        session.clear()
        return redirect("/")
    class_id, branch, year, section = selected_class

    if request.method == "POST":
        action = request.form.get("action")
        if action != "assignment":
            con.close()
            return redirect(f"/faculty/coursework?class_id={class_id}")
        title = request.form.get("title", "").strip()
        if not title:
            con.close()
            return redirect(f"/faculty/coursework?class_id={class_id}&error=title")
        created_at = dbmod.now_ist().isoformat(timespec="seconds")
        description = request.form.get("description", "").strip()
        due_at = request.form.get("due_at", "").strip()
        try:
            datetime.fromisoformat(due_at)
        except ValueError:
            con.close()
            return redirect(f"/faculty/coursework?class_id={class_id}&error=due")
        cur.execute(
            "INSERT INTO assignments (faculty_id, branch, year, section, title, description, due_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session["user_id"], branch, year, section, title, description, due_at, created_at),
        )
        con.commit()
        con.close()
        return redirect(f"/faculty/coursework?class_id={class_id}&saved=1")

    cur.execute(
        "SELECT title, body, created_at FROM announcements WHERE audience IN ('faculty', 'all') "
        "ORDER BY created_at DESC, id DESC"
    )
    announcements = cur.fetchall()
    cur.execute(
        "SELECT id, title, description, due_at, created_at FROM assignments "
        "WHERE upper(branch)=upper(?) AND year=? AND upper(section)=upper(?) ORDER BY due_at, id DESC",
        selected_class[1:],
    )
    assignments = cur.fetchall()
    submissions = {}
    for assignment_row in assignments:
        cur.execute(
            "SELECT s.student_id, u.name, s.original_filename, s.submitted_at, s.stored_filename "
            "FROM assignment_submissions s JOIN users u ON u.user_id=s.student_id "
            "WHERE s.assignment_id=? ORDER BY lower(u.name), s.student_id",
            (assignment_row[0],),
        )
        submissions[assignment_row[0]] = cur.fetchall()
    con.close()
    return render_template(
        "faculty_coursework.html", announcements=announcements, assignments=assignments,
        submissions=submissions, error=request.args.get("error"), saved=request.args.get("saved") == "1",
        class_options=class_options, selected_class_id=class_id,
        branch=branch, year=year, section=section,
    )


@app.route("/student/coursework")
def student_coursework():
    if session.get("role") != "student":
        return redirect("/")
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT branch, year, section FROM users WHERE user_id=? AND role='student'", (session["user_id"],))
    assignment = cur.fetchone()
    if not assignment:
        con.close()
        return redirect("/")
    cur.execute(
        "SELECT title, body, created_at FROM announcements WHERE audience IN ('students', 'all') "
        "ORDER BY created_at DESC, id DESC"
    )
    announcements = cur.fetchall()
    cur.execute(
        "SELECT a.id, a.title, a.description, a.due_at, s.original_filename, s.submitted_at, s.stored_filename "
        "FROM assignments a LEFT JOIN assignment_submissions s ON s.assignment_id=a.id AND s.student_id=? "
        "WHERE upper(a.branch)=upper(?) AND a.year=? AND upper(a.section)=upper(?) ORDER BY a.due_at, a.id DESC",
        (session["user_id"], *assignment),
    )
    assignments = cur.fetchall()
    con.close()
    return render_template(
        "student_coursework.html", announcements=announcements, assignments=assignments,
        error=request.args.get("error"), saved=request.args.get("saved") == "1",
    )


@app.route("/hod/announcements", methods=["GET", "POST"])
def hod_announcements():
    if session.get("role") != "hod":
        return redirect("/")
    con = get_db()
    cur = con.cursor()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        body = request.form.get("body", "").strip()
        audience = request.form.get("audience", "all").strip().lower()
        if not title or not body or audience not in {"students", "faculty", "all"}:
            con.close()
            return redirect("/hod/announcements?error=required")
        cur.execute(
            "INSERT INTO announcements (faculty_id, branch, year, section, title, body, created_at, audience) "
            "VALUES (?, 'ALL', 'ALL', 'ALL', ?, ?, ?, ?)",
            (session["user_id"], title, body, dbmod.now_ist().isoformat(timespec="seconds"), audience),
        )
        con.commit()
        con.close()
        return redirect("/hod/announcements?saved=1")

    cur.execute(
        "SELECT a.title, a.body, a.created_at, a.faculty_id, u.name, a.audience "
        "FROM announcements a LEFT JOIN users u ON lower(u.user_id)=lower(a.faculty_id) "
        "ORDER BY a.created_at DESC, a.id DESC"
    )
    announcements = cur.fetchall()
    con.close()
    return render_template(
        "hod_announcements.html", announcements=announcements,
        error=request.args.get("error"), saved=request.args.get("saved") == "1",
    )


@app.route("/student/schedule")
def student_schedule():
    if session.get("role") != "student":
        return redirect("/")
    con = get_db()
    cur = con.cursor()
    cur.execute("SELECT branch, year, section FROM users WHERE user_id=? AND role='student'", (session["user_id"],))
    assignment = cur.fetchone()
    if not assignment:
        con.close()
        return redirect("/")
    cur.execute(
        "SELECT subject, weekday, period, room FROM class_schedules "
        "WHERE upper(branch)=upper(?) AND year=? AND upper(section)=upper(?) "
        "ORDER BY weekday, period, subject",
        assignment,
    )
    schedules = cur.fetchall()
    con.close()
    weekday_names = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday"}
    return render_template(
        "faculty_schedule.html", schedules=schedules, assignment=assignment,
        weekdays=weekday_names, periods=PERIODS,
    )


@app.route("/student/coursework/<int:assignment_id>/submit", methods=["POST"])
def submit_assignment(assignment_id):
    if session.get("role") != "student":
        return redirect("/")
    upload = request.files.get("submission")
    if not upload or not upload.filename:
        return redirect("/student/coursework?error=file")
    original_filename = secure_filename(upload.filename)
    extension = os.path.splitext(original_filename)[1].lower()
    if not original_filename or extension not in {".pdf", ".doc", ".docx", ".txt", ".zip", ".png", ".jpg", ".jpeg"}:
        return redirect("/student/coursework?error=type")

    con = get_db()
    cur = con.cursor()
    cur.execute(
        "SELECT a.due_at FROM assignments a JOIN users u ON u.user_id=? AND u.role='student' "
        "WHERE a.id=? AND upper(a.branch)=upper(u.branch) AND a.year=u.year AND upper(a.section)=upper(u.section)",
        (session["user_id"], assignment_id),
    )
    assignment = cur.fetchone()
    if not assignment:
        con.close()
        return "Not found", 404
    if assignment[0] < dbmod.now_ist().strftime("%Y-%m-%dT%H:%M"):
        con.close()
        return redirect("/student/coursework?error=late")

    cur.execute(
        "SELECT stored_filename FROM assignment_submissions WHERE assignment_id=? AND student_id=?",
        (assignment_id, session["user_id"]),
    )
    previous = cur.fetchone()
    upload_dir = os.path.join(app.root_path, "instance", "submissions")
    os.makedirs(upload_dir, exist_ok=True)
    stored_filename = f"{uuid.uuid4().hex}{extension}"
    upload.save(os.path.join(upload_dir, stored_filename))
    cur.execute(
        "INSERT INTO assignment_submissions (assignment_id, student_id, original_filename, stored_filename, submitted_at) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT(assignment_id, student_id) DO UPDATE SET "
        "original_filename=excluded.original_filename, stored_filename=excluded.stored_filename, submitted_at=excluded.submitted_at",
        (assignment_id, session["user_id"], original_filename, stored_filename, dbmod.now_ist().isoformat(timespec="seconds")),
    )
    con.commit()
    con.close()
    if previous:
        old_path = os.path.join(upload_dir, previous[0])
        if os.path.isfile(old_path):
            os.remove(old_path)
    return redirect("/student/coursework?saved=1")


@app.route("/coursework-files/<stored_filename>")
def coursework_file(stored_filename):
    role = session.get("role")
    if role not in {"student", "faculty"}:
        return "Unauthorized", 401
    con = get_db()
    cur = con.cursor()
    cur.execute(
        "SELECT s.student_id, s.original_filename, a.faculty_id, a.branch, a.year, a.section "
        "FROM assignment_submissions s JOIN assignments a ON a.id=s.assignment_id "
        "WHERE s.stored_filename=?",
        (stored_filename,),
    )
    submission = cur.fetchone()
    authorized = False
    if submission and role == "student":
        authorized = submission[0] == session.get("user_id")
    elif submission and role == "faculty":
        cur.execute(
            "SELECT 1 FROM faculty_classes fc JOIN users u ON lower(u.user_id)=lower(fc.faculty_id) "
            "WHERE lower(fc.faculty_id)=lower(?) AND u.role='faculty' AND u.faculty_approved=1 "
            "AND upper(fc.branch)=upper(?) AND fc.year=? AND upper(fc.section)=upper(?)",
            (session.get("user_id"), *submission[3:6]),
        )
        authorized = cur.fetchone() is not None
    con.close()
    if not submission or not authorized:
        return "Not found", 404
    return send_from_directory(
        os.path.join(app.root_path, "instance", "submissions"), stored_filename,
        as_attachment=True, download_name=submission[1],
    )


@app.route("/hod/classes", methods=["GET", "POST"])
def hod_classes():
    if session.get("role") != "hod":
        return redirect("/")
    hod_department = get_hod_department(session.get("user_id", ""))
    con = get_db()
    cur = con.cursor()
    if request.method == "POST":
        action = request.form.get("action")
        if action == "delete":
            schedule_id = request.form.get("schedule_id", "")
            cur.execute("DELETE FROM class_schedules WHERE id=? AND (lower(branch)=lower(?) OR ? IS NULL)",
                        (schedule_id, hod_department, hod_department))
            con.commit()
            con.close()
            return redirect("/hod/classes")

        if action == "assign-class":
            faculty_id = request.form.get("faculty_id", "").strip()
            branch = request.form.get("branch", "").strip().upper()
            year = request.form.get("year", "").strip()
            section = request.form.get("section", "").strip().upper()
            cur.execute(
                "SELECT branch FROM users WHERE lower(user_id)=lower(?) AND role='faculty' AND faculty_approved=1",
                (faculty_id,),
            )
            faculty = cur.fetchone()
            valid = (
                faculty and branch in {item[0] for item in ALL_BRANCHES}
                and year in {"1", "2", "3", "4"} and section in {"A", "B", "C", "D"}
                and faculty[0] and faculty[0].upper() == branch
                and (not hod_department or branch.lower() == hod_department.lower())
            )
            if not valid:
                con.close()
                return redirect("/hod/classes?error=invalid")
            cur.execute(
                "INSERT OR IGNORE INTO faculty_classes (faculty_id, branch, year, section) VALUES (?, ?, ?, ?)",
                (faculty_id, branch, year, section),
            )
            con.commit()
            con.close()
            return redirect("/hod/classes?saved=assigned")

        if action == "remove-class":
            try:
                class_id = int(request.form.get("class_id", ""))
            except ValueError:
                class_id = -1
            cur.execute("SELECT faculty_id, branch, year, section FROM faculty_classes WHERE id=?", (class_id,))
            class_assignment = cur.fetchone()
            if class_assignment and (not hod_department or class_assignment[1].lower() == hod_department.lower()):
                cur.execute(
                    "DELETE FROM class_schedules WHERE lower(faculty_id)=lower(?) AND upper(branch)=upper(?) AND year=? AND upper(section)=upper(?)",
                    class_assignment,
                )
                cur.execute("DELETE FROM faculty_classes WHERE id=?", (class_id,))
                con.commit()
            con.close()
            return redirect("/hod/classes")

        try:
            class_id = int(request.form.get("class_assignment_id", ""))
        except ValueError:
            class_id = -1
        subject = request.form.get("subject", "").strip()
        room = request.form.get("room", "").strip()
        try:
            weekday = int(request.form.get("weekday", ""))
            period = int(request.form.get("period", ""))
        except ValueError:
            weekday, period = -1, -1
        cur.execute(
            "SELECT fc.faculty_id, fc.branch, fc.year, fc.section FROM faculty_classes fc "
            "JOIN users u ON lower(u.user_id)=lower(fc.faculty_id) "
            "WHERE fc.id=? AND u.role='faculty' AND u.faculty_approved=1",
            (class_id,),
        )
        faculty_class = cur.fetchone()
        if (not faculty_class or (hod_department and faculty_class[1].lower() != hod_department.lower())
                or not subject or not room or weekday not in range(6) or period not in PERIODS):
            con.close()
            return redirect("/hod/classes?error=invalid")
        cur.execute(
            "INSERT INTO class_schedules (branch, year, section, subject, weekday, period, room, faculty_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (faculty_class[1], faculty_class[2], faculty_class[3], subject, weekday, period, room, faculty_class[0]),
        )
        con.commit()
        con.close()
        return redirect("/hod/classes?saved=1")

    faculty_sql = "SELECT user_id, name, branch, year, section FROM users WHERE role='faculty' AND faculty_approved=1"
    faculty_params = []
    if hod_department:
        faculty_sql += " AND lower(branch)=lower(?)"
        faculty_params.append(hod_department)
    faculty_sql += " ORDER BY lower(branch), year, section, lower(name)"
    cur.execute(faculty_sql, faculty_params)
    faculty_members = cur.fetchall()
    assignment_sql = (
        "SELECT fc.id, fc.faculty_id, u.name, fc.branch, fc.year, fc.section "
        "FROM faculty_classes fc JOIN users u ON lower(u.user_id)=lower(fc.faculty_id) "
        "WHERE u.role='faculty' AND u.faculty_approved=1"
    )
    assignment_params = []
    if hod_department:
        assignment_sql += " AND lower(fc.branch)=lower(?)"
        assignment_params.append(hod_department)
    assignment_sql += " ORDER BY lower(fc.branch), fc.year, upper(fc.section), lower(u.name)"
    cur.execute(assignment_sql, assignment_params)
    class_assignments = cur.fetchall()
    schedule_sql = (
        "SELECT s.id, s.branch, s.year, s.section, s.subject, s.weekday, s.period, s.room, u.name "
        "FROM class_schedules s LEFT JOIN users u ON lower(u.user_id)=lower(s.faculty_id)"
    )
    schedule_params = []
    if hod_department:
        schedule_sql += " WHERE lower(s.branch)=lower(?)"
        schedule_params.append(hod_department)
    schedule_sql += " ORDER BY s.branch, s.year, s.section, s.weekday, s.period"
    cur.execute(schedule_sql, schedule_params)
    schedules = cur.fetchall()
    con.close()
    weekday_names = {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday"}
    return render_template(
        "hod_classes.html", faculty_members=faculty_members, class_assignments=class_assignments,
        schedules=schedules, branches=ALL_BRANCHES, periods=PERIODS, weekdays=weekday_names,
        error=request.args.get("error"), saved=request.args.get("saved"),
    )


@app.route("/student/signup", methods=["GET", "POST"])
def student_signup():
    import os, base64
    CLEAN_FACES_DIR = FACE_DATASET_DIR
    os.makedirs(CLEAN_FACES_DIR, exist_ok=True)

    if request.method == "POST":
        reg_no = request.form.get("user_id")
        name = request.form.get("name")
        dob = request.form.get("dob")
        year = request.form.get("year")
        section = request.form.get("section")
        branch = request.form.get("branch")
        password = request.form.get("password") or "123"
        images_b64 = [image.strip() for image in request.form.getlist("images[]") if image.strip()]

        if not images_b64:
            return render_template(
                "student_signup.html",
                error="Capture at least one photo before submitting.",
                preset_id=reg_no,
            )

        con = get_db()
        cur = con.cursor()
        # Ensure columns exist (backwards compatibility)
        cur.execute("PRAGMA table_info(users)")
        cols = [c[1] for c in cur.fetchall()]
        if "name" not in cols:
            cur.execute("ALTER TABLE users ADD COLUMN name TEXT")
        if "year" not in cols:
            cur.execute("ALTER TABLE users ADD COLUMN year TEXT")
        if "section" not in cols:
            cur.execute("ALTER TABLE users ADD COLUMN section TEXT")
        if "branch" not in cols:
            cur.execute("ALTER TABLE users ADD COLUMN branch TEXT")

        cur.execute("SELECT 1 FROM users WHERE lower(user_id)=lower(?)", (reg_no,))
        if cur.fetchone():
            con.close()
            return render_template("student_signup.html", error="User already exists. Please sign in.", preset_id=reg_no)

        import cv2, numpy as np, pickle, face_recognition
        face_is_duplicate = False
        duplicate_id = None
        try:
            with open(ENCODINGS_PATH, "rb") as f:
                data_enc = pickle.load(f)
            known_encs = np.array(data_enc["encodings"])
            known_names = np.array(data_enc["names"])
        except Exception:
            known_encs, known_names = [], []

        if len(known_encs) > 0 and len(images_b64) > 0:
            b64img = images_b64[0]
            try:
                header, data = b64img.split(',', 1) if ',' in b64img else ('', b64img)
                img_bytes = base64.b64decode(data)
                nparr = np.frombuffer(img_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is not None:
                    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    boxes = face_recognition.face_locations(rgb, model="hog")
                    encs = face_recognition.face_encodings(rgb, boxes)
                    if encs:
                        distances = face_recognition.face_distance(known_encs, encs[0])
                        if len(distances) > 0:
                            best_idx = np.argmin(distances)
                            if distances[best_idx] < 0.45:
                                matched_id = known_names[best_idx]
                                if matched_id.lower() != reg_no.lower():
                                    face_is_duplicate = True
                                    duplicate_id = matched_id
            except Exception as e:
                print("Face val error:", e)

        if face_is_duplicate:
            con.close()
            return render_template("student_signup.html", error=f"Face already registered under user {duplicate_id}. Multiple accounts per face are not allowed.", preset_id=reg_no)

        cur.execute("INSERT INTO users (user_id, password, role, dob, name, year, section, branch) VALUES (?, ?, 'student', ?, ?, ?, ?, ?)",
                    (reg_no, password, dob, name, year, section, branch))
        con.commit()
        con.close()

        # Save up to 5 images and dynamically encode them
        save_dir = os.path.join(CLEAN_FACES_DIR, reg_no)
        os.makedirs(save_dir, exist_ok=True)
        
        new_encodings = []
        new_names = []
        
        for idx, b64img in enumerate(images_b64[:5]):
            try:
                header, data = b64img.split(',', 1) if ',' in b64img else ('', b64img)
                img_bytes = base64.b64decode(data)
                
                # Get encoding dynamically
                nparr = np.frombuffer(img_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is not None:
                    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    boxes = face_recognition.face_locations(rgb, model="hog")
                    encs = face_recognition.face_encodings(rgb, boxes)
                    if encs:
                        new_encodings.append(encs[0])
                        new_names.append(reg_no)
                
                with open(os.path.join(save_dir, f"img_{idx+1}.jpg"), "wb") as f:
                    f.write(img_bytes)
            except Exception as e:
                print("Error saving/encoding image:", e)

        # Update encodings.pickle immediately so next camera frame recognizes the new student
        if new_encodings:
            try:
                with open(ENCODINGS_PATH, "rb") as f:
                    data_enc = pickle.load(f)
            except Exception:
                data_enc = {"encodings": [], "names": []}
            
            data_enc["encodings"].extend(new_encodings)
            data_enc["names"].extend(new_names)
            with open(ENCODINGS_PATH, "wb") as f:
                pickle.dump(data_enc, f)

        database.init_today([reg_no])
        database.init_today_periods([reg_no])
        return redirect("/student/login?signup=student")

    return render_template("student_signup.html")

@app.route("/hod/add-student", methods=["GET", "POST"])
def add_student():
    if session.get("role") != "hod":
        return redirect("/")
    if request.method == "POST":
        user_id  = request.form.get("user_id", "").strip().upper()
        password = request.form.get("password") or "123"
        dob      = request.form.get("dob")
        branch   = request.form.get("branch", "").strip().upper()
        year     = request.form.get("year", "").strip()
        section  = request.form.get("section", "").strip().upper()

        import os
        CLEAN_FACES_DIR = FACE_DATASET_DIR
        if not os.path.exists(os.path.join(CLEAN_FACES_DIR, user_id)):
            return render_template("add_student.html",
                error=f"No image folder found for '{user_id}' in the backend dataset. "
                      "Please ensure the face images are physically added first.")

        con = get_db()
        cur = con.cursor()
        # Insert with all fields — branch is critical for HOD dept filter
        cur.execute(
            "INSERT OR IGNORE INTO users (user_id, password, role, dob, branch, year, section) "
            "VALUES (?, ?, 'student', ?, ?, ?, ?)",
            (user_id, password, dob, branch or None, year or None, section or None)
        )
        con.commit()
        con.close()
        database.init_today([user_id])
        database.init_today_periods([user_id])
        return redirect("/hod")
    return render_template("add_student.html")


# ---------- STUDENT PROFILE ----------
@app.route("/student/profile", methods=["GET", "POST"])
def student_profile():
    if session.get("role") != "student":
        return redirect("/")
    sid = session["user_id"]
    con = get_db()
    cur = con.cursor()

    if request.method == "POST":
        name = request.form.get("name")
        dob = request.form.get("dob")
        year = request.form.get("year")
        section = request.form.get("section")
        branch = request.form.get("branch")
        new_password = request.form.get("new_password")
        cur.execute("UPDATE users SET name=?, dob=?, year=?, section=?, branch=? WHERE user_id=?",
                    (name, dob, year, section, branch, sid))
        if new_password:
            cur.execute("UPDATE users SET password=? WHERE user_id=?", (new_password, sid))
        con.commit()
        con.close()
        return redirect("/student/profile?saved=1")

    cur.execute("SELECT user_id, name, dob, year, section, branch FROM users WHERE user_id=?", (sid,))
    user = cur.fetchone()
    con.close()
    saved = request.args.get("saved")
    return render_template("student_profile.html", user=user, saved=saved)


# ---------- HOD DELETE STUDENT ----------
@app.route("/hod/delete-student", methods=["POST"])
def delete_student():
    if session.get("role") != "hod":
        return redirect("/")
    student_id = request.form.get("student_id")
    con = get_db()
    cur = con.cursor()
    cur.execute("DELETE FROM users WHERE user_id=? AND role='student'", (student_id,))
    cur.execute("DELETE FROM attendance WHERE student_id=?", (student_id,))
    cur.execute("DELETE FROM period_attendance WHERE student_id=?", (student_id,))
    con.commit()
    con.close()
    return redirect("/hod")

@app.route("/api/student-images/<user_id>")
def api_student_images(user_id):
    if session.get("role") != "hod":
        return jsonify({"error": "unauthorized"}), 401
    import os
    CLEAN_FACES_DIR = FACE_DATASET_DIR
    folder = os.path.join(CLEAN_FACES_DIR, user_id)
    images = []
    if os.path.exists(folder):
        images = [f"/dataset/images/{user_id}/{img}" for img in os.listdir(folder) if img.lower().endswith(('.png', '.jpg', '.jpeg'))]
    return jsonify({"images": images})

@app.route("/dataset/images/<user_id>/<filename>")
def serve_student_image(user_id, filename):
    if session.get("role") != "hod":
        return "Unauthorized", 401
    import os
    from flask import send_from_directory
    CLEAN_FACES_DIR = FACE_DATASET_DIR
    folder = os.path.join(CLEAN_FACES_DIR, user_id)
    return send_from_directory(folder, filename)


# ---------- TOGGLE ATTENDANCE ----------
@app.route("/api/toggle-attendance", methods=["POST"])
def api_toggle_attendance():
    if session.get("role") != "hod":
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json()
    student_id = data.get("student_id")
    date_str = data.get("date")
    period = data.get("period")
    new_status = data.get("status", "present")  # 'present', 'absent'
    time_now = dbmod.now_ist().strftime("%H:%M:%S")
    status_map = {'present': 1.0, 'absent': 0.0}
    value = status_map.get(new_status, 0.0)
    con = get_db()
    cur = con.cursor()
    # Update period_attendance
    if period:
        cur.execute("UPDATE period_attendance SET status=?, value=?, first_seen_time=? WHERE student_id=? AND date=? AND period=?",
                    (new_status, value, time_now if new_status != 'absent' else None, student_id, date_str, period))
    # Also update legacy table
    legacy_present = 1 if new_status == 'present' else 0
    cur.execute("UPDATE attendance SET present=?, first_seen_time=? WHERE student_id=? AND date=?",
                (legacy_present, time_now if legacy_present else None, student_id, date_str))
    con.commit()
    con.close()
    return jsonify({"ok": True, "status": new_status, "value": value})


# ---------- EXPORT EXCEL ----------
@app.route("/hod/export-excel")
def export_excel():
    if session.get("role") != "hod":
        return redirect("/")
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    except ImportError:
        return "openpyxl not installed. Run: pip install openpyxl", 500

    time_filter = request.args.get("filter", "all")
    year_filter = request.args.get("year")
    branch_filter = request.args.get("branch")
    section_filter = request.args.get("section")
    hod_dept = get_hod_department(session.get("user_id", ""))

    con = get_db()
    cur = con.cursor()
    student_query = "SELECT pa.student_id, pa.date, pa.period, pa.status, pa.value, pa.first_seen_time FROM period_attendance pa LEFT JOIN users u ON u.user_id = pa.student_id"
    student_where = []
    student_params = []
    if hod_dept:
        student_where.append("(lower(u.branch)=lower(?) OR (u.branch IS NULL AND lower(pa.student_id) LIKE '%' || lower(?) || '%'))")
        student_params.extend([hod_dept, hod_dept])
    if time_filter != "all":
        days = {"today": 0, "7days": 7, "15days": 15, "30days": 30}.get(time_filter, 7)
        start_date = (dbmod.now_ist() - timedelta(days=days)).strftime("%Y-%m-%d")
        student_where.append("pa.date >= ?")
        student_params.append(start_date)
    if year_filter:
        student_where.append("(u.year = ? OR (CASE WHEN substr(pa.student_id,1,2) IN ('21','22') THEN '4' WHEN substr(pa.student_id,1,2) = '23' THEN '3' WHEN substr(pa.student_id,1,2) = '24' THEN '2' WHEN substr(pa.student_id,1,2) = '25' THEN '1' ELSE NULL END) = ?)")
        student_params.extend([year_filter, year_filter])
    if branch_filter:
        student_where.append("(lower(u.branch) = lower(?) OR lower(pa.student_id) LIKE '%' || lower(?) || '%')")
        student_params.extend([branch_filter, branch_filter])
    if section_filter:
        student_where.append("lower(u.section) = lower(?)")
        student_params.append(section_filter)
    if student_where:
        student_query += " WHERE " + " AND ".join(student_where)
    student_query += " ORDER BY pa.date DESC, pa.student_id ASC, pa.period ASC"
    cur.execute(student_query, student_params)
    attendance_rows = cur.fetchall()

    faculty_query = "SELECT user_id, name, branch, year, section FROM users WHERE role='faculty' AND faculty_approved=1"
    faculty_where = []
    faculty_params = []
    if hod_dept:
        faculty_where.append("lower(branch)=lower(?)")
        faculty_params.append(hod_dept)
    if branch_filter:
        faculty_where.append("lower(branch)=lower(?)")
        faculty_params.append(branch_filter)
    if year_filter:
        faculty_where.append("year=?")
        faculty_params.append(year_filter)
    if section_filter:
        faculty_where.append("lower(section)=lower(?)")
        faculty_params.append(section_filter)
    if faculty_where:
        faculty_query += " AND " + " AND ".join(faculty_where)
    faculty_query += " ORDER BY branch, year, section, user_id"
    cur.execute(faculty_query, faculty_params)
    faculty_rows = cur.fetchall()
    con.close()

    wb = Workbook()
    student_sheet = wb.active
    student_sheet.title = "Students"
    faculty_sheet = wb.create_sheet("Faculty")

    header_font = Font(bold=True, color="FFFFFF", size=12)
    header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
    thin_border = Border(
        left=Side(style='thin'), right=Side(style='thin'),
        top=Side(style='thin'), bottom=Side(style='thin')
    )
    present_fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")
    absent_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")

    def style_sheet_header(sheet, headers):
        for col, header in enumerate(headers, 1):
            cell = sheet.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')
            cell.border = thin_border
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions

    student_headers = ["Student ID", "Date", "Period", "Status", "Value", "Time In"]
    style_sheet_header(student_sheet, student_headers)
    for row_index, (student_id, date_value, period, status, value, time_in) in enumerate(attendance_rows, 2):
        student_sheet.cell(row=row_index, column=1, value=student_id).border = thin_border
        student_sheet.cell(row=row_index, column=2, value=date_value).border = thin_border
        student_sheet.cell(row=row_index, column=3, value=f"P{period}").border = thin_border
        status_cell = student_sheet.cell(row=row_index, column=4, value=status.capitalize())
        status_cell.border = thin_border
        status_cell.fill = present_fill if status == "present" else absent_fill
        status_cell.alignment = Alignment(horizontal='center')
        student_sheet.cell(row=row_index, column=5, value=value).border = thin_border
        student_sheet.cell(row=row_index, column=6, value=time_in or "--").border = thin_border
    for col in range(1, 7):
        student_sheet.column_dimensions[chr(64 + col)].width = 18

    faculty_headers = ["Faculty ID", "Name", "Branch", "Year", "Section", "Approval"]
    style_sheet_header(faculty_sheet, faculty_headers)
    for row_index, (faculty_id, name, branch, year, section) in enumerate(faculty_rows, 2):
        values = [faculty_id, name or "", branch or "", year or "", section or "", "Approved"]
        for col, value in enumerate(values, 1):
            cell = faculty_sheet.cell(row=row_index, column=col, value=value)
            cell.border = thin_border
            if col in (4, 5, 6):
                cell.alignment = Alignment(horizontal='center')
    for col, width in enumerate((18, 26, 16, 12, 12, 16), 1):
        faculty_sheet.column_dimensions[chr(64 + col)].width = width

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"attendance_and_faculty_report_{dbmod.now_ist().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(buf, download_name=fname, as_attachment=True,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ---------- HOD STATS API ----------
@app.route("/api/hod-stats")
def api_hod_stats():
    if session.get("role") != "hod":
        return jsonify({"error": "unauthorized"}), 401
    con = get_db()
    cur = con.cursor()
    # Total students
    cur.execute("SELECT COUNT(*) FROM users WHERE role='student'")
    total_students = cur.fetchone()[0]
    # Today's period attendance
    today_str = dbmod.now_ist().strftime("%Y-%m-%d")
    cur.execute("SELECT COUNT(*) FROM period_attendance WHERE date=? AND status='present'", (today_str,))
    present_today = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM period_attendance WHERE date=?", (today_str,))
    total_today = cur.fetchone()[0]
    # Last 7 days trend
    trend = []
    for i in range(6, -1, -1):
        d = (dbmod.now_ist() - timedelta(days=i)).strftime("%Y-%m-%d")
        cur.execute("SELECT COUNT(*) FROM period_attendance WHERE date=? AND status='present'", (d,))
        p = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM period_attendance WHERE date=?", (d,))
        t = cur.fetchone()[0]
        trend.append({"date": d, "present": p, "total": t})
    con.close()
    return jsonify({
        "total_students": total_students,
        "present_today": present_today,
        "total_today": total_today,
        "trend": trend
    })
if __name__ == '__main__':
    # Listen on all network interfaces (0.0.0.0) so mobiles and other laptops on the same Wi-Fi can access the portal via this computer's IP address.
    app.run(host="0.0.0.0", port=5000, debug=True)
