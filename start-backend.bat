@echo off
echo Starting F.R.E.D Backend API Server...
cd DATABASE\src
start cmd /k "python api_server.py"
echo.
echo Backend API started on http://localhost:5000
echo.
echo To start the frontend, open a new terminal and run:
echo   cd UI
echo   npm run dev
echo.
pause
