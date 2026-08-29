@echo off
title wc-hamster-clint
cd /d D:\projects\HamsterWorld\backoffice  || (
  echo [wc-hamster-clint] D:\projects\HamsterWorld\backoffice NOT FOUND (drive missing?).
  echo Window left open so work-combo can detect/kill it.
  pause
  goto :eof
)
npm run dev
echo [wc-hamster-clint] dev exited; window left open.
pause
