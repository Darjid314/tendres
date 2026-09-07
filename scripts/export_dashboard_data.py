import os, json
from pathlib import Path
import gspread
from google.oauth2.service_account import Credentials

SHEET_NAME="Oman Tenders"
OUT=Path("docs/tenders.json")
scope=["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]

raw=os.environ.get("GOOGLE_CREDENTIALS")
if raw:
    Path("credentials.json").write_text(raw, encoding="utf-8")
creds=Credentials.from_service_account_file("credentials.json",scopes=scope)
sheet=gspread.authorize(creds).open(SHEET_NAME).sheet1
rows=sheet.get_all_values()

# test2.py columns:
# 0 serial, 1 tender no, 2 title, 3 agency, 4 governorate, 5 state,
# 6 bank guarantee, 7 fee, 8 sales start, 9 sales end,
# 10 purchase start, 11 purchase end, 12 submission close, 13 bid open.
out=[]
for r in rows[1:]:
    r=(r+[""]*14)[:14]
    out.append({
        "serial":r[0],"tender_no":r[1],"title":r[2],"agency":r[3],
        "governorate":r[4],"state":r[5],"bank_guarantee":r[6],"fee":r[7],
        "sales_start":r[8],"sales_end":r[9],"purchase_start":r[10],
        "purchase_end":r[11],"submission_close":r[12],"bid_open":r[13]
    })
OUT.parent.mkdir(exist_ok=True)
OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
print(f"Exported {len(out)} tenders to {OUT}")
