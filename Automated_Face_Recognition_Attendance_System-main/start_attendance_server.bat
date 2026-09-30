@echo off
title Face Attendance System Server
echo Starting Face Attendance System Server...
echo The application will be available on your local network (e.g., http://192.168.x.x:5000)
cd /d "e:\attendance_cctv"
python app.py
pause
