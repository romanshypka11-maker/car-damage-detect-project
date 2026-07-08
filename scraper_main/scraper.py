import os
from bs4 import BeautifulSoup
import re
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "database": os.getenv("DB_NAME"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "table": os.getenv("DB_TABLE", "car_listings"),
}

MAX_CONCURRENT_REQUESTS = 10


def get_cleaned_parts(element):
    """Бере BeautifulSoup елемент, розбиває текст по комі."""
    if element is None:
        return []
    text = element.get_text(strip=True)
    return [p.strip() for p in text.split(',') if p.strip()]


def extract_battery_capacity(text):
    if not text:
        return None
    match = re.search(r"(\d+)\s*kWh", text)
    if match:
        return int(match.group(1))
    return None


# --- ШАР 1: ПАРСИНГ HTML (Чиста функція) ---
def parse_car_html(html, url):
    """Приймає HTML і повертає готовий словник car_data"""
    soup = BeautifulSoup(html, "lxml")

    # 1. VIN
    vin_element = soup.find('span', class_="common-text ws-pre-wrap badge")
    vin_code = vin_element.get_text(strip=True) if vin_element else None
    vin_verified = bool(vin_element)

    # 2. МАРКА, МОДЕЛЬ, РІК
    title_element = soup.find('h1', class_='common-text ws-pre-wrap titleL')
    make_val, model_val, year_val = None, None, None
    if title_element:
        # Отримуємо текст "Audi A4 2014"
        words = title_element.get_text(strip=True).split()

        if len(words) >= 3:
            # Перше слово - завжди марка ("Audi")
            make_val = words[0]

            # Останнє слово - намагаємось перетворити на рік ("2014")
            try:
                year_val = int(words[-1])
            except ValueError:
                year_val = None

            # Все, що між першим і останнім словом - це модель
            # Якщо рік успішно знайдено, беремо до передостаннього слова
            if year_val is not None:
                model_val = " ".join(words[1:-1])
            else:
                # Якщо останнє слово не було роком, то вся решта - це модель
                model_val = " ".join(words[1:])

    # 3. ПОКОЛІННЯ ТА МОДИФІКАЦІЯ
    gen_base_div = soup.find('div', id='basicInfoGenerationBase')
    generation, modification, trim_level = None, None, None
    if gen_base_div:
        parts = [span.get_text(strip=True).replace('•', '').strip() for span in gen_base_div.find_all('span') if
                 span.get_text(strip=True)]
        generation = parts[0] if len(parts) > 0 else None
        modification = parts[1] if len(parts) > 1 else None
        trim_level = parts[2] if len(parts) > 2 else None

    # 4. ПРОБІГ
    mileage_element = soup.find('div', id='basicInfoTableMainInfo0')
    mileage = None
    if mileage_element:
        raw_text_mileage = mileage_element.get_text(strip=True)
        only_digits = ''.join(filter(str.isdigit, raw_text_mileage))
        if only_digits:
            mileage = int(only_digits) * 1000 if 'тис.' in raw_text_mileage else int(only_digits)

    # 5. КОРОБКА ПЕРЕДАЧ
    transmission_element = soup.find('div', id='descTransmissionTransmission')
    transmission_text = transmission_element.get_text(strip=True) if transmission_element else None

    # 6. ПАЛЬНЕ ТА ОБ'ЄМ
    fuel_parts = get_cleaned_parts(soup.find('div', id='basicInfoTableMainInfo2'))
    fuel_type = fuel_parts[0] if len(fuel_parts) > 0 else None
    engine_volume = None
    if len(fuel_parts) > 1:
        try:
            engine_volume = float(fuel_parts[1].replace('л', '').replace(',', '.').strip())
        except ValueError:
            pass

    # 7. БАТАРЕЯ
    battery_capacity = extract_battery_capacity(modification)

    # 8. ПОТУЖНІСТЬ
    engine_div = soup.find('div', id='descEngineEngine')
    horsepower = None
    if engine_div:
        hp_match = re.search(r"(\d+[\.,]?\d*)\s*к\.с\.", engine_div.get_text(strip=True))
        if hp_match:
            try:
                horsepower = int(round(float(hp_match.group(1).replace(',', '.'))))
            except ValueError:
                pass

    # 9. ПРИВІД ТА КОЛІР
    drive_train_div = soup.find('div', id='descDriveTypeDriveType')
    drivetrain = drive_train_div.get_text(strip=True) if drive_train_div else None

    color_div = soup.find('div', id='descColorColor')
    color = color_div.get_text(strip=True) if color_div else None

    # 10. ДТП (Виправлено баги)
    accident_div = soup.find('div', id='verifyingsPayedCheckText2')
    has_accident = False
    accident_details = ""  # Обов'язкова ініціалізація!
    if accident_div:
        accident_text = accident_div.get_text(strip=True).lower()
        if 'зафіксовано дтп' in accident_text or 'був у дтп' in accident_text:
            has_accident = True

        spans = accident_div.find_all('span')  # Виправлено: тепер ми знаходимо span-и
        if has_accident and len(spans) > 1:
            details_parts = [span.get_text(strip=True).replace('•', '').strip() for span in spans[1:]]
            accident_details = " ".join(filter(None, details_parts))

    # 11. ВЛАСНИКИ
    target_spans = soup.select('div[id^="mvsOptions"] span.common-text')

    owners_count = None

    for span in target_spans:
        text = span.get_text(strip=True).lower()
        # Перевіряємо, чи є в цьому конкретному span слово 'власник' (або 'власники')
        if 'власник' in text:
            match = re.search(r'(\d+)', text)
            if match:
                owners_count = int(match.group(1))
                break  # Знайшли потрібне - зупиняємо цикл

    # 12. ЦІНА
    price_div = soup.find('div', id='sidePrice')
    price_usd, price_uah = None, None
    if price_div:
        price_strong = price_div.find('strong')
        if price_strong:
            digits_usd = ''.join(filter(str.isdigit, price_strong.get_text(strip=True)))
            if digits_usd: price_usd = int(digits_usd)

        for span in price_div.find_all('span'):
            if 'грн' in span.get_text(strip=True).lower():
                digits_uah = ''.join(filter(str.isdigit, span.get_text(strip=True)))
                if digits_uah: price_uah = int(digits_uah)
                break

    # 13. ОПИС ТА СТАН
    description_div = soup.find('div', class_='expandable-text-template-text')
    description = " ".join(description_div.get_text(separator=" ", strip=True).split()) if description_div else ""

    tech_state_div = soup.find('div', id='descTechStateText')
    vehicle_condition = tech_state_div.get_text(strip=True) if tech_state_div else None

    # 14. ІМПОРТ ТА ЛОКАЦІЯ (Виправлено баг локації)
    imported_span = soup.find('span', id='badgesOrderFrom')
    imported_from = imported_span.get_text(strip=True) if imported_span else None

    geo_div = soup.find('div', id='basicInfoTableMainInfoGeo')
    location = None
    if geo_div:
        raw_geo = geo_div.get_text(strip=True)
        geo_parts = [p.strip() for p in raw_geo.split(',')]  # Виправлено
        location = f"{geo_parts[1]}, {geo_parts[2]}" if len(geo_parts) >= 3 else raw_geo

    # 15. КУЗОВ, ДВЕРІ, МІСЦЯ
    characteristics_div = soup.find('div', id='descCharacteristicsValue')
    body_type, doors_count, seats_count = None, None, None
    if characteristics_div:
        char_parts = [p.strip() for p in characteristics_div.get_text(separator=" ", strip=True).split('•') if
                      p.strip()]
        if char_parts: body_type = char_parts[0]

        for part in char_parts[1:]:
            if 'двер' in part.lower():
                match = re.search(r'(\d+)', part)
                if match: doors_count = int(match.group(1))
            elif 'місц' in part.lower():
                match = re.search(r'(\d+)', part)
                if match: seats_count = int(match.group(1))


        # 1. Шукаємо контейнер за ID
        seller_segment = soup.find('div', id='sellerInfoSegment')

        seller_type = None
        if seller_segment:
            seller_type = seller_segment.get_text(strip=True)
    ev_range_element = soup.find('div', id='basicInfoTableMainInfo1')
    ev_range = None

    if ev_range_element:
        raw_range_text = ev_range_element.get_text(strip=True)
        only_digits = ''.join(filter(str.isdigit, raw_range_text))
        if only_digits:
            ev_range = int(only_digits)


    return {
        "url": url.split('?')[0],
        "vin": vin_code,
        "vin_verified": vin_verified,
        "make": make_val,
        "model": model_val,
        "year": year_val,
        "generation": generation,
        "trim_level": trim_level,
        "mileage_km": mileage,
        "transmission": transmission_text,
        "fuel_type": fuel_type,
        "engine_volume_l": engine_volume,
        "battery_capacity_kwh": battery_capacity,
        "horsepower": horsepower,
        "drivetrain": drivetrain,
        "color": color,
        "has_accident": has_accident,
        "accident_details": accident_details,
        "owners_count": owners_count,
        "price_usd": price_usd,
        "price_uah": price_uah,
        "description": description,
        "category_id": 1,
        "vehicle_condition": vehicle_condition,
        "imported_from": imported_from,
        "location": location,
        "body_type": body_type,
        "doors_count": doors_count,
        "seats_count": seats_count,
        "modification": modification,
        "seller_type": seller_type,
        "ev_range_km": ev_range
    }