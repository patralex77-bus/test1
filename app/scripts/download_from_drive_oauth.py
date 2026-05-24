import os
import io
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
TOKEN_FILE = os.environ.get("GOOGLE_OAUTH_TOKEN_FILE", "token.json")
DRIVE_FILE_ID = os.environ.get("DRIVE_FILE_ID", "").strip()

def download_drive_file_bytes(file_id: str) -> bytes:
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    service = build("drive", "v3", credentials=creds)

    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)

    done = False
    while not done:
        status, done = downloader.next_chunk()

    return fh.getvalue()

def main():
    if not DRIVE_FILE_ID:
        raise SystemExit("Missing DRIVE_FILE_ID")

    b = download_drive_file_bytes(DRIVE_FILE_ID)
    print("Downloaded bytes:", len(b))

if __name__ == "__main__":
    main()
