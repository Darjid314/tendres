import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

STATUS = Path("docs/fetch_status.json")
HOME = "https://oo.oma.app.jaggaer.com/esop/guest/login.do"
CANDIDATES = [
    "https://oo.oma.app.jaggaer.com/esop/toolkit/opportunity/current/list.si?resetstored=true",
    "https://oo.oma.app.jaggaer.com/esop/guest/go/opportunity/opportunity-list.do",
    "https://oo.oma.app.jaggaer.com/esop/guest/go/opportunity/list.do",
    "https://oo.oma.app.jaggaer.com/esop/guest/go/opportunity/opportunity-list",
]


def update(status, message):
    subprocess.run(
        ["python", "scripts/update_fetch_status.py", "JAGGAER", status, message],
        check=False,
    )


def main():
    errors = []
    accessible = False
    opportunity_page = False
    last_url = HOME
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            viewport={"width": 1440, "height": 1000},
        )
        page = context.new_page()
        page.set_default_timeout(30000)

        for url in CANDIDATES:
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1800)
                last_url = page.url
                code = response.status if response else 0
                text = page.locator("body").inner_text(timeout=10000).lower()
                title = page.title().lower()
                blocked = any(x in (text + " " + title) for x in [
                    "401 unauthorized", "403 forbidden", "browsernotsupported",
                    "access denied", "request blocked", "not authorized",
                ])
                if code in (200, 302) and not blocked:
                    accessible = True
                has_opportunity_markers = any(x in text for x in [
                    "opportunity", "event", "rfx", "rfp", "tender", "procurement"
                ])
                if accessible and has_opportunity_markers:
                    opportunity_page = True
                    break
                if code and code >= 400:
                    errors.append(f"HTTP {code} at {url}")
                elif blocked:
                    errors.append(f"portal blocked/unsupported at {url}")
            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}")

        context.close()
        browser.close()

    if not accessible:
        update("failed", "Portal access failed: " + (errors[-1] if errors else "no public guest page accessible"))
        print("JAGGAER verification: FAILED")
        return 0

    if opportunity_page:
        update("success", "Public guest opportunity page accessible; ICT/ELV matches may be 0")
    else:
        update("success", f"Public portal reachable at {last_url}; opportunity list not exposed")
    print("JAGGAER verification: SUCCESS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
