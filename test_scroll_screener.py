import logging
from playwright.sync_api import sync_playwright

logging.basicConfig(level=logging.INFO)

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://localhost:9222")
    context = browser.contexts[0]
    page = context.new_page()
    page.set_viewport_size({"width": 1920, "height": 1080})
    
    page.goto("https://www.screener.in/company/DATAPATTNS/")
    
    pl_element = page.locator("#profit-loss")
    pl_element.scroll_into_view_if_needed()
    
    # Try to scroll the inner table wrapper to the far right
    page.evaluate("""
        const wrapper = document.querySelector('#profit-loss .responsive');
        if (wrapper) {
            wrapper.scrollLeft = wrapper.scrollWidth;
        } else {
            const table = document.querySelector('#profit-loss table');
            if (table && table.parentElement) {
                table.parentElement.scrollLeft = table.parentElement.scrollWidth;
            }
        }
    """)
    
    page.wait_for_timeout(1000)
    screenshot_bytes = page.screenshot(full_page=True, scale="css")
    
    with open("test_screener_right.png", "wb") as f:
        f.write(screenshot_bytes)
    
    print("Saved test_screener_right.png (full page)")
    page.close()
