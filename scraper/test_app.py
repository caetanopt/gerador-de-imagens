"""Tira screenshot da app Streamlit para verificação."""
import time
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1400, "height": 900})
    page.goto("http://localhost:8501", wait_until="load", timeout=30000)
    time.sleep(6)
    page.screenshot(path="data/app_screenshot.png", full_page=True)
    print("Screenshot: data/app_screenshot.png")
    browser.close()
