@echo off
setlocal
cd /d "%~dp0"
cmake -S . -B build
if errorlevel 1 exit /b 1
cmake --build build --config Release --parallel 2
if errorlevel 1 exit /b 1
ctest --test-dir build -C Release --output-on-failure
if errorlevel 1 exit /b 1
echo Build completo. Execute build\Release\edgeai_chat.exe models\compute_v05\transformer_int8-seed11.edge --mode eco
