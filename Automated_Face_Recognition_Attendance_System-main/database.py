import sqlite3
from datetime import datetime, date, time, timedelta
import urllib.request
import re

DB_PATH = "attendance.db"

# ---------------- PERIOD CONFIGURATION ----------------
# 6 periods: (start_hour, start_min, end_hour, end_min)
PERIODS = {
    1: (7, 30, 8, 20),
    2: (8, 20, 9, 10),
    3: (9, 10, 10, 0),
    4: (10, 30, 11, 20),
    5: (11, 20, 12, 10),
    6: (12, 10, 13, 0),
}

# Thresholds removed as per user request: any capture during period is purely Present (1.0).

def now_ist():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Kolkata"))
    except Exception:
        # Fallback to system local time if tzdata not available
        return datetime.now()

# ---------------- INITIALIZE DATABASE ----------------
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT,
        date TEXT,
        first_seen_time TEXT,
        present INTEGER,
        class TEXT,
        UNIQUE(student_id, date)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        password TEXT,
        role TEXT,
        dob TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS holidays (
        date TEXT PRIMARY KEY,
        name TEXT
    )
    """)

    # Period-wise attendance table (new)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS period_attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT,
        date TEXT,
        period INTEGER,
        status TEXT DEFAULT 'absent',
        value REAL DEFAULT 0.0,
        first_seen_time TEXT,
        UNIQUE(student_id, date, period)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cctv_attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL,
        date TEXT NOT NULL,
        period INTEGER NOT NULL,
        room TEXT NOT NULL,
        first_seen_time TEXT NOT NULL,
        UNIQUE(student_id, date, period, room)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cctv_completed_periods (
        date TEXT NOT NULL,
        period INTEGER NOT NULL,
        room TEXT NOT NULL,
        completed_at TEXT NOT NULL,
        PRIMARY KEY(date, period, room)
    )
    """)

    cursor.execute("PRAGMA table_info(cctv_attendance)")
    if 'room' not in [column[1] for column in cursor.fetchall()]:
        cursor.execute("ALTER TABLE cctv_attendance RENAME TO cctv_attendance_legacy")
        cursor.execute("""
        CREATE TABLE cctv_attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            date TEXT NOT NULL,
            period INTEGER NOT NULL,
            room TEXT NOT NULL,
            first_seen_time TEXT NOT NULL,
            UNIQUE(student_id, date, period, room)
        )
        """)
        cursor.execute(
            "INSERT INTO cctv_attendance (student_id, date, period, room, first_seen_time) "
            "SELECT student_id, date, period, '', first_seen_time FROM cctv_attendance_legacy"
        )
        cursor.execute("DROP TABLE cctv_attendance_legacy")

    cursor.execute("PRAGMA table_info(cctv_completed_periods)")
    if 'room' not in [column[1] for column in cursor.fetchall()]:
        cursor.execute("ALTER TABLE cctv_completed_periods RENAME TO cctv_completed_periods_legacy")
        cursor.execute("""
        CREATE TABLE cctv_completed_periods (
            date TEXT NOT NULL,
            period INTEGER NOT NULL,
            room TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            PRIMARY KEY(date, period, room)
        )
        """)
        cursor.execute(
            "INSERT INTO cctv_completed_periods (date, period, room, completed_at) "
            "SELECT date, period, '', completed_at FROM cctv_completed_periods_legacy"
        )
        cursor.execute("DROP TABLE cctv_completed_periods_legacy")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS faculty_attendance_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        class_id INTEGER NOT NULL,
        student_id TEXT NOT NULL,
        date TEXT NOT NULL,
        period INTEGER NOT NULL,
        status TEXT NOT NULL,
        submitted_at TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance_review_flags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id TEXT NOT NULL,
        date TEXT NOT NULL,
        period INTEGER NOT NULL,
        flag_type TEXT NOT NULL,
        details TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(student_id, date, period, flag_type)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS class_schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        branch TEXT NOT NULL,
        year TEXT NOT NULL,
        section TEXT NOT NULL,
        subject TEXT NOT NULL,
        weekday INTEGER NOT NULL,
        period INTEGER NOT NULL,
        room TEXT NOT NULL,
        faculty_id TEXT NOT NULL,
        UNIQUE(branch, year, section, subject, weekday, period)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        branch TEXT NOT NULL,
        year TEXT NOT NULL,
        section TEXT NOT NULL,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL,
        audience TEXT NOT NULL DEFAULT 'all'
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS assignments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        branch TEXT NOT NULL,
        year TEXT NOT NULL,
        section TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        due_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS assignment_submissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        assignment_id INTEGER NOT NULL,
        student_id TEXT NOT NULL,
        original_filename TEXT NOT NULL,
        stored_filename TEXT NOT NULL,
        submitted_at TEXT NOT NULL,
        UNIQUE(assignment_id, student_id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS leave_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        requester_id TEXT NOT NULL,
        requester_role TEXT NOT NULL CHECK(requester_role IN ('student', 'faculty')),
        branch TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        reason TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
        decision_note TEXT,
        created_at TEXT NOT NULL,
        reviewed_by TEXT,
        reviewed_at TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS faculty_attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        branch TEXT NOT NULL,
        attendance_date TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('present', 'absent')),
        note TEXT,
        marked_by TEXT NOT NULL,
        marked_at TEXT NOT NULL,
        UNIQUE(faculty_id, attendance_date)
    )
    """)

    cursor.execute("CREATE INDEX IF NOT EXISTS idx_class_schedules_class ON class_schedules(branch, year, section)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_announcements_class ON announcements(branch, year, section, created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_assignments_class ON assignments(branch, year, section, due_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_leave_requests_branch_status ON leave_requests(branch, status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_faculty_attendance_date ON faculty_attendance(branch, attendance_date)")

    # Check and add missing columns for backwards compatibility
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'dob' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN dob TEXT")
    if 'branch' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN branch TEXT")
    if 'name' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN name TEXT")
    if 'year' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN year TEXT")
    if 'section' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN section TEXT")
    if 'faculty_approved' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN faculty_approved INTEGER NOT NULL DEFAULT 0")
    if 'faculty_status' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN faculty_status TEXT")
    cursor.execute(
        "UPDATE users SET faculty_status=CASE WHEN faculty_approved=1 THEN 'approved' ELSE 'pending' END "
        "WHERE role='faculty' AND (faculty_status IS NULL OR faculty_status='')"
    )
    if 'email' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
    if 'phone' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN phone TEXT")

    cursor.execute("PRAGMA table_info(announcements)")
    announcement_columns = [column[1] for column in cursor.fetchall()]
    if 'audience' not in announcement_columns:
        cursor.execute("ALTER TABLE announcements ADD COLUMN audience TEXT NOT NULL DEFAULT 'all'")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS faculty_classes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        faculty_id TEXT NOT NULL,
        branch TEXT NOT NULL,
        year TEXT NOT NULL,
        section TEXT NOT NULL,
        UNIQUE(faculty_id, branch, year, section)
    )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_faculty_classes_owner ON faculty_classes(faculty_id)")
    cursor.execute("""
    INSERT OR IGNORE INTO faculty_classes (faculty_id, branch, year, section)
    SELECT user_id, branch, year, section FROM users
    WHERE role='faculty' AND branch IS NOT NULL AND year IS NOT NULL AND section IS NOT NULL
    AND NOT EXISTS (SELECT 1 FROM faculty_classes fc WHERE lower(fc.faculty_id)=lower(users.user_id))
    """)

    # Seed only verified student accounts (hod accounts must be created via /hod/signup)
    users = [
        ('21CSE001', '123', 'student', '2003-05-15'),
        ('21CSE002', '123', 'student', '2003-05-16'),
        ('21CSE003', '123', 'student', '2003-05-17'),
        ('21CSE004', '123', 'student', '2003-05-18'),
        ('21CSE005', '123', 'student', '2003-05-19'),
        ('21CSE006', '123', 'student', '2003-05-20'),
        ('24CSE001', '123', 'student', '2005-08-10'),
    ]
    cursor.executemany("INSERT OR IGNORE INTO users (user_id, password, role, dob) VALUES (?, ?, ?, ?)", users)

    try:
        sync_holidays_google()
    except Exception:
        pass

    conn.commit()
    conn.close()

# ---------------- HOLIDAYS & WORKING DAY ----------------
def is_working_day(date_str: str) -> bool:
    dt = datetime.strptime(date_str, "%Y-%m-%d").date()
    if dt.weekday() == 6:
        return False
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM holidays WHERE date=?", (date_str,))
    row = cur.fetchone()
    conn.close()
    return row is None

def sync_holidays_google():
    year = now_ist().date().year
    url = "https://calendar.google.com/calendar/ical/en.indian%23holiday%40group.v.calendar.google.com/public/basic.ics"
    with urllib.request.urlopen(url, timeout=5) as resp:
        content = resp.read().decode("utf-8", errors="ignore")
    events = re.split(r"BEGIN:VEVENT", content)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    for ev in events:
        mdate = re.search(r"DTSTART;VALUE=DATE:(\d{8})", ev)
        msum = re.search(r"SUMMARY:(.+)", ev)
        if mdate and msum:
            ymd = mdate.group(1)
            y, m, d = ymd[0:4], ymd[4:6], ymd[6:8]
            if int(y) in (year, year+1):
                ds = f"{y}-{m}-{d}"
                name = msum.group(1).strip()
                cur.execute("INSERT OR IGNORE INTO holidays (date, name) VALUES (?, ?)", (ds, name))
    conn.commit()
    conn.close()

# ---------------- MARK ALL STUDENTS ABSENT FOR TODAY ----------------
def init_today(all_students):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    today = now_ist().strftime("%Y-%m-%d")

    for student in all_students:
        cursor.execute("""
        INSERT OR IGNORE INTO attendance (student_id, date, first_seen_time, present)
        VALUES (?, ?, NULL, 0)
        """, (student, today))

    conn.commit()
    conn.close()


# ---------------- MARK STUDENT PRESENT ----------------
def mark_present(student_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    today = now_ist().strftime("%Y-%m-%d")
    time_now = now_ist().strftime("%H:%M:%S")

    cursor.execute("""
    UPDATE attendance
    SET present = 1, first_seen_time = ?
    WHERE student_id = ? AND date = ?
    """, (time_now, student_id, today))

    conn.commit()
    conn.close()


# ================================================================
#  PERIOD-WISE ATTENDANCE SYSTEM
# ================================================================

def get_current_period(now_time=None):
    """Return current period number (1-6) or None if outside all periods."""
    t = now_time or now_ist().time()
    for pnum, (sh, sm, eh, em) in PERIODS.items():
        start = time(sh, sm)
        end = time(eh, em)
        if start <= t < end:
            return pnum
    return None


def get_period_status(period_num, capture_time_str):
    """
    Given a period number and a capture time string (HH:MM:SS or HH:MM),
    return (status, value):
      - ('present', 1.0)  always, as soon as they are captured in the period.
    """
    return ('present', 1.0)


def init_today_periods(all_students):
    """Insert 6 absent rows per student for today (one per period)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    today = now_ist().strftime("%Y-%m-%d")

    for student in all_students:
        for pnum in PERIODS:
            cursor.execute("""
            INSERT OR IGNORE INTO period_attendance
                (student_id, date, period, status, value, first_seen_time)
            VALUES (?, ?, ?, 'absent', 0.0, NULL)
            """, (student, today, pnum))

    conn.commit()
    conn.close()


def mark_period_present(student_id, period_num=None):
    """
    Mark a student's period attendance based on current time.
    Auto-detects the current period if period_num is None.
    Returns (period_num, status, value) or None if no active period.
    """
    now = now_ist()
    today = now.strftime("%Y-%m-%d")
    time_now = now.strftime("%H:%M:%S")

    if period_num is None:
        period_num = get_current_period(now.time())
    if period_num is None:
        return None

    status, value = get_period_status(period_num, time_now)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Only update if not already marked present (don't downgrade)
    cursor.execute("""
    SELECT value FROM period_attendance
    WHERE student_id=? AND date=? AND period=?
    """, (student_id, today, period_num))
    row = cursor.fetchone()

    if row is None:
        # Row doesn't exist yet — insert
        cursor.execute("""
        INSERT INTO period_attendance
            (student_id, date, period, status, value, first_seen_time)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (student_id, today, period_num, status, value, time_now))
    elif row[0] < value:
        # Only upgrade (don't downgrade from present to late)
        cursor.execute("""
        UPDATE period_attendance
        SET status=?, value=?, first_seen_time=?
        WHERE student_id=? AND date=? AND period=?
        """, (status, value, time_now, student_id, today, period_num))

    conn.commit()
    conn.close()
    return (period_num, status, value)


def record_cctv_presence(student_id, date_str, period_num, room, first_seen_time):
    """Store one recognized CCTV sighting per student and period."""
    if period_num not in PERIODS:
        raise ValueError("Invalid attendance period")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO cctv_attendance (student_id, date, period, room, first_seen_time) "
        "VALUES (?, ?, ?, ?, ?)",
        (student_id, date_str, period_num, room, first_seen_time),
    )
    inserted = cursor.rowcount == 1
    conn.commit()
    conn.close()
    return inserted


def get_scheduled_roster(room, date_str, period_num):
    """Return student IDs scheduled in a room for the date and period."""
    if period_num not in PERIODS:
        raise ValueError("Invalid attendance period")
    weekday = datetime.strptime(date_str, "%Y-%m-%d").weekday()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT DISTINCT u.user_id FROM class_schedules s "
        "JOIN users u ON upper(u.branch)=upper(s.branch) AND u.year=s.year "
        "AND upper(u.section)=upper(s.section) "
        "WHERE lower(s.room)=lower(?) AND s.weekday=? AND s.period=? AND u.role='student' "
        "ORDER BY lower(u.user_id)",
        (room, weekday, period_num),
    )
    roster = [row[0] for row in cursor.fetchall()]
    conn.close()
    return roster


def reconcile_cctv_period(date_str, period_num, room, roster_students):
    """Apply completed CCTV evidence to the supplied class roster."""
    if period_num not in PERIODS:
        raise ValueError("Invalid attendance period")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = now_ist().isoformat(timespec="seconds")
    cursor.execute(
        "INSERT INTO cctv_completed_periods (date, period, room, completed_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(date, period, room) DO UPDATE SET completed_at=excluded.completed_at",
        (date_str, period_num, room, now),
    )

    discrepancies = []
    for student_id in roster_students:
        cursor.execute(
            "SELECT first_seen_time FROM cctv_attendance "
            "WHERE student_id=? AND date=? AND period=? AND room=?",
            (student_id, date_str, period_num, room),
        )
        cctv_row = cursor.fetchone()
        status = "present" if cctv_row else "absent"
        value = 1.0 if cctv_row else 0.0
        first_seen_time = cctv_row[0] if cctv_row else None

        cursor.execute(
            "SELECT status FROM period_attendance WHERE student_id=? AND date=? AND period=?",
            (student_id, date_str, period_num),
        )
        current_row = cursor.fetchone()
        if current_row and current_row[0] != status:
            discrepancies.append(student_id)
        cursor.execute(
            "SELECT status FROM faculty_attendance_submissions "
            "WHERE student_id=? AND date=? AND period=? ORDER BY id DESC LIMIT 1",
            (student_id, date_str, period_num),
        )
        faculty_row = cursor.fetchone()
        if faculty_row and faculty_row[0] != status:
            cursor.execute(
                "INSERT OR IGNORE INTO attendance_review_flags "
                "(student_id, date, period, flag_type, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    student_id, date_str, period_num, "cctv_mismatch",
                    f"Faculty marked {faculty_row[0]}; verified CCTV marked {status}.", now,
                ),
            )

        cursor.execute(
            "INSERT INTO period_attendance (student_id, date, period, status, value, first_seen_time) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(student_id, date, period) DO UPDATE SET "
            "status=excluded.status, value=excluded.value, first_seen_time=excluded.first_seen_time",
            (student_id, date_str, period_num, status, value, first_seen_time),
        )

    conn.commit()
    conn.close()
    return discrepancies


# ================================================================
#  BACKFILL MISSING WORKING DAYS WITH ABSENT PERIOD RECORDS
# ================================================================

def backfill_student_periods(student_id):
    """
    Fill in absent period_attendance records for all past working days
    that are missing for this student. Uses the student's OWN earliest
    date so late-enrolled students are not penalised with pre-enrollment absents.
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Find the earliest date THIS student has in either table
    cur.execute("SELECT MIN(date) FROM period_attendance WHERE student_id=?", (student_id,))
    d1 = cur.fetchone()[0]
    cur.execute("SELECT MIN(date) FROM attendance WHERE student_id=?", (student_id,))
    d2 = cur.fetchone()[0]

    dates = [d for d in [d1, d2] if d]
    if not dates:
        conn.close()
        return

    start = datetime.strptime(min(dates), "%Y-%m-%d").date()
    end = now_ist().date()

    current = start
    while current <= end:
        ds = current.strftime("%Y-%m-%d")
        if is_working_day(ds):
            cur.execute(
                "SELECT COUNT(*) FROM period_attendance WHERE student_id=? AND date=?",
                (student_id, ds)
            )
            if cur.fetchone()[0] == 0:
                for pnum in PERIODS:
                    cur.execute("""
                        INSERT OR IGNORE INTO period_attendance
                            (student_id, date, period, status, value, first_seen_time)
                        VALUES (?, ?, ?, 'absent', 0.0, NULL)
                    """, (student_id, ds, pnum))
        current += timedelta(days=1)

    conn.commit()
    conn.close()


def backfill_all_students():
    """Backfill missing working days for every student in the users table."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE role='student'")
    student_ids = [r[0] for r in cur.fetchall()]
    conn.close()
    for sid in student_ids:
        backfill_student_periods(sid)
