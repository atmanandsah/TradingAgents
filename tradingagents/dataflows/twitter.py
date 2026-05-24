"""X.com (Twitter) real-time scraper using Playwright CDP.

Connects to your EXISTING, running Brave browser via Chrome DevTools Protocol (CDP).
Opens a new tab in your browser, navigates to X.com and extracts recent posts.

Prerequisites (one-time setup):
  Run this once to relaunch Brave with remote debugging enabled:
    /Applications/Brave\\ Browser.app/Contents/MacOS/Brave\\ Browser --remote-debugging-port=9222
  
  After the first run of your script, Brave will be automatically relaunched with
  remote debugging enabled and will stay that way until you manually restart it.
"""

import logging
import subprocess
import time
import os
from typing import List

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    sync_playwright = None

logger = logging.getLogger(__name__)

BRAVE_PATH = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
DEBUG_PORT = 9222


def _is_brave_running_with_debug() -> bool:
    """Check if Brave is already running with remote debugging on port 9222."""
    result = subprocess.run(
        ["lsof", "-i", f":{DEBUG_PORT}", "-sTCP:LISTEN"],
        capture_output=True, text=True
    )
    return len(result.stdout.strip()) > 0


def _relaunch_brave_with_debug() -> bool:
    """Gracefully quit Brave and relaunch it with remote debugging enabled."""
    logger.info("Relaunching Brave Browser with remote debugging enabled...")
    os.system("osascript -e 'quit app \"Brave Browser\"'")
    time.sleep(2)
    subprocess.Popen([BRAVE_PATH, f"--remote-debugging-port={DEBUG_PORT}", "--no-first-run"])
    for _ in range(15):
        time.sleep(1)
        if _is_brave_running_with_debug():
            logger.info(f"Brave is ready with remote debugging on port {DEBUG_PORT}")
            return True
    logger.error("Brave did not start with remote debugging in time.")
    return False


def fetch_twitter_posts(ticker: str, limit: int = 50, timeout_sec: int = 60) -> str:
    """Fetch recent tweets for a ticker using your existing, logged-in Brave browser.
    
    Connects to the already-running Brave browser via CDP, opens a NEW TAB for the
    X.com search, scrapes tweets, then closes only that tab.
    Your other Brave tabs are untouched.
    """
    if not sync_playwright:
        return "<twitter unavailable: Playwright not installed>"

    # Remove .NS suffix and strip any $ prefix
    base_cashtag = ticker.upper().split(".")[0]
    if base_cashtag.startswith("$"):
        base_cashtag = base_cashtag[1:]

    posts: List[str] = []
    page = None

    try:
        # Ensure Brave is running with remote debugging
        if not _is_brave_running_with_debug():
            if not _relaunch_brave_with_debug():
                return "<twitter unavailable: Could not start Brave with remote debugging>"

        with sync_playwright() as p:
            # Connect to the EXISTING Brave browser - no closing, no new window
            logger.info(f"Connecting to existing Brave browser on port {DEBUG_PORT}...")
            browser = p.chromium.connect_over_cdp(f"http://localhost:{DEBUG_PORT}")

            # Use the existing logged-in context (your normal browser session)
            context = browser.contexts[0]
            logger.info(f"Connected! Browser has {len(context.pages)} existing tab(s)")

            # Calculate the date 5 days ago for the search filter
            import datetime
            import urllib.parse
            five_days_ago = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
            
            # Build the query: "TICKER since:YYYY-MM-DD"
            search_query = f"{base_cashtag} since:{five_days_ago}"
            encoded_query = urllib.parse.quote(search_query)

            # Open a BRAND NEW tab - doesn't touch your existing tabs
            # f=live (Latest), pf=on (People you follow)
            search_url = f"https://x.com/search?q={encoded_query}&src=typed_query&f=live&pf=on"
            logger.info(f"Opening new tab for: {search_url}")
            page = context.new_page()
            page.goto(search_url, timeout=30000)

            # This selector targets tweet article elements
            tweet_selector = "article[data-testid='tweet']"
            logger.info("Waiting for tweets to load...")

            try:
                page.wait_for_selector(tweet_selector, timeout=timeout_sec * 1000)
            except PlaywrightTimeoutError:
                logger.warning("Timeout waiting for tweets - possibly a login wall or rate limit.")
                return f"<twitter unavailable: Timeout waiting for tweets for {base_cashtag}>"

            # Set viewport so scrollHeight and innerHeight are accurate
            page.set_viewport_size({"width": 1280, "height": 800})

            # X.com uses virtual DOM recycling — off-screen tweets get REMOVED from the DOM.
            # So we must collect tweet text on every scroll step and deduplicate.
            seen_texts: set = set()
            
            logger.info(f"Scrolling to collect up to {limit} unique tweets...")
            for scroll_attempt in range(30):  # Max 30 scroll attempts
                tweet_elements = page.query_selector_all(tweet_selector)
                new_this_round = 0
                for element in tweet_elements:
                    try:
                        text_content = element.inner_text().strip()
                        if text_content and text_content not in seen_texts:
                            seen_texts.add(text_content)
                            cleaned = " ".join(text_content.split("\n"))
                            posts.append(f"[{len(posts)+1}] {cleaned}")
                            new_this_round += 1
                    except Exception as e:
                        logger.debug(f"Failed to parse tweet: {e}")

                logger.info(f"  Scroll {scroll_attempt+1}: {len(posts)} unique tweets collected (+{new_this_round} new)")

                if len(posts) >= limit:
                    logger.info(f"Reached target of {limit} tweets!")
                    break
                if new_this_round == 0 and scroll_attempt > 2:
                    logger.info("No new tweets in this scroll. End of feed reached.")
                    break

                # Scroll to bottom of page to trigger next batch
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2.5)

    except Exception as e:
        logger.error(f"Playwright error during Twitter fetch: {e}")
        return f"<twitter unavailable: {type(e).__name__}: {e}>"
    finally:
        # Close only the tab we opened, leave everything else untouched
        if page and not page.is_closed():
            try:
                page.close()
            except Exception:
                pass

    if not posts:
        return f"<no Twitter posts found for {base_cashtag}>"
    print("posts",posts)

    return "\n\n".join(posts)
