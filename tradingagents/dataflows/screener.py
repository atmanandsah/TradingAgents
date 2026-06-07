"""Screener.in scraper — direct DOM extraction (no screenshots, no vision model).

Strategy:
1. Open screener.in via Playwright CDP.
2. Scroll full page to trigger lazy-loading of all sections.
3. Extract table data directly from the DOM using JavaScript.
4. Return structured plain-text tables for llama3.1 to analyze.
"""

import logging
import subprocess
import time
import os
from typing import Optional

logger = logging.getLogger(__name__)

BRAVE_PATH = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
DEBUG_PORT = 9222

# Sections to extract: (CSS selector, friendly label)
SECTIONS = [
    ("#quarters",    "Quarterly Results"),
    ("#profit-loss", "Profit & Loss"),
]


def _is_brave_running_with_debug() -> bool:
    result = subprocess.run(
        ["lsof", "-i", f":{DEBUG_PORT}", "-sTCP:LISTEN"],
        capture_output=True, text=True
    )
    return len(result.stdout.strip()) > 0


def _relaunch_brave_with_debug() -> bool:
    logger.info("Relaunching Brave with remote debugging...")
    os.system("osascript -e 'quit app \"Brave Browser\"'")
    time.sleep(2)
    subprocess.Popen([BRAVE_PATH, f"--remote-debugging-port={DEBUG_PORT}", "--no-first-run"])
    for _ in range(15):
        time.sleep(1)
        if _is_brave_running_with_debug():
            return True
    return False


# JavaScript that converts a <table> element inside a section to plain text
_TABLE_TO_TEXT_JS = """
(sectionId) => {
    const section = document.querySelector(sectionId);
    if (!section) return null;

    const table = section.querySelector('table');
    if (!table) return null;

    const rows = Array.from(table.querySelectorAll('tr'));
    return rows.map(row => {
        const cells = Array.from(row.querySelectorAll('th, td'));
        return cells.map(c => c.innerText.trim().replace(/\\n/g, ' ')).join(' | ');
    }).join('\\n');
}
"""

# JavaScript to extract the CAGR / compounded growth summary block
_SUMMARY_JS = """
(sectionId) => {
    const section = document.querySelector(sectionId);
    if (!section) return '';
    const boxes = Array.from(section.querySelectorAll('.twenty-numbers, .flex-row'));
    return boxes.map(b => b.innerText.trim()).join('\\n');
}
"""


def fetch_screener_data(ticker: str) -> Optional[str]:
    """Extract P&L and Quarterly Results as plain text from screener.in.

    Returns a formatted text string ready to be sent to a text LLM.
    Returns None on failure.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError:
        logger.error("Playwright not installed.")
        return None

    base_ticker = ticker.upper().split(".")[0]
    url = f"https://www.screener.in/company/{base_ticker}/"
    page = None

    try:
        if not _is_brave_running_with_debug():
            if not _relaunch_brave_with_debug():
                logger.error("Could not start Brave with remote debugging.")
                return None

        with sync_playwright() as p:
            logger.info(f"Connecting to Brave (port {DEBUG_PORT})...")
            browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
            context = browser.contexts[0]

            page = context.new_page()
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            page.wait_for_selector("#profit-loss", timeout=15000)

            # Scroll to bottom once to trigger lazy-load, then wait briefly.
            # For text/DOM extraction we don't need the CSS rendering tricks
            # that screenshots require — the data is already in the HTML.
            logger.info("Triggering lazy-load via single scroll-to-bottom...")
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2.0)
            page.evaluate("window.scrollTo(0, 0)")
            logger.info("Lazy-load triggered.")

            # Extract top card data (company info, ratios, about section)
            top_card_data = page.evaluate("""
                () => {
                    const top = document.querySelector('#top');
                    if (!top) return null;
                    
                    const h1 = top.querySelector('h1');
                    const name = h1 ? h1.innerText.trim() : '';
                    
                    const linksDiv = top.querySelector('.company-links') || top.querySelector('.links');
                    const linksText = linksDiv ? linksDiv.innerText.replace(/\\n/g, ' | ').trim() : '';
                    
                    const ratiosLi = Array.from(top.querySelectorAll('#top-ratios li'));
                    const ratiosText = ratiosLi.map(li => {
                        const nameSpan = li.querySelector('.name');
                        const valueSpan = li.querySelector('.value');
                        const n = nameSpan ? nameSpan.innerText.trim() : '';
                        const v = valueSpan ? valueSpan.innerText.trim() : '';
                        return `${n}: ${v}`;
                    }).join('\\n');
                    
                    const profileDiv = top.querySelector('.company-profile');
                    const profileText = profileDiv ? profileDiv.innerText.trim() : '';
                    
                    return {
                        name,
                        linksText,
                        ratiosText,
                        profileText
                    };
                }
            """)

            # Extract each section as plain text
            parts = []
            if top_card_data:
                top_parts = []
                if top_card_data.get("name"):
                    top_parts.append(f"Company Name: {top_card_data['name']}")
                if top_card_data.get("linksText"):
                    top_parts.append(f"Links/Identifiers: {top_card_data['linksText']}")
                if top_card_data.get("ratiosText"):
                    top_parts.append(f"=== Key Ratios ===\n{top_card_data['ratiosText']}")
                if top_card_data.get("profileText"):
                    profile_clean = top_card_data['profileText'].replace("READ MORE", "").strip()
                    top_parts.append(f"=== Company Profile & Key Points ===\n{profile_clean}")
                
                parts.append("\n".join(top_parts))

            for selector, label in SECTIONS:
                table_text = page.evaluate(_TABLE_TO_TEXT_JS, selector)
                summary_text = page.evaluate(_SUMMARY_JS, selector)

                if table_text:
                    parts.append(f"=== {label} ===\n{table_text}")
                    if summary_text and summary_text.strip():
                        parts.append(f"--- {label} Summary ---\n{summary_text.strip()}")
                else:
                    logger.warning(f"No table found for section: {label}")

            page.close()
            page = None

            if not parts:
                logger.error("No data extracted from screener.in")
                return None

            result = f"Company: {base_ticker}\nSource: screener.in\n\n" + "\n\n".join(parts)
            logger.info(f"✅ Extracted {len(result)} chars of financial data for {base_ticker}")
            return result

    except Exception as e:
        logger.error(f"Screener fetch error for {ticker}: {e}")
        return None
    finally:
        if page is not None:
            try:
                if not page.is_closed():
                    page.close()
            except Exception:
                pass
