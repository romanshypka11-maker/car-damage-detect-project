import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def collect_active_chrome_lots(filename_to_save, max_pages=3):
    print(f"Connecting to the active Chrome instance on port 9222...")

    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", "chrome:9222")
    chrome_options.page_load_strategy = "eager"

    driver = webdriver.Chrome(options=chrome_options)
    unique_lots = set()

    if os.path.exists(filename_to_save):
        with open(filename_to_save, "r") as f:
            for line in f:
                line_cleaned = line.strip()
                if line_cleaned:
                    unique_lots.add(line_cleaned)
        print(f"Loaded {len(unique_lots)} lots from file to prevent duplicates.")

    try:
        print(f"Successfully connected to Chrome. Current URL: {driver.current_url}")

        # Open file in append mode ('a') to maintain connection during the loop execution
        with open(filename_to_save, "a") as file_out:
            for page in range(1, max_pages + 1):
                print(f"\nProcessing page {page}...")

                # Brief pause to allow Javascript to re-render elements
                time.sleep(3)

                print("Searching for lot numbers on the page...")
                xpath_rule = "//a[contains(@href, '/lot/') or contains(@data-url, '/lot/') or @class='search-results']"

                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located((By.XPATH, xpath_rule))
                    )
                except Exception:
                    print("Warning: Element explicit wait timeout. Attempting to parse available data.")

                driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 3);")
                time.sleep(1)
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 1.5);")
                time.sleep(1)

                # Element collection is executed inside the page iteration loop
                elements = driver.find_elements(By.XPATH, xpath_rule)
                links_found_on_page = 0

                for element in elements:
                    try:
                        lot_number = element.text.strip()

                        if not lot_number or not lot_number.isdigit():
                            href = element.get_attribute("href")
                            if href and "/lot/" in href:
                                for part in href.split("/"):
                                    if part.isdigit() and len(part) >= 7:
                                        lot_number = part
                                        break

                        if not lot_number or not lot_number.isdigit():
                            lot_number = element.get_attribute("lot_number")

                        # Uniqueness verification and immediate disk write operation
                        if lot_number and lot_number.isdigit() and len(lot_number) >= 7:
                            if lot_number not in unique_lots:
                                unique_lots.add(lot_number)
                                links_found_on_page += 1

                                # Immediate file write operation
                                file_out.write(f"{lot_number}\n")
                                file_out.flush()  # Flush the buffer directly to disk

                                print(f"[Saved to disk] lot: {lot_number}")
                    except Exception:
                        continue

                print(
                    f"Page {page}: found {links_found_on_page} new lots. Total unique database records: {len(unique_lots)}")

                # --- Pagination logic (transition to the next page) ---
                if page < max_pages:
                    try:
                        next_xpath = "//button[@aria-label='Next Page'] | //a[contains(text(), 'Next')] | //li[contains(@class, 'next')]/a"

                        print("Waiting for the 'Next' button to become available in HTML...")
                        next_button = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.XPATH, next_xpath))
                        )

                        is_disabled = False
                        button_class = next_button.get_attribute("class") or ""

                        if "p-disabled" in button_class or next_button.get_attribute("disabled"):
                            is_disabled = True

                        if is_disabled:
                            print("The 'Next' button is disabled. Reached the last page of search results.")
                            break

                        # Scroll element into viewport and trigger click event via Javascript
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                        time.sleep(1.5)

                        driver.execute_script("arguments[0].click();", next_button)
                        print("Clicked 'Next Page' button. Waiting 6 seconds for JS table update...")
                        time.sleep(6)

                    except Exception as e:
                        print(f"Failed to navigate to the next page. Technical reason: {e}")
                        break

    except Exception as e:
        print(f"Critical execution error: {e}")

    print(f"\nExecution completed. Database '{filename_to_save}' successfully updated.")



# RUN SCRAPER FOR 30 PAGES
collect_active_chrome_lots("rear_end_damage_lots.txt", max_pages=30)