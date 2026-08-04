import base64
import io
import logging
from typing import Any

import cv2
import numpy as np
import requests
import supervision as sv
from PIL import Image
from rfdetr import RFDETRMedium

from core.config import get_settings

logger = logging.getLogger(__name__)

ZONE_CLASSES = {
    1: "Пошкоджено кузов (зона)",
    2: "Пошкоджено внутрішні вузли/салон/безпека (зона)",
}

DETAIL_DAMAGE_CLASSES = {
    0: "Auto-Auction-Damage-MVP",
    1: "Circles_marks",
    2: "X-marks",
    3: "broken_glass",
    4: "broken_headlight",
    5: "broken_mirror",
    6: "damage_front_bamber",
    7: "damaged-hood",
    8: "damaged_rear_bumper",
    9: "damaged_trunk",
    10: "damaged_upholstery",
    11: "damaged_wheel",
    12: "dent",
    13: "deployed_airbag_front",
    14: "deployed_airbag_rear",
    15: "door_damage",
    16: "flooded_interior",
    17: "ground",
    18: "interior_corrosion",
    19: "messy_interier",
    20: "missing_bumper",
    21: "missing_rear_bumper",
    22: "rust",
    23: "scratch",
    24: "severe_bumper_damage",
    25: "severe_door_damage",
    26: "severe_rear_bumper_damage",
    27: "severe_side_damage",
    28: "side_damage",
}

_zone_model: RFDETRMedium | None = None
_defects_model: RFDETRMedium | None = None


def _get_zone_model() -> RFDETRMedium:
    global _zone_model
    if _zone_model is None:
        settings = get_settings()
        logger.info("Loading zone detection model from %s", settings.cv_zone_model_path)
        _zone_model = RFDETRMedium(
            pretrain_weights=str(settings.cv_zone_model_path),
            patch_size=16,
        )
    return _zone_model


def _get_defects_model() -> RFDETRMedium:
    global _defects_model
    if _defects_model is None:
        settings = get_settings()
        logger.info("Loading defect detection model from %s", settings.cv_defects_model_path)
        _defects_model = RFDETRMedium(
            pretrain_weights=str(settings.cv_defects_model_path),
            patch_size=16,
        )
    return _defects_model


def analyze_damage(urls: list[str], max_images: int = 10) -> dict[str, Any]:
    processed_images_b64: list[str] = []
    found_global_zones: set[str] = set()
    found_detailed_defects: set[str] = set()

    zone_model = _get_zone_model()
    defects_model = _get_defects_model()
    zone_annotator = sv.BoxAnnotator(color=sv.Color.RED)
    defect_annotator = sv.BoxAnnotator(color=sv.Color.YELLOW)

    for url in urls[:max_images]:
        try:
            res = requests.get(url, timeout=7)
            if res.status_code != 200:
                continue

            img_bgr = cv2.imdecode(np.frombuffer(res.content, np.uint8), cv2.IMREAD_COLOR)
            if img_bgr is None:
                continue
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)

            zone_results = zone_model.predict(images=pil_img, conf=0.25)
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

                    defect_results = defects_model.predict(images=pil_crop, conf=0.25)
                    defect_detections = defect_results[0]

                    if len(defect_detections) > 0:
                        shifted_xyxy = defect_detections.xyxy + np.array([x1, y1, x1, y1])
                        shifted_detections = sv.Detections(
                            xyxy=shifted_xyxy,
                            confidence=defect_detections.confidence,
                            class_id=defect_detections.class_id,
                        )
                        annotated_img = defect_annotator.annotate(
                            scene=annotated_img,
                            detections=shifted_detections,
                        )

                        for d_id in defect_detections.class_id:
                            if d_id in DETAIL_DAMAGE_CLASSES:
                                found_detailed_defects.add(DETAIL_DAMAGE_CLASSES[d_id])

                img_byte_arr = io.BytesIO()
                annotated_img.save(img_byte_arr, format="JPEG")
                processed_images_b64.append(base64.b64encode(img_byte_arr.getvalue()).decode("utf-8"))
            else:
                processed_images_b64.append(base64.b64encode(res.content).decode("utf-8"))

        except Exception:
            logger.exception("Computer vision frame evaluation failed for URL: %s", url)
            continue

    return {
        "images": processed_images_b64,
        "reports": list(found_global_zones) + list(found_detailed_defects),
    }
