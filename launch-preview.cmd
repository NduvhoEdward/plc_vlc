@echo off
setlocal
cd /d "%~dp0"
where node >nul 2>nul
if %errorlevel% equ 0 (
  node preview.mjs
) else (
  if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" (
    "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe" preview.mjs
  ) else (
    echo Install Node.js 22 or newer, then run node preview.mjs in this directory.
  )
)
pause
