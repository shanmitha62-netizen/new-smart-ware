@echo off

title Smart Warehouse Operations System

echo ==============================================
echo   SMART WAREHOUSE OPERATIONS SYSTEM
echo ==============================================
echo.

echo Checking Python...
python --version

echo.
echo Activating virtual environment...

call .venv\Scripts\activate.bat

echo.
echo Installing required packages...
python -m pip install -r requirements.txt

echo.
echo ==============================================
echo   Starting Smart Warehouse System
echo ==============================================
echo.
echo Open your browser:
echo http://127.0.0.1:5000
echo.
echo Press CTRL+C to stop the server.
echo.

python app.py

pause