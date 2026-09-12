import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

OUTPUT_FILE = "docs/external_tenders.json"

# Keep this EXACTLY aligned with the ICT / ELV keyword set already used by
# test2.py and the SQU scraper. No new keyword list is introduced here.
KEYWORDS = [
    "network", "networking", "it infrastructure", "cctv", "surveillance",
    "interactive display", "smart board", "telecommunication", "telecom",
    "software", "server", "switch", "router", "hardware", "cabling",
    "computer", "fiber", "hybrid fiber", "cable",
    "شبكات", "شبكة", "تقنية المعلومات", "اتصالات", "شاشة", "شاشات",
    "كمبيوتر", "حاسب آلي", "برمجيات", "أنظمة", "كاميرات", "مراقبة", "سيرفر"
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; OmanTenderCommandCenter/1.0)"}

BEAH_LIST = (
    "https://bidmate.beah.om/front-tender/tender-list/"
    "Vh13JKaNHVSAzFzLhlBzIouPabyA3YV0JitjzwsCc8Y%3D"
)
OMANTEL_LIST = "https://tenders.omantel.om/esop/oma-host/public/omantel/rfpList.jsp?rfpType=InFlight"
JAGGAER_HOME = "https://oo.oma.app.jaggaer.com/esop/guest/login.do"
JAGGAER_CANDIDATES = [
    "https://oo.oma.app.jaggaer.com/esop/guest/go/opportunity/opportunity-list.do",
    "https://oo.oma.app.jaggaer.com/esop/guest/go/opportunity/list.do",
    "https://oo.oma.app.jaggaer.com/esop/guest/go/opportunity/opportunity-list",
]


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def keyword_matches(text):
    haystack = clean(text).lower()
    return [k for k in KEYWORDS if k.lower() in haystack]


def normalize_date(value):
    value = clean(value)
    if not value:
        return ""
    formats = [
        "%d %b %Y %I:%M %p", "%d %b %Y %H:%M",
        "%d %B %Y %I:%M %p", "%d %B %Y %H:%M",
        "%d-%m-%Y %H:%M", "%d-%m-%Y", "%d/%m/%Y %H:%M", "%d/%m/%Y",
        "%Y-%m-%d %H:%M", "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).strftime("%d-%m-%Y %H:%M")
        except ValueError:
            pass
    # Handle strings with a trailing timezone or seconds conservatively.
    value2 = re.sub(r"\s+(GMT|UTC|Oman Time|OMT)$", "", value, flags=re.I)
    for fmt in formats:
        try:
            return datetime.strptime(value2, fmt).strftime("%d-%m-%Y %H:%M")
        except ValueError:
            pass
    return value


def absolutize(base, href):
    return urljoin(base, href or "")


def parse_beah(page):
    records = []
    seen = set()
    for page_no in range(1, 11):
        url = BEAH_LIST if page_no == 1 else f"{BEAH_LIST}?page={page_no}"
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1200)
        soup = BeautifulSoup(page.content(), "html.parser")
        found = 0
        for card in soup.select("a[href*='tender-preview']"):
            href = absolutize(url, card.get("href"))
            container = card
            for _ in range(4):
                if container.parent:
                    container = container.parent
            text = clean(container.get_text(" ", strip=True))
            if not text:
                text = clean(card.get_text(" ", strip=True))
            m = re.search(r"Tender Id\s*:?\s*(TD\d{2}-\d{4})", text, re.I)
            tender_no = m.group(1) if m else ""
            title = clean(card.get_text(" ", strip=True))
            if not tender_no:
                m = re.search(r"TD\d{2}-\d{4}", text)
                tender_no = m.group(0) if m else ""
            if not tender_no or tender_no in seen:
                continue
            seen.add(tender_no)
            # The listing card text begins with the tender title; remove common
            # labels when present.
            title = re.sub(r"^Published\s+", "", title, flags=re.I)
            matches = keyword_matches(" ".join([title, text]))
            if not matches:
                continue
            records.append({
                "source": "BEAH",
                "source_name": "be'ah / Bidmate",
                "serial": tender_no,
                "tender_no": tender_no,
                "title": title or "be'ah Tender",
                "agency": "be'ah",
                "governorate": "",
                "state": "Oman",
                "bank_guarantee": "",
                "fee": "",
                "sales_start": "",
                "sales_end": "",
                "purchase_start": "",
                "purchase_end": "",
                "submission_close": "",
                "bid_open": "",
                "tender_url": href,
                "keyword_matches": matches,
            })
            found += 1
        if page_no > 1 and not soup.select("a[href*='tender-preview']"):
            break
        print(f"BEAH page {page_no}: {found} ICT/ELV matches")
    return records


def table_records(page, source, source_name, base_url):
    soup = BeautifulSoup(page.content(), "html.parser")
    records = []
    seen = set()
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        values = [clean(c.get_text(" ", strip=True)) for c in cells]
        row_text = " | ".join(values)
        links = [absolutize(base_url, a.get("href")) for a in tr.find_all("a", href=True)]
        detail = next((u for u in links if any(x in u.lower() for x in ["rfp", "tender", "opportunity"])), "")
        # Capture likely reference numbers from the row. Keep this broad because
        # Omantel's eSourcing UI can change its column labels.
        ref = ""
        for pattern in [r"\b[A-Z]{1,8}[-_/]?\d{2,}[A-Z0-9/_-]*\b", r"\b\d{4,}\b"]:
            m = re.search(pattern, row_text, re.I)
            if m:
                ref = m.group(0)
                break
        title = values[0]
        # Prefer the longest non-date cell as title when the first cell is a
        # serial number.
        if re.fullmatch(r"[A-Z0-9/_-]{3,}", title or "") and len(values) > 1:
            candidates = [v for v in values[1:] if len(v) > len(title)]
            if candidates:
                title = candidates[0]
        matches = keyword_matches(row_text)
        if not matches or not detail:
            continue
        key = ref or detail
        if key in seen:
            continue
        seen.add(key)
        records.append({
            "source": source,
            "source_name": source_name,
            "serial": ref or key,
            "tender_no": ref or key,
            "title": title or source_name,
            "agency": source_name,
            "governorate": "",
            "state": "Oman",
            "bank_guarantee": "",
            "fee": "",
            "sales_start": "",
            "sales_end": "",
            "purchase_start": "",
            "purchase_end": "",
            "submission_close": "",
            "bid_open": "",
            "tender_url": detail,
            "keyword_matches": matches,
        })
    return records


def parse_omantel(page):
    page.goto(OMANTEL_LIST, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(2500)
    records = table_records(page, "OMANTEL", "Omantel", OMANTEL_LIST)
    print(f"OMANTEL ICT/ELV matches: {len(records)}")
    return records


def parse_jaggaer(page):
    # JAGGAER commonly exposes public opportunities through /guest/go/...
    # routes. Start at the supplied login URL and follow any public opportunity
    # links found on the page before trying known generic opportunity-list URLs.
    records = []
    visited = set()
    urls = [JAGGAER_HOME] + JAGGAER_CANDIDATES
    for url in urls:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1800)
        except Exception as exc:
            print(f"⚠️ JAGGAER navigation failed: {url}: {exc}")
            continue
        hrefs = page.locator("a[href]").evaluate_all("els => els.map(a => a.href)")
        detail_hrefs = [u for u in hrefs if "/opportunity/detail" in u.lower()]
        if detail_hrefs:
            for detail in detail_hrefs[:200]:
                if detail in visited:
                    continue
                visited.add(detail)
                try:
                    page.goto(detail, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(700)
                    text = clean(page.locator("body").inner_text())
                    matches = keyword_matches(text)
                    if not matches:
                        continue
                    title = ""
                    h1 = page.locator("h1")
                    if h1.count():
                        title = clean(h1.first.inner_text())
                    if not title:
                        title = clean(page.title())
                    m = re.search(r"(?:opportunity|event|ITT|RFX)[^0-9]{0,30}(\d{3,})", detail, re.I)
                    ref = m.group(1) if m else detail
                    records.append({
                        "source": "JAGGAER",
                        "source_name": "JAGGAER eSourcing (OO)",
                        "serial": ref,
                        "tender_no": ref,
                        "title": title or "JAGGAER Tender",
                        "agency": "JAGGAER eSourcing",
                        "governorate": "",
                        "state": "Oman",
                        "bank_guarantee": "",
                        "fee": "",
                        "sales_start": "",
                        "sales_end": "",
                        "purchase_start": "",
                        "purchase_end": "",
                        "submission_close": "",
                        "bid_open": "",
                        "tender_url": detail,
                        "keyword_matches": matches,
                    })
                except Exception as exc:
                    print(f"⚠️ JAGGAER opportunity read failed: {detail}: {exc}")
            if records:
                break
        else:
            # Some JAGGAER list pages render the opportunities directly in a
            # table rather than as detail links in the initial HTML.
            generic = table_records(page, "JAGGAER", "JAGGAER eSourcing (OO)", url)
            if generic:
                records.extend(generic)
                break
    print(f"JAGGAER ICT/ELV matches: {len(records)}")
    return records


def dedupe(records):
    out = []
    seen = set()
    for item in records:
        key = f"{item.get('source','')}|{item.get('tender_no','')}|{item.get('tender_url','')}"
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(extra_http_headers=HEADERS)
        all_records = []
        for name, fn in [("BEAH", parse_beah), ("OMANTEL", parse_omantel), ("JAGGAER", parse_jaggaer)]:
            try:
                all_records.extend(fn(page))
            except Exception as exc:
                # One portal must never stop the other portal scrapers or the
                # existing Oman/SQU workflow.
                print(f"⚠️ {name} scraper failed: {exc}")
        browser.close()

    all_records = dedupe(all_records)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)
    print(f"✅ External tender matches exported: {len(all_records)}")
    print(f"💾 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
