@echo off
rem Regenerate the whole MSE Innovation package (submission\MSE_Innovation and paper\mse\AUDIT.md).
cd /d "%~dp0..\..\.."
.venv\Scripts\python paper\mse\source\build_package.py
