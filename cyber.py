import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import gspread
from google.oauth2.service_account import Credentials
import re
import time
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from deep_translator import GoogleTranslator
import json
import base64

# =========================================================
# CONFIGURATION
# =========================================================
SHEET_NAME = "Oman Tenders"
TARGET_TAB_NAME = "Cybersecurity_Tenders"
SENDER_EMAIL = "darjid314@gmail.com"
RECEIVER_EMAIL = "sales@allakuniversal.com"

# Broad Cybersecurity & IT Security Keywords
KEYWORDS = [
    "cyber", "security", "infosec", "soc", "siem", "firewall", 
    "endpoint", "vulnerability", "penetration", "vapt", "dlp", 
    "zero trust", "network security", "threat", "edr", "xdr", 
    "iso 27001", "ciso", "iam", "identity", "waf", "ddos", "pam",
    "cloud security", "surveillance", "cctv", "data center",
    "الأمن السيبراني", "أمن المعلومات", "حماية البيانات", "الشبكات الأمنية", "أمن", "حماية", "مراقبة"
]

if os.environ.get("GOOGLE_CREDENTIALS"):
    raw_creds = os.environ.get("GOOGLE_CREDENTIALS")
    try:
        decoded = base64.b64decode(raw_creds).decode('utf-8')
        if "private_key" in decoded:
            raw_creds = decoded
    except Exception:
        pass
    with open("credentials.json", "w") as f:
        f.write(raw_creds)

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

try:
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPE)
    client = gspread.authorize(creds)
    try:
        spreadsheet = client.open(SHEET_NAME)
    except Exception:
        spreadsheet = client.openall()[0]

    try:
        sheet = spreadsheet.worksheet(TARGET_TAB_NAME)
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet(title=TARGET_TAB_NAME, rows="2500", cols="15")
        sheet.append_row([
            "S.No", "Tender No", "Tender Title (English)", "Agency (English)", 
            "Governorate", "State", "Bank Guarantee", "Tender Fee", 
            "Sales Start", "Sales End", "Proposal Start", "Proposal End", 
            "Submission Close", "Bid Opening"
        ])
    print(f"Connected to Sheet: {spreadsheet.title} | Tab: {TARGET_TAB_NAME}")
except Exception as e:
    print(f"Google Sheet Connection Error: {e}")
    exit()

def translate_to_english(text):
    if not text or not str(text).strip() or text == "N/A": 
        return "N/A"
    clean_text = str(text).strip()[:500]
    for attempt in range(2):
        try:
            time.sleep(0.3)
            translated = GoogleTranslator(source='auto', target='en').translate(clean_text)
            if translated and translated.strip():
                return translated
        except Exception:
            time.sleep(0.5)
    return clean_text

def parse_sequential_dates(full_text):
    raw_dates = re.findall(r"\d{2}-\d{2}-\d{4}(?:\s+\d{2}:\d{2})?", full_text)
    clean_dates = [f"'{d.strip()}" for d in raw_dates if d.strip()]
    s_start, s_end, p_start, p_end, sub_close, bid_open = ["N/A"] * 6
    if len(clean_dates) >= 1: s_start = clean_dates[0]
    if len(clean_dates) >= 2: s_end = clean_dates[1]
    if len(clean_dates) >= 3: p_start = clean_dates[2]
    if len(clean_dates) >= 4: p_end = clean_dates[3]
    if len(clean_dates) >= 5: sub_close = clean_dates[4]
    if len(clean_dates) >= 6: bid_open = clean_dates[5]
    return s_start, s_end, p_start, p_end, sub_close, bid_open

def get_total_pages(soup):
    try:
        tables = soup.find_all('table')
        if len(tables) >= 3:
            text = tables[2].get_text()
            pages = re.findall(r'\d+', text)
            if pages: return max(map(int, pages))
    except: pass
    return 1

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True) 
        context = await browser.new_context(locale="en-US", timezone_id="Asia/Muscat")
        page = await context.new_page()
        
        # Scrape both Search Tenders (Full Archive) & New Tenders
        endpoints = [
            "https://etendering.tenderboard.gov.om/product/publicDash?viewFlag=searchTenders",
            "https://etendering.tenderboard.gov.om/product/publicDash?viewFlag=NewTenders"
        ]
        
        all_rows = sheet.get_all_values()
        existing_tenders = set([row[1] for row in all_rows if len(row) > 1])
        new_rows_session = []
        
        for base_url in endpoints:
            print(f"\n--- Connecting to Section: {base_url} ---")
            try:
                await page.goto(base_url, wait_until="networkidle", timeout=90000)
            except Exception as e:
                print(f"Error opening section: {e}")
                continue
                
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            total_pages = get_total_pages(soup)
            print(f"Total Pages detected: {total_pages}")
            
            # Scan all pages
            for current_page in range(1, total_pages + 1):
                url = f"{base_url}&pageNo={current_page}"
                print(f"Scanning Page {current_page}/{total_pages}...")
                
                try:
                    await page.goto(url, wait_until="networkidle", timeout=60000)
                except Exception:
                    await asyncio.sleep(2)
                    await page.goto(url, wait_until="networkidle", timeout=60000)
                    
                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                tables = soup.find_all('table')
                if len(tables) < 2: 
                    continue
                    
                tender_table = tables[1]
                rows = tender_table.find_all('tr')[1:]
                
                for index, row in enumerate(rows):
                    cols = row.find_all('td')
                    if len(cols) < 7: 
                        continue
                    
                    cols_text = [c.text.strip() for c in cols]
                    tender_no = cols_text[1]
                    
                    if tender_no in existing_tenders:
                        continue
                    
                    tender_title = cols_text[2]
                    agency = cols_text[3]
                    category = cols_text[4]
                    
                    combined_text = f"{tender_title} {category} {agency}".lower()
                    match_found = any(keyword.lower() in combined_text for keyword in KEYWORDS)
                    
                    if match_found:
                        print(f" 🎯 [MATCH FOUND] {tender_no} | Title: {tender_title[:50]}")
                        gov, state, bg, fee = ["N/A"] * 4
                        s_start, s_end, p_start, p_end, sub_close, bid_open = ["N/A"] * 6
                        
                        try:
                            row_locator = page.locator("table").nth(1).locator("tr").nth(index + 1)
                            clickable_icon = row_locator.locator("td").nth(9).locator("a, img, i").first
                            
                            if await clickable_icon.count() > 0:
                                popup_html = ""
                                try:
                                    async with context.expect_page(timeout=5000) as new_page_info:
                                        await clickable_icon.click()
                                    popup_target_page = await new_page_info.value
                                    await popup_target_page.wait_for_load_state("networkidle")
                                    popup_html = await popup_target_page.content()
                                    await popup_target_page.close()
                                except Exception:
                                    await page.wait_for_load_state("networkidle")
                                    popup_html = await page.content()
                                    if "Tender Calendar Dates" in popup_html and "S.No" not in popup_html:
                                        await page.go_back(wait_until="networkidle")
                                
                                if popup_html:
                                    popup_soup = BeautifulSoup(popup_html, 'html.parser')
                                    raw_text = popup_soup.get_text()
                                    
                                    s_start, s_end, p_start, p_end, sub_close, bid_open = parse_sequential_dates(raw_text)
                                    
                                    gov_ar = re.search(r"(?:المحافظة|Governorate)\s*:\s*([^\n\r\t\d:]+)", raw_text, re.IGNORECASE)
                                    if gov_ar: gov = translate_to_english(gov_ar.group(1).split('\t')[0].strip())
                                        
                                    state_ar = re.search(r"(?:الولاية|State|Wilayat)\s*:\s*([^\n\r\t\d:]+)", raw_text, re.IGNORECASE)
                                    if state_ar: state = translate_to_english(state_ar.group(1).split('\t')[0].strip())
                                        
                                    bg_ar = re.search(r"(?:الضمان|Guarantee|Bank guarantee value)\s*:\s*([^:\n\r]+)", raw_text, re.IGNORECASE)
                                    if bg_ar: bg = translate_to_english(bg_ar.group(1).strip())
                                        
                                    fee_ar = re.search(r"(?:رسوم|Fees|Tender fees)\s*:\s*([^:\n\r]+)", raw_text, re.IGNORECASE)
                                    if fee_ar: fee = translate_to_english(fee_ar.group(1).strip())
                        except Exception as e:
                            print(f" Details extraction skipped: {e}")
                        
                        english_title = translate_to_english(tender_title)
                        english_agency = translate_to_english(agency)
                        row_values = [gov, state, bg, fee, s_start, s_end, p_start, p_end, sub_close, bid_open]
                        
                        serial_no = len(existing_tenders) + len(new_rows_session) + 1
                        entry_pack = [serial_no, tender_no, english_title, english_agency] + row_values
                        new_rows_session.append(entry_pack)
                        existing_tenders.add(tender_no)
                            
                if new_rows_session:
                    sheet.append_rows(new_rows_session)
                    print(f" ✅ Saved {len(new_rows_session)} tenders to Google Sheet tab.")
                    new_rows_session = []

        print(f"\n🎉 ALL ARCHIVE & NEW TENDERS SCANNED SUCCESSFULLY!")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
