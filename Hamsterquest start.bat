@echo off
title wc-hamsterquest
cd /d D:\Hamsquest  || (
  echo [wc-hamsterquest] D:\Hamsquest NOT FOUND (drive missing?).
  echo Window left open so work-combo can detect/kill it.
  pause
  goto :eof
)
npm run dev
echo [wc-hamsterquest] dev exited; window left open.
pause
