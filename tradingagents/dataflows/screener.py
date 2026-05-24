"""Screener.in P&L scraper using Playwright CDP.

Connects to your existing Brave browser, navigates to screener.in for a given
ticker, scrolls to the Profit & Loss section, and takes a screenshot of it.

Returns the screenshot as PNG bytes for use with a vision LLM.
"""

import logging
import subprocess
import time
import os
from typing import Optional

logger = logging.getLogger(__name__)

BRAVE_PATH = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
DEBUG_PORT = 9222


def _is_brave_running_with_debug() -> bool:
    result = subprocess.run(
        ["lsof", "-i", f":{DEBUG_PORT}", "-sTCP:LISTEN"],
        capture_output=True, text=True
    )
    return len(result.stdout.strip()) > 0


def _relaunch_brave_with_debug() -> bool:
    logger.info("Relaunching Brave Browser with remote debugging enabled...")
    os.system("osascript -e 'quit app \"Brave Browser\"'")
    time.sleep(2)
    subprocess.Popen([BRAVE_PATH, f"--remote-debugging-port={DEBUG_PORT}", "--no-first-run"])
    for _ in range(15):
        time.sleep(1)
        if _is_brave_running_with_debug():
            logger.info(f"Brave ready with remote debugging on port {DEBUG_PORT}")
            return True
    logger.error("Brave did not start in time.")
    return False


def fetch_screener_pl_screenshot(ticker: str) -> Optional[bytes]:
    """Navigate to screener.in, find the P&L section, and return a screenshot.

    Args:
        ticker: NSE ticker e.g. "DATAPATTNS.NS" or "DATAPATTNS"

    Returns:
        PNG screenshot bytes of the Profit & Loss section, or None on failure.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    except ImportError:
        logger.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return None

    # Strip .NS suffix
    base_ticker = ticker.upper().split(".")[0]
    # Screener.in URL for consolidated financials
    screener_url = f"https://www.screener.in/company/{base_ticker}/consolidated/"

    page = None
    try:
        if not _is_brave_running_with_debug():
            if not _relaunch_brave_with_debug():
                logger.error("Could not start Brave with remote debugging.")
                return None

        with sync_playwright() as p:
            logger.info(f"Connecting to Brave on port {DEBUG_PORT}...")
            browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")
            context = browser.contexts[0]

            logger.info(f"Opening screener.in for {base_ticker}...")
            page = context.new_page()
            page.set_viewport_size({"width": 1440, "height": 900})
            page.goto(screener_url, timeout=30000, wait_until="domcontentloaded")

            # Screener.in may redirect to standalone if no consolidated data exists
            # Check and fall back to standalone
            if "consolidated" in page.url and page.locator("#profit-loss").count() == 0:
                standalone_url = f"https://www.screener.in/company/{base_ticker}/"
                logger.info(f"No consolidated data, trying standalone: {standalone_url}")
                page.goto(standalone_url, timeout=30000, wait_until="domcontentloaded")

            # Wait for the P&L section to load
            pl_selector = "#profit-loss"
            logger.info("Waiting for Profit & Loss section...")
            try:
                page.wait_for_selector(pl_selector, timeout=20000)
            except PlaywrightTimeoutError:
                logger.warning(f"P&L section not found on screener.in for {base_ticker}")
                page.close()
                return None

            # Scroll to the P&L section so it's fully in view
            pl_element = page.locator(pl_selector)
            pl_element.scroll_into_view_if_needed()
            time.sleep(1.5)  # Let the section fully render after scrolling

            # Take screenshot of ONLY the P&L section element
            logger.info("Taking screenshot of P&L section...")
            screenshot_bytes = pl_element.screenshot()
            logger.info(f"✅ P&L screenshot captured ({len(screenshot_bytes)} bytes) for {base_ticker}")

            page.close()
            page = None
            return screenshot_bytes

    except Exception as e:
        logger.error(f"Screener.in fetch error for {ticker}: {e}")
        return None
    finally:
        if page is not None:
            try:
                if not page.is_closed():
                    page.close()
            except Exception:
                pass
