import base64
import logging
import httpx
import re
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InputMediaPhoto, BufferedInputFile
from cachetools import TTLCache
from core.config import get_settings

logger = logging.getLogger(__name__)
router = Router()

# Створюємо кеш: запам'ятовує до 200 машин, кожна зберігається 1 годину (3600 секунд)
car_results_cache = TTLCache(maxsize=200, ttl=6700)


def extract_car_url(message: Message) -> str | None:
    text = message.text or message.caption
    entities = message.entities or message.caption_entities or []

    if not text:
        return None

    # 1. Шукаємо приховані посилання (фіолетовий текст, як на скріншоті)
    for entity in entities:
        if entity.type == "text_link":
            return entity.url  # Telegram сам дає нам готовий прихований URL

        # 2. Якщо Telegram розпізнав шматок тексту як URL
        if entity.type == "url":
            extracted = text[entity.offset: entity.offset + entity.length]
            # Додаємо https:// якщо його немає
            return extracted if extracted.startswith("http") else f"https://{extracted}"

    match = re.search(r'(https?://[^\s]+)', text)
    if match:
        return match.group(1)

    return None

def is_car_link_message(message: Message) -> bool:
    url = extract_car_url(message)
    if not url:
        return False
    url_lower = url.lower()
    return "ria.com" in url_lower or "auto.ria" in url_lower

@router.message(CommandStart())
async def cmd_start(message: Message):
    start_text = (
        "👋 **Вітаю! Я DeepAuto — твій персональний помічник при купівлі авто.**\n\n"
        "Я вмію «пробивати» машини по базах, знаходити приховані дефекти та оцінювати реальну вартість автомобіля, щоб ти не переплачував.\n\n"
        "🚀 **З чого почати?** Протестуй мене прямо зараз! Скинь посилання на авто з **Auto.ria** або просто запитай щось про ціни! 👇"
    )
    await message.answer(start_text, parse_mode="Markdown")


@router.message(lambda msg: is_car_link_message(msg))
async def handle_auto_link(message: Message):
    clean_url = extract_car_url(message)
    if clean_url in car_results_cache:
        cached_data = car_results_cache[clean_url]
        await message.answer("⚡️ _Знайдено в кеші (миттєва відповідь):_\n\n" + cached_data["text"],
                             parse_mode="Markdown")

        # Якщо в кеші були фотографії дефектів, відправляємо і їх
        if cached_data.get("cv_images"):
            media = [
                InputMediaPhoto(media=BufferedInputFile(base64.b64decode(img), filename=f"cv_{i}.jpg"))
                for i, img in enumerate(cached_data["cv_images"])
            ]
            await message.answer_media_group(media=media)
        return
    status_msg = await message.answer(
        "🔍 **Запускаю повний аналіз авто через агента DeepAuto...** ⏳\n\n"
        "_Це може зайняти близько хвилини (скрапінг, пошук аукціонів, CV, генерація вердикту)_",
        parse_mode="Markdown"
    )
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(240.0, connect=10.0)) as client:
            response = await client.post(
                f"{settings.ai_service_url}/api/ai/agent",
                json={"text": clean_url},
            )
            response.raise_for_status()
            state = response.json().get("result", {})
            rid = response.json().get("request_id", "-")
            logger.info("[%s] Bot received response in handle_auto_link", rid)

        car_data = state.get("car_data") or {}

        if "error" in car_data or not car_data:
            await status_msg.edit_text(f"❌ Помилка завантаження: {car_data.get('error', 'Невідома помилка')}")
            return

        # 2. Формуємо базовий опис з AgentState
        make = car_data.get("make", "Невідомо")
        model = car_data.get("model", "")
        year = car_data.get("year", "")
        price = car_data.get("price_usd", "???")
        predicted_price = state.get("predicted_price", 0)
        mileage = car_data.get("mileage_km", 0)
        vin = car_data.get("vin", "Прихований")

        parts = [
            f"🚗 **{make} {model} {year}**",
            f"📅 **Рік:** {year}",
            f"💰 **Ціна продавця:** {price}$",
            f"🤖 **Оцінка моделі:** {round(predicted_price):,}$" if predicted_price else "🤖 **Оцінка моделі:** Не вдалося",
            f"🛣 **Пробіг:** {mileage} км",
            f"🔍 **VIN:** `{vin}`"
        ]

        if car_data.get("color"): parts.append(f"🎨 **Колір:** {car_data['color']}")
        if car_data.get("location"): parts.append(f"📍 **Локація:** {car_data['location']}")
        if car_data.get("has_accident"): parts.append(f"💥 **ДТП в історії:** Так")

        main_text = "\n".join(parts)
        description = car_data.get("description", "")
        if description:
            main_text += f"\n\n**Опис:**\n{description[:300]}..."

        await status_msg.delete()
        await message.answer(main_text, parse_mode="Markdown")

        full_cached_text = main_text

        # 3. Вивід результатів Computer Vision
        cv_images = state.get("cv_images") or []
        if cv_images:
            media = [
                InputMediaPhoto(media=BufferedInputFile(base64.b64decode(img), filename=f"cv_{i}.jpg"))
                for i, img in enumerate(cv_images)
            ]
            await message.answer_media_group(media=media)

        cv_reports_text = ""
        cv_reports = state.get("cv_reports") or []
        if cv_reports:
            cv_reports_text = "⚠️ **DeepAuto CV зафіксував дефекти:**\n" + "\n".join([f"• {r}" for r in cv_reports])
        elif vin != "Прихований" and state.get("auction_photos"):
            cv_reports_text = "✅ На аукціонних фото видимості дефектів не виявлено."
        elif vin != "Прихований":
            cv_reports_text = "📭 Архівних фото з аукціонів для цього VIN не знайдено."

        if cv_reports_text:
            await message.answer(cv_reports_text)
            full_cached_text += f"\n\n{cv_reports_text}"  # Додаємо до кешу


        # 4. Вивід фінального вердикту
        verdict = state.get("verdict")
        if verdict:
            verdict_text = f"📋 **Експертний висновок DeepAuto:**\n\n{verdict}"
            await message.answer(verdict_text, parse_mode="Markdown")
            full_cached_text += f"\n\n{verdict_text}"  # Додаємо до кешу
        else:
            await message.answer("❌ Не вдалося сформувати висновок ШІ.")

        car_results_cache[clean_url] = {
            "text": full_cached_text,
            "cv_images": cv_images
        }

    except Exception as e:
        logger.exception("Global failure in handle_auto_link: %s", e)
        await status_msg.edit_text("❌ Сталася помилка під час повного аналізу посилання.")


@router.message()
async def handle_ai_text_query(message: Message):
    if not message.text or is_car_link_message(message):
        return

    status_msg = await message.answer("🤖 Опрацьовую запит... ⏳")
    settings = get_settings()

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0)) as client:
            response = await client.post(
                f"{settings.ai_service_url}/api/ai/agent",
                json={"text": message.text},
            )
            response.raise_for_status()
            state = response.json().get("result", {})
            rid = response.json().get("request_id", "-")
            logger.info("[%s] Bot received response in handle_ai_text_query", rid)

        db_result = state.get("db_result")
        if db_result and isinstance(db_result, list) and len(db_result) > 0:
            first_row = db_result[0]
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
            reply = "📊 **Результати пошуку в базі:**\n\n"
            for i, car in enumerate(db_result[:5], 1):
                price = f"{car.get('price_usd'):,}".replace(",", " ") if car.get("price_usd") else "—"
                mileage = f"{car.get('mileage_km'):,}".replace(",", " ") if car.get("mileage_km") else "0"
                reply += f"{i}. 🚗 **{car.get('make', '')} {car.get('model', '')}** ({car.get('year', '—')})\n💰 {price} $ | 🛣 {mileage} км\n\n"
            await status_msg.edit_text(reply, parse_mode="Markdown")
        else:
            await status_msg.edit_text("📭 За вашим запитом нічого не знайдено.")

    except Exception as e:
        logger.exception("Text query failed: %s", e)
        await status_msg.edit_text("❌ Сталася помилка при обробці текстового запиту.")