@echo off
REM Bespin (BSP) Mining Script for Windows
REM Simple continuous mining loop

SET MINER_ADDRESS=%1
SET API_URL=%2

IF "%MINER_ADDRESS%"=="" (
    echo Error: Please provide your wallet address
    echo Usage: mine.bat YOUR_WALLET_ADDRESS [API_URL]
    echo Example: mine.bat 1YourBespinAddressHere
    exit /b 1
)

IF "%API_URL%"=="" SET API_URL=http://localhost:8000

echo ========================================
echo Bespin (BSP) Miner
echo ========================================
echo Miner Address: %MINER_ADDRESS%
echo API URL: %API_URL%
echo Press Ctrl+C to stop
echo ========================================
echo.

:loop
echo [%date% %time%] Mining block...

curl -s -X POST "%API_URL%/mine" -H "Content-Type: application/json" -d "{\"miner_address\": \"%MINER_ADDRESS%\"}"

echo.
timeout /t 2 /nobreak >nul
goto loop
