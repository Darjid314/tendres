import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials
import re
import time
import os
import smtplib
import json

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from deep_translator import GoogleTranslator
from urllib.parse import urljoin


# =========================================================
# CONFIG
# =========================================================

SHEET_NAME = "Oman Tenders"

SENDER_EMAIL = "darjid314@gmail.com"
RECEIVER_EMAIL = "sales@allakuniversal.com"

BASE_URL = (
    "https://etendering.tenderboard.gov.om/"
    "product/publicDash?viewFlag=NewTenders"
)

SEEN_FILE = "portal_seen_tenders.json"


# =========================================================
# ICT / ELV KEYWORDS
# =========================================================

KEYWORDS = [
    "network",
    "networking",
    "it infrastructure",
    "cctv",
    "surveillance",
    "interactive display",
    "smart board",
    "telecommunication",
    "telecom",
    "software",
    "server",
    "switch",
    "router",
    "hardware",
    "cabling",
    "computer",
    "fiber",
    "hybrid fiber",
    "cable",

    "شبكات",
    "شبكة",
    "تقنية المعلومات",
    "اتصالات",
    "شاشة",
    "شاشات",
    "كمبيوتر",
    "حاسب آلي",
    "برمجيات",
    "أنظمة",
    "كاميرات",
    "مراقبة",
    "سيرفر"
]


# =========================================================
# GOOGLE SHEET AUTH
# =========================================================

if os.environ.get("GOOGLE_CREDENTIALS"):

    with open(
        "credentials.json",
        "w",
        encoding="utf-8"
    ) as f:

        f.write(
            os.environ.get("GOOGLE_CREDENTIALS")
        )


SCOPE = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]


try:

    creds = Credentials.from_service_account_file(
        "credentials.json",
        scopes=SCOPE
    )

    client = gspread.authorize(creds)

    sheet = (
        client
        .open(SHEET_NAME)
        .sheet1
    )

except Exception as e:

    print(
        f"❌ Google Sheet Connection Error: {e}"
    )

    raise


# =========================================================
# EMAIL ALERT
# =========================================================

def send_email_alert(new_tenders_list):

    gmail_pass = os.environ.get(
        "GMAIL_PASSWORD"
    )

    if not gmail_pass:
        return

    msg = MIMEMultipart()

    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL

    msg["Subject"] = (
        f"🚀 Alert: "
        f"{len(new_tenders_list)} "
        f"New Oman Tenders Matched!"
    )

    html = """
    <html>
    <body>

        <h2>
            Bhai, New Tenders Matched
            Your ICT/ELV Keywords!
        </h2>

        <table
            border="1"
            cellpadding="5"
            cellspacing="0"
            style="
                border-collapse:collapse;
                font-family:Arial;
            "
        >

            <tr style="background-color:#f2f2f2;">

                <th>Tender No</th>
                <th>Title</th>
                <th>Agency</th>
                <th>Governorate</th>
                <th>Sales Start</th>

            </tr>
    """

    for t in new_tenders_list:

        html += f"""
            <tr>

                <td>
                    <b>{t[1]}</b>
                </td>

                <td>
                    {t[2]}
                </td>

                <td>
                    {t[3]}
                </td>

                <td>
                    {t[4]}
                </td>

                <td>
                    {t[8]}
                </td>

            </tr>
        """

    html += """
        </table>

    </body>
    </html>
    """

    msg.attach(
        MIMEText(
            html,
            "html"
        )
    )

    try:

        server = smtplib.SMTP(
            "smtp.gmail.com",
            587
        )

        server.starttls()

        server.login(
            SENDER_EMAIL,
            gmail_pass
        )

        server.sendmail(
            SENDER_EMAIL,
            RECEIVER_EMAIL,
            msg.as_string()
        )

        server.quit()

        print(
            "📨 Email alert sent successfully!"
        )

    except Exception as e:

        print(
            f"❌ Email Alert Error: {e}"
        )


# =========================================================
# TRANSLATION
# =========================================================

def translate_to_english(text):

    if (
        not text
        or not str(text).strip()
        or text == "N/A"
    ):
        return "N/A"

    clean_text = (
        str(text)
        .strip()
        [:500]
    )

    for attempt in range(2):

        try:

            time.sleep(0.5)

            translated = GoogleTranslator(
                source="auto",
                target="en"
            ).translate(
                clean_text
            )

            if (
                translated
                and
                "500 (server error)"
                in translated.lower()
            ):

                time.sleep(1)
                continue

            if (
                translated
                and translated.strip()
            ):

                return translated

        except Exception:

            time.sleep(1)

    return clean_text


# =========================================================
# DATE PARSER
# =========================================================

def parse_sequential_dates(full_text):

    raw_dates = re.findall(
        r"\d{2}-\d{2}-\d{4}(?:\s+\d{2}:\d{2})?",
        full_text
    )

    clean_dates = [
        f"'{d.strip()}"
        for d in raw_dates
        if d.strip()
    ]

    (
        s_start,
        s_end,
        p_start,
        p_end,
        sub_close,
        bid_open
    ) = ["N/A"] * 6

    if len(clean_dates) >= 1:
        s_start = clean_dates[0]

    if len(clean_dates) >= 2:
        s_end = clean_dates[1]

    if len(clean_dates) >= 3:
        p_start = clean_dates[2]

    if len(clean_dates) >= 4:
        p_end = clean_dates[3]

    if len(clean_dates) >= 5:
        sub_close = clean_dates[4]

    if len(clean_dates) >= 6:
        bid_open = clean_dates[5]

    return (
        s_start,
        s_end,
        p_start,
        p_end,
        sub_close,
        bid_open
    )


# =========================================================
# TOTAL PAGES
# =========================================================

def get_total_pages(soup):

    try:

        tables = soup.find_all(
            "table"
        )

        if len(tables) >= 3:

            text = tables[2].get_text()

            pages = re.findall(
                r"\d+",
                text
            )

            if pages:

                return max(
                    map(
                        int,
                        pages
                    )
                )

    except Exception:

        pass

    return 1


# =========================================================
# URL VALIDATION
# =========================================================

def is_real_url(value):

    if not value:
        return False

    value = str(value).strip()

    return (
        value.startswith(
            (
                "http://",
                "https://"
            )
        )
        and
        "tenderboard.gov.om"
        in value
    )


# =========================================================
# LOAD PORTAL SEEN STATE
# =========================================================

def load_seen_portal_tenders():

    if not os.path.exists(
        SEEN_FILE
    ):

        print(
            "🆕 No portal history found."
        )

        print(
            "   First run will build "
            "the portal index."
        )

        return set()

    try:

        with open(
            SEEN_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if isinstance(
            data,
            list
        ):

            return set(
                str(x).strip()
                for x in data
                if str(x).strip()
            )

    except Exception as e:

        print(
            f"⚠️ Portal history read error: {e}"
        )

    return set()


# =========================================================
# SAVE PORTAL SEEN STATE
# =========================================================

def save_seen_portal_tenders(
    seen_tenders
):

    try:

        data = sorted(
            list(seen_tenders)
        )

        with open(
            SEEN_FILE,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )

        print(
            f"💾 Portal history saved: "
            f"{len(data)} tender numbers"
        )

    except Exception as e:

        print(
            f"❌ Could not save portal history: {e}"
        )


# =========================================================
# SAFE PAGE LOAD
# =========================================================

async def safe_goto(
    page,
    url,
    label,
    attempts=3,
    timeout=30000
):

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

            # Give JS/table a moment
            await page.wait_for_timeout(
                1200
            )

            return True

        except Exception as e:

            print(
                f"⚠️ {label} "
                f"load attempt "
                f"{attempt}/{attempts} failed: "
                f"{str(e)[:180]}"
            )

            if attempt < attempts:

                await asyncio.sleep(3)

    print(
        f"⏭️ Skipping {label} "
        "after failed attempts."
    )

    return False


# =========================================================
# MAIN
# =========================================================

async def main():

    seen_portal_tenders = (
        load_seen_portal_tenders()
    )

    first_index_build = (
        len(seen_portal_tenders) == 0
    )

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        context = await browser.new_context(
            locale="en-US",
            timezone_id="Asia/Muscat"
        )

        page = await context.new_page()

        print(
            "🚀 System Init: "
            "Connecting to Oman Tender Board..."
        )

        # -------------------------------------------------
        # FIRST PAGE
        # -------------------------------------------------

        loaded = await safe_goto(
            page,
            BASE_URL,
            "Initial Tender Board",
            attempts=3,
            timeout=30000
        )

        if not loaded:

            await browser.close()

            raise RuntimeError(
                "Could not load Oman Tender Board."
            )

        content = await page.content()

        soup = BeautifulSoup(
            content,
            "html.parser"
        )

        total_pages = get_total_pages(
            soup
        )

        print(
            f"📊 Total Pages detected: "
            f"{total_pages}"
        )

        if first_index_build:

            print(
                "🧱 FIRST INDEX BUILD MODE"
            )

            print(
                "   All pages will be scanned "
                "once to create portal history."
            )

        else:

            print(
                "⚡ INCREMENTAL MODE"
            )

            print(
                "   Scanner will stop when it "
                "reaches an entirely known page."
            )

        # -------------------------------------------------
        # GOOGLE SHEET EXISTING TENDERS
        # -------------------------------------------------

        all_rows = sheet.get_all_values()

        existing_tenders = set()

        for row in all_rows:

            if len(row) > 1:

                tender_no = (
                    str(row[1])
                    .strip()
                )

                if tender_no:

                    existing_tenders.add(
                        tender_no
                    )

        print(
            f"📚 Existing ICT/ELV tenders "
            f"in Sheet: "
            f"{len(existing_tenders)}"
        )

        # -------------------------------------------------
        # SESSION
        # -------------------------------------------------

        new_rows_session = []

        pages_scanned = 0

        stop_incremental = False

        # -------------------------------------------------
        # PAGE LOOP
        # -------------------------------------------------

        for current_page in range(
            1,
            total_pages + 1
        ):

            if stop_incremental:

                break

            url = (
                f"{BASE_URL}"
                f"&pageNo={current_page}"
            )

            print(
                f"\n📄 Scanning Page "
                f"{current_page}/{total_pages}..."
            )

            loaded = await safe_goto(
                page,
                url,
                f"Page {current_page}",
                attempts=3,
                timeout=30000
            )

            if not loaded:

                continue

            pages_scanned += 1

            content = await page.content()

            soup = BeautifulSoup(
                content,
                "html.parser"
            )

            tables = soup.find_all(
                "table"
            )

            if len(tables) < 2:

                print(
                    "⚠️ Tender table not found."
                )

                continue

            tender_table = tables[1]

            rows = tender_table.find_all(
                "tr"
            )[1:]

            page_tender_numbers = []

            page_has_unseen = False

            page_new_matches = 0

            # -------------------------------------------------
            # READ ALL TENDER NUMBERS ON PAGE
            # -------------------------------------------------

            for row in rows:

                cols = row.find_all(
                    "td"
                )

                if len(cols) < 7:

                    continue

                cols_text = [
                    c.get_text(
                        " ",
                        strip=True
                    )
                    for c in cols
                ]

                tender_no = (
                    cols_text[1]
                    .strip()
                )

                if not tender_no:

                    continue

                page_tender_numbers.append(
                    tender_no
                )

                # NEW PORTAL TENDER
                if (
                    tender_no
                    not in seen_portal_tenders
                ):

                    page_has_unseen = True

                    seen_portal_tenders.add(
                        tender_no
                    )

            # -------------------------------------------------
            # INCREMENTAL STOP
            # -------------------------------------------------

            if (
                not first_index_build
                and not page_has_unseen
            ):

                print(
                    "🛑 PAGE ALREADY FULLY KNOWN."
                )

                print(
                    f"   All {len(page_tender_numbers)} "
                    "tender numbers on this page "
                    "were already seen."
                )

                print(
                    "⚡ Incremental scan complete."
                )

                stop_incremental = True

                break

            # -------------------------------------------------
            # PROCESS NEW / UNKNOWN TENDERS
            # -------------------------------------------------

            for index, row in enumerate(
                rows
            ):

                cols = row.find_all(
                    "td"
                )

                if len(cols) < 7:

                    continue

                cols_text = [
                    c.get_text(
                        " ",
                        strip=True
                    )
                    for c in cols
                ]

                tender_no = (
                    cols_text[1]
                    .strip()
                )

                if not tender_no:

                    continue

                # Already stored in Google Sheet
                if tender_no in existing_tenders:

                    continue

                tender_title = (
                    cols_text[2]
                    .strip()
                )

                agency = (
                    cols_text[3]
                    .strip()
                )

                category = (
                    cols_text[4]
                    .strip()
                )

                combined_text = (
                    f"{tender_title} "
                    f"{category}"
                ).lower()

                match_found = any(
                    keyword in combined_text
                    for keyword in KEYWORDS
                )

                if not match_found:

                    continue

                page_new_matches += 1

                print(
                    f"   🎯 NEW TARGET MATCH FOUND: "
                    f"{tender_no}"
                )

                gov, state, bg, fee = [
                    "N/A"
                ] * 4

                (
                    s_start,
                    s_end,
                    p_start,
                    p_end,
                    sub_close,
                    bid_open
                ) = ["N/A"] * 6

                tender_url = "N/A"

                # -------------------------------------------------
                # DETAIL / ACTION
                # -------------------------------------------------

                try:

                    row_locator = (
                        page
                        .locator("table")
                        .nth(1)
                        .locator("tr")
                        .nth(index + 1)
                    )

                    action_cell = (
                        row_locator
                        .locator("td")
                        .nth(9)
                    )

                    # ---------------------------------------------
                    # DIRECT HREF
                    # ---------------------------------------------

                    anchors = action_cell.locator(
                        "a"
                    )

                    anchor_count = (
                        await anchors.count()
                    )

                    if anchor_count > 0:

                        for ai in range(
                            anchor_count
                        ):

                            href = await (
                                anchors
                                .nth(ai)
                                .get_attribute(
                                    "href"
                                )
                            )

                            if href:

                                candidate = urljoin(
                                    page.url,
                                    href
                                )

                                if is_real_url(
                                    candidate
                                ):

                                    tender_url = (
                                        candidate
                                    )

                                    print(
                                        "     🔗 Direct URL "
                                        "found from Action href"
                                    )

                                    break

                    # ---------------------------------------------
                    # POPUP / ACTION CLICK
                    # ---------------------------------------------

                    clickable_icon = (
                        action_cell
                        .locator(
                            "a, img, i"
                        )
                        .first
                    )

                    if (
                        await clickable_icon.count()
                        > 0
                    ):

                        popup_html = ""

                        try:

                            async with (
                                context.expect_page(
                                    timeout=6000
                                )
                            ) as new_page_info:

                                await clickable_icon.click()

                            popup_target_page = (
                                await new_page_info.value
                            )

                            try:

                                await popup_target_page.wait_for_load_state(
                                    "domcontentloaded",
                                    timeout=10000
                                )

                            except Exception:

                                pass

                            popup_url = (
                                popup_target_page.url
                            )

                            if is_real_url(
                                popup_url
                            ):

                                tender_url = (
                                    popup_url
                                )

                            popup_html = (
                                await popup_target_page.content()
                            )

                            await popup_target_page.close()

                        except Exception:

                            try:

                                await page.wait_for_load_state(
                                    "domcontentloaded",
                                    timeout=5000
                                )

                            except Exception:

                                pass

                            current_url = page.url

                            if (
                                is_real_url(
                                    current_url
                                )
                                and
                                "publicDash"
                                not in current_url
                            ):

                                tender_url = (
                                    current_url
                                )

                            popup_html = (
                                await page.content()
                            )

                            if (
                                "Tender Calendar Dates"
                                in popup_html
                                and
                                "S.No"
                                not in popup_html
                            ):

                                try:

                                    await page.go_back(
                                        wait_until="domcontentloaded",
                                        timeout=10000
                                    )

                                except Exception:

                                    pass

                        # -----------------------------------------
                        # DETAIL EXTRACTION
                        # -----------------------------------------

                        if popup_html:

                            popup_soup = (
                                BeautifulSoup(
                                    popup_html,
                                    "html.parser"
                                )
                            )

                            raw_text = (
                                popup_soup.get_text(
                                    " ",
                                    strip=True
                                )
                            )

                            (
                                s_start,
                                s_end,
                                p_start,
                                p_end,
                                sub_close,
                                bid_open
                            ) = parse_sequential_dates(
                                raw_text
                            )

                            gov_ar = re.search(
                                r"(?:المحافظة|Governorate)"
                                r"\s*:\s*([^\n\r\t\d:]+)",
                                raw_text,
                                re.IGNORECASE
                            )

                            if gov_ar:

                                gov = (
                                    translate_to_english(
                                        gov_ar
                                        .group(1)
                                        .split("\t")[0]
                                        .strip()
                                    )
                                )

                            state_ar = re.search(
                                r"(?:الولاية|State|Wilayat)"
                                r"\s*:\s*([^\n\r\t\d:]+)",
                                raw_text,
                                re.IGNORECASE
                            )

                            if state_ar:

                                state = (
                                    translate_to_english(
                                        state_ar
                                        .group(1)
                                        .split("\t")[0]
                                        .strip()
                                    )
                                )

                            bg_ar = re.search(
                                r"(?:الضمان|Guarantee|"
                                r"Bank guarantee value)"
                                r"\s*:\s*([^\n\r]+)",
                                raw_text,
                                re.IGNORECASE
                            )

                            if bg_ar:

                                bg = (
                                    translate_to_english(
                                        bg_ar
                                        .group(1)
                                        .strip()
                                    )
                                )

                            fee_ar = re.search(
                                r"(?:رسوم|Fees|Tender fees)"
                                r"\s*:\s*([^\n\r]+)",
                                raw_text,
                                re.IGNORECASE
                            )

                            if fee_ar:

                                fee = (
                                    translate_to_english(
                                        fee_ar
                                        .group(1)
                                        .strip()
                                    )
                                )

                    print(
                        f"     ✓ Extracted -> "
                        f"Gov: {gov} | "
                        f"State: {state}"
                    )

                    print(
                        f"     🔗 Direct Tender URL: "
                        f"{tender_url}"
                    )

                except Exception as e:

                    print(
                        f"     ❌ Scan Failed: {e}"
                    )

                # -------------------------------------------------
                # TRANSLATION
                # -------------------------------------------------

                english_title = (
                    translate_to_english(
                        tender_title
                    )
                )

                english_agency = (
                    translate_to_english(
                        agency
                    )
                )

                row_values = [

                    gov,
                    state,
                    bg,
                    fee,

                    s_start,
                    s_end,

                    p_start,
                    p_end,

                    sub_close,
                    bid_open

                ]

                serial_no = (
                    len(existing_tenders)
                    +
                    len(new_rows_session)
                    +
                    1
                )

                # -------------------------------------------------
                # 15 COLUMNS
                # -------------------------------------------------

                entry_pack = (

                    [
                        serial_no,
                        tender_no,
                        english_title,
                        english_agency
                    ]

                    +
                    row_values

                    +
                    [
                        tender_url
                    ]

                )

                new_rows_session.append(
                    entry_pack
                )

                print(
                    "     ✅ Tender prepared "
                    "for Google Sheet."
                )

            # -------------------------------------------------
            # SAVE NEW MATCHES AFTER EACH PAGE
            # -------------------------------------------------

            if new_rows_session:

                sheet.append_rows(
                    new_rows_session
                )

                existing_tenders.update(
                    r[1]
                    for r in new_rows_session
                )

                send_email_alert(
                    new_rows_session
                )

                print(
                    f"📨 Saved "
                    f"{len(new_rows_session)} "
                    "new matching tender(s)."
                )

                new_rows_session = []

            # -------------------------------------------------
            # PAGE SUMMARY
            # -------------------------------------------------

            print(
                f"   ✓ Page {current_page} complete"
            )

            print(
                f"   Portal tenders on page: "
                f"{len(page_tender_numbers)}"
            )

            print(
                f"   New ICT/ELV matches: "
                f"{page_new_matches}"
            )

        # -------------------------------------------------
        # SAVE PORTAL HISTORY
        # -------------------------------------------------

        save_seen_portal_tenders(
            seen_portal_tenders
        )

        print(
            "\n===================================="
        )

        print(
            "🎉 SCRAPER COMPLETE"
        )

        print(
            f"📄 Pages scanned: "
            f"{pages_scanned}"
        )

        print(
            f"📚 Portal history size: "
            f"{len(seen_portal_tenders)}"
        )

        if stop_incremental:

            print(
                "⚡ FAST INCREMENTAL STOP USED"
            )

        else:

            print(
                "🧱 FULL INDEX / SAFETY SCAN USED"
            )

        print(
            "===================================="
        )

        await browser.close()


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )
