@echo off
chcp 65001 >nul
cd /d %~dp0
rem 每日報告：台北 08:10（日 K 08:00 收盤後）
schtasks /Create /F /TN "KKCompass2_Daily" /TR "\"%~dp0run_daily.bat\"" /SC DAILY /ST 08:10
rem 4H 掃描：台北 00/04/08/12/16/20 點收盤，各延後 3 分鐘
schtasks /Create /F /TN "KKCompass2_Scan_00" /TR "\"%~dp0run_scan.bat\"" /SC DAILY /ST 00:03
schtasks /Create /F /TN "KKCompass2_Scan_04" /TR "\"%~dp0run_scan.bat\"" /SC DAILY /ST 04:03
schtasks /Create /F /TN "KKCompass2_Scan_08" /TR "\"%~dp0run_scan.bat\"" /SC DAILY /ST 08:03
schtasks /Create /F /TN "KKCompass2_Scan_12" /TR "\"%~dp0run_scan.bat\"" /SC DAILY /ST 12:03
schtasks /Create /F /TN "KKCompass2_Scan_16" /TR "\"%~dp0run_scan.bat\"" /SC DAILY /ST 16:03
schtasks /Create /F /TN "KKCompass2_Scan_20" /TR "\"%~dp0run_scan.bat\"" /SC DAILY /ST 20:03
echo.
echo 已建立排程。可在「工作排程器」看到 KKCompass2_ 開頭的工作。電腦要開著才會執行。
pause
