# backend/dump_fsra.py
import asyncio
from playwright.async_api import async_playwright

async def dump_fsra_dom():
    url = "https://regulatorrateranger.fsrao.ca/"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto(url, wait_until="networkidle")

        # 1. Save full page HTML to file
        content = await page.content()
        with open("page_debug.html", "w", encoding="utf-8") as f:
            f.write(content)
        print("Saved full page DOM to backend/page_debug.html")

        # 2. Extract and format all select/input tags specifically
        elements = await page.query_selector_all("select, input, button")
        debug_lines = []
        for el in elements:
            html_tag = await el.evaluate("e => e.outerHTML")
            debug_lines.append(html_tag)

        with open("selects_debug.txt", "w", encoding="utf-8") as f:
            f.write("\n\n".join(debug_lines))
        print("Saved element breakdown to backend/selects_debug.txt")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(dump_fsra_dom())