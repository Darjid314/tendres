import json
import re
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

OUTPUT = "docs/external_tenders.json"
KEYWORDS = [
    "network", "networking", "it infrastructure", "cctv", "surveillance",
    "interactive display", "smart board", "telecommunication", "telecom",
    "software", "server", "switch", "router", "hardware", "cabling",
    "computer", "fiber", "hybrid fiber", "cable",
    "شبكات", "شبكة", "تقنية المعلومات", "اتصالات", "شاشة", "شاشات",
    "كمبيوتر", "حاسب آلي", "برمجيات", "أنظمة", "كاميرات", "مراقبة", "سيرفر"
]
OMANTEL = "https://tenders.omantel.om/esop/oma-host/public/omantel/rfpList.jsp?rfpType=InFlight"
JAGGAER = "https://oo.oma.app.jaggaer.com/esop/toolkit/opportunity/current/list.si?resetstored=true"

UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/110.0.0.0 Safari/537.36",
]


def clean(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def matches(s):
    s = clean(s).lower()
    return [k for k in KEYWORDS if k.lower() in s]


def normalize_date(s):
    s = clean(s).replace("–", "-").replace("—", "-")
    for fmt in (
        "%d %b %Y %I:%M %p", "%d %b %Y %H:%M",
        "%d %B %Y %I:%M %p", "%d %B %Y %H:%M",
        "%d-%m-%Y %H:%M", "%d-%m-%Y",
        "%d/%m/%Y %H:%M", "%d/%m/%Y",
        "%Y-%m-%d %H:%M", "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(s, fmt).strftime("%d-%m-%Y %H:%M")
        except ValueError:
            pass
    return s


def active(deadline):
    if not deadline:
        return True
    try:
        dt = datetime.strptime(normalize_date(deadline), "%d-%m-%Y %H:%M")
        return dt.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc)
    except ValueError:
        return True


def fetch(session, url):
    last = None
    for ua in UAS:
        try:
            r = session.get(url, headers={"User-Agent": ua, "Accept": "text/html,application/xhtml+xml"}, timeout=45, allow_redirects=True)
            text = r.text
            print(f"🔎 fallback GET {r.status_code}: {r.url} | {len(text)} chars | UA Chrome/{ua.split('Chrome/')[1].split('.')[0] if 'Chrome/' in ua else 'Firefox'}")
            if r.ok and len(text) > 1500 and "Upgrade Your Browser" not in text:
                return r.url, text
            last = (r.url, text)
        except Exception as exc:
            print(f"⚠️ fallback GET failed {url}: {exc}")
    return last if last else (url, "")


def extract_records(base, html, source, source_name):
    soup = BeautifulSoup(html, "html.parser")
    records, seen = [], set()
    nodes = soup.find_all(["tr", "li", "article"])
    nodes += soup.select("[role='row'], .tableRow, .table-row, .rfpRow, .rfp-row, .opportunity, .opportunityRow")
    if not nodes:
        nodes = soup.find_all(["div"])
    for node in nodes:
        text = clean(node.get_text(" ", strip=True))
        if len(text) < 20:
            continue
        km = matches(text)
        if not km:
            continue
        links = [urljoin(base, a.get("href")) for a in node.find_all("a", href=True)]
        detail = next((u for u in links if any(x in u.lower() for x in ("rfp", "tender", "opportunity", "event"))), "")
        if not detail:
            # JAGGAER sometimes puts opportunity IDs in onclick/data attributes.
            raw = " ".join(str(x) for x in node.attrs.values())
            m = re.search(r"(?:opportunityId|opportunity|event)[=/'\" ]+(\d{3,})", raw, re.I)
            if m:
                detail = urljoin(base, "/esop/guest/go/opportunity/detail?opportunityId=" + m.group(1))
        if not detail:
            continue
        cells = [clean(x.get_text(" ", strip=True)) for x in node.find_all(["td", "th"])]
        title = cells[0] if cells else clean(node.find("a").get_text(" ", strip=True) if node.find("a") else "")
        if not title or title.lower() in {"view", "details", "more details", "open"}:
            title = text[:220]
        ref = ""
        for pat in (r"\bTD\d{2}-\d{4}\b", r"\b[A-Z]{1,10}[-_/]?\d{2,}[A-Z0-9/_-]*\b", r"\b\d{4,}\b"):
            m = re.search(pat, text, re.I)
            if m:
                ref = m.group(0)
                break
        dm = re.search(r"(?:submission|closing|deadline|due|close)[^\d]{0,50}(\d{1,2}[ /-][A-Za-z0-9]{2,9}[ /-]\d{2,4}(?:\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)?)", text, re.I)
        deadline = normalize_date(dm.group(1)) if dm else ""
        if not active(deadline):
            continue
        key = ref or detail
        if key in seen:
            continue
        seen.add(key)
        records.append({
            "source": source, "source_name": source_name,
            "serial": ref or key, "tender_no": ref or key,
            "title": title, "agency": source_name, "governorate": "", "state": "Oman",
            "bank_guarantee": "", "fee": "", "sales_start": "", "sales_end": "",
            "purchase_start": "", "purchase_end": "", "submission_close": deadline,
            "bid_open": "", "tender_url": detail, "keyword_matches": km,
        })
    return records


def main():
    session = requests.Session()
    session.headers.update({"Accept-Language": "en-US,en;q=0.9"})
    all_new = []
    for url, source, name in ((OMANTEL, "OMANTEL", "Omantel"), (JAGGAER, "JAGGAER", "JAGGAER eSourcing (OO)")):
        final_url, html = fetch(session, url)
        if not html:
            continue
        print(f"🔎 {source} fallback final URL: {final_url}")
        recs = extract_records(final_url, html, source, name)
        print(f"{source} fallback ICT/ELV matches: {len(recs)}")
        all_new.extend(recs)
    try:
        with open(OUTPUT, "r", encoding="utf-8") as f:
            existing = json.load(f)
    except Exception:
        existing = []
    merged = []
    seen = set()
    for item in existing + all_new:
        key = f"{item.get('source','')}|{item.get('tender_no','')}|{item.get('tender_url','')}"
        if key not in seen:
            seen.add(key)
            merged.append(item)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"✅ External fallback merged: {len(all_new)} new candidates; {len(merged)} total external records")


if __name__ == "__main__":
    main()
