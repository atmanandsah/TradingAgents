"""X.com (Twitter) real-time scraper using Playwright.

This module uses Playwright to open a visible Chromium browser (headless=False)
and navigates to X.com to search for the given ticker (e.g. `$RELIANCE.NS` or `$RELIANCE`).
It extracts recent posts from the search results.

Note: X.com heavily restricts search for unauthenticated users. The browser will
remain open visibly to allow the user to log in if a login wall is encountered.
"""

import logging
import time
from typing import List

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
except ImportError:
    sync_playwright = None

logger = logging.getLogger(__name__)

def fetch_twitter_posts(ticker: str, limit: int = 15, timeout_sec: int = 45) -> str:
    """Fetch recent tweets for a ticker using Playwright.
    
    Opens a visible browser window, searches for the cashtag, and extracts posts.
    Provides enough time for the user to manually log in if prompted.
    """
    if not sync_playwright:
        return "<twitter unavailable: Playwright not installed>"
        
    # Standardize the cashtag format
    cashtag = ticker.upper()
    if not cashtag.startswith("$"):
        cashtag = f"${cashtag}"
        
    # Often the `.NS` suffix confuses Twitter search, so we might want to search both
    # or just use the base name if it has a suffix. But we'll search the exact cashtag first.
    base_cashtag = cashtag.split(".")[0]

    posts: List[str] = []
    
    try:
        with sync_playwright() as p:
            # headless=False so the user can see it and intervene (log in/captcha)
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                viewport={'width': 1280, 'height': 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = context.new_page()
            
            # Go to the search page directly
            search_url = f"https://x.com/search?q={base_cashtag}&src=typed_query&f=live"
            logger.info(f"Navigating to {search_url}...")
            
            page.goto(search_url, wait_until="domcontentloaded")
            
            # Wait for either tweets to load OR a login prompt.
            # We give a generous timeout so the user has time to type their password if needed.
            logger.info("Waiting for tweets to load or for user to log in manually...")
            
            # This selector targets the article elements which contain tweets
            tweet_selector = "article[data-testid='tweet']"
            
            try:
                # Wait up to timeout_sec for tweets to appear
                page.wait_for_selector(tweet_selector, timeout=timeout_sec * 1000)
            except PlaywrightTimeoutError:
                logger.warning(f"Timeout waiting for tweets. The page might be stuck on a login wall or CAPTCHA.")
                return f"<twitter unavailable: Timeout waiting for tweets for {base_cashtag}. Possibly blocked by login wall.>"
                
            # Allow some time for tweets to fully render
            time.sleep(3)
            
            # Extract tweets
            tweet_elements = page.query_selector_all(tweet_selector)
            
            for i, element in enumerate(tweet_elements[:limit]):
                try:
                    # Extract the text content of the tweet
                    text_content = element.inner_text()
                    # Clean up the text a bit (removing multiple newlines)
                    cleaned_text = " ".join(text_content.split("\n"))
                    posts.append(f"[{i+1}] {cleaned_text}")
                except Exception as e:
                    logger.debug(f"Failed to parse a tweet element: {e}")
                    
            browser.close()
            
    except Exception as e:
        logger.error(f"Playwright error during Twitter fetch: {e}")
        return f"<twitter unavailable: {type(e).__name__}>"
        
    if not posts:
        return f"<no Twitter posts found for {base_cashtag}>"
        
    # Format the return string
    formatted_posts = "\n\n".join(posts)
    return formatted_posts
