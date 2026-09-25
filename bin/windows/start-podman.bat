@echo off
title WScaner - WhatsApp OCR Bot (Podman)
cd /d "%~dp0..\.."
echo ======================================================
echo           Memulai WScaner via Podman
echo ======================================================
echo.

:: Pastikan Podman Machine berjalan
echo [1/3] Memeriksa status Podman Machine...
podman machine start 2>nul

:: Build & Jalankan container
echo [2/3] Menjalankan container...
podman compose up -d --build

:: Tampilkan log secara realtime (untuk scan QR WhatsApp)
echo [3/3] Membuka log bot (Tekan Ctrl+C untuk menutup tampilan log)...
echo.
podman compose logs -f
pause
