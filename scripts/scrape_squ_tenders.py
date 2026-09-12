"""Collect public Sultan Qaboos University tender notices into a dedicated sheet tab."""
import hashlib
import os
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

import gspread
import requests
from bs4 import BeautifulSoup
from google.oauth2.service_account import Credentials

SHEET_NAME = "Oman Tenders"
WORKSHEET_NAME = "SQU Tenders"
SQU_TENDERS_URL = os.environ.get("SQU_TENDERS_URL") or "https://www.squ.edu.om/tenders"
SOURCE = "Sultan Qaboos University"
HEADERS = [
    "S.No", "Tender No", "Tender Title (English)", "Agency (English)",
    "Governorate", "State", "Bank Guarantee", "Tender Fee", "Sales Start",
    "Sales End", "Proposal Start", "Proposal End", "Submission Close",
    "Bid Opening", "Tender URL", "Source",
]
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]


def clean(value):
    return " ".join(str(value or "").split())


def is_squ_url(url):
    try:
        return urlparse(url).hostname in {"squ.edu.om", "www.squ.edu.om"}
    except ValueError:
        return False


def first_value(cells, labels):
    for label in labels:
        for key, value in cells.items():
            if label in key:
                return value
    return ""


def tender_number(title, url):
    match = re.search(r"(?:tender|rfq|rft|مناقصة)\s*(?:no\.?|number)?\s*[:#-]?\s*([A-Za-z0-9/-]+)", title, re.I)
    if match:
        return "SQU-" + match.group(1).upper()
    digest = hashlib.sha256(f"{title}|{url}".encode()).hexdigest()[:12].upper()
    return "SQU-" + digest


def parse_tenders(html, page_url=SQU_TENDERS_URL):
    """Parse SQU notices from tables or linked notice cards without site-specific markup."""
    soup = BeautifulSoup(html, "html.parser")
    tenders, seen = [], set()

    for table in soup.find_all("table"):
        headers = [clean(cell.get_text(" ", strip=True)).lower() for cell in table.find_all("th")]
        if not headers or not any("tender" in header or "مناقصة" in header for header in headers):
            continue
        for row in table.find_all("tr")[1:]:
            values = [clean(cell.get_text(" ", strip=True)) for cell in row.find_all("td")]
            if not values:
                continue
            cells = dict(zip(headers, values))
            link = row.find("a", href=True)
            url = urljoin(page_url, link["href"]) if link else page_url
            title = first_value(cells, ("title", "subject", "description", "مناقصة")) or values[0]
            append_tender(tenders, seen, title, url, cells)

    # SQU pages may publish notices as document/detail links rather than a table.
    for link in soup.find_all("a", href=True):
        title = clean(link.get_text(" ", strip=True))
        context = clean(link.parent.get_text(" ", strip=True)) if link.parent else title
        if not re.search(r"tender|rfq|rft|bid|مناقصة", f"{title} {context}", re.I):
            continue
        append_tender(tenders, seen, title or context, urljoin(page_url, link["href"]), {})
    return tenders


def append_tender(tenders, seen, title, url, cells):
    title = clean(title)
    if not title or not is_squ_url(url):
        return
    number = first_value(cells, ("tender no", "reference", "number", "رقم")) or tender_number(title, url)
    # A notice can appear once in a table and again as its detail link.
    # Treat either its canonical URL or tender number as the same notice.
    if number in seen or url in seen:
        return
    seen.update((number, url))
    tenders.append({
        "tender_no": number,
        "title": title,
        "agency": SOURCE,
        "governorate": "Muscat",
        "state": "",
        "bank_guarantee": first_value(cells, ("guarantee", "ضمان")),
        "fee": first_value(cells, ("fee", "price", "رسوم")),
        "sales_start": first_value(cells, ("sales start", "issue date", "publish")),
        "sales_end": first_value(cells, ("sales end", "purchase close")),
        "purchase_start": "",
        "purchase_end": "",
        "submission_close": first_value(cells, ("submission", "closing", "deadline", "آخر")),
        "bid_open": first_value(cells, ("opening", "فتح")),
        "tender_url": url,
        "source": SOURCE,
    })


def get_sheet():
    credentials_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not credentials_json:
        raise RuntimeError("GOOGLE_CREDENTIALS secret is missing.")
    creds = Credentials.from_service_account_info(__import__("json").loads(credentials_json), scopes=SCOPE)
    spreadsheet = gspread.authorize(creds).open(SHEET_NAME)
    try:
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=WORKSHEET_NAME, rows=1000, cols=len(HEADERS))
        worksheet.append_row(HEADERS)
    return worksheet


def main():
    response = requests.get(SQU_TENDERS_URL, timeout=45, headers={"User-Agent": "Mozilla/5.0 (compatible; TenderDashboard/1.0)"})
    response.raise_for_status()
    tenders = parse_tenders(response.text, response.url)
    worksheet = get_sheet()
    existing = {row[1] for row in worksheet.get_all_values()[1:] if len(row) > 1}
    new = [t for t in tenders if t["tender_no"] not in existing]
    rows = []
    for serial, tender in enumerate(new, start=len(existing) + 1):
        rows.append([serial] + [tender[key] for key in HEADERS[1:]])
    if rows:
        worksheet.append_rows(rows)
    print(f"SQU scrape completed at {datetime.now(timezone.utc).isoformat()}: {len(tenders)} notices found, {len(rows)} added.")


if __name__ == "__main__":
    main()
