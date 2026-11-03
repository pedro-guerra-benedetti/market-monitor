@echo off
setlocal
pushd "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found. Install Python 3 and ensure it is available on PATH.
    popd
    exit /b 1
)

python -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo Installing requirements failed.
    popd
    exit /b 1
)

python -m streamlit run "%~dp0app.py"
set "result=%errorlevel%"
popd
exit /b %result%
