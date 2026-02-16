import os
import json
import time
from typing import List, Dict, Any

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


# ================= CONFIG =================
BASE_URL = "https://nepalstock.com"
PULL_LATEST = True

# Read from env so GitHub Actions can control it
HEADLESS = os.getenv("HEADLESS", "false").strip().lower() in ("1", "true", "yes")

# Output file (useful for Actions artifacts)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_JSON = os.getenv(
    "OUTPUT_JSON",
    os.path.join(BASE_DIR, "companies.json"),
)
# ==========================================


def get_random_user_agent() -> str:
    # Keep stable UA in CI to reduce randomness-related issues
    return (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )


def get_regulatory_body(sector_name: str) -> str:
    return "SEBON"


def init_driver() -> webdriver.Chrome:
    options = Options()

    # Consistent window size
    options.add_argument("--window-size=1280,720")

    # CI-safe flags
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    # Reduce automation fingerprints (doesn't guarantee bypass)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # Headless toggle
    if HEADLESS:
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")

    options.add_argument(f"user-agent={get_random_user_agent()}")
    options.add_experimental_option("prefs", {"intl.accept_languages": "en-US,en;q=0.9"})

    # ✅ Selenium 4.6+ uses Selenium Manager automatically (no webdriver_manager)
    driver = webdriver.Chrome(options=options)

    # Extra hardening: hide webdriver flag where possible
    try:
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": """
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                """
            },
        )
    except Exception:
        pass

    return driver


def get_companies(pull_latest: bool) -> List[Dict[str, Any]]:
    if not pull_latest:
        return []

    url = f"{BASE_URL}/company"
    driver = init_driver()
    wait = WebDriverWait(driver, 60)

    companies: List[Dict[str, Any]] = []
    page_no = 1

    try:
        driver.get(url)

        # ✅ Select "500" from the page-size dropdown (omit all-instruments selection)
        page_size_select = wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//select[.//option[@value='500' and normalize-space(.)='500']]")
            )
        )
        Select(page_size_select).select_by_value("500")

        # Give time for table to refresh
        time.sleep(2)

        while True:
            try:
                wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))

                soup = BeautifulSoup(driver.page_source, "html.parser")
                rows = soup.select("tbody tr")

                for row in rows:
                    cols = row.find_all("td")
                    if len(cols) < 8:
                        continue

                    link = cols[1].find("a")
                    company_id = (
                        link["href"].split("/")[-1]
                        if link and link.get("href")
                        else None
                    )

                    sector_name = cols[4].get_text(strip=True)

                    companies.append(
                        {
                            "id": int(company_id) if company_id else None,
                            "companyName": cols[1].get_text(strip=True),
                            "symbol": cols[2].get_text(strip=True),
                            "securityName": cols[1].get_text(strip=True),
                            "status": cols[3].get_text(strip=True),
                            "sectorName": sector_name,
                            "instrumentType": cols[5].get_text(strip=True),
                            "companyEmail": cols[6].get_text(strip=True),
                            "website": cols[7].get_text(strip=True),
                            "regulatoryBody": get_regulatory_body(sector_name),
                        }
                    )

                print(f"[Companies] Scraped page {page_no}")
                page_no += 1

                # Pagination
                try:
                    next_btn = driver.find_element(By.CSS_SELECTOR, "li.pagination-next a")
                    next_btn.click()
                    time.sleep(3)
                except NoSuchElementException:
                    break

            except TimeoutException:
                break

        print(f"\n✅ Fetched {len(companies)} companies")
        return companies

    finally:
        driver.quit()


# if __name__ == "__main__":
data = get_companies(PULL_LATEST)

# Save to JSON for GitHub Actions artifact
with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("\nSample output:")
print(data[:3])
print(f"\nSaved -> {OUTPUT_JSON}")
