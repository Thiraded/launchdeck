@echo off

call "D:\workcombo\OmniRoute CLI start.bat" >> "D:\workcombo\wc_logs\omniroute-cli.log.txt" 2>&1

set RC=%ERRORLEVEL%

echo __WC_DONE__ %RC% >> "D:\workcombo\wc_logs\omniroute-cli.done.txt"

