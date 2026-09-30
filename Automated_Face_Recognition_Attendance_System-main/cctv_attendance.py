import cv2
import face_recognition
import pickle
import numpy as np
import os
from datetime import datetime, time
from database import (
    init_today, mark_present, is_working_day, init_today_periods,
    record_cctv_presence, get_scheduled_roster, reconcile_cctv_period,
    mark_period_present, get_current_period, PERIODS
)

# ---------------- CONFIG ----------------
THRESHOLD = 0.45
MAX_CAMERA_GAP_SECONDS = 30
ENCODINGS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "encodings.pickle")
CCTV_SOURCE = os.environ.get("CCTV_SOURCE", "0")
CCTV_ROOM = os.environ.get("CCTV_ROOM", "").strip()
if CCTV_SOURCE.isdigit():
    CCTV_SOURCE = int(CCTV_SOURCE)

# ---------------- LOAD ENCODINGS ----------------
if not os.path.isfile(ENCODINGS_PATH):
    raise SystemExit("Face encodings are missing. Add clear student face photos, then run: python encode_faces.py")

with open(ENCODINGS_PATH, "rb") as f:
    data = pickle.load(f)

known_encodings = np.array(data["encodings"])
known_names = np.array(data["names"])

all_students = set(known_names)
present_students = set()          # For legacy daily attendance
present_period_set = set()
period_rosters = {}

# Build attendance windows from PERIODS config
def in_attendance_window(now=None):
    now_dt = now or datetime.now().time()
    try:
        from zoneinfo import ZoneInfo
        now_dt = now or datetime.now(ZoneInfo("Asia/Kolkata")).time()
    except Exception:
        pass
    for pnum, (sh, sm, eh, em) in PERIODS.items():
        if time(sh, sm) <= now_dt < time(eh, em):
            return True
    return False

# Initialize today's attendance only on working days
try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = None

today_str = (datetime.now(IST) if IST else datetime.now()).strftime("%Y-%m-%d")
working_today = is_working_day(today_str)
if working_today:
    init_today(all_students)
    init_today_periods(all_students)

if not CCTV_ROOM:
    raise SystemExit("Set CCTV_ROOM to a room used in the HOD class schedule before starting attendance.")

# ---------------- START CAMERA ----------------
cap = cv2.VideoCapture(CCTV_SOURCE)
if not cap.isOpened():
    raise SystemExit("Could not open CCTV_SOURCE. Check the camera URL and network connection.")
camera_started_at = datetime.now(IST) if IST else datetime.now()
last_frame_at = camera_started_at
completed_periods = set()
period_coverage_gaps = set()
print("Press 'Q' to stop")
print(f"CCTV room: {CCTV_ROOM}")
print(f"📋 Period Schedule: {', '.join(f'P{k}: {v[0]:02d}:{v[1]:02d}-{v[2]:02d}:{v[3]:02d}' for k, v in PERIODS.items())}")

while True:
    ret, frame = cap.read()
    if not ret:
        break
    frame_received_at = datetime.now(IST) if IST else datetime.now()
    if (frame_received_at - last_frame_at).total_seconds() > MAX_CAMERA_GAP_SECONDS:
        for period_num, (start_hour, start_minute, end_hour, end_minute) in PERIODS.items():
            period_start = camera_started_at.replace(
                hour=start_hour, minute=start_minute, second=0, microsecond=0
            )
            period_end = camera_started_at.replace(
                hour=end_hour, minute=end_minute, second=0, microsecond=0
            )
            if last_frame_at < period_end and frame_received_at > period_start:
                period_coverage_gaps.add(period_num)
    last_frame_at = frame_received_at

    # Resize for speed
    small = cv2.resize(frame, (0, 0), fx=0.5, fy=0.5)
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

    boxes = face_recognition.face_locations(rgb, model="hog")
    encodings = face_recognition.face_encodings(rgb, boxes)
    now_dt = datetime.now(IST) if IST else datetime.now()

    for (top, right, bottom, left), encoding in zip(boxes, encodings):
        distances = face_recognition.face_distance(known_encodings, encoding)
        best_idx = np.argmin(distances)
        best_dist = distances[best_idx]

        # Scale back box
        top, right, bottom, left = top*2, right*2, bottom*2, left*2

        if best_dist < THRESHOLD and in_attendance_window() and working_today:
            student_id = known_names[best_idx]
            accuracy = round((1 - best_dist) * 100, 2)
            current_period = get_current_period(now_dt.time())
            if current_period is not None:
                if current_period not in period_rosters:
                    period_rosters[current_period] = set(
                        get_scheduled_roster(CCTV_ROOM, today_str, current_period)
                    )
                if student_id in period_rosters[current_period]:
                    if student_id not in present_students:
                        mark_present(student_id)
                        present_students.add(student_id)
                    combo = (student_id, current_period)
                    if combo not in present_period_set:
                        inserted = record_cctv_presence(
                            student_id, today_str, current_period, CCTV_ROOM,
                            now_dt.strftime("%H:%M:%S"),
                        )
                        mark_period_present(student_id, current_period)
                        present_period_set.add(combo)
                        if inserted:
                            print(f"  ✅ CCTV sighting: {student_id} → P{current_period}")
                    label = f"{student_id} ({accuracy}%)"
                    color = (0, 255, 0)
                else:
                    label = f"{student_id} (not on room roster)"
                    color = (0, 165, 255)
            else:
                label = f"{student_id} (outside period)"
                color = (0, 165, 255)
        else:
            label = "UNKNOWN"
            color = (0, 0, 255)

        # Draw box & label
        cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
        cv2.rectangle(frame, (left, top - 30), (right, top), color, -1)
        cv2.putText(
            frame, label,
            (left + 5, top - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7, (255, 255, 255), 2
        )

    for period_num, (start_hour, start_minute, end_hour, end_minute) in PERIODS.items():
        period_start = camera_started_at.replace(
            hour=start_hour, minute=start_minute, second=0, microsecond=0
        )
        period_end = camera_started_at.replace(
            hour=end_hour, minute=end_minute, second=0, microsecond=0
        )
        if period_num in completed_periods or now_dt < period_end or not working_today:
            continue
        completed_periods.add(period_num)
        if camera_started_at > period_start or period_num in period_coverage_gaps:
            print(f"  ⚠ P{period_num} not reconciled: camera did not provide verified full-period coverage")
            continue
        roster = get_scheduled_roster(CCTV_ROOM, today_str, period_num)
        if not roster:
            print(f"  ⚠ P{period_num} not reconciled: no class roster scheduled in {CCTV_ROOM}")
            continue
        discrepancies = reconcile_cctv_period(today_str, period_num, CCTV_ROOM, roster)
        print(
            f"  📋 P{period_num} reconciled for {len(roster)} students; "
            f"{len(discrepancies)} faculty/CCTV differences"
        )

    cv2.imshow("CCTV Attendance", frame)

    if cv2.waitKey(1) & 0xFF in (ord('q'), ord('Q')):
        print("✔ Attendance session ended by user")
        break

# ---------------- CLEAN EXIT ----------------
cap.release()
cv2.destroyAllWindows()

# ---------------- FINAL SUMMARY ----------------
print("\n📊 ATTENDANCE SUMMARY (PRESENT ONLY)")
print(f"Present: {len(present_students)}")
for s in sorted(present_students):
    print(" ✔", s)

print("\n📋 CCTV evidence is reconciled only for periods covered from start to end.")

