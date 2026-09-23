@echo off
title WScaner - Document Scanner
cd /d "%~dp0"

echo ======================================================
echo           WScaner - Document Scanner
echo ======================================================
echo.
python src/ocr/ocr_processor.py %*
echo.
pause
