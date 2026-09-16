@echo off
chcp 65001 > nul
title Pi Akademiya Telegram Boti
color 0A

echo =======================================================
echo          PI AKADEMIYA TELEGRAM YORDAMCHI BOTI
echo =======================================================
echo.
echo Bot ishga tushirilmoqda...
echo To'xtatish uchun Ctrl + C bosing.
echo.

cd /d "%~dp0"
:restart
py bot.py
if errorlevel 2 goto done
if not errorlevel 1 goto done
echo Bot xato bilan toxtadi. 10 soniyadan keyin qayta ishga tushadi.
timeout /t 10
goto restart
:done

pause
