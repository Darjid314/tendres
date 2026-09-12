import io
import json
import re
from datetime import datetime, timezone
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader


BASE_URL = "https://tenders.squ.edu.om/AllCategs"
OUTPUT_FILE = "docs/squ_tenders.json"

# EXACT same ICT / ELV keyword set used by test2.py.
KEYWORDS = [
    "network", "networking", "it infrastructure", "cctv", "surveillance",
    "interactive display", "smart board", "telecommunication", "telecom",
    "software", "server", "switch", "router", "hardware", "cabling",
    "computer", "fiber", "hybrid fiber", "cable",
    "شبكات", "شبكة", "تقنية المعلومات", "اتصالات", "شاشة", "شاشات",
    "كمبيوتر", "حاسب آلي", "برمجيات", "أنظمة", "كاميرات", "مراقبة", "سيرفر"
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; OmanTenderCommandCenter/1.0)"
}


# Common SQU UOM values. Kept broad because the portal uses several variants.
UOM_PATTERN = (
    r"Each|Eachs|Nos|No|Pieces|Piece|Sets|Set|Units|Unit|Pair|Pairs|Lot|Lots|"
    r"Box|Boxes|Pack|Packs|Meter|Meters|M|Kg|Kgs|Litre|Liters|Liter|Hours|Hour"
)


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def canonical_pdf_url(href, ref_no, sub_date):
    # Do not persist the portal's transient jsessionid URL.
    return (
        "https://tenders.squ.edu.om/tender/pdf?"
        f"param_ref_no={ref_no}&param_sub_date={sub_date}"
    )


def keyword_matches(text):
    haystack = clean(text).lower()
    return [k for k in KEYWORDS if k.lower() in haystack]


def extract_pdf_text(session, pdf_url):
    try:
        response = session.get(pdf_url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        reader = PdfReader(io.BytesIO(response.content))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return clean("\n".join(pages))
    except Exception as exc:
        print(f"⚠️ SQU PDF read failed: {pdf_url}: {exc}")
        return ""


def extract_primary_description(pdf_text):
    """
    Extract the actual first-item Description from an SQU requisition PDF.

    The PDF header is normally:
        S.N. SQU Product Code Description Qty UOM Remarks

    and the first item is normally:
        1 PRODUCT_CODE ACTUAL DESCRIPTION 1 Each ...

    The previous implementation matched the header itself and could therefore
    produce the bogus dashboard title 'Qty UOM'.
    """
    text = clean(pdf_text)
    if not text:
        return ""

    # First, explicitly anchor after the table header and capture the first
    # numbered product row. This handles examples such as:
    # 1 COMNTNET0006 DESKTOP with Monitor 1 Each Mac Studio with...
    row_pattern = re.compile(
        rf"(?:S\.N\.\s+)?SQU\s+Product\s+Code\s+Description\s+Qty\s+UOM\s+Remarks\s+"
        rf"1\s+[A-Z0-9_-]+\s+(.+?)\s+\d+(?:\.\d+)?\s+(?:{UOM_PATTERN})\b",
        flags=re.IGNORECASE,
    )
    match = row_pattern.search(text)
    if match:
        title = clean(match.group(1))
        if title and title.lower() not in {"qty uom", "qty", "uom"}:
            return title

    # Fallback: search for a numbered product row even if the PDF extractor
    # altered/removed the table header text.
    fallback_pattern = re.compile(
        rf"\b1\s+[A-Z][A-Z0-9_-]{{5,}}\s+(.+?)\s+\d+(?:\.\d+)?\s+(?:{UOM_PATTERN})\b",
        flags=re.IGNORECASE,
    )
    match = fallback_pattern.search(text)
    if match:
        title = clean(match.group(1))
        if title and title.lower() not in {"qty uom", "qty", "uom"}:
            return title

    return ""


def parse_rows(html):
    soup = BeautifulSoup(html, "html.parser")
    rows = []

    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) < 5:
            continue

        values = [clean(c.get_text(" ", strip=True)) for c in cells]
        ref_no = values[0]
        if not re.match(r"^\d{3,4}/\d{2}/\d{4}$", ref_no):
            continue

        invite_date = values[1]
        submission_date = values[2]
        category = values[3]

        pdf_href = ""
        for a in tr.find_all("a", href=True):
            href = a.get("href", "")
            if "pdf" in href.lower() or "tender" in href.lower():
                pdf_href = urljoin(BASE_URL, href)
                break

        # Build a stable URL from the requisition number/date when possible.
        pdf_url = canonical_pdf_url(
            pdf_href,
            ref_no,
            submission_date,
        ) if submission_date else pdf_href

        rows.append({
            "tender_no": ref_no,
            "invitation_date": invite_date,
            "submission_close": submission_date,
            "category": category,
            "pdf_url": pdf_url,
        })

    return rows


def main():
    session = requests.Session()
    response = session.get(BASE_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    candidates = parse_rows(response.text)
    print(f"📡 SQU candidates found: {len(candidates)}")

    output = []
    seen = set()

    for item in candidates:
        tender_no = item["tender_no"]
        if tender_no in seen:
            continue
        seen.add(tender_no)

        pdf_text = extract_pdf_text(session, item["pdf_url"])
        combined = " ".join([
            item["tender_no"],
            item["category"],
            pdf_text,
        ])
        matches = keyword_matches(combined)

        if not matches:
            print(f"⏭️ SQU skip (no existing keyword): {tender_no}")
            continue

        # IMPORTANT: use the real first-item Description from the PDF, not
        # the HTML category and never the PDF header text "Qty UOM".
        title = extract_primary_description(pdf_text)
        if not title:
            title = item["category"] or "SQU Request for Quotation"

        output.append({
            "source": "SQU",
            "source_name": "Sultan Qaboos University",
            "serial": tender_no,
            "tender_no": tender_no,
            "title": title,
            "agency": "Sultan Qaboos University",
            "governorate": "Muscat",
            "state": "Oman",
            "bank_guarantee": "",
            "fee": "",
            "sales_start": item["invitation_date"],
            "sales_end": "",
            "purchase_start": "",
            "purchase_end": "",
            "submission_close": item["submission_close"],
            "bid_open": "",
            "tender_url": item["pdf_url"],
            "keyword_matches": matches,
        })

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"✅ SQU matched tenders exported: {len(output)}")
    print(f"💾 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
