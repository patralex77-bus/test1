from __future__ import annotations

import imaplib
import os
import smtplib
import sys
from pathlib import Path


def load_env_file(path: str = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        print(f"[WARN] .env file not found: {env_path.resolve()}")
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def test_imap() -> bool:
    host = os.getenv("IMAP_HOST", "").strip()
    port = int(os.getenv("IMAP_PORT", "993"))
    username = os.getenv("IMAP_USERNAME", "").strip()
    password = os.getenv("IMAP_PASSWORD", "").strip()
    folder = os.getenv("IMAP_FOLDER", "INBOX").strip() or "INBOX"

    print("\n=== IMAP TEST ===")
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"User: {username}")
    print(f"Folder: {folder}")

    if not host or not username or not password:
        print("[FAIL] IMAP settings are incomplete")
        return False

    client = None
    try:
        client = imaplib.IMAP4_SSL(host, port)
        client.login(username, password)
        status, _ = client.select(folder)
        if status != "OK":
            print(f"[FAIL] IMAP login ok, but folder select failed: {folder}")
            return False
        print("[OK] IMAP login successful")
        return True
    except Exception as e:
        print(f"[FAIL] IMAP login failed: {e}")
        return False
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
            try:
                client.logout()
            except Exception:
                pass


def test_smtp() -> bool:
    host = os.getenv("SMTP_HOST", "").strip()
    port = int(os.getenv("SMTP_PORT", "465"))
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    use_ssl = os.getenv("SMTP_USE_SSL", "0").strip() == "1"
    use_tls = os.getenv("SMTP_USE_TLS", "1").strip() == "1"
    timeout = int(os.getenv("SMTP_TIMEOUT", "30"))

    print("\n=== SMTP TEST ===")
    print(f"Host: {host}")
    print(f"Port: {port}")
    print(f"User: {username}")
    print(f"SSL: {use_ssl}")
    print(f"TLS: {use_tls}")

    if not host or not username or not password:
        print("[FAIL] SMTP settings are incomplete")
        return False

    smtp = None
    try:
        if use_ssl:
            smtp = smtplib.SMTP_SSL(host, port, timeout=timeout)
            smtp.ehlo()
        else:
            smtp = smtplib.SMTP(host, port, timeout=timeout)
            smtp.ehlo()
            if use_tls:
                smtp.starttls()
                smtp.ehlo()

        smtp.login(username, password)
        print("[OK] SMTP login successful")
        return True
    except Exception as e:
        print(f"[FAIL] SMTP login failed: {e}")
        return False
    finally:
        if smtp is not None:
            try:
                smtp.quit()
            except Exception:
                pass


def main() -> int:
    env_arg = sys.argv[1] if len(sys.argv) > 1 else ".env"
    load_env_file(env_arg)

    imap_ok = test_imap()
    smtp_ok = test_smtp()

    print("\n=== RESULT ===")
    print(f"IMAP: {'OK' if imap_ok else 'FAIL'}")
    print(f"SMTP: {'OK' if smtp_ok else 'FAIL'}")

    return 0 if (imap_ok and smtp_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
