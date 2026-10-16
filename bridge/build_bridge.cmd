@echo off
call "%~dp0..\scripts\setup_msvc.cmd"
if errorlevel 1 exit /b %errorlevel%
cd /d "%~dp0"
if not "%~1"=="" set "OEMPA_BRIDGE_OUTPUT=%~1"
if not defined OEMPA_BRIDGE_OUTPUT set "OEMPA_BRIDGE_OUTPUT=oempa_bridge.dll"
if not defined OEMPA_AOS_SOURCES set "OEMPA_AOS_SOURCES=%ProgramData%\AOS\OEMPA 1.1.5.4\Sources"
cl /nologo /EHsc /LD /Od /MD /D "_WIN64" /D "OEMPA_BRIDGE_EXPORTS" /I "%OEMPA_AOS_SOURCES%\Common" /I "%OEMPA_AOS_SOURCES%\UserHeaders\x64" oempa_bridge.cpp /link /LIBPATH:"%OEMPA_AOS_SOURCES%\UTKernel\x64\Release" UTKernelDriver.lib UTKernelDriverOEMPA.lib win_stub.lib User32.lib /OUT:"%OEMPA_BRIDGE_OUTPUT%"
exit /b %errorlevel%
