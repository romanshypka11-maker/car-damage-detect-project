import json
import logging
from typing import Any

import pandas as pd
from catboost import CatBoostRegressor

from core.config import get_settings

logger = logging.getLogger(__name__)

_model: CatBoostRegressor | None = None
_feature_columns: list[str] | None = None


def _load_feature_columns() -> list[str]:
    global _feature_columns
    if _feature_columns is None:
        settings = get_settings()
        with open(settings.feature_columns_path, encoding="utf-8") as f:
            _feature_columns = json.load(f)
    return _feature_columns


def get_model() -> CatBoostRegressor:
    global _model
    if _model is None:
        settings = get_settings()
        logger.info("Loading CatBoost price model from %s", settings.catboost_model_path)
        _model = CatBoostRegressor()
        _model.load_model(str(settings.catboost_model_path))
    return _model


def predict_price(features: dict[str, Any]) -> float:
    columns = _load_feature_columns()
    input_df = pd.DataFrame(features)

    for col in columns:
        if col not in input_df.columns:
            input_df[col] = "" if col == "accident_details" else 0

    input_df = input_df[columns]
    prediction = get_model().predict(input_df)[0]
    return float(prediction)
