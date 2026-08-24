@echo off
chcp 65001 >nul 2>&1
:: Launch scratchpad (console logs visible, minimize after Electron window pops up)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0lumo.ps1" %*
