import os
import json
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials


SHEET_NAME = "Oman Tenders"

OUT = Path("docs/tenders.json")

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]


raw = os.environ.get("GOOGLE_CREDENTIALS")

if raw:

    Path("credentials.json").write_text(
        raw,
        encoding="utf-8"
    )


creds = Credentials.from_service_account_file(
    "credentials.json",
    scopes=SCOPE
)


sheet = (
    gspread
    .authorize(creds)
    .open(SHEET_NAME)
    .sheet1
)


rows = sheet.get_all_values()

out = []


for r in rows[1:]:

    # 15 columns
    r = (r + [""] * 15)[:15]

    out.append({

        "serial": r[0],

        "tender_no": r[1],

        "title": r[2],

        "agency": r[3],

        "governorate": r[4],

        "state": r[5],

        "bank_guarantee": r[6],

        "fee": r[7],

        "sales_start": r[8],

        "sales_end": r[9],

        "purchase_start": r[10],

        "purchase_end": r[11],

        "submission_close": r[12],

        "bid_open": r[13],

        # NEW
        "tender_url": r[14]

    })


OUT.parent.mkdir(
    exist_ok=True
)


OUT.write_text(
    json.dumps(
        out,
        ensure_ascii=False,
        indent=2
    ),
    encoding="utf-8"
)


print(
    f"Exported {len(out)} tenders "
    f"to {OUT}"
)
