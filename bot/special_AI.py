import httpx
import asyncpg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
from scraper_main.scraper import DB_CONFIG
import traceback
import logging
app = FastAPI()
from dotenv import load_dotenv

load_dotenv()


class UserRequest(BaseModel):
    text: str
# 1. Read the base URL for Ollama from environment variables (.env).
# If OLLAMA_URL is not set, fallback to the local default 'http://127.0.0.1:11434'.
OLLAMA_BASE_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")


async def generate_car_verdict(car_data: dict, cv_reports: list, predicted_price: float) -> str:
    """
    Generates a final, detailed report on the vehicle based on
    parsing, CatBoost scoring, and a computer vision report.
    """
    # Safeguard against cases where car_data is passed as None
    car_dict = car_data if car_data else {}

    # Compile computer vision report into a single string
    if not cv_reports:
        cv_text = "Архівних фото з аукціонів для цього VIN не знайдено."
    else:
        cv_text = ", ".join(cv_reports)

    # Safely extract values for the prompt (using variables to avoid missing key/None errors)
    car_make = car_dict.get('make', 'Невідома марка')
    car_model = car_dict.get('model', '')
    car_year = car_dict.get('year', 'Рік не вказано')
    seller_price = car_dict.get('price_usd', 0)
    mileage = car_dict.get('mileage_km', 'Невідомо')
    imported = car_dict.get('imported_from') or 'Не вказано (можливо офіціал)'
    has_accident = 'Так' if car_dict.get('has_accident') else 'Ні'
    description = car_dict.get('description', '')[:300]

    prompt = f"""
    Ти — професійний експерт з підбору уживаних автомобілів та автотехнік. Твоє завдання — проаналізувати зібрані дані про автомобіль і дати ОДИН розгорнутий, чесний, структурований висновок для покупця українською мовою.

    ДАНІ ПРО АВТОМОБІЛЬ:
    - Марка та модель: {car_make} {car_model} ({car_year} рік)
    - Ціна продавця: {seller_price}$
    - Реальна ринкова оцінка (наша ML-модель): {round(predicted_price)}$
    - Пробіг: {mileage} км
    - Країна імпорту: {imported}
    - Факт ДТП в історії: {has_accident}
    - Звіт комп'ютерного зору з аукціону США: {cv_text}
    - Опис від продавця: "{description}..."

    
    ІНСТРУКЦІЯ ДЛЯ ФОРМУВАННЯ ВИСНОВКУ:
    1. Напиши аналіз ціни. Порівняй ціну продавця з оцінкою нашої моделі (чи завищена вона, чи є простір для торгу).
    2. Проаналізуй технічний стан та ризики. Зістав слова продавця в описі з суворими фактами: пробігом, ДТП та тим, що зафіксував комп'ютерний зір.
    3. Дай фінальний вердикт: чи варто розглядати це авто до покупки, на що звернути увагу під час огляду на СТО.

    Пиши професійно, лаконічно, без зайвої «води». Оформлюй текст за допомогою емодзі та Markdown-форматування (жирний текст).
    """

    # Construct the full request URL dynamically based on the base environment URL
    request_url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate"

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                request_url,
                json={
                    "model": "qwen3:8b",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3}  # 0.3 is optimal for analytical tasks to minimize hallucination
                }
            )
            if response.status_code == 200:
                return response.json().get("response", "").strip()
            return "❌ Не вдалося згенерувати висновок ШІ через помилку API."
    except Exception as e:
        logging.exception(f"CRITICAL ERROR IN generate_car_verdict pipeline: {e}")
        return "❌ Помилка підключення до ШІ-моделі для аналізу вердикту."


async def generate_sql_via_qwen(user_text: str) -> str:
    """
    Generates a valid PostgreSQL query using Qwen3 based on user input.
    """
    # Dynamic table extraction from DB_CONFIG inside the function
    table_name = os.getenv("DB_TABLE") or DB_CONFIG.get("table") or "car_listings"

    table_schema = f"""
    The table is named '{table_name}' and has the following schema:
    - id (int64): Unique identifier
    - url (object): Link to the listing
    - vin (object): VIN code of the vehicle
    - vin_verified (bool): True if verified
    - make (object): Vehicle brand/manufacturer (e.g., 'Audi', 'Tesla', 'BMW' - ALWAYS capitalized)
    - model (object): Vehicle model (e.g., 'Q7', 'A4', 'Model 3')
    - year (int64): Manufacturing year (e.g., 2017, 2018)
    - generation (object): Car generation description
    - trim_level (object): Trim package
    - mileage_km (float64): Mileage in kilometers
    - transmission (object): Transmission type (e.g., 'Automatic', 'Manual')
    - fuel_type (object): Fuel type (e.g., 'Petrol', 'Diesel', 'Electric')
    - engine_volume_l (float64): Engine volume in liters (e.g., 2.0, 3.0)
    - battery_capacity_kwh (float64): Battery capacity for EVs
    - horsepower (float64): Engine horsepower
    - drivetrain (object): Wheel drive type (e.g., 'AWD', 'FWD', 'RWD')
    - color (object): Car color
    - has_accident (bool): True if the car was in an accident / has damage
    - accident_details (object): Text description of damage
    - owners_count (float64): Number of previous owners
    - price_usd (float64): Price in US Dollars (USD) - USE THIS FOR AVERAGE PRICE IN USD
    - description (object): Full text description
    - category_id (int64): ID of category
    - scraped_at (datetime64): Date when data was collected
    - vehicle_condition (object): e.g., 'Used', 'New'
    - imported_from (object): Country of origin
    - location (object): City or region
    - body_type (object): e.g., 'SUV', 'Sedan'
    - doors_count (float64): Number of doors
    - seats_count (float64): Number of seats
    - modification (object): Specific modification
    - seller_type (object): e.g., 'Private', 'Dealer'
    - ev_range_km (float64): Electric range in km
    """

    system_prompt = f"""You are an expert SQL assistant. Your task is to convert human language queries into a single, valid PostgreSQL query for the table '{table_name}'.

    {table_schema}

    Strictly follow these critical SQL rules:
    1. Use ONLY the column names listed above. Do not hallucinate column names like 'price' or 'brand'.
    2. For prices in dollars, ALWAYS use 'price_usd'. For brand, ALWAYS use 'make'.
    3. When filtering string values like brand/make or model, use case-insensitive matching using ILIKE or ensure proper capitalization (e.g., WHERE make ILIKE 'audi' or WHERE make = 'Audi').
    4. Return ONLY the raw SQL code. 
    5. Do NOT wrap it in markdown code blocks like ```sql ... ```, do not write explanations.
    """

    request_url = f"{OLLAMA_BASE_URL.rstrip('/')}/api/generate"

    try:
        async with httpx.AsyncClient(timeout=200.0) as client:
            response = await client.post(
                request_url,
                json={
                    "model": "qwen3:8b",
                    "prompt": f"{system_prompt}\n\nUser request: {user_text}\nSQL:",
                    "stream": False,
                    "options": {"temperature": 0.0}  # 0.0 temperature prevents syntax hallucinations
                }
            )
            if response.status_code == 200:
                return response.json().get("response", "").strip()
            return ""
    except Exception as e:
        logging.exception(f"Error inside generate_sql_via_qwen flow: {e}")
        return ""