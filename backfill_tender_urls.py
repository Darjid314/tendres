import asyncio
import os
import re
from urllib.parse import urljoin

import gspread
from google.oauth2.service_account import Credentials
from playwright.async_api import async_playwright


SHEET_NAME = "Oman Tenders"

BASE_URL = (
    "https://etendering.tenderboard.gov.om/"
    "product/publicDash?viewFlag=NewTenders"
)

SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]


def is_real_url(value):
    if not value:
        return False

    value = str(value).strip()

    return (
        value.startswith(("http://", "https://"))
        and "tenderboard.gov.om" in value
    )


def extract_url(text, base):
    if not text:
        return ""

    text = str(text)

    # Direct full URL
    match = re.search(
        r'https?://[^"\'\s<>]*tenderboard\.gov\.om[^"\'\s<>]*',
        text
    )

    if match and is_real_url(match.group(0)):
        return match.group(0)

    # Relative URL hidden inside JavaScript/HTML
    matches = re.findall(
        r'["\']([^"\']*(?:tender|Tender|publicDash)[^"\']*)["\']',
        text
    )

    for match in matches:

        candidate = urljoin(
            base,
            match
        )

        if (
            is_real_url(candidate)
            and "publicDash" not in candidate
        ):
            return candidate

    return ""


async def safe_goto(
    page,
    url,
    label="page",
    attempts=3,
    timeout=60000
):
    """
    Safely load a Tender Board page.

    Retries temporary timeout/network failures.
    Returns True if successful.
    Returns False after all attempts fail.
    """

    for attempt in range(
        1,
        attempts + 1
    ):

        try:

            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=timeout
            )

            return True

        except Exception as e:

            print(
                f"   ⚠️ {label} load attempt "
                f"{attempt}/{attempts} failed: {e}"
            )

            if attempt < attempts:
                await asyncio.sleep(5)

    print(
        f"   ⏭️ Skipping {label} after "
        f"{attempts} failed attempts."
    )

    return False


async def click_for_url(
    context,
    page,
    row_locator
):
    """
    Try to extract the tender detail URL
    from the Action cell.

    This does NOT bypass authentication.
    """

    action = (
        row_locator
        .locator("td")
        .nth(9)
    )

    # -----------------------------------------
    # 1. Check Action cell HTML
    # -----------------------------------------

    try:

        html = await action.evaluate(
            "el => el.outerHTML"
        )

        found = extract_url(
            html,
            page.url
        )

        if found:
            return found

    except Exception:
        pass

    # -----------------------------------------
    # 2. Check action controls
    # -----------------------------------------

    controls = action.locator(
        "a,button,input,"
        "[onclick],[data-url],[data-href]"
    )

    try:
        control_count = await controls.count()
    except Exception:
        control_count = 0

    for i in range(
        min(control_count, 8)
    ):

        control = controls.nth(i)

        # -------------------------------------
        # Check attributes first
        # -------------------------------------

        for attr in (
            "href",
            "onclick",
            "data-url",
            "data-href"
        ):

            try:

                value = await control.get_attribute(
                    attr
                )

                found = extract_url(
                    value or "",
                    page.url
                )

                if found:
                    return found

            except Exception:
                continue

        # -------------------------------------
        # Try clicking
        # -------------------------------------

        old_url = page.url
        old_pages = list(context.pages)

        try:

            await control.click(
                timeout=5000
            )

            await asyncio.sleep(1.5)

            # ---------------------------------
            # Check newly opened tab/window
            # ---------------------------------

            for popup_page in list(
                context.pages
            ):

                if popup_page not in old_pages:

                    try:

                        await popup_page.wait_for_load_state(
                            "domcontentloaded",
                            timeout=10000
                        )

                    except Exception:
                        pass

                    popup_url = (
                        popup_page.url
                    )

                    if (
                        is_real_url(popup_url)
                        and "publicDash"
                        not in popup_url
                    ):

                        try:
                            await popup_page.close()
                        except Exception:
                            pass

                        return popup_url

                    try:
                        await popup_page.close()
                    except Exception:
                        pass

            # ---------------------------------
            # Check normal page navigation
            # ---------------------------------

            if (
                page.url != old_url
                and is_real_url(page.url)
                and "publicDash" not in page.url
            ):

                found_url = page.url

                try:

                    await page.go_back(
                        wait_until="domcontentloaded",
                        timeout=10000
                    )

                except Exception:

                    await safe_goto(
                        page,
                        old_url,
                        label="return page",
                        attempts=2,
                        timeout=30000
                    )

                return found_url

            # ---------------------------------
            # Check HTML after action/modal
            # ---------------------------------

            try:

                current_html = (
                    await page.content()
                )

                found = extract_url(
                    current_html,
                    page.url
                )

                if found:
                    return found

            except Exception:
                pass

        except Exception as e:

            print(
                f"      ⚠️ Action control "
                f"{i + 1} failed: {e}"
            )

            continue

    return ""


async def main():

    # =========================================
    # GOOGLE CREDENTIALS
    # =========================================

    raw_credentials = os.environ.get(
        "GOOGLE_CREDENTIALS"
    )

    if not raw_credentials:

        raise RuntimeError(
            "GOOGLE_CREDENTIALS is missing"
        )

    with open(
        "credentials.json",
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            raw_credentials
        )

    creds = (
        Credentials
        .from_service_account_file(
            "credentials.json",
            scopes=SCOPE
        )
    )

    sheet = (
        gspread
        .authorize(creds)
        .open(SHEET_NAME)
        .sheet1
    )

    # =========================================
    # READ GOOGLE SHEET
    # =========================================

    rows = sheet.get_all_values()

    if not rows:

        print(
            "No rows found."
        )

        return

    # =========================================
    # MAKE SURE COLUMN O EXISTS
    # =========================================

    header = list(rows[0])

    while len(header) < 15:
        header.append("")

    if not header[14]:

        sheet.update(
            "O1",
            [["Tender URL"]]
        )

        print(
            "✅ Column O header created: Tender URL"
        )

    # =========================================
    # FIND TENDERS WITHOUT URL
    # =========================================

    targets = {}

    for sheet_row, row in enumerate(
        rows[1:],
        start=2
    ):

        r = list(row)

        while len(r) < 15:
            r.append("")

        tender_no = r[1].strip()

        if (
            tender_no
            and not is_real_url(r[14])
        ):

            targets[tender_no] = sheet_row

    print(
        f"URLs to backfill: {len(targets)}"
    )

    if not targets:

        print(
            "Nothing to backfill."
        )

        return

    # =========================================
    # START PLAYWRIGHT
    # =========================================

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        context = await browser.new_context(
            locale="en-US",
            timezone_id="Asia/Muscat"
        )

        page = await context.new_page()

        # =====================================
        # INITIAL PAGE LOAD
        # =====================================

        loaded = await safe_goto(
            page,
            BASE_URL,
            label="initial Tender Board page",
            attempts=3,
            timeout=60000
        )

        if not loaded:

            print(
                "❌ Tender Board unavailable "
                "after 3 initial attempts."
            )

            await browser.close()

            return

        # =====================================
        # DETECT TOTAL PAGES
        # =====================================

        total_pages = 1

        try:

            table_count = await page.locator(
                "table"
            ).count()

            if table_count >= 3:

                pagination_text = (
                    await page
                    .locator("table")
                    .nth(2)
                    .inner_text()
                )

                numbers = re.findall(
                    r"\d+",
                    pagination_text
                )

                if numbers:

                    total_pages = max(
                        map(int, numbers)
                    )

        except Exception as e:

            print(
                f"⚠️ Could not detect "
                f"total pages: {e}"
            )

        print(
            f"📊 Pages detected: {total_pages}"
        )

        found = 0

        # =====================================
        # SCAN ALL PAGES
        # =====================================

        for page_no in range(
            1,
            total_pages + 1
        ):

            if not targets:

                print(
                    "\n🎉 All target URLs found."
                )

                break

            print(
                f"\n📄 Page "
                f"{page_no}/{total_pages}"
            )

            url = (
                f"{BASE_URL}"
                f"&pageNo={page_no}"
            )

            # =================================
            # SAFE PAGE LOAD
            # =================================

            page_loaded = await safe_goto(
                page,
                url,
                label=f"Page {page_no}",
                attempts=3,
                timeout=60000
            )

            if not page_loaded:

                continue

            # =================================
            # FIND TABLE
            # =================================

            try:

                table_count = await page.locator(
                    "table"
                ).count()

            except Exception:

                table_count = 0

            if table_count < 2:

                print(
                    f"   ⚠️ No tender table "
                    f"on Page {page_no}"
                )

                continue

            rows_locator = (
                page
                .locator("table")
                .nth(1)
                .locator("tr")
            )

            try:

                row_count = (
                    await rows_locator.count()
                )

            except Exception:

                row_count = 0

            # =================================
            # SCAN ROWS
            # =================================

            for i in range(
                1,
                row_count
            ):

                if not targets:
                    break

                row = rows_locator.nth(i)

                try:

                    cells = row.locator(
                        "td"
                    )

                    cell_count = (
                        await cells.count()
                    )

                except Exception:

                    continue

                if cell_count < 7:
                    continue

                try:

                    tender_no = (
                        await cells
                        .nth(1)
                        .inner_text()
                    ).strip()

                except Exception:

                    continue

                if tender_no not in targets:
                    continue

                print(
                    f"   🔎 Checking "
                    f"{tender_no}"
                )

                # =================================
                # GET DIRECT URL
                # =================================

                tender_url = await click_for_url(
                    context,
                    page,
                    row
                )

                if tender_url:

                    sheet_row = targets[
                        tender_no
                    ]

                    try:

                        sheet.update_cell(
                            sheet_row,
                            15,
                            tender_url
                        )

                        del targets[
                            tender_no
                        ]

                        found += 1

                        print(
                            f"      ✅ FOUND: "
                            f"{tender_url}"
                        )

                    except Exception as e:

                        print(
                            f"      ❌ Sheet update "
                            f"failed for "
                            f"{tender_no}: {e}"
                        )

                else:

                    print(
                        "      ⚠️ Not exposed "
                        "as a direct URL."
                    )

        # =====================================
        # CLOSE BROWSER
        # =====================================

        await browser.close()

    # =========================================
    # FINAL RESULT
    # =========================================

    print(
        "\n========== BACKFILL COMPLETE =========="
    )

    print(
        f"URLs found: {found}"
    )

    print(
        f"Still unresolved: {len(targets)}"
    )


if __name__ == "__main__":
    asyncio.run(main())
