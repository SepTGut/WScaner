@echo off
title WScaner - WhatsApp OCR Bot
cd /d "%~dp0"

echo ======================================================
echo           WScaner - WhatsApp OCR Bot
echo ======================================================
echo.
echo Pilih Mesin Pemindaian (OCR Engine) untuk Bot:
echo   [1] Windows Native OCR (Lokal, Super Cepat, Offline, Gratis)
echo   [2] Groq Cloud Vision LLM (Ultra-Cepat ~1.2s, Cloud LPU AI)
echo   [3] Google Gemini Vision LLM (Cloud AI, Sangat Cerdas, Bebas Regex)
echo   [4] Google Drive Native OCR (Built-in via Google Cloud Docs)
echo   [5] Auto / Hybrid (Windows OCR -> Fallback Cloud jika kurang lengkap)
echo.

set "choice=1"
set /p "choice=Pilihan Anda [1/2/3/4/5] (default: 1): "

if "%choice%"=="2" (
    set OCR_ENGINE=groq
    echo.
    echo [INFO] Mesin Terpilih: Groq Cloud Vision LLM (Ultra-Fast LPU)
) else if "%choice%"=="3" (
    set OCR_ENGINE=gemini
    echo.
    echo [INFO] Mesin Terpilih: Google Gemini Vision LLM (Cloud AI)
) else if "%choice%"=="4" (
    set OCR_ENGINE=drive
    echo.
    echo [INFO] Mesin Terpilih: Google Drive Native OCR (Built-in Google Cloud Docs)
) else if "%choice%"=="5" (
    set OCR_ENGINE=auto
    echo.
    echo [INFO] Mesin Terpilih: Auto / Hybrid (Windows OCR -> Fallback Cloud)
) else (
    set OCR_ENGINE=windows
    echo.
    echo [INFO] Mesin Terpilih: Windows Native OCR (Lokal)
)

echo [INFO] Memulai bot WhatsApp...
echo.
node src/bot/bot.js
pause
