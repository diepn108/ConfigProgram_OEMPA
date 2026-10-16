@echo off
if /I "%VSCMD_ARG_TGT_ARCH%"=="x64" (
  where cl >nul 2>nul
  if not errorlevel 1 exit /b 0
)
if not defined OEMPA_VCVARS set "OEMPA_VCVARS=%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not exist "%OEMPA_VCVARS%" (
  echo Open an x64 VS Developer Command Prompt or set OEMPA_VCVARS to vcvars64.bat.
  exit /b 1
)
call "%OEMPA_VCVARS%"
exit /b %errorlevel%
