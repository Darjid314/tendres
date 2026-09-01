import base64
import json
import os
import re
import time
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from google.oauth2.service_account import Credentials
import gspread
from playwright.sync_api import sync_playwright

# --- 1. GOOGLE SHEET AUTH (Uses your existing GOOGLE_CREDENTIALS) ---
scope = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]
raw_key = os.environ.get('GOOGLE_CREDENTIALS', '')

try:
  creds_dict = json.loads(raw_key)
except Exception:
  # Agar base64 encoded ya format issue ho
  try:
    decoded = base64.b64decode(raw_key).decode('utf-8')
    creds_dict = json.loads(decoded)
  except Exception:
    creds_dict = json.loads(raw_key.replace('\n', '\\n'))

if 'private_key' in creds_dict:
  creds_dict['private_key'] = creds_dict['private_key'].replace('\\n', '\n')

creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
client = gspread.authorize(creds)

# Sheet Setup - Ye aapki sheet me "Cybersecurity_Tenders" tab create/open karega
SHEET_NAME = 'Oman_Tenders_Tracker'
sh = client.open(SHEET_NAME)

try:
  worksheet = sh.worksheet('Cybersecurity_Tenders')
except gspread.WorksheetNotFound:
  worksheet = sh.add_worksheet(
      title='Cybersecurity_Tenders', rows='1000', cols='9'
  )
  worksheet.append_row([
      'Tender No',
      'Original Title (Arabic/Eng)',
      'Translated Title (English)',
      'Agency',
      'Category',
      'Purchase Deadline',
      'Submission Deadline',
      'Status',
      'Scraped Date',
  ])

# --- 2. CYBERSECURITY KEYWORDS ---
CYBER_KEYWORDS = [
    'cyber security',
    'cybersecurity',
    'information security',
    'infosec',
    'soc',
    'security operations center',
    'siem',
    'firewall',
    'endpoint security',
    'vulnerability assessment',
    'penetration testing',
    'vapt',
    'dlp',
    'zero trust',
    'network security',
    'threat intelligence',
    'edr',
    'xdr',
    'iso 27001',
    'ciso',
    'iam',
    'identity and access',
    'waf',
    'ddos',
    'pam',
    'cloud security',
    'الأمن السيبراني',
    'أمن المعلومات',
    'حماية البيانات',
]


def is_cyber(text):
  t = text.lower()
  return any(kw in t for kw in CYBER_KEYWORDS)


def safe_translate(text):
  try:
    if any('\u0600' <= char <= '\u06ff' for char in text):
      return GoogleTranslator(source='auto', target='en').translate(text)
    return text
  except Exception:
    return text


# --- 3. SCRAPING ALL PAGES VIA PLAYWRIGHT ---
def scrape_all_cyber_tenders():
  all_data = []
  with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=(
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            ' (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
    )
    page = context.new_page()

    print('Opening Oman Tender Board portal...')
    page.goto(
        'https://etendering.tenderboard.gov.om/supplier/public/tender/list',
        timeout=90000,
    )
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(5000)

    current_page = 1
    max_pages = 50

    while current_page <= max_pages:
      print(f'Scanning Page {current_page}...')
      html = page.content()
      soup = BeautifulSoup(html, 'html.parser')

      # Table rows detect karein
      rows = soup.find_all('tr')
      tender_count_on_page = 0

      for r in rows:
        cols = [c.text.strip() for c in r.find_all('td')]
        if len(cols) >= 4:
          tender_count_on_page += 1
          tender_no = cols[0]
          raw_title = cols[1]
          agency = cols[2] if len(cols) > 2 else ''
          p_deadline = cols[3] if len(cols) > 3 else ''
          s_deadline = cols[4] if len(cols) > 4 else ''
          status = cols[5] if len(cols) > 5 else 'Active'

          # Combine for keyword checking
          check_text = f'{raw_title} {agency} {tender_no}'

          if is_cyber(check_text):
            print(f'Matched: {raw_title}')
            eng_title = safe_translate(raw_title)
            all_data.append([
                tender_no,
                raw_title,
                eng_title,
                agency,
                'Cybersecurity',
                p_deadline,
                s_deadline,
                status,
                time.strftime('%Y-%m-%d'),
            ])

      print(
          f'Page {current_page} complete ({tender_count_on_page} total tenders'
          ' checked).'
      )

      # Next page click
      try:
        next_button = page.locator(
            "a:has-text('Next'), a[aria-label='Next'], .pagination-next, button:has-text('>')"
        ).first
        if (
            next_button.is_visible()
            and next_button.is_enabled()
            and current_page < max_pages
        ):
          next_button.click()
          page.wait_for_load_state('networkidle')
          page.wait_for_timeout(3000)
          current_page += 1
        else:
          print('Reached last page or no next button.')
          break
      except Exception as e:
        print(f'Pagination finished or stopped: {e}')
        break

    browser.close()

  # Append to Google Sheet
  if all_data:
    worksheet.append_rows(all_data)
    print(
        f'Done! Successfully added {len(all_data)} Cybersecurity tenders to'
        ' Google Sheet!'
    )
  else:
    print('Scan complete. No cybersecurity tenders matched.')


if __name__ == '__main__':
  scrape_all_cyber_tenders()
