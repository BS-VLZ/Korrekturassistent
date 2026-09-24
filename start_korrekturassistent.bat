@echo off
set "PYTHONPATH=%~dp0src"
"C:\Users\b.skacel\AppData\Local\Programs\Python\Python314\python.exe" -m korrekturassistent.project_workflow
if errorlevel 1 pause

