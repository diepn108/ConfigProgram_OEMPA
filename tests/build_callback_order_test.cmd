@echo off
call "%~dp0..\scripts\setup_msvc.cmd"
if errorlevel 1 exit /b %errorlevel%
cd /d "%~dp0"
cl /nologo /EHsc /std:c++14 callback_order_native.cpp /Fe:callback_order_native.exe
exit /b %errorlevel%
