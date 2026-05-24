@echo off
cd /d "C:\Users\offic\OneDrive\Dokumente\all\excell"

set DRIVE_FILE_ID=1dOSFon3rxVThdXIk1Ed5Zdv2N2VfQtj6ad7KYxYxaEo
set SYNC_YEAR=2024

"C:\Users\offic\AppData\Local\Programs\Python\Python313\python.exe" -m app.scripts.sync_drive_xlsx_oauth >> "C:\Users\offic\OneDrive\Dokumente\all\excell\sync_log.txt" 2>&1
