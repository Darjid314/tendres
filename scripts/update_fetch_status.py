import json
import os
import sys
from datetime import datetime, timezone

STATUS_FILE = "docs/fetch_status.json"


def main():
    if len(sys.argv) < 3:
        raise SystemExit("Usage: update_fetch_status.py SOURCE STATUS [MESSAGE]")
    source, status = sys.argv[1], sys.argv[2].lower()
    message = sys.argv[3] if len(sys.argv) > 3 else ""
    now = datetime.now(timezone.utc).isoformat()

    try:
        with open(STATUS_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        payload = {"updated_at": None, "sources": {}}

    payload.setdefault("sources", {})
    previous = payload["sources"].get(source, {})
    payload["sources"][source] = {
        **previous,
        "status": status,
        "fetched_at": now,
        "message": message,
    }
    payload["updated_at"] = now

    os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
    tmp = STATUS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, STATUS_FILE)
    print(f"Fetch status: {source}={status} at {now}")


if __name__ == "__main__":
    main()
