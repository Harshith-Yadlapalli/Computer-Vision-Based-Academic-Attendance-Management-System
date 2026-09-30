Set WshShell = CreateObject("WScript.Shell") 
WshShell.Run chr(34) & "e:\attendance_cctv\start_attendance_server.bat" & Chr(34), 0
Set WshShell = Nothing
