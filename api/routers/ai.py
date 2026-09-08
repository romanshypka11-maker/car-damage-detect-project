import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ai_agent.graph import ask
from ai_agent.llm import generate_car_verdict, generate_sql_via_qwen
from ai_agent.sql_guard import validate_sql
from core.db import fetch_all
from core.timing import get_request_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["ai"])


class UserRequest(BaseModel):
    text: str


class VerdictRequest(BaseModel):
    car_data: Dict[str, Any]
    cv_reports: List[str]
    predicted_price: float


class AgentRequest(BaseModel):
    text: str


@router.post("/ask")
async def ask_ai_database(request: UserRequest):
    logger.info("Incoming Text-to-SQL query: '%s'", request.text)
    try:
        raw_sql = await generate_sql_via_qwen(request.text)
    except Exception:
        logger.exception("LLM SQL generation failed")
        raise HTTPException(status_code=500, detail="Помилка генерації ШІ")

    sql_query = validate_sql(raw_sql)
    if not sql_query:
        raise HTTPException(status_code=400, detail="ШІ не зміг побудувати валідний SQL-запит.")

    try:
        result_data = await fetch_all(sql_query)
        return {"status": "success", "sql_used": sql_query, "result": result_data}
    except Exception as db_err:
        logger.exception("SQL execution failed")
        raise HTTPException(status_code=500, detail=f"Помилка БД: {str(db_err)}")


@router.post("/verdict")
async def get_car_verdict(request: VerdictRequest):
    verdict_text = await generate_car_verdict(
        car_data=request.car_data,
        cv_reports=request.cv_reports,
        predicted_price=request.predicted_price,
    )
    return {"status": "success", "verdict": verdict_text}


@router.post("/agent")
async def run_agent(request: AgentRequest):
    try:
        result = await ask(request.text)
        return {"status": "success", "result": result, "request_id": get_request_id()}
    except Exception:
        logger.exception("Agent execution failed")
        raise HTTPException(status_code=500, detail="Помилка виконання агента")
