@echo off
chcp 65001 > nul
title WScaner - Live Camera Auto-Scanner

echo ======================================================
echo           WSCANER LIVE CAMERA AUTO-SCANNER
echo ======================================================
echo.

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python tidak ditemukan di PATH sistem.
    echo Silakan install Python 3.10+ atau tambahkan ke PATH.
    pause
    exit /b 1
)

python -c "import cv2" >nul 2>nul
if %errorlevel% neq 0 (
    echo [INFO] Menginstal dependensi OpenCV...
    pip install opencv-python
    echo.
)

python src/ocr/live_camera.py %*

if %errorlevel% neq 0 (
    echo.
    echo [INFO] Program kamera keluar dengan kode error.
    pause
)
