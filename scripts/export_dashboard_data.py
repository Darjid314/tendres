import json
import os
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials

SHEET_NAME = "Oman Tenders"
OUTPUT_FILE = "docs/tenders.json"
NEW_FILE = "docs/new_tenders.json"
LAST_UPDATE_FILE = "docs/last_update.json"
SQU_FILE = "docs/squ_tenders.json"
EXTERNAL_FILE = "docs/external_tenders.json"

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


def clean(value):
    return "" if value is None else str(value).strip()


def load_previous_data():
    if not os.path.exists(OUTPUT_FILE):
        return {}
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            old = json.load(f)
        result = {}
        for item in old:
            tender_no = clean(item.get("tender_no"))
            if tender_no:
                source = clean(item.get("source")) or "Oman Tender Board"
                result[f"{source}|{tender_no}"] = item
        return result
    except Exception as exc:
        print(f"⚠️ Previous dashboard data read failed: {exc}")
        return {}


def load_json_list(path):
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as exc:
        print(f"⚠️ {path} read failed: {exc}")
        return []


def main():
    credentials_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not credentials_json:
        raise RuntimeError("GOOGLE_CREDENTIALS secret is missing.")

    with open("credentials.json", "w", encoding="utf-8") as f:
        f.write(credentials_json)

    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
    rows = sheet.get_all_values()

    if not rows:
        raise RuntimeError("Google Sheet is empty.")

    previous = load_previous_data()
    updated_at = datetime.now(timezone.utc).isoformat()
    tenders = []

    # Existing Oman Tender Board data remains unchanged in shape.
    for row in rows[1:]:
        r = list(row) + [""] * 15
        tender_no = clean(r[1])
        if not tender_no:
            continue

        tender = {
            "source": "Oman Tender Board",
            "source_name": "Oman Tender Board",
            "serial": clean(r[0]),
            "tender_no": tender_no,
            "title": clean(r[2]),
            "agency": clean(r[3]),
            "governorate": clean(r[4]),
            "state": clean(r[5]),
            "bank_guarantee": clean(r[6]),
            "fee": clean(r[7]),
            "sales_start": clean(r[8]),
            "sales_end": clean(r[9]),
            "purchase_start": clean(r[10]),
            "purchase_end": clean(r[11]),
            "submission_close": clean(r[12]),
            "bid_open": clean(r[13]),
            "tender_url": clean(r[14]),
        }
        key = f"{tender['source']}|{tender_no}"
        tender["is_new"] = key not in previous
        tenders.append(tender)

    # Merge SQU into the SAME dashboard feed.
    for tender in load_json_list(SQU_FILE):
        tender = dict(tender)
        tender["source"] = "SQU"
        tender["source_name"] = "Sultan Qaboos University"
        key = f"SQU|{clean(tender.get('tender_no'))}"
        tender["is_new"] = key not in previous
        tenders.append(tender)

    # Merge the three additional public procurement portals into the same feed.
    # Each portal has its own source label so filters and NEW detection remain
    # independent of Oman Tender Board/SQU records.
    for tender in load_json_list(EXTERNAL_FILE):
        tender = dict(tender)
        source = clean(tender.get("source")) or "External"
        tender["source"] = source
        key = f"{source}|{clean(tender.get('tender_no'))}"
        tender["is_new"] = key not in previous
        tenders.append(tender)

    # New records first, then stable serial ordering.
    tenders.sort(key=lambda x: (not bool(x.get("is_new")), str(x.get("serial", ""))), reverse=False)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(tenders, f, ensure_ascii=False, indent=2)

    new_tenders = [t for t in tenders if t.get("is_new") is True]

    with open(NEW_FILE, "w", encoding="utf-8") as f:
        json.dump({"updated_at": updated_at, "count": len(new_tenders), "tenders": new_tenders}, f, ensure_ascii=False, indent=2)

    with open(LAST_UPDATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"updated_at": updated_at}, f, ensure_ascii=False, indent=2)

    source_counts = {}
    for item in tenders:
        source = clean(item.get("source")) or "Unknown"
        source_counts[source] = source_counts.get(source, 0) + 1

    print("======================================")
    for source, count in sorted(source_counts.items()):
        print(f"{source}: {count}")
    print(f"Total dashboard tenders: {len(tenders)}")
    print(f"NEW tenders this run: {len(new_tenders)}")
    print(f"Updated at: {updated_at}")
    print("======================================")


if __name__ == "__main__":
    main()
