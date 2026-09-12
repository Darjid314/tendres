import json
import os
from datetime import datetime, timezone

import gspread
from google.oauth2.service_account import Credentials


# =====================================================
# CONFIG
# =====================================================

SHEET_NAME = "Oman Tenders"

OMAN_SOURCE = "Oman Tender Board"
SQU_SOURCE = "Sultan Qaboos University"
SHEET_SOURCES = {
    "SQU Tenders": SQU_SOURCE,
}

OUTPUT_FILE = "docs/tenders.json"

NEW_FILE = "docs/new_tenders.json"

LAST_UPDATE_FILE = "docs/last_update.json"


# =====================================================
# GOOGLE API SCOPE
# =====================================================

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


# =====================================================
# CLEAN VALUE
# =====================================================

def clean(value):

    if value is None:
        return ""

    return str(value).strip()


# =====================================================
# CHECK REAL TENDER URL
# =====================================================

def is_real_url(value):

    value = clean(value)

    return (
        value.startswith("https://")
        and "tenderboard.gov.om" in value
    )


# =====================================================
# LOAD PREVIOUS DASHBOARD DATA
# =====================================================

def tender_key(tender_no, source):
    """Keep identically numbered tenders from different publishers distinct."""
    return f"{clean(source) or OMAN_SOURCE}:{clean(tender_no)}"


def load_previous_data():

    """
    Previous dashboard data.

    Used to detect which tender numbers
    are genuinely new.
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

                result[tender_key(tender_no, item.get("source"))] = item


        return result


    except Exception as e:

        print(
            f"Could not read previous dashboard data: {e}"
        )

        return {}


# =====================================================
# MAIN
# =====================================================

def main():

    # -------------------------------------------------
    # GOOGLE CREDENTIALS
    # -------------------------------------------------

    credentials_json = os.environ.get(
        "GOOGLE_CREDENTIALS"
    )


    if not credentials_json:

        raise RuntimeError(
            "GOOGLE_CREDENTIALS secret is missing."
        )


    # -------------------------------------------------
    # CREATE TEMP CREDENTIAL FILE
    # -------------------------------------------------

    with open(
        "credentials.json",
        "w",
        encoding="utf-8"
    ) as f:

        f.write(credentials_json)


    # -------------------------------------------------
    # GOOGLE AUTH
    # -------------------------------------------------

    creds = (
        Credentials
        .from_service_account_file(
            "credentials.json",
            scopes=SCOPE
        )
    )


    client = gspread.authorize(creds)


    # -------------------------------------------------
    # OPEN GOOGLE SHEET
    # -------------------------------------------------

    spreadsheet = client.open(SHEET_NAME)


    # -------------------------------------------------
    # TIMESTAMP
    #
    # Create ONE timestamp for the whole run.
    # The same timestamp is used in:
    #
    # 1. new_tenders.json
    # 2. last_update.json
    #
    # -------------------------------------------------

    previous = load_previous_data()

    updated_at = datetime.now(
        timezone.utc
    ).isoformat()


    print(
        f"Previous dashboard tenders: "
        f"{len(previous)}"
    )


    print(
        f"Dashboard update timestamp: "
        f"{updated_at}"
    )


    # -------------------------------------------------
    # BUILD TENDER DATA
    # -------------------------------------------------

    tenders = []


    # sheet1 remains the Oman Tender Board source regardless of its display
    # name, preserving the established workbook configuration.
    worksheets = [(spreadsheet.sheet1, OMAN_SOURCE)]

    for worksheet_name, source in SHEET_SOURCES.items():

        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            # The SQU worksheet is created by its scraper.  Its absence must
            # never stop the established Oman Tender Board export.
            print(f"Worksheet not found, skipping: {worksheet_name}")
            continue

        worksheets.append((worksheet, source))

    for worksheet, default_source in worksheets:

        rows = worksheet.get_all_values()
        if not rows:
            continue

        for row in rows[1:]:

            r = list(row) + [""] * 16


            tender_no = clean(r[1])


            if not tender_no:

                continue


            source = clean(r[15]) or default_source
            tender = {

            "serial":
                clean(r[0]),

            "tender_no":
                tender_no,

            "title":
                clean(r[2]),

            "agency":
                clean(r[3]),

            "governorate":
                clean(r[4]),

            "state":
                clean(r[5]),

            "bank_guarantee":
                clean(r[6]),

            "fee":
                clean(r[7]),

            "sales_start":
                clean(r[8]),

            "sales_end":
                clean(r[9]),

            "purchase_start":
                clean(r[10]),

            "purchase_end":
                clean(r[11]),

            "submission_close":
                clean(r[12]),

            "bid_open":
                clean(r[13]),

                "tender_url": clean(r[14]),

                "source": source,

            }


        # -------------------------------------------------
        # NEW TENDER DETECTION
        # -------------------------------------------------

            tender["is_new"] = tender_key(tender_no, source) not in previous


            tenders.append(tender)


    # =================================================
    # SAVE MAIN DASHBOARD DATA
    # =================================================

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


    # =================================================
    # FIND NEW TENDERS
    # =================================================

    new_tenders = [

        tender

        for tender in tenders

        if tender["is_new"]

    ]


    # =================================================
    # SAVE NEW TENDERS
    # =================================================

    with open(
        NEW_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            {
                "updated_at":
                    updated_at,

                "count":
                    len(new_tenders),

                "tenders":
                    new_tenders,
            },
            f,
            ensure_ascii=False,
            indent=2
        )


    # =================================================
    # SAVE LAST UPDATE METADATA
    #
    # This file is read by the dashboard.
    # =================================================

    with open(
        LAST_UPDATE_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            {
                "updated_at":
                    updated_at
            },
            f,
            ensure_ascii=False,
            indent=2
        )


    # =================================================
    # LOG
    # =================================================

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


    print(
        f"Last update file: "
        f"{LAST_UPDATE_FILE}"
    )


    print(
        f"Updated at: "
        f"{updated_at}"
    )


    # =================================================
    # SHOW NEW TENDERS
    # =================================================

    if new_tenders:

        print(
            "\n🆕 NEW TENDERS:"
        )


        for tender in new_tenders:

            print(
                f"  • "
                f"{tender['tender_no']} - "
                f"{tender['title']}"
            )


    else:

        print(
            "\nNo new tenders this run."
        )


    print(
        "======================================"
    )


# =====================================================
# ENTRY POINT
# =====================================================

if __name__ == "__main__":

    main()
