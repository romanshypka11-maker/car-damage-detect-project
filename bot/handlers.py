import asyncio
import base64
import httpx
from aiogram import Router, F
from aiogram.types import Message, InputMediaPhoto, BufferedInputFile
import os
import logging
from aiogram.filters import CommandStart
from ai_agent import ask
from core.config import get_settings
from scraping.plc_ua import get_photos_by_vin
from scraping.autoria import AutoRiaParser

logger = logging.getLogger(__name__)
router = Router()
PHOTO_CACHE = {}

@router.message(CommandStart())
async def cmd_start(message: Message):
    start_text = (
        "👋 **Вітаю! Я DeepAuto — твій персональний помічник при купівлі авто.**\n\n"
        "Я вмію «пробивати» машини по базах, знаходити приховані дефекти та оцінювати реальну вартість автомобіля, щоб ти не переплачував.\n\n"
        "⚙️ **ОСЬ МОЇ ГОЛОВНІ ФІШКИ:**\n\n"
        "1️⃣ **Повна перевірка авто з США** 🇺🇸\n"
        "Просто скинь мені посилання на оголошення з **Auto.ria**. Я автоматично знайду оригінальний VIN-код, "
        "витягну архивні фотографії з американського аукціону, **знайду і обведу всі пошкодження на фото** "
        "та порівняю ціну продавця з реальною ринковою вартістю. Наприкінці ти отримаєш чіткий розгорнутий висновок експерта — варто брати цю машину чи ні.\n\n"
        "2️⃣ **Жива аналітика цін (у мене в базі 240 000+ авто!)** 📊\n"
        "Ти можеш запитати мене про ціни чи пробіги простою людською мовою. Наприклад:\n"
        "• _'яка середня ціна Audi Q7 2017 року'_ \n"
        "• _'скільки всього машин марки Tesla в базі'_\n"
        "• _'який середній пробіг у BMW X5 2019 року'_\n\n"
        "🚀 **З чого почати?** Протестуй мене прямо зараз! Скинь посилання на авто з **Auto.ria** або просто запитай щось про ціни! 👇"
    )

    # Відправляємо красиве вітальне повідомлення
    await message.answer(start_text, parse_mode="Markdown")

@router.message(F.text.contains("auto.ria.com"))
async def handle_auto_link(message: Message):
    url = message.text
    # Creating a parser object
    parser = AutoRiaParser()
    data = await parser.get_data(url)

    if "error" in data:
        await message.answer(f" Помилка: {data['error']}")
        return

    try:
        make = data.get('make') or 'Невідомо'
        model = data.get('model') or ''
        year = data.get('year') or ''
        price = data.get('price_usd') or '???'
        mileage = data.get('mileage_km') or 0
        vin = data.get('vin') or 'Прихований'
        color = data.get('color') or ''
        location = data.get('location') or ''
        seller_type = data.get('seller_type') or ''
        imported_from = data.get('imported_from') or ''
        has_accident = data.get('has_accident') or False
        description = data.get('description') or ''
        engine_volume_l = data.get('engine_volume_l') or ''

        horsepower = data.get('horsepower') or 0
        battery_capacity_kwh = data.get('battery_capacity_kwh') or 0
        ev_range_km = data.get('ev_range_km') or 0
        accident_details = data.get('accident_details') or ''
        body_type = data.get('body_type') or ''
        fuel_type = data.get('fuel_type') or ''
        transmission = data.get('transmission') or ''

        is_suv = 1 if any(x in str(body_type).lower() for x in ['позашляховик', 'кросовер', 'джип', 'suv']) else 0
        is_imported = 1 if imported_from or data.get('is_imported') else 0

        # Dictionary of attributes to send to the API
        input_dict = {
            "make": [make],
            "model": [model],
            "year": [int(year) if year else 0],
            "mileage_km": [int(mileage) if mileage else 0],
            "engine_volume_l": [float(engine_volume_l) if engine_volume_l else 0.0],
            "horsepower": [int(horsepower) if horsepower else 0],
            "battery_capacity_kwh": [float(battery_capacity_kwh) if battery_capacity_kwh else 0.0],
            "ev_range_km": [int(ev_range_km) if ev_range_km else 0],
            "is_suv": [is_suv],
            "is_imported": [is_imported],
            "has_accident": [1 if has_accident else 0],
            "accident_details": [accident_details],
            "body_type": [body_type],
            "fuel_type": [fuel_type],
            "transmission": [transmission],
            "color": [color],
            "region": [location],
            "description": [description]
        }

        # --- QUESTION 1: Estimating the price of CatBoost using FastAPI ---
        async with httpx.AsyncClient() as client:
            price_res = await client.post(
                f"{settings.ai_service_url}/predict-price",
                json={"features": input_dict},
                timeout=10
            )
            predictor_price = price_res.json().get("predicted_price", 0)

        # Creating a message with properties
        parts = [
            f"🚗 **{make} {model} {year}**",
            f"📅 **Рік:** {year}",
            f"💰 **Ціна:** {price}$",
            f"🤖 **Оцінка моделі:** {round(predictor_price):,}$",
            f"🛣 **Пробіг:** {mileage} км",
            f"🔍 **VIN:** `{vin}`"
        ]

        if color: parts.append(f"🎨 **Колір:** {color}")
        if engine_volume_l: parts.append(f"⚙️ **Двигун:** {engine_volume_l}")
        if location: parts.append(f"📍 **Локація:** {location}")
        if seller_type: parts.append(f"👤 **Продавець:** {seller_type}")
        if imported_from: parts.append(f"🚢 **Пригнаний з:** {imported_from}")

        dtp_status = "Так" if has_accident else "Ні"
        parts.append(f"💥 **ДТП:** {dtp_status}")

        response_text = "\n".join(parts)
        response_text += f"\n\n **Опис:**\n{description[:300]}..."
        await message.answer(response_text, parse_mode="Markdown")

        if vin and vin != 'Прихований' and len(vin) == 17:

            # 🟢 ОБРОБКА КЕШУ (якщо лінк кидають повторно)
            if vin in PHOTO_CACHE:
                print(f"📦 [КЕШ] Дані для VIN {vin} знайдені в пам'яті!")
                cache_entry = PHOTO_CACHE[vin]

                if cache_entry["photos"]:
                    media_group = [
                        InputMediaPhoto(media=BufferedInputFile(base64.b64decode(p), filename="cached.jpg"))
                        for p in cache_entry["photos"]
                    ]
                    await message.answer_media_group(media=media_group)

                    if cache_entry["reports"]:
                        await message.answer(f"⚠️ **Звіт комп'ютерного зору (Кеш):**\n" + "\n".join(
                            [f"• {r}" for r in cache_entry["reports"]]))

                    # Виводимо збережений вердикт ШІ з кешу, щоб не смикати Ollama двічі
                    if cache_entry.get("verdict"):
                        await message.answer(f"📋 **Експертний висновок DeepAuto (Кеш):**\n\n{cache_entry['verdict']}",
                                             parse_mode="Markdown")
                else:
                    await message.answer("📭 Архівних фото з аукціонів для цього VIN немає.")
                return

            status_msg = await message.answer(
                "🔍 Шукаю оригінальні фотографії з аукціону та аналізую пошкодження  ⏳")


            # Parsing links using Selenium in a separate thread
            auction_photos = await asyncio.to_thread(get_photos_by_vin, vin)

            if auction_photos:
                # --- QUESTION 2: Cascading CV analysis of photos using FastAPI ---
                async with httpx.AsyncClient() as client:
                    cv_res = await client.post(
                        f"{settings.ai_service_url}/analyze-damage",
                        json={"urls": auction_photos},
                        timeout=60.0,
                    )
                    cv_data = cv_res.json() if cv_res.status_code == 200 else {}

                processed_b64_images = cv_data.get("images", [])
                final_reports = cv_data.get("reports", [])

                try:
                    await status_msg.delete()
                except Exception:
                    pass

                if processed_b64_images:
                    media_group = [
                        InputMediaPhoto(media=BufferedInputFile(base64.b64decode(img_b64), filename=f"cascade_{i}.jpg"))
                        for i, img_b64 in enumerate(processed_b64_images)
                    ]
                    await message.answer_media_group(media=media_group)
                else:
                    await message.answer(
                        "📸 Вдалося знайти згадку про аукціон, але не вдалося отримати прямі зображення.")

                if final_reports:
                    report_msg = "⚠️ ** DeepAuto зафіксував на аукціоні такі деталі:**\n"
                    report_msg += "\n".join([f"• {r}" for r in final_reports])
                    await message.answer(report_msg)
                else:
                    await message.answer(
                        "✅ DeepAuto перевірив фотографії: видимих дефектів кузова чи вузлів не виявлено.")

            else:
                # If there are no photos, we first notify the user and clear the status
                processed_b64_images = []
                final_reports = []
                try:
                    await status_msg.edit_text("📭 Архівних фото з аукціонів для цього VIN не знайдено.")
                except Exception:
                    await message.answer("📭 Архівних фото з аукціонів для цього VIN не знайдено.")

            # --- CALLING FOR A VERDICT ASSISTANT ---
            verdict_msg = await message.answer("🧠 ** DeepAuto аналізує всі фактори для фінального вердикту...** ⏳")

            ai_verdict = "Не вдалося сформувати висновок."
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=10.0)) as client:
                    verdict_res = await client.post(
                        f"{settings.ai_service_url}/api/ai/verdict",
                        json={
                            "car_data": data,
                            "cv_reports": final_reports,  # тут буде порожній список, якщо фото не знайшли
                            "predicted_price": float(predictor_price)
                        },
                    )
                    if verdict_res.status_code == 200:
                        ai_verdict = verdict_res.json().get("verdict", ai_verdict)
                        await verdict_msg.edit_text(f"📋 **Експертний висновок DeepAuto:**\n\n{ai_verdict}",
                                                    parse_mode="Markdown")
                    else:
                        await verdict_msg.edit_text("❌ Сервер ШІ повернув помилку при формуванні вердикту.")
            except httpx.ReadTimeout:
                print("⚠️ Запит до AI_SERVICE перевищив ліміт у 120 секунд.")
                await verdict_msg.edit_text( "⏳ Генерація аналізу затягнулася. Спробуйте ще раз за декілька секунд.")
            except Exception as verdict_err:
                print(f"Помилка отримання вердикту: {verdict_err}")
                await verdict_msg.edit_text("❌ Не вдалося побудувати фінальний висновок ШІ.")

            # We cache the results (even if there are 0 photos, the verdict will still be cached!)
            PHOTO_CACHE[vin] = {
                "photos": processed_b64_images,
                "reports": final_reports,
                "verdict": ai_verdict
            }
        else:
            await message.answer("🔒 Додатковий пошук фото неможливий: оригінальний VIN приховано.")

    except Exception as e:
        logging.exception(f"Global exception caught inside link evaluation flow: {e}")
        await message.answer(f"❌ Помилка при відображенні даних: {e}")


@router.message()
async def handle_ai_text_query(message: Message):
    if not message.text or "auto.ria.com" in message.text:
        return

    status_msg = await message.answer("🤖 Опрацьовую запит... ⏳")

    try:
        # Виклик LangGraph-агента напряму через ai_agent
        data = await ask(message.text)

        if data.get("status") == "success" and data.get("result"):
            cars = data["result"]
            first_row = cars[0]

            # Аналітична відповідь (агреговані дані)
            if len(first_row.keys()) <= 2 and not any(k in first_row for k in ["make", "model"]):
                col_name = list(first_row.keys())[0]
                agg_val = first_row[col_name]

                if agg_val is not None:
                    formatted_val = f"{round(float(agg_val)):,}".replace(",", " ")
                    await status_msg.edit_text(f"📊 **Результат аналітики:** {formatted_val}", parse_mode="Markdown")
                else:
                    await status_msg.edit_text("📭 Немає даних для обчислення.")
                return

        else:
            await status_msg.edit_text("📭 За вашим запитом нічого не знайдено.")

    except Exception as e:
        logger.exception("Text query failed: %s", e)
        await status_msg.edit_text("❌ Сталася помилка при обробці текстового запиту.")