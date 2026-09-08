from typing import Annotated, TypedDict
import time
import logging
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from functools import lru_cache
from ai_agent.llm import generate_car_verdict, generate_sql_via_qwen
from ai_agent.sql_guard import validate_sql
from ai_agent.tools import (
    tool_analyze_damage,
    tool_get_auction_photos,
    tool_predict_price,
    tool_query_database,
    tool_scrape_autoria,
)
from core.timing import new_request_id, log_duration_async, log_duration_sync

logger = logging.getLogger(__name__)

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    user_text: str
    intent: str
    car_data: dict | None
    predicted_price: float | None
    auction_photos: list[str]
    cv_reports: list[str]
    cv_images: list[str]
    sql_query: str | None
    db_result: list[dict]
    verdict: str | None
    response: str | None


def _detect_intent(state: AgentState) -> AgentState:
    text = state["user_text"].lower()
    keywords = ["auto.ria.com", "ria.com", "auto.ria.ua", "auto.ria"]
    if any(keyword in text for keyword in keywords):
        state["intent"] = "analyze_car"
    else:
        state["intent"] = "analytics"
    return state

@log_duration_async("scrape_car_node")
async def _scrape_car_node(state: AgentState) -> AgentState:
    url = state["user_text"].strip()
    state["car_data"] = await tool_scrape_autoria(url)
    return state

@log_duration_sync("predict_price_node")
def _predict_price_node(state: AgentState) -> AgentState:
    data = state.get("car_data") or {}
    if "error" in data:
        return state

    body_type = data.get("body_type") or ""
    imported_from = data.get("imported_from") or ""
    is_suv = 1 if any(x in str(body_type).lower() for x in ["позашляховик", "кросовер", "джип", "suv"]) else 0
    is_imported = 1 if imported_from or data.get("is_imported") else 0
    fuel_type = (data.get("fuel_type") or "").lower()
    is_electric = 1 if "електр" in fuel_type or "electric" in fuel_type else 0

    features = {
        "make": [data.get("make") or ""],
        "model": [data.get("model") or ""],
        "year": [int(data.get("year") or 0)],
        "mileage_km": [int(data.get("mileage_km") or 0)],
        "engine_volume_l": [float(data.get("engine_volume_l") or 0.0)],
        "horsepower": [int(data.get("horsepower") or 0)],
        "battery_capacity_kwh": [float(data.get("battery_capacity_kwh") or 0.0)],
        "ev_range_km": [int(data.get("ev_range_km") or 0)],
        "is_suv": [is_suv],
        "is_imported": [is_imported],
        "is_electric": [is_electric],
        "has_accident": [1 if data.get("has_accident") else 0],
        "accident_details": [data.get("accident_details") or ""],
        "body_type": [body_type],
        "fuel_type": [data.get("fuel_type") or ""],
        "transmission": [data.get("transmission") or ""],
        "color": [data.get("color") or ""],
        "description": [(data.get("description") or "")[:300]],
    }
    print("--- RAW FEATURES FOR CATBOOST ---")
    print(features)
    print ("- ---------------------------------")

    state["predicted_price"] = tool_predict_price(features)
    return state

@log_duration_async("fetch_photos_node")
async def _fetch_auction_photos_node(state: AgentState) -> AgentState:
    data = state.get("car_data") or {}
    vin = data.get("vin")
    if vin and len(vin) == 17:
        state["auction_photos"] = await tool_get_auction_photos(vin)
    else:
        state["auction_photos"] = []
    return state

@log_duration_sync("analyze_damage_node")
def _analyze_damage_node(state: AgentState) -> AgentState:
    photos = state.get("auction_photos") or []
    if photos:
        result = tool_analyze_damage(photos)
        state["cv_images"] = result.get("images", [])
        state["cv_reports"] = result.get("reports", [])
    else:
        state["cv_images"] = []
        state["cv_reports"] = []
    return state

@log_duration_async("generate_verdict_node")
async def _generate_verdict_node(state: AgentState) -> AgentState:
    state["verdict"] = await generate_car_verdict(
        car_data=state.get("car_data") or {},
        cv_reports=state.get("cv_reports") or [],
        predicted_price=state.get("predicted_price") or 0.0,
    )
    return state


async def _analytics_node(state: AgentState) -> AgentState:
    raw_sql = await generate_sql_via_qwen(state["user_text"])
    validated = validate_sql(raw_sql)
    state["sql_query"] = validated

    if validated:
        state["db_result"] = await tool_query_database(validated)
    else:
        state["db_result"] = []

    return state


def _route_intent(state: AgentState) -> str:
    return state.get("intent", "analytics")


def build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("detect_intent", _detect_intent)
    graph.add_node("scrape_car", _scrape_car_node)
    graph.add_node("predict_price", _predict_price_node)
    graph.add_node("fetch_photos", _fetch_auction_photos_node)
    graph.add_node("analyze_damage", _analyze_damage_node)
    graph.add_node("generate_verdict", _generate_verdict_node)
    graph.add_node("analytics", _analytics_node)

    graph.add_edge(START, "detect_intent")
    graph.add_conditional_edges(
        "detect_intent",
        _route_intent,
        {
            "analyze_car": "scrape_car",
            "analytics": "analytics",
        },
    )
    graph.add_edge("scrape_car", "predict_price")
    graph.add_edge("predict_price", "fetch_photos")
    graph.add_edge("fetch_photos", "analyze_damage")
    graph.add_edge("analyze_damage", "generate_verdict")
    graph.add_edge("generate_verdict", END)
    graph.add_edge("analytics", END)

    return graph.compile()

@lru_cache(maxsize=1)
def get_graph():
    return build_graph()


async def ask(user_text: str) -> dict:
    rid = new_request_id()
    logger.info("[%s] New request: %s", rid, user_text[:80])

    graph = get_graph()
    initial_state: AgentState = {
        "messages": [],
        "user_text": user_text,
        "intent": "",
        "car_data": None,
        "predicted_price": None,
        "auction_photos": [],
        "cv_reports": [],
        "cv_images": [],
        "sql_query": None,
        "db_result": [],
        "verdict": None,
        "response": None,
    }
    start = time.perf_counter()
    result = await graph.ainvoke(initial_state)
    logger.info("[%s] TOTAL graph.ainvoke took %.0fms", rid, (time.perf_counter() - start) * 1000)
    return dict(result)
