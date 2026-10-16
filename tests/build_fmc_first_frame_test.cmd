@echo off
call "%~dp0..\scripts\setup_msvc.cmd"
if errorlevel 1 exit /b %errorlevel%
cd /d "%~dp0"
cl /nologo /EHsc /std:c++14 fmc_first_frame_native.cpp /Fe:fmc_first_frame_native.exe
exit /b %errorlevel%
