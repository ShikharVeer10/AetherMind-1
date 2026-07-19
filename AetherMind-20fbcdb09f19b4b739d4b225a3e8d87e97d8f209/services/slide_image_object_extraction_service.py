from __future__ import annotations

import io
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
from PIL import Image

from models.document_model import DocumentElementModel, PositionModel, StyleModel


class SlideImageObjectExtractionService:
    """Extract visible non-text slide objects from a flat slide image.

    This is a pixel-structure inventory stage, not OCR and not captioning. It
    detects visible regions that the renderer must preserve: panels, divider
    lines, shape/icon-like components, and large visual regions. Text itself is
    still handled by the existing OCR branch and is used here only as exclusion
    geometry so text glyphs are not duplicated as shapes.
    """

    def extract_visual_objects(
        self,
        image_bytes: bytes,
        canvas_width: float,
        canvas_height: float,
        existing_elements: Sequence[DocumentElementModel] | None = None,
        start_z_order: int = 1,
        slide_number: int = 1,
    ) -> List[DocumentElementModel]:
        try:
            import cv2
        except Exception as exc:
            print(f"[SlideImageObjectExtractionService] OpenCV unavailable: {exc}")
            return []

        try:
            pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            rgb = np.array(pil_img)
            img_h, img_w = rgb.shape[:2]
            bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        except Exception as exc:
            print(f"[SlideImageObjectExtractionService] Could not decode image: {exc}")
            return []

        text_boxes = [
            self._element_bbox_px(e, img_w, img_h, canvas_width, canvas_height)
            for e in (existing_elements or [])
            if getattr(e, "text", None) and getattr(e, "element_type", "") in {"text_box", "text"}
        ]
        existing_boxes = [
            self._element_bbox_px(e, img_w, img_h, canvas_width, canvas_height)
            for e in (existing_elements or [])
            if getattr(e, "element_type", "") not in {"image"}
        ]

        objects: List[DocumentElementModel] = []
        seen: List[Tuple[int, int, int, int]] = []
        z_order = start_z_order

        contour_boxes = self._detect_contour_objects(gray, img_w, img_h)
        line_boxes = self._detect_line_objects(gray, img_w, img_h)
        color_region_boxes = self._detect_color_regions(bgr, img_w, img_h)

        for box, source, confidence in contour_boxes + line_boxes + color_region_boxes:
            if self._is_mostly_text(box, text_boxes):
                continue
            if self._is_duplicate(box, seen):
                continue
            if self._is_duplicate_existing(box, existing_boxes, source):
                continue

            x, y, w, h = box
            element_type, shape_type = self._classify_box(box, img_w, img_h, source)
            style = self._sample_style(bgr, box, element_type)
            elem = DocumentElementModel(
                element_id=f"slide_{slide_number}_visual_{len(objects) + 1}",
                element_type=element_type,
                text="",
                paragraphs=[],
                position=PositionModel(
                    x=(x / img_w) * canvas_width,
                    y=(y / img_h) * canvas_height,
                    width=(w / img_w) * canvas_width,
                    height=(h / img_h) * canvas_height,
                ),
                style=style,
                shape_type=shape_type,
                metadata={
                    "name": f"Detected {element_type} {len(objects) + 1}",
                    "visible": True,
                    "is_placeholder": False,
                    "z_order": z_order,
                    "detected_from_pixels": True,
                    "detection_source": source,
                    "confidence": confidence,
                    "preserve_for_regeneration": True,
                },
            )
            objects.append(elem)
            seen.append(box)
            z_order += 1

        self._assign_visual_children(objects, existing_elements or [])
        print(f"[SlideImageObjectExtractionService] Detected {len(objects)} non-text visual objects")
        return objects

    def _detect_contour_objects(self, gray, img_w: int, img_h: int) -> List[Tuple[Tuple[int, int, int, int], str, float]]:
        import cv2

        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(blurred, 40, 120)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        results = []
        slide_area = img_w * img_h
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            if area < slide_area * 0.0005:
                continue
            if area > slide_area * 0.92:
                continue
            if w < 3 or h < 3:
                continue
            aspect = w / max(h, 1)
            if aspect > 80 or aspect < 0.0125:
                continue
            contour_area = cv2.contourArea(contour)
            fill_ratio = contour_area / max(area, 1)
            confidence = min(0.95, max(0.45, fill_ratio))
            results.append(((x, y, w, h), "contour", round(confidence, 3)))
        return sorted(results, key=lambda item: item[0][2] * item[0][3], reverse=True)

    def _detect_line_objects(self, gray, img_w: int, img_h: int) -> List[Tuple[Tuple[int, int, int, int], str, float]]:
        import cv2

        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        min_len = max(25, int(min(img_w, img_h) * 0.06))
        lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=60, minLineLength=min_len, maxLineGap=8)
        if lines is None:
            return []

        results = []
        for line in lines[:160]:
            x1, y1, x2, y2 = [int(v) for v in line[0]]
            x = min(x1, x2)
            y = min(y1, y2)
            w = max(abs(x2 - x1), 2)
            h = max(abs(y2 - y1), 2)
            if w * h > img_w * img_h * 0.25:
                continue
            pad = 2
            results.append(((max(0, x - pad), max(0, y - pad), min(img_w - x, w + pad * 2), min(img_h - y, h + pad * 2)), "line", 0.82))
        return results

    def _detect_color_regions(self, bgr, img_w: int, img_h: int) -> List[Tuple[Tuple[int, int, int, int], str, float]]:
        import cv2

        quantized = (bgr // 24) * 24
        flat = quantized.reshape(-1, 3)
        colors, counts = np.unique(flat, axis=0, return_counts=True)
        slide_area = img_w * img_h
        candidates = []
        for color, count in sorted(zip(colors, counts), key=lambda item: item[1], reverse=True)[:10]:
            if count < slide_area * 0.01 or count > slide_area * 0.80:
                continue
            mask = cv2.inRange(quantized, color, color)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                area = w * h
                if area < slide_area * 0.004 or area > slide_area * 0.85:
                    continue
                candidates.append(((x, y, w, h), "color_region", 0.72))
        return candidates

    @staticmethod
    def _classify_box(box: Tuple[int, int, int, int], img_w: int, img_h: int, source: str) -> Tuple[str, str]:
        x, y, w, h = box
        aspect = w / max(h, 1)
        area_ratio = (w * h) / max(img_w * img_h, 1)
        if source == "line" or h <= 4 or w <= 4 or aspect > 12 or aspect < 0.08:
            return "line", "line"
        if area_ratio > 0.04 and source in {"color_region", "contour"}:
            return "shape", "panel"
        if max(w, h) < max(img_w, img_h) * 0.08:
            return "icon", "pixel_icon"
        return "shape", "rect"

    @staticmethod
    def _sample_style(bgr, box: Tuple[int, int, int, int], element_type: str) -> StyleModel:
        x, y, w, h = box
        crop = bgr[y : y + h, x : x + w]
        if crop.size == 0:
            fill = "#ffffff"
            stroke = "#000000"
        else:
            median = np.median(crop.reshape(-1, 3), axis=0)
            fill = f"#{int(median[2]):02x}{int(median[1]):02x}{int(median[0]):02x}"
            border_pixels = np.concatenate([
                crop[0:1, :, :].reshape(-1, 3),
                crop[-1:, :, :].reshape(-1, 3),
                crop[:, 0:1, :].reshape(-1, 3),
                crop[:, -1:, :].reshape(-1, 3),
            ])
            stroke_median = np.median(border_pixels, axis=0)
            stroke = f"#{int(stroke_median[2]):02x}{int(stroke_median[1]):02x}{int(stroke_median[0]):02x}"
        if element_type == "line":
            return StyleModel(background_color=None, border_color=stroke, border_thickness=1.0, border_style="solid", opacity=1.0)
        return StyleModel(background_color=fill, border_color=stroke, border_thickness=1.0, border_style="solid", opacity=1.0)

    @staticmethod
    def _element_bbox_px(
        element: DocumentElementModel,
        img_w: int,
        img_h: int,
        canvas_w: float,
        canvas_h: float,
    ) -> Tuple[int, int, int, int]:
        p = element.position
        x = int((p.x / canvas_w) * img_w)
        y = int((p.y / canvas_h) * img_h)
        w = int((p.width / canvas_w) * img_w)
        h = int((p.height / canvas_h) * img_h)
        return x, y, max(1, w), max(1, h)

    @staticmethod
    def _overlap_ratio(a: Tuple[int, int, int, int], b: Tuple[int, int, int, int]) -> float:
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        x1 = max(ax, bx)
        y1 = max(ay, by)
        x2 = min(ax + aw, bx + bw)
        y2 = min(ay + ah, by + bh)
        if x2 <= x1 or y2 <= y1:
            return 0.0
        overlap = (x2 - x1) * (y2 - y1)
        return overlap / max(min(aw * ah, bw * bh), 1)

    def _is_mostly_text(self, box: Tuple[int, int, int, int], text_boxes: Sequence[Tuple[int, int, int, int]]) -> bool:
        return any(self._overlap_ratio(box, text_box) > 0.45 for text_box in text_boxes)

    def _is_duplicate(self, box: Tuple[int, int, int, int], seen: Sequence[Tuple[int, int, int, int]]) -> bool:
        return any(self._overlap_ratio(box, prior) > 0.70 for prior in seen)

    def _is_duplicate_existing(self, box: Tuple[int, int, int, int], existing: Sequence[Tuple[int, int, int, int]], source: str) -> bool:
        threshold = 0.82 if source == "line" else 0.65
        return any(self._overlap_ratio(box, prior) > threshold for prior in existing)

    @staticmethod
    def _assign_visual_children(
        visual_objects: Sequence[DocumentElementModel],
        existing_elements: Sequence[DocumentElementModel],
    ) -> None:
        containers = [
            obj for obj in visual_objects
            if obj.element_type == "shape" and obj.shape_type in {"panel", "rect"}
        ]
        for child in existing_elements:
            if getattr(child, "element_type", "") == "image":
                continue
            cp = child.position
            cx = cp.x + cp.width / 2.0
            cy = cp.y + cp.height / 2.0
            containing = []
            for container in containers:
                pp = container.position
                if pp.x <= cx <= pp.x + pp.width and pp.y <= cy <= pp.y + pp.height:
                    containing.append(container)
            if not containing:
                continue
            parent = min(containing, key=lambda c: c.position.width * c.position.height)
            if not getattr(child, "parent", None):
                child.parent = parent.element_id
            if child.element_id not in parent.children:
                parent.children.append(child.element_id)
