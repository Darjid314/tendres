import asyncio
import os
import re
from urllib.parse import urljoin

import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright

SHEET_NAME = "Oman Tenders"
BASE_URL = "https://etendering.tenderboard.gov.om/product/publicDash?viewFlag=NewTenders"
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

def is_real_url(value):
    if not value:
        return False
    value = str(value).strip()
    return value.startswith(("http://", "https://")) and "tenderboard.gov.om" in value

def extract_url(text, base):
    if not text:
        return ""
    m = re.search(r'https?://[^"\'\s<>]*tenderboard\.gov\.om[^"\'\s<>]*', text)
    if m and is_real_url(m.group(0)):
        return m.group(0)
    for m in re.findall(r'["\']([^"\']*(?:tender|Tender|publicDash)[^"\']*)["\']', text):
        candidate = urljoin(base, m)
        if is_real_url(candidate) and "publicDash" not in candidate:
            return candidate
    return ""

async def click_for_url(context, page, row_locator):
    action = row_locator.locator("td").nth(9)
    html = await action.evaluate("el => el.outerHTML")
    found = extract_url(html, page.url)
    if found:
        return found

    controls = action.locator("a,button,input,[onclick],[data-url],[data-href]")
    for i in range(min(await controls.count(), 8)):
        c = controls.nth(i)
        for attr in ("href", "onclick", "data-url", "data-href"):
            value = await c.get_attribute(attr)
            found = extract_url(value or "", page.url)
            if found:
                return found

        old_url = page.url
        old_pages = list(context.pages)
        try:
            await c.click(timeout=5000)
            await asyncio.sleep(1.5)

            for p in context.pages:
                if p not in old_pages:
                    try:
                        await p.wait_for_load_state("domcontentloaded", timeout=8000)
                    except Exception:
                        pass
                    u = p.url
                    if is_real_url(u) and "publicDash" not in u:
                        await p.close()
                        return u
                    await p.close()

            if page.url != old_url and is_real_url(page.url) and "publicDash" not in page.url:
                u = page.url
                try:
                    await page.go_back(wait_until="domcontentloaded", timeout=10000)
                except Exception:
                    await page.goto(old_url, wait_until="domcontentloaded", timeout=30000)
                return u

            found = extract_url(await page.content(), page.url)
            if found:
                return found

            # If Action opens a modal, try links inside it.
            links = page.locator("a[href]")
            for j in range(min(await links.count(), 30)):
                href = await links.nth(j).get_attribute("href")
                u = urljoin(page.url, href or "")
                if is_real_url(u) and "publicDash" not in u:
                    try:
                        await page.go_back(wait_until="domcontentloaded", timeout=10000)
                    except Exception:
                        pass
                    return u
        except Exception:
            continue

    return ""

async def main():
    raw = os.environ.get("GOOGLE_CREDENTIALS")
    if not raw:
        raise RuntimeError("GOOGLE_CREDENTIALS is missing")

    with open("credentials.json", "w", encoding="utf-8") as f:
        f.write(raw)

    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPE)
    sheet = gspread.authorize(creds).open(SHEET_NAME).sheet1
    rows = sheet.get_all_values()

    if not rows:
        print("No rows found.")
        return

    header = list(rows[0]) + [""] * 15
    if not header[14]:
        sheet.update("O1", [["Tender URL"]])

    targets = {}
    for sheet_row, row in enumerate(rows[1:], start=2):
        r = list(row) + [""] * 15
        tender_no = r[1].strip()
        if tender_no and not is_real_url(r[14]):
            targets[tender_no] = sheet_row

    print(f"URLs to backfill: {len(targets)}")
    if not targets:
        print("Nothing to backfill.")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="en-US", timezone_id="Asia/Muscat")
        page = await context.new_page()

        await page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)

        total_pages = 1
        tables = await page.locator("table").count()
        if tables >= 3:
            txt = await page.locator("table").nth(2).inner_text()
            nums = re.findall(r"\d+", txt)
            if nums:
                total_pages = max(map(int, nums))

        print(f"Pages detected: {total_pages}")
        found = 0

        for page_no in range(1, total_pages + 1):
            print(f"Page {page_no}/{total_pages}")
            url = f"{BASE_URL}&pageNo={page_no}"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except Exception:
                await asyncio.sleep(2)
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            if await page.locator("table").count() < 2:
                continue

            rows_locator = page.locator("table").nth(1).locator("tr")
            count = await rows_locator.count()

            for i in range(1, count):
                row = rows_locator.nth(i)
                cells = row.locator("td")
                if await cells.count() < 7:
                    continue

                tender_no = (await cells.nth(1).inner_text()).strip()
                if tender_no not in targets:
                    continue

                print(f"  Checking {tender_no}")
                tender_url = await click_for_url(context, page, row)

                if tender_url:
                    sheet.update_cell(targets[tender_no], 15, tender_url)
                    del targets[tender_no]
                    found += 1
                    print(f"    FOUND: {tender_url}")
                else:
                    print("    Not exposed as a direct URL.")

        await browser.close()

    print("========== BACKFILL COMPLETE ==========")
    print(f"URLs found: {found}")
    print(f"Still unresolved: {len(targets)}")

if __name__ == "__main__":
    asyncio.run(main())
