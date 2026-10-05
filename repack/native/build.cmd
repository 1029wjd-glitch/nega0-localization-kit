@echo off
setlocal
where cl >nul 2>nul
if errorlevel 1 (
  echo Run this from an x86 Native Tools Command Prompt for Visual Studio.
  exit /b 1
)
pushd "%~dp0"
if not exist display_mapping.h (
  echo Generate display_mapping.h with prepare_display_mapping.py first.
  popd
  exit /b 1
)
cl /nologo /W4 /O2 /MT /LD korean.c fullscreen.c /link /MACHINE:X86 /DEF:korean.def /OUT:Nega0Korean.dll gdi32.lib user32.lib d3d9.lib
set "taskResult=%ERRORLEVEL%"
popd
exit /b %taskResult%
