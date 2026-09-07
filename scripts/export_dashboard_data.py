import json
import os
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials


SHEET_NAME = "Oman Tenders"
OUTPUT_FILE = "docs/tenders.json"
NEW_FILE = "docs/new_tenders.json"

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


def clean(value):
    if value is None:
        return ""
    return str(value).strip()


def is_real_url(value):
    value = clean(value)

    return (
        value.startswith("https://")
        and "tenderboard.gov.om" in value
    )


def load_previous_data():
    """
    Previous dashboard data.
    Used to detect which tender numbers are genuinely new.
    """

    if not os.path.exists(OUTPUT_FILE):
        return {}

    try:
        with open(
            OUTPUT_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            old = json.load(f)

        result = {}

        for item in old:

            tender_no = clean(
                item.get("tender_no")
            )

            if tender_no:
                result[tender_no] = item

        return result

    except Exception as e:

        print(
            f"Could not read previous dashboard data: {e}"
        )

        return {}


def main():

    credentials_json = os.environ.get(
        "GOOGLE_CREDENTIALS"
    )

    if not credentials_json:
        raise RuntimeError(
            "GOOGLE_CREDENTIALS secret is missing."
        )

    with open(
        "credentials.json",
        "w",
        encoding="utf-8"
    ) as f:

        f.write(credentials_json)

    creds = (
        Credentials
        .from_service_account_file(
            "credentials.json",
            scopes=SCOPE
        )
    )

    client = gspread.authorize(creds)

    sheet = (
        client
        .open(SHEET_NAME)
        .sheet1
    )

    rows = sheet.get_all_values()

    if not rows:
        print("Google Sheet is empty.")
        return


    previous = load_previous_data()

    print(
        f"Previous dashboard tenders: "
        f"{len(previous)}"
    )


    tenders = []


    for row in rows[1:]:

        r = list(row) + [""] * 15

        tender_no = clean(r[1])

        if not tender_no:
            continue


        tender = {

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

            "tender_url":
                clean(r[14]),

        }


        # A tender is NEW only when its
        # tender number did not exist in
        # the previous dashboard export.

        tender["is_new"] = (
            tender_no not in previous
        )


        tenders.append(tender)


    # -------------------------------------------------
    # SAVE MAIN DASHBOARD DATA
    # -------------------------------------------------

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            tenders,
            f,
            ensure_ascii=False,
            indent=2
        )


    # -------------------------------------------------
    # SAVE ONLY NEW TENDERS
    # -------------------------------------------------

    new_tenders = [
        t
        for t in tenders
        if t["is_new"]
    ]


    with open(
        NEW_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            {
                "updated_at":
                    datetime.now(
                        timezone.utc
                    ).isoformat(),

                "count":
                    len(new_tenders),

                "tenders":
                    new_tenders,
            },
            f,
            ensure_ascii=False,
            indent=2
        )


    print(
        "======================================"
    )

    print(
        f"Total tenders exported: "
        f"{len(tenders)}"
    )

    print(
        f"NEW tenders this run: "
        f"{len(new_tenders)}"
    )


    if new_tenders:

        print(
            "\n🆕 NEW TENDERS:"
        )

        for t in new_tenders:

            print(
                f"  • "
                f"{t['tender_no']} - "
                f"{t['title']}"
            )

    else:

        print(
            "\nNo new tenders this run."
        )


    print(
        "======================================"
    )


if __name__ == "__main__":
    main()
