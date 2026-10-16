@echo off
call "%~dp0..\scripts\setup_msvc.cmd"
if errorlevel 1 exit /b %errorlevel%
cd /d "%~dp0"
cl /nologo /EHsc /std:c++14 fmc_batch_readback_native.cpp /Fe:fmc_batch_readback_native.exe
exit /b %errorlevel%
