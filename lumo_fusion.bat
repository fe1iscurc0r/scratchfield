@echo off
chcp 65001 >nul 2>&1
:: 陆墨 × NEKO 融合一键启动（包装 lumo_fusion.ps1）
:: 参数透传，例：lumo_fusion.bat -NoNeo4j -NoFrontend
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0lumo_fusion.ps1" %*
