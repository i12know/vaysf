import asyncio
import os
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

# Configuration
FORM_EXPORTS = (
    {
        "name": "Consent Form",
        "url": "https://vay.chmeetings.com/2E3F3637741B61D9/FormsList/301494",
        "filename": "consent_forms.xlsx",
    },
    {
        "name": "Individual Application Form",
        "url": "https://vay.chmeetings.com/2E3F3637741B61D9/FormsList/301433",
        "filename": "individual_application_forms.xlsx",
    },
)
DOWNLOAD_DIR = Path(__file__).resolve().parent / "data"
CDP_PORT = 9222  # Chrome remote debugging port
PAGE_LOAD_TIMEOUT_MS = 2 * 60 * 1000
DOWNLOAD_TIMEOUT_MS = 15 * 60 * 1000


async def export_form(context, form):
    page = await context.new_page()

    try:
        print(f"[{datetime.now():%H:%M:%S}] Navigating to {form['name']}...")
        await page.goto(
            form["url"],
            wait_until="domcontentloaded",
            timeout=PAGE_LOAD_TIMEOUT_MS,
        )

        # Wait for the submissions table to load
        await page.wait_for_selector(
            f"text={form['name']}",
            timeout=PAGE_LOAD_TIMEOUT_MS,
        )
        print(f"[{datetime.now():%H:%M:%S}] {form['name']} loaded. Clicking Export...")

        # Click the Export button
        await page.click("button:has-text('Export')")

        # Wait for the modal to appear
        await page.wait_for_selector("text=Export Submissions", timeout=10000)
        print(f"[{datetime.now():%H:%M:%S}] {form['name']} export modal opened.")

        # Format is already Excel and all columns are selected.
        print(
            f"[{datetime.now():%H:%M:%S}] Waiting up to 15 minutes for "
            f"{form['name']}..."
        )
        async with page.expect_download(timeout=DOWNLOAD_TIMEOUT_MS) as download_info:
            await page.click("button:has-text('Download')")

        download = await download_info.value
        save_path = DOWNLOAD_DIR / form["filename"]

        await download.save_as(save_path)
        print(f"[{datetime.now():%H:%M:%S}] File saved to: {save_path}")
    finally:
        await page.close()


async def export_forms():
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    async with async_playwright() as p:
        # Connect to the dedicated, already-authenticated Chrome instance.
        browser = await p.chromium.connect_over_cdp(f"http://localhost:{CDP_PORT}")
        context = browser.contexts[0]

        results = await asyncio.gather(
            *(export_form(context, form) for form in FORM_EXPORTS),
            return_exceptions=True,
        )

        failures = []
        for form, result in zip(FORM_EXPORTS, results):
            if isinstance(result, Exception):
                failures.append(form["name"])
                print(
                    f"[{datetime.now():%H:%M:%S}] {form['name']} failed: "
                    f"{type(result).__name__}: {result}"
                )

        if failures:
            raise RuntimeError(f"Export failed for: {', '.join(failures)}")


if __name__ == "__main__":
    asyncio.run(export_forms())
