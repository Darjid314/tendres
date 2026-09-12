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
OMANTEL_LOGIN = "https://tenders.omantel.om/esop/oma-host/public/omantel/web/login.jst?_ncp=1691918557028.5705-1"
OMANTEL = "https://tenders.omantel.om/esop/oma-host/public/omantel/rfpList.jsp?rfpType=InFlight"
JAGGAER_HOME = "https://oo.oma.app.jaggaer.com/esop/guest/login.do"
JAGGAER = "https://oo.oma.app.jaggaer.com/esop/toolkit/opportunity/current/list.si?resetstored=true"
JAGGAER_ALT = [
    "https://oo.oma.app.jaggaer.com/esop/guest/go/opportunity/opportunity-list.do",
    "https://oo.oma.app.jaggaer.com/esop/guest/go/opportunity/list.do",
    "https://oo.oma.app.jaggaer.com/esop/guest/go/opportunity/opportunity-list",
]
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
    for fmt in ("%d %b %Y %I:%M %p", "%d %b %Y %H:%M", "%d %B %Y %I:%M %p", "%d %B %Y %H:%M", "%d-%m-%Y %H:%M", "%d-%m-%Y", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
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

def fetch(session, url, bootstrap=None):
    last = None
    if bootstrap:
        try:
            r0 = session.get(bootstrap, headers={"User-Agent": UAS[0], "Accept": "text/html,application/xhtml+xml"}, timeout=45, allow_redirects=True)
            print(f"🔎 bootstrap GET {r0.status_code}: {r0.url} | {len(r0.text)} chars")
        except Exception as exc:
            print(f"⚠️ bootstrap failed {bootstrap}: {exc}")
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

def build_record(base, text, detail, source, source_name, title_hint=""):
    km = matches(text)
    if not km:
        return None
    title = clean(title_hint)
    if not title or title.lower() in {"view", "details", "more details", "open", "login"}:
        title = clean(text[:220])
    ref = ""
    for pat in (r"\bTD\d{2}-\d{4}\b", r"\b[A-Z]{1,10}[-_/]?\d{2,}[A-Z0-9/_-]*\b", r"\b\d{4,}\b"):
        m = re.search(pat, text, re.I)
        if m:
            ref = m.group(0)
            break
    dm = re.search(r"(?:bid\s+submission|submission|closing|deadline|due|close)[^\d]{0,70}(\d{1,2}[ /-][A-Za-z0-9]{2,9}[ /-]\d{2,4}(?:\s+\d{1,2}:\d{2}\s*(?:AM|PM)?)?)", text, re.I)
    deadline = normalize_date(dm.group(1)) if dm else ""
    if not active(deadline):
        return None
    key = ref or detail or title
    return {
        "source": source, "source_name": source_name,
        "serial": ref or key, "tender_no": ref or key,
        "title": title, "agency": source_name, "governorate": "", "state": "Oman",
        "bank_guarantee": "", "fee": "", "sales_start": "", "sales_end": "",
        "purchase_start": "", "purchase_end": "", "submission_close": deadline,
        "bid_open": "", "tender_url": detail or base, "keyword_matches": km,
    }

def extract_records(base, html, source, source_name, allow_missing_detail=False):
    soup = BeautifulSoup(html, "html.parser")
    records, seen = [], set()
    nodes = soup.find_all(["tr", "li", "article"])
    nodes += soup.select("[role='row'], .tableRow, .table-row, .rfpRow, .rfp-row, .opportunity, .opportunityRow")
    if not nodes:
        nodes = soup.find_all("div")
    for node in nodes:
        text = clean(node.get_text(" ", strip=True))
        if len(text) < 20 or not matches(text):
            continue
        links = [urljoin(base, a.get("href")) for a in node.find_all("a", href=True)]
        raw_attrs = " ".join(str(x) for tag in node.find_all(True) for x in tag.attrs.values()) + " " + " ".join(str(x) for x in node.attrs.values())
        for raw in (raw_attrs, text):
            for m in re.finditer(r"(?:rfp(?:Id)?|opportunityId|eventId|tender(?:Id)?)[=/'\" :]+([A-Za-z0-9_-]{3,})", raw, re.I):
                ident = m.group(1)
                if source == "OMANTEL":
                    links.append(urljoin(base, "rfpDetail.jsp?rfpId=" + ident))
                elif source == "JAGGAER":
                    links.append(urljoin(base, "/esop/guest/go/opportunity/detail?opportunityId=" + ident))
        detail = next((u for u in links if any(x in u.lower() for x in ("rfp", "tender", "opportunity", "event"))), "")
        if not detail and not allow_missing_detail:
            continue
        cells = [clean(x.get_text(" ", strip=True)) for x in node.find_all(["td", "th"])]
        anchors = [clean(a.get_text(" ", strip=True)) for a in node.find_all("a")]
        title = next((c for c in cells if len(c) > 12 and not re.search(r"deadline|closing|submission|published|date", c, re.I)), "")
        if not title:
            title = next((a for a in anchors if len(a) > 12 and a.lower() not in {"view", "details", "open"}), "")
        rec = build_record(base, text, detail or base, source, source_name, title)
        if not rec:
            continue
        key = f"{rec['tender_no']}|{rec['title']}"
        if key in seen:
            continue
        seen.add(key)
        records.append(rec)
    return records

def extract_omantel_fallback(base, html):
    soup = BeautifulSoup(html, "html.parser")
    records, seen = [], set()
    records.extend(extract_records(base, html, "OMANTEL", "Omantel", allow_missing_detail=True))
    for r in records:
        seen.add(f"{r['tender_no']}|{r['title']}")
    for tag in soup.find_all(["a", "button", "input"]):
        raw = clean(" ".join([tag.get_text(" ", strip=True), str(tag.get("value", "")), str(tag.get("onclick", "")), str(tag.get("href", ""))]))
        parent = tag
        for _ in range(4):
            if parent.parent:
                parent = parent.parent
        block = clean(parent.get_text(" ", strip=True))
        if not matches(block):
            continue
        href = tag.get("href", "")
        onclick = tag.get("onclick", "")
        detail = urljoin(base, href) if href and href.lower() not in {"#", "javascript:void(0)"} else ""
        if not detail:
            m = re.search(r"(?:rfp(?:Id)?|tender(?:Id)?)[=/'\" (,:]+([A-Za-z0-9_-]{3,})", onclick, re.I)
            if m:
                detail = urljoin(base, "rfpDetail.jsp?rfpId=" + m.group(1))
        rec = build_record(base, block, detail or base, "OMANTEL", "Omantel", clean(tag.get_text(" ", strip=True)))
        if not rec:
            continue
        key = f"{rec['tender_no']}|{rec['title']}"
        if key not in seen:
            seen.add(key)
            records.append(rec)
    print(f"🔎 OMANTEL fallback keyword blocks: {len(records)}")
    for r in records[:20]:
        print(f"   OMANTEL match: {r['tender_no']} | {r['title'][:180]} | {r['submission_close']}")
    return records

def extract_jaggaer(html, base):
    """Parse public Current Opportunities even when JAGGAER renders the table through JS/config blobs."""
    soup = BeautifulSoup(html, "html.parser")
    records, seen = [], set()
    records.extend(extract_records(base, html, "JAGGAER", "JAGGAER eSourcing (OO)", allow_missing_detail=False))
    for r in records:
        seen.add(f"{r['tender_no']}|{r['title']}")
    # Public JAGGAER pages often expose opportunity links in anchors/scripts even when rows are not
    # represented as <tr>. Inspect every detail URL and its nearby HTML text.
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "opportunity/detail" not in href.lower():
            continue
        detail = urljoin(base, href)
        parent = a
        for _ in range(5):
            if parent.parent:
                parent = parent.parent
        block = clean(parent.get_text(" ", strip=True))
        if not block:
            block = clean(a.get_text(" ", strip=True))
        rec = build_record(base, block, detail, "JAGGAER", "JAGGAER eSourcing (OO)", clean(a.get_text(" ", strip=True)))
        if rec:
            key = f"{rec['tender_no']}|{rec['title']}"
            if key not in seen:
                seen.add(key)
                records.append(rec)
    # Last-resort extraction from inline JS/JSON. Keep only contexts that actually contain our
    # existing ICT/ELV keywords, and require a public opportunityId before creating a record.
    raw = str(html)
    for m in re.finditer(r"opportunityId\s*[=:]\s*[\"']?([0-9]+)", raw, re.I):
        oid = m.group(1)
        lo = max(0, m.start() - 900)
        hi = min(len(raw), m.end() + 1800)
        context = BeautifulSoup(raw[lo:hi], "html.parser").get_text(" ", strip=True)
        if not matches(context):
            continue
        detail = urljoin(base, "/esop/guest/go/opportunity/detail?opportunityId=" + oid)
        # Prefer a quoted/string field that looks like a title; otherwise use the keyword context.
        title = ""
        for pat in (r"(?:name|title|description)\"?\s*[:=]\s*\"([^\"]{8,180})\"", r"(?:name|title|description)\"?\s*[:=]\s*'([^']{8,180})'"):
            tm = re.search(pat, raw[lo:hi], re.I)
            if tm:
                title = clean(tm.group(1))
                break
        rec = build_record(base, context, detail, "JAGGAER", "JAGGAER eSourcing (OO)", title)
        if rec:
            key = f"{rec['tender_no']}|{rec['title']}"
            if key not in seen:
                seen.add(key)
                records.append(rec)
    print(f"🔎 JAGGAER public parser records: {len(records)}")
    for r in records[:20]:
        print(f"   JAGGAER match: {r['tender_no']} | {r['title'][:180]} | {r['submission_close']}")
    return records

def main():
    session = requests.Session()
    session.headers.update({"Accept-Language": "en-US,en;q=0.9", "Referer": "https://tenders.omantel.om/"})
    all_new = []
    final_url, html = fetch(session, OMANTEL, bootstrap=OMANTEL_LOGIN)
    if html:
        print(f"🔎 OMANTEL fallback final URL: {final_url}")
        recs = extract_omantel_fallback(final_url, html)
        print(f"OMANTEL fallback ICT/ELV matches: {len(recs)}")
        all_new.extend(recs)
    j_session = requests.Session()
    j_session.headers.update({"Accept-Language": "en-US,en;q=0.9", "Referer": JAGGAER_HOME})
    try:
        r0 = j_session.get(JAGGAER_HOME, headers={"User-Agent": UAS[0], "Accept": "text/html,application/xhtml+xml"}, timeout=45, allow_redirects=True)
        print(f"🔎 JAGGAER bootstrap GET {r0.status_code}: {r0.url} | {len(r0.text)} chars")
    except Exception as exc:
        print(f"⚠️ JAGGAER bootstrap failed: {exc}")
    jaggaer_recs = []
    for candidate in [JAGGAER] + JAGGAER_ALT:
        final_url, html = fetch(j_session, candidate)
        if not html:
            continue
        print(f"🔎 JAGGAER fallback final URL: {final_url}")
        recs = extract_jaggaer(html, final_url)
        if recs:
            jaggaer_recs.extend(recs)
            break
    print(f"JAGGAER fallback ICT/ELV matches: {len(jaggaer_recs)}")
    all_new.extend(jaggaer_recs)
    try:
        with open(OUTPUT, "r", encoding="utf-8") as f:
            existing = json.load(f)
    except Exception:
        existing = []
    merged, seen = [], set()
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
