# Automated Face Recognition Attendance System

**Authors**

D Nethrasree (Y22ACS442)  

A Akhil (Y22ACS402)

K Venkata Siva Naga Sai (Y22ACS472)

D Rama Lakshman (Y22ACS447)


**Implementation**

Face Recognition Engine, Flask Web Application, and Attendance Database implementation.


🔗 **GitHub Repo:** https://github.com/DiddiNethraSree/Automated_Face_Recognition_Attendance_System

🌐 **Live Web Dashboard:** [https://nethrasree19.pythonanywhere.com](https://nethrasree19.pythonanywhere.com)
### 🔑 Live Demo Test Credentials
You can test the live web application using the following credentials:
- **Student View:** ID: `21CSE001` | Password: `123`
- **HOD View:** ID: `cshod` | Password: `Becbapatla@1`
---

## Overview

The Automated Face Recognition Attendance System (AFRAS) is an AI-powered attendance management system designed to eliminate manual roll calls in academic institutions. The system uses CCTV cameras to automatically detect and recognize students' faces in real time, records attendance period-wise in a local database, and makes it accessible through a web dashboard for both Heads of Department (HODs) and students.

The platform also supports manual attendance correction, student self-registration with live webcam photo capture, and automated detection of working days.

This project was developed as a final-year B.Tech project at **Bapatla Engineering College**, Department of Computer Science and Engineering.

---

## Project Components

### 1. Face Recognition Engine
- Captures live video frames from a connected CCTV or webcam
- Detects faces using the HOG (Histogram of Oriented Gradients) model
- Matches detected faces against precomputed encodings stored in `encodings.pickle`
- Automatically marks attendance for the active class period upon recognition
- Dynamically updates encodings when new students register

### 2. Flask Web Application
- Provides a secure login system with role-based access for HODs and Students
- **HOD Dashboard:** view, filter, and manually edit student attendance records
- **Student Dashboard:** view personal attendance percentage and period-wise history
- Supports student self-registration with webcam-based photo capture
- Includes password recovery using Date of Birth verification
- Classifies students as Eligible (≥75%), Condonation (65–75%), or Detained (<65%)

### 3. Attendance Database
- Stores all student and HOD account information
- Records period-wise daily attendance for up to 6 periods per day
- Automatically initializes attendance records for each working day
- Detects and skips weekends and holidays (non-working days)
- Supports backfilling of missed attendance records for past working days

---

## System Architecture

The AFRAS system integrates multiple components including a CCTV Camera Feed, Face Detection and Recognition Engine, SQLite Attendance Database, Flask Web Server, HOD Dashboard, and Student Dashboard.

These components work together to automate attendance recording and deliver accurate period-wise attendance data to both HODs and students through a centralized web interface.

---

## Technologies Used

**Backend**
- Python
- Flask
- SQLite3

**Face Recognition**
- `face_recognition` library
- dlib
- OpenCV (cv2)

**Frontend**
- HTML5
- CSS3
- JavaScript
- Jinja2 Templates

**Image Processing**
- NumPy
- Pillow

**Deployment**
- PythonAnywhere (Cloud Hosting for Web Portal)
- Windows OS (For local CCTV Engine)
- Flask Development Server

---

## Key Features

- Real-time face detection and recognition from CCTV camera feed
- Period-wise attendance tracking (6 periods per day)
- Role-based access control for HODs and Students
- Student self-registration with live webcam photo capture
- Dynamic face encoding — new students recognized immediately after signup
- Automatic working day detection (weekends and holidays skipped)
- Manual attendance entry and correction by HOD
- Attendance eligibility classification (Eligible / Condonation / Detained)
- Multi-department support with HOD accounts auto-scoped to their department
- Password recovery using Date of Birth verification

---

## Installation and Setup

**1. Clone the repository**
```
git clone https://github.com/DiddiNethraSree/Automated_Face_Recognition_Attendance_System.git
cd Automated_Face_Recognition_Attendance_System
```

**2. Create and activate a virtual environment**
```
python -m venv venv
venv\Scripts\activate
```

**3. Install dependencies**
```
pip install -r requirements.txt
```

**4. Run the Flask web application**
```
python app.py
```

**5. Configure and run the CCTV attendance script (in a separate terminal)**

Create the room schedule under HOD → Class schedules, then set `CCTV_ROOM` to the exact room value used there. Set `CCTV_SOURCE` to the camera's RTSP stream URL. Keep camera credentials in a local environment variable; do not commit them.

In PowerShell, from the project folder:
```
$env:CCTV_SOURCE = "rtsp://<camera-host>/<stream-path>"
$env:CCTV_ROOM = "C-305"
.\venv\Scripts\python.exe cctv_attendance.py
```

The camera process records recognized students immediately. It marks other roster members absent only after it has received video from the start through the end of a scheduled period with no frame gap longer than 30 seconds. If the feed drops, the process stops, or it starts late, that period is not auto-corrected. Repeated faculty present submissions and faculty/CCTV differences appear in the HOD attendance-review section as signals for human review; they are not proof of proxy attendance.

The HOD dashboard's daily CCTV attendance audit lists each scheduled student as Seen, Not seen, or Not verified for the selected date and room. It displays recognition records only; CCTV footage is not stored or played in the portal.

**6. Open the web dashboard in a browser**
```
http://127.0.0.1:5000
```

> Note: To regenerate face encodings after adding new images manually, run `python encode_faces.py`

---

## User Roles

**HOD (Head of Department)**
- Register at `/hod/signup` with department selection
- View attendance records with filters by date, year, branch, and section
- Manually add or edit attendance for any student
- Delete student records
- View attendance eligibility categories

**Student**
- Register at `/student/signup` with webcam photo capture (up to 5 photos)
- View personal attendance percentage and period-wise history
- Update profile information and change password
- Recover forgotten password using Date of Birth

---

## Research Contribution

This project demonstrates how Computer Vision and Machine Learning can be applied to automate academic attendance management. By integrating face recognition with a web-based platform, the system removes the dependency on manual roll calls, reduces errors, and provides real-time attendance visibility to both faculty and students.

---

## Future Work

- Migration from SQLite to a cloud-based database such as PostgreSQL or Firebase
- Email and SMS alerts for students with low attendance
- Development of a Flutter-based mobile application for students
- Upgrade face recognition model from HOG to a CNN-based deep learning approach
- Analytics dashboard with charts and export functionality to Excel and PDF
- Deployment on a cloud server such as AWS or Render
- Support for multiple simultaneous CCTV cameras

---

## Department of Computer Science and Engineering
**Bapatla Engineering College**
Bapatla, Andhra Pradesh, India

---

## GitHub Repository

The source code for the Automated Face Recognition Attendance System is available at:

🔗 https://github.com/DiddiNethraSree/Automated_Face_Recognition_Attendance_System
