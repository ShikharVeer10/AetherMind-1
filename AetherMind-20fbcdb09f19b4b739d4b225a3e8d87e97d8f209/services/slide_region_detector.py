"""
Slide Region Detector
=====================
Identifies the actual document/slide content area within a screenshot,
cropping out application UI chrome (toolbars, sidebars, taskbars).

This is critical for screenshot inputs where the user takes a screenshot
of a PDF viewer, presentation tool, etc. The actual slide is a sub-region
of the full screenshot image.
"""

from __future__ import annotations
import io
from typing import Optional, Tuple, Dict, Any

import numpy as np
from PIL import Image


class SlideRegionDetector:
    """Detects and crops the actual slide/document content from a screenshot."""

    # Minimum fraction of the screenshot area that a detected region must
    # occupy to be considered the "main content" (avoids tiny false positives).
    MIN_CONTENT_AREA_RATIO = 0.15

    # Common application UI zone heights (as fraction of image height)
    TOOLBAR_MAX_FRACTION = 0.25  # Top 25% could be toolbars
    TASKBAR_MAX_FRACTION = 0.08  # Bottom 8% could be OS taskbar
    SIDEBAR_MAX_FRACTION = 0.30  # Left/right 30% could be sidebar

    def detect_slide_region(
        self, image_bytes: bytes
    ) -> Tuple[Optional[bytes], Dict[str, Any]]:
        """
        Detect the slide/document content region and return the cropped image.

        Returns:
            (cropped_image_bytes, metadata_dict)
            If no crop is needed (image appears to be already a clean slide),
            returns (None, metadata) and the caller should use the original.
        """
        try:
            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            img_array = np.array(img)
            h, w = img_array.shape[:2]

            # Strategy 1: Look for the largest rectangular content area
            # by finding strong horizontal/vertical edges that delimit a box
            crop_box = self._find_content_rectangle(img_array, w, h)

            if crop_box is None:
                # Strategy 2: Heuristic-based UI zone removal
                crop_box = self._heuristic_ui_removal(img_array, w, h)

            if crop_box is None:
                return None, {"method": "none", "reason": "no UI chrome detected"}

            x1, y1, x2, y2 = crop_box
            crop_w = x2 - x1
            crop_h = y2 - y1

            # Don't crop if the result is too small
            if (crop_w * crop_h) < (w * h * self.MIN_CONTENT_AREA_RATIO):
                return None, {"method": "none", "reason": "detected region too small"}

            # Don't crop if we'd only be trimming tiny margins
            if crop_w > w * 0.95 and crop_h > h * 0.95:
                return None, {"method": "none", "reason": "region covers nearly full image"}

            cropped = img.crop((x1, y1, x2, y2))
            buf = io.BytesIO()
            cropped.save(buf, format="JPEG", quality=95)
            cropped_bytes = buf.getvalue()

            metadata = {
                "method": "content_rectangle",
                "original_size": (w, h),
                "crop_box": (x1, y1, x2, y2),
                "crop_size": (crop_w, crop_h),
                "content_area_ratio": (crop_w * crop_h) / (w * h),
            }

            print(
                f"[SlideRegionDetector] Cropped slide region: "
                f"({x1},{y1})-({x2},{y2}) from {w}x{h} "
                f"({metadata['content_area_ratio']:.1%} of original)"
            )

            return cropped_bytes, metadata

        except Exception as e:
            print(f"[SlideRegionDetector] Detection failed: {e}")
            return None, {"method": "error", "reason": str(e)}

    def _find_content_rectangle(
        self, img: np.ndarray, w: int, h: int
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        Find the largest uniform-background rectangular region that looks
        like an embedded document/slide.

        Uses edge detection to find strong rectangular boundaries.
        """
        import cv2

        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)

        # Apply edge detection
        edges = cv2.Canny(gray, 30, 100)

        # Dilate edges to connect nearby edge segments
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        dilated = cv2.dilate(edges, kernel, iterations=2)

        # Find contours
        contours, _ = cv2.findContours(
            dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            return None

        # Look for the largest rectangular contour that could be a slide
        best_box = None
        best_area = 0
        total_area = w * h

        for contour in contours:
            area = cv2.contourArea(contour)
            if area < total_area * self.MIN_CONTENT_AREA_RATIO:
                continue

            # Approximate the contour to a polygon
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

            # We want roughly rectangular shapes (4 vertices)
            if 4 <= len(approx) <= 8:
                x, y, bw, bh = cv2.boundingRect(approx)
                rect_area = bw * bh

                # Check aspect ratio is reasonable for a slide (not a thin bar)
                aspect = bw / bh if bh > 0 else 0
                if 0.5 < aspect < 3.0 and rect_area > best_area:
                    # Must not be the full image itself
                    if rect_area < total_area * 0.95:
                        best_box = (x, y, x + bw, y + bh)
                        best_area = rect_area

        return best_box

    def _heuristic_ui_removal(
        self, img: np.ndarray, w: int, h: int
    ) -> Optional[Tuple[int, int, int, int]]:
        """
        Use luminance gradient analysis to detect UI chrome zones.

        Application UIs typically have distinct color bands at edges:
        - Dark/gray toolbars at top
        - Gray sidebars on left
        - Taskbar at bottom

        The slide content area typically has a different luminance profile.
        """
        gray = np.mean(img, axis=2)  # Luminance

        # Analyze horizontal strips to find toolbar/taskbar boundaries
        strip_height = max(1, h // 100)

        # Scan from top down: find where the UI toolbar ends
        top_boundary = 0
        for y in range(0, int(h * self.TOOLBAR_MAX_FRACTION), strip_height):
            strip = gray[y : y + strip_height, :]
            mean_lum = np.mean(strip)
            std_lum = np.std(strip)

            # UI toolbars tend to have uniform luminance (low std)
            # The slide content typically has more variance
            if std_lum > 30 and y > h * 0.05:
                # Check if there's a significant luminance shift
                prev_strip = gray[max(0, y - strip_height) : y, :]
                if abs(np.mean(prev_strip) - mean_lum) > 15:
                    top_boundary = y
                    break

        # Scan from bottom up: find where taskbar begins
        bottom_boundary = h
        for y in range(h - strip_height, int(h * (1 - self.TASKBAR_MAX_FRACTION)), -strip_height):
            strip = gray[y : y + strip_height, :]
            mean_lum = np.mean(strip)

            # OS taskbars are usually very dark or have a specific color
            if mean_lum < 60 and y < h * 0.95:
                bottom_boundary = y
                break

        # Scan from left: find where sidebar ends
        strip_width = max(1, w // 100)
        left_boundary = 0
        for x in range(0, int(w * self.SIDEBAR_MAX_FRACTION), strip_width):
            strip = gray[:, x : x + strip_width]
            mean_lum = np.mean(strip)

            # Check for sidebar-to-content transition
            if x > w * 0.05:
                prev_strip = gray[:, max(0, x - strip_width) : x]
                if abs(np.mean(prev_strip) - mean_lum) > 20:
                    left_boundary = x
                    break

        # Right boundary: usually no sidebar on right for PDF viewers
        right_boundary = w

        # Only return if we actually found significant UI to remove
        removed_area = (
            (top_boundary * w)
            + ((h - bottom_boundary) * w)
            + (left_boundary * (bottom_boundary - top_boundary))
        )

        if removed_area > w * h * 0.05:  # At least 5% UI removed
            return (left_boundary, top_boundary, right_boundary, bottom_boundary)

        return None

    def filter_ocr_by_region(
        self,
        ocr_results: list,
        crop_metadata: Dict[str, Any],
        original_w: int,
        original_h: int,
    ) -> list:
        """
        Filter OCR results to only include text boxes within the detected
        content region.

        Args:
            ocr_results: List of (bbox, text, confidence) tuples from EasyOCR
            crop_metadata: Metadata from detect_slide_region
            original_w: Original image width
            original_h: Original image height

        Returns:
            Filtered OCR results with coordinates remapped to the cropped region
        """
        if crop_metadata.get("method") == "none":
            return ocr_results

        crop_box = crop_metadata.get("crop_box")
        if not crop_box:
            return ocr_results

        cx1, cy1, cx2, cy2 = crop_box
        filtered = []

        for bbox, text, conf in ocr_results:
            # Get the center of the OCR bounding box
            try:
                xs = [float(p[0]) for p in bbox]
                ys = [float(p[1]) for p in bbox]
                center_x = sum(xs) / len(xs)
                center_y = sum(ys) / len(ys)
            except (TypeError, IndexError, ValueError):
                continue

            # Check if the center is within the content region
            if cx1 <= center_x <= cx2 and cy1 <= center_y <= cy2:
                # Remap coordinates to the cropped region
                new_bbox = [
                    [p[0] - cx1, p[1] - cy1] for p in bbox
                ]
                filtered.append((new_bbox, text, conf))

        print(
            f"[SlideRegionDetector] Filtered OCR: "
            f"{len(ocr_results)} → {len(filtered)} boxes "
            f"(removed {len(ocr_results) - len(filtered)} UI elements)"
        )

        return filtered
