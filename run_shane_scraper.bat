@echo off
REM Auto-generated script to run Shane's NWS Scraper
REM It activates the Anaconda environment and runs the script

REM Set the path to your Anaconda installation (adjust if necessary)
set "CONDA_PATH=C:\Users\%USERNAME%\anaconda3"

REM Check if actiavation script exists there, otherwise try miniconda
if not exist "%CONDA_PATH%\Scripts\activate.bat" (
    set "CONDA_PATH=C:\Users\%USERNAME%\miniconda3"
)

REM Activate the environment
call "%CONDA_PATH%\Scripts\activate.bat" weather_pull_env

REM Change to the directory where the script is located
cd /d "%~dp0"

REM Run the python script
python shanes_nws_scraper.py

REM Optional: Deactivate environment when done
call conda deactivate
