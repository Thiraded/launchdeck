@echo off
title wc-hamster-server
cd /d D:\HamsterWorld\server  || (
  echo [wc-hamster-server] D:\HamsterWorld\server NOT FOUND (drive missing?).
  echo Window left open so work-combo can detect/kill it.
  pause
  goto :eof
)
npm run dev
echo [wc-hamster-server] dev exited; window left open.
pause
