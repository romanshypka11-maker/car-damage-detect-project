import io
import json
import cv2
import logging
import asyncpg
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Dict, Any
import requests
from PIL import Image
import numpy as np
import supervision as sv
from catboost import CatBoostRegressor
from rfdetr import RFDETRMedium
from pathlib import Path
from contextlib import asynccontextmanager
import os

# FIX: Explicitly import DB_CONFIG to maintain code clarity in Docker containers
from scraper_main.scraper import DB_CONFIG
from bot.special_AI import UserRequest, generate_sql_via_qwen, generate_car_verdict

# Setup logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# FIX: Create a lifespan manager to safely initialize and close the DB Pool once
@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Initializing asyncpg connection pool...")
    connect_args = {k: v for k, v in DB_CONFIG.items() if k != "table"}

    # Якщо бачимо, що працюємо в Docker, міняємо локальний хост на міст із Windows
    if os.getenv("IS_DOCKER") == "true":
        if connect_args.get("host") in ["127.0.0.1", "localhost"]:
            logging.info("Docker environment detected. Remapping PostgreSQL host to host.docker.internal")
            connect_args["host"] = "host.docker.internal"

    app.state.db_pool = await asyncpg.create_pool(**connect_args, min_size=1, max_size=5)
    yield
    logging.info("Closing asyncpg connection pool...")
    await app.state.db_pool.close()


app = FastAPI(title="Cars Microservice", version="1.0", lifespan=lifespan)

# 1. INITIALIZATION OF MODELS AND CONFIGURATIONS
logging.info("Loading ML and CV models into memory...")
BASE_DIR = Path(__file__).resolve().parent.parent

CAT_MODEL_PATH = BASE_DIR / "models_ML" / "current_model_for_car_predict_price_cat_boost"
CV_MODEL_DETECT_ZONE_PATH = BASE_DIR / "models_ML" / "detect_damage_zone_final.pth"
CV_MODEL_DETENTS_PATH = BASE_DIR / "models_ML" / "rf_detr_car_damage_final_auction_damage.pth"

cat_model = CatBoostRegressor()
cat_model.load_model(str(CAT_MODEL_PATH))

cv_model_detect_zone = RFDETRMedium(pretrain_weights=str(CV_MODEL_DETECT_ZONE_PATH), patch_size=16)
cv_model_detents = RFDETRMedium(pretrain_weights=str(CV_MODEL_DETENTS_PATH), patch_size=16)

ZONE_CLASSES = {1: "Пошкоджено кузов (зона)", 2: "Пошкоджено внутрішні вузли/салон/безпека (зона)"}
DETAIL_DAMAGE_CLASSES = {
    0: "Auto-Auction-Damage-MVP", 1: "Circles_marks", 2: "X-marks", 3: "broken_glass",
    4: "broken_headlight", 5: "broken_mirror", 6: "damage_front_bamber", 7: "damaged-hood",
    8: "damaged_rear_bumper", 9: "damaged_trunk", 10: "damaged_upholstery", 11: "damaged_wheel",
    12: "dent", 13: "deployed_airbag_front", 14: "deployed_airbag_rear", 15: "door_damage",
    16: "flooded_interior", 17: "ground", 18: "interior_corrosion", 19: "messy_interier",
    20: "missing_bumper", 21: "missing_rear_bumper", 22: "rust", 23: "scratch",
    24: "severe_bumper_damage", 25: "severe_door_damage", 26: "severe_rear_bumper_damage",
    27: "severe_side_damage", 28: "side_damage"
}

FEATURE_COLUMNS_PATH = BASE_DIR / "feature_columns3.json"
with open(FEATURE_COLUMNS_PATH, "r", encoding="utf-8") as f:
    saved_columns = json.load(f)

logging.info("All models and analytical configurations loaded successfully!")


class PricePredictRequest(BaseModel):
    features: Dict[str, Any]


class DamageAnalysisRequest(BaseModel):
    urls: List[str]


class VerdictRequest(BaseModel):
    car_data: Dict[str, Any]
    cv_reports: List[str]
    predicted_price: float


@app.post("/predict-price")
def predict_price(request: PricePredictRequest):
    try:
        import pandas as pd
        input_df = pd.DataFrame(request.features)

        for col in saved_columns:
            if col not in input_df.columns:
                input_df[col] = "" if col in ['accident_details'] else 0

        input_df = input_df[saved_columns]
        prediction = cat_model.predict(input_df)[0]
        return {'predicted_price': float(prediction)}
    except Exception as e:
        logging.exception("CatBoost prediction pipeline failed")
        raise HTTPException(status_code=500, detail=f"Помилка CatBoost: {str(e)}")


@app.post("/api/ai/ask")
async def ask_ai_database(request: UserRequest):
    logging.info(f"Incoming Text-to-SQL query from bot: '{request.text}'")

    try:
        sql_query = await generate_sql_via_qwen(request.text)
    except Exception as ai_err:
        logging.exception("LLM SQL generation sequence failed")
        raise HTTPException(status_code=500, detail=f"Помилка генерації ШІ: {str(ai_err)}")

    if not sql_query or "SELECT" not in sql_query.upper():
        logging.warning("Generated SQL query rejected: Empty or missing SELECT statement.")
        raise HTTPException(status_code=400, detail="ШІ не зміг побудувати валідний SQL-запит.")

    try:
        # FIX: Reuse the pre-warmed connection pool from app state instead of recreating it
        async with app.state.db_pool.acquire() as conn:
            logging.info("Executing generated query on target database...")
            db_rows = await conn.fetch(sql_query)
            result_data = [dict(row) for row in db_rows]

        return {
            "status": "success",
            "sql_used": sql_query,
            "result": result_data
        }
    except Exception as db_err:
        logging.exception("SQL execution failed on database side")
        raise HTTPException(status_code=500, detail=f"Помилка БД: {str(db_err)}")


@app.post("/api/ai/verdict")
async def get_car_verdict(request: VerdictRequest):
    verdict_text = await generate_car_verdict(
        car_data=request.car_data,
        cv_reports=request.cv_reports,
        predicted_price=request.predicted_price
    )
    return {"status": "success", "verdict": verdict_text}


@app.post("/analyze-damage")
def analyze_damage(request: DamageAnalysisRequest):
    import base64
    processed_images_b64 = []
    found_global_zones = set()
    found_detailed_defects = set()

    zone_annotator = sv.BoxAnnotator(color=sv.Color.RED)
    defect_annotator = sv.BoxAnnotator(color=sv.Color.YELLOW)

    for url in request.urls[:10]:
        try:
            res = requests.get(url, timeout=7)
            if res.status_code != 200:
                continue

            img_bgr = cv2.imdecode(np.frombuffer(res.content, np.uint8), cv2.IMREAD_COLOR)
            if img_bgr is None:
                continue
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)

            zone_results = cv_model_detect_zone.predict(images=pil_img, conf=0.25)
            zone_detections = zone_results[0]

            if len(zone_detections) > 0:
                annotated_img = pil_img.copy()
                annotated_img = zone_annotator.annotate(scene=annotated_img, detections=zone_detections)

                for z_id in zone_detections.class_id:
                    if z_id in ZONE_CLASSES:
                        found_global_zones.add(ZONE_CLASSES[z_id])

                for bbox in zone_detections.xyxy:
                    x1, y1, x2, y2 = map(int, bbox)
                    cropped_zone = img_rgb[y1:y2, x1:x2]
                    if cropped_zone.size == 0 or cropped_zone.shape[0] < 10 or cropped_zone.shape[1] < 10:
                        continue
                    pil_crop = Image.fromarray(cropped_zone)

                    defect_results = cv_model_detents.predict(images=pil_crop, conf=0.25)
                    defect_detections = defect_results[0]

                    if len(defect_detections) > 0:
                        shifted_xyxy = defect_detections.xyxy + np.array([x1, y1, x1, y1])
                        shifted_detections = sv.Detections(
                            xyxy=shifted_xyxy, confidence=defect_detections.confidence,
                            class_id=defect_detections.class_id
                        )
                        annotated_img = defect_annotator.annotate(scene=annotated_img, detections=shifted_detections)

                        for d_id in defect_detections.class_id:
                            if d_id in DETAIL_DAMAGE_CLASSES:
                                found_detailed_defects.add(DETAIL_DAMAGE_CLASSES[d_id])

                img_byte_arr = io.BytesIO()
                annotated_img.save(img_byte_arr, format='JPEG')
                base64_str = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
                processed_images_b64.append(base64_str)
            else:
                base64_str = base64.b64encode(res.content).decode('utf-8')
                processed_images_b64.append(base64_str)

        except Exception as e:
            # FIX: Replaced raw print statements with standard logging tracking
            logging.exception(f"Computer vision frame evaluation failed for resource URL: {url}")
            continue

    return {
        "images": processed_images_b64,
        "reports": list(found_global_zones) + list(found_detailed_defects)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)