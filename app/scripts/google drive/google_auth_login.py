from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

HERE = Path(__file__).resolve().parent
CLIENT_SECRET_FILE = HERE / "client_secret.json"   # сложи файла тук
TOKEN_FILE = HERE / "token.json"

def main():
    if not CLIENT_SECRET_FILE.exists():
        raise FileNotFoundError(
            f"Няма {CLIENT_SECRET_FILE}. Сложи OAuth JSON тук и го преименувай на client_secret.json"
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
    creds = flow.run_local_server(port=0)

    TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
    print(f"OK: saved {TOKEN_FILE}")

if __name__ == "__main__":
    main()
