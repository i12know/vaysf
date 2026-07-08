import asyncio
import sys
from datetime import datetime
from pathlib import Path

from loguru import logger
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
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
LOG_DIR = Path(__file__).resolve().parent / "logs"
CDP_PORT = 9222  # Chrome remote debugging port
PAGE_LOAD_TIMEOUT_MS = 2 * 60 * 1000
DOWNLOAD_TIMEOUT_MS = 15 * 60 * 1000


def make_console_stream_safe(stream):
    """Use UTF-8 console output when available so names with diacritics do not break runs."""
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="backslashreplace")
    return stream


async def dismiss_blocking_overlays(page, form_name: str):
    """Dismiss ChMeetings promotional dialogs that can block Export clicks."""
    no_thank_you = page.locator("button:has-text('No, Thank You')").first
    try:
        if await no_thank_you.is_visible(timeout=2000):
            logger.info(f"{form_name}: dismissing ChMeetings promotional overlay.")
            await no_thank_you.click(force=True, timeout=5000)
            await page.wait_for_timeout(500)
            return
    except PlaywrightTimeoutError:
        pass

    await page.keyboard.press("Escape")
    await page.wait_for_timeout(500)


def configure_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"sportsfest_{datetime.now():%Y%m%d}.log"

    logger.remove()
    logger.add(
        log_file,
        rotation="1 day",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    )
    logger.add(
        make_console_stream_safe(sys.stdout),
        level="DEBUG",
        format="{time:HH:mm:ss} | {level} | {message}",
        colorize=True,
    )


async def export_form(context, form):
    page = await context.new_page()

    try:
        logger.info(f"Navigating to {form['name']}...")
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
        logger.info(f"{form['name']} loaded. Clicking Export...")

        # A prior interrupted export can leave a ChMeetings modal overlay in the
        # tab, which blocks pointer events on the Export button. Close it if
        # possible, then fall back to a force click if the overlay still wins.
        await dismiss_blocking_overlays(page, form["name"])
        export_button = page.locator("button:has-text('Export')").first
        try:
            await export_button.click(timeout=10000)
        except PlaywrightTimeoutError:
            logger.warning(
                f"{form['name']} Export button was blocked by an overlay; "
                "retrying with force click."
            )
            await export_button.click(force=True, timeout=10000)

        # Wait for the modal to appear
        await page.wait_for_selector("text=Export Submissions", timeout=10000)
        logger.info(f"{form['name']} export modal opened.")

        # Format is already Excel and all columns are selected.
        logger.info(f"Waiting up to 15 minutes for {form['name']}...")
        async with page.expect_download(timeout=DOWNLOAD_TIMEOUT_MS) as download_info:
            await page.locator("button:has-text('Download')").first.click(force=True)

        download = await download_info.value
        save_path = DOWNLOAD_DIR / form["filename"]

        await download.save_as(save_path)
        logger.info(f"{form['name']} saved to: {save_path}")
    finally:
        await page.close()


async def export_forms():
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Starting VAYSF ChMeetings form exports")

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
                logger.error(
                    f"{form['name']} failed: {type(result).__name__}: {result}"
                )

        if failures:
            raise RuntimeError(f"Export failed for: {', '.join(failures)}")

    logger.info("VAYSF ChMeetings form exports completed successfully")


if __name__ == "__main__":
    configure_logging()
    try:
        asyncio.run(export_forms())
    except Exception:
        logger.exception("VAYSF ChMeetings form export failed")
        raise
