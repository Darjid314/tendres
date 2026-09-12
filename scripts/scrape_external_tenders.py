import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

OUTPUT_FILE = "docs/external_tenders.json"
KEYWORDS = [
    "network", "networking", "it infrastructure", "cctv", "surveillance",
    "interactive display", "smart board", "telecommunication", "telecom",
    "software", "server", "switch", "router", "hardware", "cabling",
    "computer", "fiber", "hybrid fiber", "cable",
    "شبكات", "شبكة", "تقنية المعلومات", "اتصالات", "شاشة", "شاشات",
    "كمبيوتر", "حاسب آلي", "برمجيات", "أنظمة", "كاميرات", "مراقبة", "سيرفر"
]
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; OmanTenderCommandCenter/1.0)"}
OMAN_TZ = ZoneInfo("Asia/Muscat")
BEAH_LIST = "https://bidmate.beah.om/front-tender/tender-list/Vh13JKaNHVSAzFzLhlBzIouPabyA3YV0JitjzwsCc8Y%3D"
OMANTEL_LOGIN = "https://tenders.omantel.om/esop/oma-host/public/omantel/web/login.jst?_ncp=1691918557028.5705-1"
OMANTEL_LIST = "https://tenders.omantel.om/esop/oma-host/public/omantel/rfpList.jsp?rfpType=InFlight"
JAGGAER_HOME = "https://oo.oma.app.jaggaer.com/esop/guest/login.do"
JAGGAER_CANDIDATES = [
    "https://oo.oma.app.jaggaer.com/esop/toolkit/opportunity/current/list.si?resetstored=true",
    "https://oo.oma.app.jaggaer.com/esop/guest/go/opportunity/opportunity-list.do",
    "https://oo.oma.app.jaggaer.com/esop/guest/go/opportunity/list.do",
    "https://oo.oma.app.jaggaer.com/esop/guest/go/opportunity/opportunity-list",
]


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def keyword_matches(text):
    text = clean(text).lower()
    return [k for k in KEYWORDS if k.lower() in text]


def normalize_date(value):
    value = clean(value).replace("–", "-").replace("—", "-")
    value = re.sub(r"\s+", " ", value)
    if not value:
        return ""
    formats = [
        "%d %b %Y %I:%M %p", "%d %b %Y %H:%M",
        "%d %B %Y %I:%M %p", "%d %B %Y %H:%M",
        "%d-%m-%Y %H:%M", "%d-%m-%Y",
        "%d/%m/%Y %H:%M", "%d/%m/%Y",
        "%Y-%m-%d %H:%M", "%Y-%m-%d",
        "%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).strftime("%d-%m-%Y %H:%M")
        except ValueError:
            pass
    return value


def parsed_deadline(value):
    value = normalize_date(value)
    for fmt in ["%d-%m-%Y %H:%M", "%d-%m-%Y"]:
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=OMAN_TZ)
        except ValueError:
            pass
    return None


def active_deadline(value):
    dt = parsed_deadline(value)
    return dt is None or dt > datetime.now(OMAN_TZ)


def absolutize(base, href):
    return urljoin(base, href or "")


def beah_detail(page, url):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(700)
        text = clean(page.locator("body").inner_text())
        m = re.search(
            r"Bid Submission Date\s+(.*?)(?:\s+Clarification End Date|\s+Tender Sells End Date|$)",
            text, re.I
        )
        return normalize_date(m.group(1)) if m else ""
    except Exception as exc:
        print(f"⚠️ BEAH detail read failed: {url}: {exc}")
        return ""


def parse_beah(page):
    records, seen = [], set()
    for page_no in range(1, 11):
        url = BEAH_LIST if page_no == 1 else f"{BEAH_LIST}?page={page_no}"
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1200)
        soup = BeautifulSoup(page.content(), "html.parser")
        found = 0
        links = soup.select("a[href*='tender-preview']")
        for card in links:
            href = absolutize(url, card.get("href"))
            container = card
            for _ in range(5):
                if container.parent:
                    container = container.parent
            text = clean(container.get_text(" ", strip=True)) or clean(card.get_text(" ", strip=True))
            m = re.search(r"Tender Id\s*:?\s*(TD\d{2}-\d{4})", text, re.I)
            tender_no = m.group(1) if m else ""
            if not tender_no:
                m = re.search(r"TD\d{2}-\d{4}", text, re.I)
                tender_no = m.group(0) if m else ""
            if not tender_no or tender_no in seen:
                continue
            seen.add(tender_no)

            before_published = clean(re.split(r"\bPublished\b", text, maxsplit=1, flags=re.I)[0])
            title = before_published or clean(card.get_text(" ", strip=True))
            if title.lower() == "more details":
                title = ""
            matches = keyword_matches(" ".join([title, text]))
            if not matches:
                continue

            close_date = beah_detail(page, href)
            if not active_deadline(close_date):
                print(f"⏭️ BEAH expired: {tender_no} {close_date}")
                continue
            records.append({
                "source": "BEAH", "source_name": "be'ah / Bidmate",
                "serial": tender_no, "tender_no": tender_no,
                "title": title or "be'ah Tender", "agency": "be'ah",
                "governorate": "", "state": "Oman", "bank_guarantee": "", "fee": "",
                "sales_start": "", "sales_end": "", "purchase_start": "", "purchase_end": "",
                "submission_close": close_date, "bid_open": "", "tender_url": href,
                "keyword_matches": matches,
            })
            found += 1
        if page_no > 1 and not links:
            break
        print(f"BEAH page {page_no}: {found} active ICT/ELV matches")
    return records


def extract_url_from_text(base_url, value):
    if not value:
        return ""
    m = re.search(r"https?://[^\s'\"]+", value)
    if m:
        return m.group(0).rstrip(")];,\"'")
    m = re.search(r"(?:location\.href|window\.open)\s*\(?\s*['\"]([^'\"]+)", value, re.I)
    if m:
        return absolutize(base_url, m.group(1))
    return ""


def row_like_records(page, source, source_name, base_url):
    """Extract tender-like rows from classic tables AND div/list based e-procurement UIs."""
    soup = BeautifulSoup(page.content(), "html.parser")
    records, seen = [], set()
    containers = soup.find_all(["tr", "li", "article"])
    containers += soup.select("[role='row'], .tableRow, .table-row, .rfpRow, .rfp-row, .opportunity, .opportunityRow")

    for node in containers:
        text = clean(node.get_text(" ", strip=True))
        if len(text) < 15:
            continue
        anchors = node.find_all("a", href=True)
        links = [absolutize(base_url, a.get("href")) for a in anchors]
        for a in node.find_all("a"):
            links.append(extract_url_from_text(base_url, a.get("onclick", "")))
        for tag in node.find_all(True):
            links.append(extract_url_from_text(base_url, tag.get("onclick", "")))
        links = [u for u in links if u]
        detail = next((u for u in links if any(x in u.lower() for x in ["rfp", "tender", "opportunity", "event"])), "")
        if not detail:
            continue
        matches = keyword_matches(text)
        if not matches:
            continue
        values = [clean(x.get_text(" ", strip=True)) for x in node.find_all(["td", "th"])]
        title = values[0] if values else clean(anchors[0].get_text(" ", strip=True) if anchors else "")
        if not title or title.lower() in {"view", "details", "more details", "open", "login"}:
            parts = [p for p in re.split(r"\s+\|\s+", text) if p]
            title = next((p for p in parts if len(p) > 12 and not re.search(r"deadline|closing|submission|published|date", p, re.I)), text)
        ref = ""
        for pattern in [r"\b[A-Z]{1,8}[-_/]?\d{2,}[A-Z0-9/_-]*\b", r"\b\d{4,}\b"]:
            m = re.search(pattern, text, re.I)
            if m:
                ref = m.group(0)
                break
        close_date = ""
        m = re.search(r"(?:bid submission|submission|closing|close|deadline|due)[^\d]{0,40}(\d{1,2}[ /-][A-Za-z0-9]{2,9}[ /-]\d{2,4}(?:\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)?)", text, re.I)
        if m:
            close_date = normalize_date(m.group(1))
        key = ref or detail
        if key in seen:
            continue
        seen.add(key)
        records.append({
            "source": source, "source_name": source_name,
            "serial": ref or key, "tender_no": ref or key,
            "title": title or source_name, "agency": source_name,
            "governorate": "", "state": "Oman", "bank_guarantee": "", "fee": "",
            "sales_start": "", "sales_end": "", "purchase_start": "", "purchase_end": "",
            "submission_close": close_date, "bid_open": "", "tender_url": detail,
            "keyword_matches": matches,
        })
    return records


def parse_omantel(page):
    # The public RFP list can depend on the portal session; establish the public session first.
    try:
        page.goto(OMANTEL_LOGIN, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1200)
    except Exception as exc:
        print(f"⚠️ Omantel login/public landing failed: {exc}")
    page.goto(OMANTEL_LIST, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(3000)
    print(f"🔎 OMANTEL page: {page.url} | title={clean(page.title())}")
    body = clean(page.locator("body").inner_text())
    print(f"🔎 OMANTEL visible text: {len(body)} chars")
    records = row_like_records(page, "OMANTEL", "Omantel", page.url)

    # Some Oracle/Bravo pages render links through javascript rather than href attributes.
    if not records:
        soup = BeautifulSoup(page.content(), "html.parser")
        candidates = []
        for tag in soup.find_all(["a", "button"]):
            txt = clean(tag.get_text(" ", strip=True))
            raw = " ".join([tag.get("href", ""), tag.get("onclick", ""), txt])
            if keyword_matches(raw):
                candidates.append(raw)
        print(f"🔎 OMANTEL keyword-bearing interactive elements: {len(candidates)}")
        for raw in candidates[:100]:
            print(f"   OMANTEL candidate: {raw[:240]}")
    print(f"OMANTEL ICT/ELV matches: {len(records)}")
    return records


def parse_jaggaer(page):
    records, visited = [], set()
    urls = [JAGGAER_HOME] + JAGGAER_CANDIDATES
    for url in urls:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2200)
        except Exception as exc:
            print(f"⚠️ JAGGAER navigation failed: {url}: {exc}")
            continue
        print(f"🔎 JAGGAER page: {page.url} | title={clean(page.title())}")
        body = clean(page.locator("body").inner_text())
        print(f"🔎 JAGGAER visible text: {len(body)} chars")

        hrefs = page.locator("a[href]").evaluate_all("els => els.map(a => a.href)")
        details = [u for u in hrefs if "/opportunity/detail" in u.lower()]
        if details:
            print(f"🔎 JAGGAER opportunity detail links found: {len(details)}")
        for detail in details[:300]:
            if detail in visited:
                continue
            visited.add(detail)
            try:
                page.goto(detail, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(800)
                text = clean(page.locator("body").inner_text())
                matches = keyword_matches(text)
                if not matches:
                    continue
                h1 = page.locator("h1")
                title = clean(h1.first.inner_text()) if h1.count() else clean(page.title())
                ref_match = re.search(r"(?:opportunity|event|ITT|RFX)[^0-9]{0,30}(\d{3,})", detail, re.I)
                ref = ref_match.group(1) if ref_match else detail
                dm = re.search(r"(?:submission|closing|deadline|due)[^\d]{0,40}(\d{1,2}[ /-][A-Za-z0-9]{2,9}[ /-]\d{2,4}(?:\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)?)", text, re.I)
                close_date = normalize_date(dm.group(1)) if dm else ""
                if not active_deadline(close_date):
                    continue
                records.append({
                    "source": "JAGGAER", "source_name": "JAGGAER eSourcing (OO)",
                    "serial": ref, "tender_no": ref, "title": title or "JAGGAER Tender",
                    "agency": "JAGGAER eSourcing", "governorate": "", "state": "Oman",
                    "bank_guarantee": "", "fee": "", "sales_start": "", "sales_end": "",
                    "purchase_start": "", "purchase_end": "", "submission_close": close_date,
                    "bid_open": "", "tender_url": detail, "keyword_matches": matches,
                })
            except Exception as exc:
                print(f"⚠️ JAGGAER opportunity read failed: {detail}: {exc}")
        if records:
            break
        generic = row_like_records(page, "JAGGAER", "JAGGAER eSourcing (OO)", page.url)
        if generic:
            records.extend(generic)
            break
    print(f"JAGGAER ICT/ELV matches: {len(records)}")
    return records


def dedupe(records):
    out, seen = [], set()
    for item in records:
        key = f"{item.get('source','')}|{item.get('tender_no','')}|{item.get('tender_url','')}"
        if key not in seen:
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
                print(f"⚠️ {name} scraper failed: {exc}")
        browser.close()
    all_records = dedupe(all_records)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)
    print(f"✅ External tender matches exported: {len(all_records)}")
    print(f"💾 {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
