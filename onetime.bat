@echo off
title WScaner - Onetimeused Foto Extractor
cd /d "%~dp0"
echo ======================================================
echo       WScaner - Onetimeused Foto Extractor
echo       Menyimpan Foto Hari Ini ke GetDataFolder
echo ======================================================
echo.
node src/oneTimeUsed.js %*
pause
