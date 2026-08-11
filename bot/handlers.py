import asyncio
import base64
import logging
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InputMediaPhoto, BufferedInputFile

# Беремо лише ask() — усю іншу логіку та HTTP-запити він зробить сам усередині LangGraph
from ai_agent import ask

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    start_text = (
        "👋 **Вітаю! Я DeepAuto — твій персональний помічник при купівлі авто.**\n\n"
        "Я вмію «пробивати» машини по базах, знаходити приховані дефекти та оцінювати реальну вартість автомобіля, щоб ти не переплачував.\n\n"
        "🚀 **З чого почати?** Протестуй мене прямо зараз! Скинь посилання на авто з **Auto.ria** або просто запитай щось про ціни! 👇"
    )
    await message.answer(start_text, parse_mode="Markdown")


@router.message(F.text.contains("auto.ria.com"))
async def handle_auto_link(message: Message):
    status_msg = await message.answer(
        "🔍 **Запускаю повний аналіз авто через агента DeepAuto...** ⏳\n\n"
        "_Це може зайняти близько хвилини (скрапінг, пошук аукціонів, CV, генерація вердикту)_",
        parse_mode="Markdown"
    )

    try:
        # 1. ВИРІШЕННЯ ПРОБЛЕМ 1 та 2: Викликаємо граф напряму, ніяких ручних httpx та settings
        state = await ask(message.text)
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

        # 3. Вивід результатів Computer Vision
        cv_images = state.get("cv_images") or []
        if cv_images:
            media = [
                InputMediaPhoto(media=BufferedInputFile(base64.b64decode(img), filename=f"cv_{i}.jpg"))
                for i, img in enumerate(cv_images)
            ]
            await message.answer_media_group(media=media)

        cv_reports = state.get("cv_reports") or []
        if cv_reports:
            await message.answer("⚠️ **DeepAuto CV зафіксував дефекти:**\n" + "\n".join([f"• {r}" for r in cv_reports]))
        elif vin != "Прихований" and state.get("auction_photos"):
            await message.answer("✅ На аукціонних фото видимості дефектів не виявлено.")
        elif vin != "Прихований":
            await message.answer("📭 Архівних фото з аукціонів для цього VIN не знайдено.")

        # 4. Вивід фінального вердикту
        verdict = state.get("verdict")
        if verdict:
            await message.answer(f"📋 **Експертний висновок DeepAuto:**\n\n{verdict}", parse_mode="Markdown")
        else:
            await message.answer("❌ Не вдалося сформувати висновок ШІ.")

    except Exception as e:
        logger.exception("Global failure in handle_auto_link: %s", e)
        await status_msg.edit_text("❌ Сталася помилка під час повного аналізу посилання.")


@router.message()
async def handle_ai_text_query(message: Message):
    if not message.text or "auto.ria.com" in message.text:
        return

    status_msg = await message.answer("🤖 Опрацьовую запит... ⏳")

    try:
        # ВИРІШЕННЯ ПРОБЛЕМИ 3: Правильний парсинг AgentState замість {"status": "success"}
        state = await ask(message.text)
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

            # Список авто (ТОП-5)
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