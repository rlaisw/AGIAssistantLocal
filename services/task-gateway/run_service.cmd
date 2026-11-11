@echo off
REM Spec 038 (T020): task-gateway service entrypoint for the Scheduled Task.
REM Auto-started at logon via windows\task-gateway-task.xml; loopback :8080.
cd /d "%~dp0"
python service.py