@echo off
chcp 65001 >nul
cd /d %~dp0
echo 安裝需要的套件...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo 安裝失敗。請確認已安裝 Python 3.12 以上，並在安裝時勾選 "Add python.exe to PATH"。
  pause & exit /b 1
)
echo.
echo 安裝完成。接著雙擊 run_daily.bat 跑第一次（首次約 10~15 分鐘）。
pause
