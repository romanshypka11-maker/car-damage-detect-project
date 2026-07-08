import os
import time
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


def download_all_photos_to_single_folder(queue_file, output_dir):
    if not os.path.exists(queue_file):
        print(f"Error: File {queue_file} not found.")
        return

    with open(queue_file, "r") as f:
        lot_numbers = [line.strip() for line in f.readlines() if line.strip()]

    print(f"Queue loaded. Total items in list: {len(lot_numbers)} vehicles.")

    # Create a single global directory
    os.makedirs(output_dir, exist_ok=True)

    chrome_options = Options()
    chrome_options.add_experimental_option("debuggerAddress", "chrome:9222")
    driver = webdriver.Chrome(options=chrome_options)

    skipped_count = 0

    for index, lot_number in enumerate(lot_numbers):
        # Progress check using the first image frame
        first_photo_check = os.path.join(output_dir, f"car_{lot_number}_00.jpg")
        if os.path.exists(first_photo_check):
            skipped_count += 1
            if skipped_count % 10 == 0 or index == 0:
                print(f"Skipping lot {lot_number} (already downloaded).")
            continue

        print(f"Processing item {index + 1} of {len(lot_numbers)}: Opening lot {lot_number}")

        lot_url = f"https://www.copart.com/lot/{lot_number}"

        try:
            driver.get(lot_url)

            # Allow the web page sufficient time to completely render Angular assets
            print("Waiting 3 seconds for page rendering...")
            time.sleep(3)

            # Cloudflare security interception check
            if "cloudflare" in driver.page_source.lower() or "just a moment" in driver.title.lower():
                print("Cloudflare detected. Please solve the captcha manually in the Chrome window.")
                time.sleep(6)

            # Global image lookup strategy: targeting all img elements on the page
            img_elements = driver.find_elements(By.TAG_NAME, "img")

            photo_urls = set()
            for img in img_elements:
                try:
                    url = img.get_attribute("src") or img.get_attribute("data-src") or img.get_attribute("full-src")
                    if url and "http" in url and (".jpg" in url.lower() or "hrs" in url.lower()):
                        # Verify the URL points to Copart asset servers
                        if "copart.com" in url:
                            clean_url = url.split('?')[0]

                            # Upgrade thumbnail resolution to maximum high-resolution source
                            if "_thb.jpg" in clean_url:
                                clean_url = clean_url.replace("_thb.jpg", "_hrs.jpg")
                            elif "_ful.jpg" in clean_url:
                                clean_url = clean_url.replace("_ful.jpg", "_hrs.jpg")

                            photo_urls.add(clean_url)
                except:
                    continue

            if not photo_urls:
                print(f"No photos discovered in the HTML source code for lot {lot_number}. Skipping.")
                continue

            print(f"Discovered {len(photo_urls)} unique high-res photos. Starting download...")

            # Download assets using the resolved direct URLs
            downloaded_idx = 0
            for img_url in sorted(photo_urls):
                filename = f"car_{lot_number}_{downloaded_idx:02d}.jpg"
                file_path = os.path.join(output_dir, filename)

                try:
                    res = requests.get(img_url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
                    if res.status_code == 200:
                        with open(file_path, "wb") as img_file:
                            img_file.write(res.content)
                        print(f"    Downloaded: {filename}")
                        downloaded_idx += 1
                except Exception as img_err:
                    print(f"    Failed to download file: {img_err}")
                    if os.path.exists(file_path):
                        os.remove(file_path)

            # Delay to throttle requests between lots
            time.sleep(1.5)

        except KeyboardInterrupt:
            print("\nProcess interrupted by user (Ctrl+C). Current progress saved.")
            return
        except Exception as e:
            print(f"Error processing lot {lot_number}: {e}")
            continue

    print(f"\nScraping complete. All assets are located in the directory: {output_dir}")


if __name__ == "__main__":
    input_queue = "rear_end_damage_lots.txt"
    output_directory = "data/rear_end_damage"
    download_all_photos_to_single_folder(input_queue, output_directory)