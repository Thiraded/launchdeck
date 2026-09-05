@echo off

call "D:\workcombo\OmniRoute Web start.bat" >> "D:\workcombo\wc_logs\omniroute-web.log.txt" 2>&1

set RC=%ERRORLEVEL%

echo __WC_DONE__ %RC% >> "D:\workcombo\wc_logs\omniroute-web.done.txt"

