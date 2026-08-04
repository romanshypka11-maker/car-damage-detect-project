import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from pricing.model import predict_price

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pricing"])


class PricePredictRequest(BaseModel):
    features: Dict[str, Any]


@router.post("/predict-price")
def predict_price_endpoint(request: PricePredictRequest):
    try:
        price = predict_price(request.features)
        return {"predicted_price": price}
    except Exception as e:
        logger.exception("CatBoost prediction failed")
        raise HTTPException(status_code=500, detail=f"Помилка CatBoost: {str(e)}")
