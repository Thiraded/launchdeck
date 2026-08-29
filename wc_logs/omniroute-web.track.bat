@echo off
call "C:\Users\thira\OneDrive\Desktop\OmniRoute Web start.bat" >> "C:\Users\thira\OneDrive\Desktop\wc_logs\omniroute-web.log.txt" 2>&1
set RC=%ERRORLEVEL%
echo __WC_DONE__ %RC% >> "C:\Users\thira\OneDrive\Desktop\wc_logs\omniroute-web.done.txt"
