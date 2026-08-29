@echo off
title wc-hamster-clint
cd /d D:\HamsterWorld\backoffice  || (
  echo [wc-hamster-clint] D:\HamsterWorld\backoffice NOT FOUND (drive missing?).
  echo Window left open so work-combo can detect/kill it.
  pause
  goto :eof
)
npm run dev
echo [wc-hamster-clint] dev exited; window left open.
pause
