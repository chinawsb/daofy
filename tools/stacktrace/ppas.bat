@echo off
SET THEFILE=C:\user\daofy-agent\daofy\tools\stacktrace\test_exception.exe
echo Linking %THEFILE%
C:\lazarus\fpc\3.2.2\bin\x86_64-win64\ld.exe -b pei-x86-64  --gc-sections    --entry=_mainCRTStartup    -o C:\user\daofy-agent\daofy\tools\stacktrace\test_exception.exe link15024.res
if errorlevel 1 goto linkend
goto end
:asmend
echo An error occurred while assembling %THEFILE%
goto end
:linkend
echo An error occurred while linking %THEFILE%
:end
