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

# =========================================================
# CONFIGURATION & RECIPIENTS
# =========================================================
SHEET_NAME = "Oman Tenders"
SENDER_EMAIL = "your-email@gmail.com"   # 👈 APNA Gmail ID likhein
RECEIVER_EMAIL = "your-email@gmail.com" # 👈 Receiver Gmail ID likhein

KEYWORDS = [
    "network", "networking", "it infrastructure", "cctv", "surveillance", 
    "interactive display", "smart board", "telecommunication", "telecom",
    "software", "server", "switch", "router", "hardware", "cabling", "computer",
    "fiber", "hybrid fiber", "cable",
    "شبكات", "شبكة", "تقنية المعلومات", "اتصالات", "شاشة", "شاشات", 
    "كمبيوتر", "حاسب آلي", "برمجيات", "أنظمة", "كاميرات", "مراقبة", "سيرفر"
]

if os.environ.get("GOOGLE_CREDENTIALS"):
    with open("credentials.json", "w") as f:
        f.write(os.environ.get("GOOGLE_CREDENTIALS"))

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
try:
    creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPE)
    client = gspread.authorize(creds)
    sheet = client.open(SHEET_NAME).sheet1
except Exception as e:
    print(f"❌ Google Sheet Connection Error: {e}")
    exit()

def send_email_alert(new_tenders_list):
    gmail_pass = os.environ.get("GMAIL_PASSWORD")
    if not gmail_pass: return

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = f"🚀 Alert: {len(new_tenders_list)} New Oman Tenders Matched!"

    html = f"""
    <html>
    <body>
        <h2>Bhai, New Tenders Matched Your ICT/ELV Keywords!</h2>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse; font-family:Arial;">
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
                <td><b>{t[1]}</b></td>
                <td>{t[2]}</td>
                <td>{t[3]}</td>
                <td>{t[4]}</td>
                <td>{t[8]}</td>
            </tr>
        """
    html += "</table></body></html>"
    msg.attach(MIMEText(html, 'html'))
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, gmail_pass)
        server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"❌ Email Alert Error: {e}")

def translate_to_english(text):
    if not text or not text.strip(): return "N/A"
    try:
        time.sleep(0.5)
        return GoogleTranslator(source='auto', target='en').translate(text)
    except:
        return text

def parse_sequential_dates(full_text):
    """Bina kisi data compression ke strict format me dates select karna"""
    # DD-MM-YYYY HH:MM ya plain DD-MM-YYYY ke saare instances pure text se order me nikalna
    raw_dates = re.findall(r"\d{2}-\d{2}-\d{4}(?:\s+\d{2}:\d{2})?", full_text)
    
    # Har date ke aage single quote (') force karna bina sorting chhede
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
        
        base_url = "https://etendering.tenderboard.gov.om/product/publicDash?viewFlag=NewTenders"
        print("🚀 System Init: Connecting to Oman Tender Board Cloud Node...")
        await page.goto(base_url, wait_until="networkidle")
        
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        total_pages = get_total_pages(soup)
        print(f"📊 Total Pages detected: {total_pages}. Scanning...\n")
        
        all_rows = sheet.get_all_values()
        existing_tenders = [row[1] for row in all_rows] if len(all_rows) > 0 else []
        new_rows_session = []
        
        for current_page in range(1, total_pages + 1):
            url = f"{base_url}&pageNo={current_page}"
            print(f"📄 Scanning Page {current_page}/{total_pages}...")
            
            try:
                await page.goto(url, wait_until="networkidle", timeout=60000)
            except Exception:
                await asyncio.sleep(3)
                await page.goto(url, wait_until="networkidle", timeout=60000)
                
            await asyncio.sleep(2)
            content = await page.content()
            soup = BeautifulSoup(content, 'html.parser')
            
            tables = soup.find_all('table')
            if len(tables) < 2: continue
                
            tender_table = tables[1]
            rows = tender_table.find_all('tr')[1:]
            
            for index, row in enumerate(rows):
                cols = row.find_all('td')
                if len(cols) < 7: continue
                
                cols_text = [c.text.strip() for c in cols]
                tender_no = cols_text[1]
                tender_title = cols_text[2]
                agency = cols_text[3]
                category = cols_text[4]
                
                combined_text = f"{tender_title} {category}".lower()
                match_found = any(keyword in combined_text for keyword in KEYWORDS)
                
                if match_found:
                    print(f"   🎯 TARGET MATCH FOUND: {tender_no}")
                    gov, state, bg, fee = ["N/A"] * 4
                    s_start, s_end, p_start, p_end, sub_close, bid_open = ["N/A"] * 6
                    
                    try:
                        row_locator = page.locator("table").nth(1).locator("tr").nth(index + 1)
                        clickable_icon = row_locator.locator("td").nth(9).locator("a, img, i").first
                        
                        if await clickable_icon.count() > 0:
                            popup_html = ""
                            try:
                                async with context.expect_page(timeout=6000) as new_page_info:
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
                                
                                # Pure chronological ordering fix
                                s_start, s_end, p_start, p_end, sub_close, bid_open = parse_sequential_dates(raw_text)
                                
                                # Safe English Parsing Layer
                                eng_text = translate_to_english(raw_text)
                                gov_m = re.search(r"(?:Governorate|Governorates)\s*:\s*([^:\n\d]+)", eng_text, re.IGNORECASE)
                                state_m = re.search(r"(?:State|States|Wilayat)\s*:\s*([^:\n\d]+)", eng_text, re.IGNORECASE)
                                bg_m = re.search(r"(?:Bank guarantee value|Bank Guarantee)\s*:\s*([^:\n]+)", eng_text, re.IGNORECASE)
                                fee_m = re.search(r"(?:Tender fees)\s*:\s*([^:\n]+)", eng_text, re.IGNORECASE)
                                
                                gov = gov_m.group(1).strip() if gov_m else "N/A"
                                state = state_m.group(1).strip() if state_m else "N/A"
                                bg = bg_m.group(1).strip() if bg_m else "N/A"
                                fee = fee_m.group(1).strip() if fee_m else "N/A"
                                
                                # Smart Fallback to raw layout tokens if English Translation drops out
                                if gov == "N/A" or "محافظة" in raw_text:
                                    gov_ar = re.search(r"(?:المحافظة|Governorate)\s*:\s*([^\n\d:]+)", raw_text, re.IGNORECASE)
                                    if gov_ar: gov = translate_to_english(gov_ar.group(1).split('\t')[0].strip())
                                if state == "N/A" or "الولاية" in raw_text:
                                    state_ar = re.search(r"(?:الولاية|State|Wilayat)\s*:\s*([^\n\d:]+)", raw_text, re.IGNORECASE)
                                    if state_ar: state = translate_to_english(state_ar.group(1).split('\t')[0].strip())
                                if bg == "N/A":
                                    bg_ar = re.search(r"(?:الضمان|Guarantee)\s*:\s*([^:\n]+)", raw_text, re.IGNORECASE)
                                    if bg_ar: bg = translate_to_english(bg_ar.group(1).strip())
                                if fee == "N/A":
                                    fee_ar = re.search(r"(?:رسوم|Fees)\s*:\s*([^:\n]+)", raw_text, re.IGNORECASE)
                                    if fee_ar: fee = translate_to_english(fee_ar.group(1).strip())
                            
                            print(f"     ✓ Extracted -> Gov: {gov} | State: {state} | Start: {s_start}")
                    except Exception as e:
                        print(f"     ❌ Action Extraction Failed: {e}")
                    
                    english_title = translate_to_english(tender_title)
                    english_agency = translate_to_english(agency)
                    row_values = [gov, state, bg, fee, s_start, s_end, p_start, p_end, sub_close, bid_open]
                    
                    if tender_no in existing_tenders:
                        sheet_row_idx = existing_tenders.index(tender_no) + 1
                        cell_range = f"E{sheet_row_idx}:N{sheet_row_idx}"
                        sheet.update(range_name=cell_range, values=[row_values])
                        print(f"     🔄 Updated Row {sheet_row_idx} details.")
                    else:
                        serial_no = len(existing_tenders) + len(new_rows_session) + 1
                        entry_pack = [serial_no, tender_no, english_title, english_agency] + row_values
                        new_rows_session.append(entry_pack)
                        print(f"     ✓ Added new entry to cache pack.")
                        
            if new_rows_session:
                sheet.append_rows(new_rows_session)
                existing_tenders.extend([r[1] for r in new_rows_session])
                send_email_alert(new_rows_session)
                new_rows_session = []
                
            await asyncio.sleep(2)

        print(f"\n🎉 ALL {total_pages} PAGES SCANNED COMPLETELY!")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
