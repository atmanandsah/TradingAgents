from playwright.sync_api import sync_playwright
import os

user_data_dir = os.path.expanduser("~/.tradingagents/playwright_chrome_profile")
os.makedirs(user_data_dir, exist_ok=True)

with sync_playwright() as p:
    print("Launching browser...")
    context = p.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        channel="chrome",
        headless=True
    )
    page = context.new_page()
    page.goto("https://x.com")
    print("Browser launched successfully. Title:", page.title())
    context.close()
