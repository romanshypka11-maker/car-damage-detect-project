import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from damage_detection.analyzer import analyze_damage

logger = logging.getLogger(__name__)
router = APIRouter(tags=["damage"])


class DamageAnalysisRequest(BaseModel):
    urls: List[str]


@router.post("/analyze-damage")
def analyze_damage_endpoint(request: DamageAnalysisRequest):
    try:
        return analyze_damage(request.urls)
    except Exception as e:
        logger.exception("Damage analysis failed")
        raise HTTPException(status_code=500, detail=f"Помилка CV: {str(e)}")
