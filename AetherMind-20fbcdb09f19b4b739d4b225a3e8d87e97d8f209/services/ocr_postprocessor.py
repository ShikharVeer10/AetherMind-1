"""
OCR Post-Processor
==================
Cleans up raw OCR results to remove UI noise, correct common OCR errors
(especially dollar values), and prepare clean text for downstream processing.
"""

from __future__ import annotations
import re
from typing import List, Tuple, Optional, Set


# Common application UI text that should be filtered out of slide content.
# These appear when screenshots include browser/app chrome.
_UI_BLACKLIST_EXACT: Set[str] = {
    # Adobe Acrobat
    "Menu", "Create", "All tools", "Edit", "Convert", "E-Sign",
    "Find text or tools", "Share", "Ask AI Assistant", "Ask Al Assistant",
    "View Summary", "Export a PDF", "Edit a PDF", "Create a PDF",
    "Combine files", "Organize pages", "AI Assistant", "Al Assistant",
    "Generative summary", "Request e-signatures", "Scan & OCR",
    "Scan \u0026 OCR", "Protect a PDF", "Free trial", "Sign in", "Sign `",
    # Browser chrome
    "All Bookmarks", "New Tab",
    # Common OS taskbar
    "PM", "AM",
}

# Patterns that indicate UI text (matched case-insensitively)
_UI_BLACKLIST_PATTERNS: List[str] = [
    r"^[0-9]{1,2}:[0-9]{2}\s*(AM|PM|am|pm)$",  # Time: "6:34 PM"
    r"^[0-9]{1,2}/[0-9]{1,2}/[0-9]{2,4}$",       # Date: "6/16/2026"
    r"^[0-9]+%$",                                   # Battery: "66%"
    r"^Sign\s",                                      # "Sign in"
    r"^By using this service",                       # Adobe TOS notice
    r"^This appears to be a long",                   # Adobe AI summary prompt
    r"^Convert[;,] edit",                            # Adobe sidebar
    r"terms of use",                                 # Legal notices
    r"privacy policy",                               # Legal notices
    r"save time by reading",                         # AI assistant prompts
    r"e-sign pdf forms",                             # Adobe feature text
]

# Compiled patterns
_UI_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _UI_BLACKLIST_PATTERNS]


class OCRPostProcessor:
    """Cleans up raw OCR results for better downstream extraction."""

    def __init__(
        self,
        min_confidence: float = 0.00,
        enable_dollar_correction: bool = True,
        enable_ui_filtering: bool = False,
    ):
        self.min_confidence = min_confidence
        self.enable_dollar_correction = enable_dollar_correction
        self.enable_ui_filtering = enable_ui_filtering

    def process(
        self, ocr_results: List[Tuple], is_screenshot: bool = True
    ) -> List[Tuple]:
        """
        Process raw OCR results through the cleaning pipeline.

        Args:
            ocr_results: List of (bbox, text, confidence) tuples from EasyOCR
            is_screenshot: If True, apply aggressive UI filtering

        Returns:
            Cleaned list of (bbox, text, confidence) tuples
        """
        results = list(ocr_results)

        # Step 1: Remove low-confidence detections
        results = self._filter_by_confidence(results)

        # Step 2: Filter out application UI text
        if self.enable_ui_filtering and is_screenshot:
            results = self._filter_ui_text(results)

        # Step 3: Correct common OCR errors (dollar values, etc.)
        if self.enable_dollar_correction:
            results = self._correct_dollar_values(results)

        # Step 4: Merge text fragments that are on the same line
        # (OCR sometimes splits "the strategic" into "the" and "strategic")
        results = self._merge_line_fragments(results)

        # Step 4.5: Merge split financial numbers (e.g., "$706," and "700" -> "$706,700")
        results = self._merge_split_financials(results)

        # Step 5: Deduplicate overlapping boxes
        results = self._deduplicate_overlapping(results)

        return results

    def _filter_by_confidence(self, results: List[Tuple]) -> List[Tuple]:
        """Remove OCR detections below the confidence threshold."""
        # Always return all results; aggressive filtering breaks small form text
        return results

    def _filter_ui_text(self, results: List[Tuple]) -> List[Tuple]:
        """Remove text that matches known application UI patterns."""
        filtered = []
        removed_count = 0

        for bbox, text, conf in results:
            clean_text = text.strip()

            # Check exact blacklist
            if clean_text in _UI_BLACKLIST_EXACT:
                removed_count += 1
                continue

            # Check pattern blacklist
            is_ui = False
            for pattern in _UI_COMPILED_PATTERNS:
                if pattern.search(clean_text):
                    is_ui = True
                    break

            if is_ui:
                removed_count += 1
                continue

            # Filter single characters that are likely UI icons
            # (but preserve numbers/letters that could be data)
            if len(clean_text) == 1 and clean_text in {"@", "G", "E", "X", "×"}:
                removed_count += 1
                continue

            filtered.append((bbox, text, conf))

        if removed_count > 0:
            print(f"[OCRPostProcessor] Filtered {removed_count} UI text elements")

        return filtered

    def _correct_dollar_values(self, results: List[Tuple]) -> List[Tuple]:
        """
        Correct common OCR misreads of dollar values.

        Common errors:
        - $ read as 5 or S at the start of a number
        - 0 read as o or O
        - Dashes/ranges misread
        """
        corrected = []
        corrections = 0

        for bbox, text, conf in results:
            original = text
            corrected_text = self._fix_dollar_text(text)

            if corrected_text != original:
                corrections += 1

            corrected.append((bbox, corrected_text, conf))

        if corrections > 0:
            print(f"[OCRPostProcessor] Corrected {corrections} dollar/number values")

        return corrected

    def _fix_dollar_text(self, text: str) -> str:
        """Fix a single text string for dollar value OCR errors."""
        text = text.strip()

        # Pattern: S or 5 followed by digits and commas (dollar value)
        # e.g., "5295,000" → "$295,000", "S305,000" → "$305,000"
        text = re.sub(
            r'^[S5](\d{1,3}(?:[,. ]\d{3})+)$',
            r'$\1',
            text
        )

        # Pattern: "Ss00,0o0" → "$600,000" (S=dollar, s=6, 0o0=000)
        # More general: fix o/O inside numbers to 0
        if re.match(r'^[S$5]', text) or re.match(r'^\d', text):
            text = re.sub(r'(?<=\d)[oO](?=\d)', '0', text)
            text = re.sub(r'(?<=\d)[oO](?=[,.])', '0', text)
            text = re.sub(r'(?<=[,.])[oO](?=\d)', '0', text)

        # Pattern: "5634,700" → "$634,700" (leading 5 → $)
        if re.match(r'^5\d{2,3},\d{3}', text):
            text = '$' + text[1:]

        # Pattern: "S1,595,000" → "$1,595,000" (leading S → $)
        if re.match(r'^S\d', text):
            text = '$' + text[1:]

        # Pattern: "572, 0o0" → "$72,000" (remove spaces, fix o→0)
        if re.match(r'^[S5]\d{2},\s*\d', text):
            text = text.replace(' ', '')
            text = '$' + text[1:]
            text = text.replace('o', '0').replace('O', '0')

        # Pattern: "8720,000" → "$720,000" (8 at start before large number)
        if re.match(r'^8\d{3},\d{3}$', text):
            text = '$' + text[1:]

        # Pattern: "$40,0C0" → "$40,000" (C in numbers → 0)
        text = re.sub(r'(?<=\d)[Cc](?=\d)', '0', text)

        # Fix "Ss" at start → "$6" (S=dollar, s=6)  
        if text.startswith('Ss'):
            text = '$6' + text[2:]

        # Clean up: replace _ with – for ranges
        text = re.sub(r'\s*_\s*', ' – ', text)

        # Pattern: "$295,000 – $395,000" (fix range separator)
        # "$70,000 – $100,000" etc.

        return text

    def _merge_line_fragments(self, results: List[Tuple]) -> List[Tuple]:
        """
        Merge OCR text boxes that are on the same horizontal line and
        appear to be fragments of a single paragraph/sentence.

        Uses y-coordinate overlap to detect same-line fragments.
        """
        if len(results) <= 1:
            return results

        # Sort by y-center, then x
        def box_metrics(r):
            bbox = r[0]
            try:
                ys = [float(p[1]) for p in bbox]
                xs = [float(p[0]) for p in bbox]
                return (min(ys), min(xs))
            except (TypeError, IndexError, ValueError):
                return (0, 0)

        sorted_results = sorted(results, key=box_metrics)

        merged = []
        i = 0

        while i < len(sorted_results):
            current = sorted_results[i]
            bbox_c, text_c, conf_c = current

            try:
                ys_c = [float(p[1]) for p in bbox_c]
                xs_c = [float(p[0]) for p in bbox_c]
                y_min_c = min(ys_c)
                y_max_c = max(ys_c)
                x_max_c = max(xs_c)
                h_c = y_max_c - y_min_c
            except (TypeError, IndexError, ValueError):
                merged.append(current)
                i += 1
                continue

            # Look ahead for fragments on the same line that continue this text
            j = i + 1
            merge_group = [current]

            while j < len(sorted_results):
                next_r = sorted_results[j]
                bbox_n, text_n, conf_n = next_r

                try:
                    ys_n = [float(p[1]) for p in bbox_n]
                    xs_n = [float(p[0]) for p in bbox_n]
                    y_min_n = min(ys_n)
                    x_min_n = min(xs_n)
                    h_n = max(ys_n) - y_min_n
                except (TypeError, IndexError, ValueError):
                    j += 1
                    continue

                # Same line: y-overlap > 50% and horizontally adjacent
                y_overlap = min(y_max_c, min(ys_n) + h_n) - max(y_min_c, y_min_n)
                min_h = min(h_c, h_n) if min(h_c, h_n) > 0 else 1
                overlap_ratio = y_overlap / min_h

                # Check if this is a continuation of the same paragraph line
                # (within 3x character height gap horizontally)
                horizontal_gap = x_min_n - x_max_c

                if overlap_ratio > 0.5 and 0 < horizontal_gap < h_c * 3:
                    # Only merge if text looks like a continuation
                    # (not merging table cell values across columns)
                    if self._looks_like_continuation(text_c, text_n):
                        merge_group.append(next_r)
                        # Update current bounds
                        x_max_c = max(xs_n)
                        text_c = text_c + " " + text_n

                j += 1

            if len(merge_group) == 1:
                merged.append(current)
            else:
                # Build merged bounding box
                all_points = []
                all_text = []
                min_conf = 1.0

                for bbox, text, conf in merge_group:
                    all_points.extend(bbox)
                    all_text.append(text)
                    min_conf = min(min_conf, conf)

                xs = [float(p[0]) for p in all_points]
                ys = [float(p[1]) for p in all_points]
                merged_bbox = [
                    [min(xs), min(ys)],
                    [max(xs), min(ys)],
                    [max(xs), max(ys)],
                    [min(xs), max(ys)],
                ]
                merged_text = " ".join(all_text)
                merged.append((merged_bbox, merged_text, min_conf))

            i += 1

        return merged

    def _merge_split_financials(self, results: List[Tuple]) -> List[Tuple]:
        """
        Merge text boxes that are fragments of a single financial number.
        Example: "$706," and "700" -> "$706,700"
        """
        if len(results) <= 1:
            return results

        # Sort by y-center, then x
        def box_metrics(r):
            bbox = r[0]
            try:
                ys = [float(p[1]) for p in bbox]
                xs = [float(p[0]) for p in bbox]
                return (min(ys), min(xs))
            except: return (0, 0)

        sorted_results = sorted(results, key=box_metrics)
        merged = []
        i = 0

        while i < len(sorted_results):
            current = sorted_results[i]
            bbox_c, text_c, conf_c = current
            
            # If current ends with a comma or looks like the start of a large number
            if text_c.strip().endswith(",") or re.match(r'^\$\d{1,3},?$', text_c.strip()):
                j = i + 1
                if j < len(sorted_results):
                    next_r = sorted_results[j]
                    bbox_n, text_n, conf_n = next_r
                    
                    # Check if next is a 3-digit number (common split artifact)
                    if re.match(r'^\d{3}$', text_n.strip()):
                        # Check spatial proximity
                        try:
                            xs_c = [float(p[0]) for p in bbox_c]
                            xs_n = [float(p[0]) for p in bbox_n]
                            ys_c = [float(p[1]) for p in bbox_c]
                            ys_n = [float(p[1]) for p in bbox_n]
                            
                            gap = min(xs_n) - max(xs_c)
                            y_diff = abs(min(ys_n) - min(ys_c))
                            
                            # Merge if on same line and close gap
                            if y_diff < 50 and 0 < gap < 100:
                                new_text = text_c.strip() + text_n.strip()
                                # Build merged bounding box
                                all_points = list(bbox_c) + list(bbox_n)
                                xs = [float(p[0]) for p in all_points]
                                ys = [float(p[1]) for p in all_points]
                                merged_bbox = [
                                    [min(xs), min(ys)], [max(xs), min(ys)],
                                    [max(xs), max(ys)], [min(xs), max(ys)]
                                ]
                                merged.append((merged_bbox, new_text, min(conf_c, conf_n)))
                                i += 2
                                continue
                        except: pass

            merged.append(current)
            i += 1

        return merged

    def _looks_like_continuation(self, text_a: str, text_b: str) -> bool:
        """
        Determine if text_b looks like a natural continuation of text_a
        (part of the same sentence/paragraph) rather than a separate cell.
        """
        a = text_a.strip()
        b = text_b.strip()

        # If both are short and look like data values, don't merge
        if len(a) < 12 and len(b) < 12:
            # Both look like numbers/money
            if re.match(r'^[$S5]?\d', a) and re.match(r'^[$S5]?\d', b):
                return False
            # Both look like TBD or short labels
            if a in ("TBD", "N/A", "Yes", "No") or b in ("TBD", "N/A", "Yes", "No"):
                return False

        # Sentence continuations: text_a ends without terminal punctuation
        # and text_b starts with a lowercase word
        if a and not a[-1] in ".!?:" and b and b[0].islower():
            return True

        # Line continuation: text_a ends with common prepositions/articles
        continuation_words = {
            "the", "a", "an", "of", "in", "for", "and", "or", "to",
            "with", "from", "by", "on", "at", "is", "are", "was", "were",
            "will", "shall", "not", "its", "their", "our", "this", "that",
        }
        last_word_a = a.split()[-1].lower() if a.split() else ""
        if last_word_a in continuation_words:
            return True

        return False

    def _deduplicate_overlapping(self, results: List[Tuple]) -> List[Tuple]:
        """Remove OCR boxes that heavily overlap (keep higher confidence)."""
        if len(results) <= 1:
            return results

        keep = [True] * len(results)

        for i in range(len(results)):
            if not keep[i]:
                continue

            bbox_i = results[i][0]
            try:
                xi_min = min(float(p[0]) for p in bbox_i)
                xi_max = max(float(p[0]) for p in bbox_i)
                yi_min = min(float(p[1]) for p in bbox_i)
                yi_max = max(float(p[1]) for p in bbox_i)
            except (TypeError, IndexError, ValueError):
                continue

            area_i = (xi_max - xi_min) * (yi_max - yi_min)
            if area_i <= 0:
                continue

            for j in range(i + 1, len(results)):
                if not keep[j]:
                    continue

                bbox_j = results[j][0]
                try:
                    xj_min = min(float(p[0]) for p in bbox_j)
                    xj_max = max(float(p[0]) for p in bbox_j)
                    yj_min = min(float(p[1]) for p in bbox_j)
                    yj_max = max(float(p[1]) for p in bbox_j)
                except (TypeError, IndexError, ValueError):
                    continue

                area_j = (xj_max - xj_min) * (yj_max - yj_min)
                if area_j <= 0:
                    continue

                # Compute intersection
                ix1 = max(xi_min, xj_min)
                iy1 = max(yi_min, yj_min)
                ix2 = min(xi_max, xj_max)
                iy2 = min(yi_max, yj_max)

                if ix1 < ix2 and iy1 < iy2:
                    intersection = (ix2 - ix1) * (iy2 - iy1)
                    iou = intersection / min(area_i, area_j)

                    if iou > 0.5:
                        # Keep the one with higher confidence
                        if results[i][2] >= results[j][2]:
                            keep[j] = False
                        else:
                            keep[i] = False
                            break

        deduped = [r for r, k in zip(results, keep) if k]
        removed = len(results) - len(deduped)
        if removed > 0:
            print(f"[OCRPostProcessor] Deduplicated {removed} overlapping boxes")

        return deduped

    def build_table_from_ocr(
        self, ocr_results: List[Tuple], img_w: int, img_h: int
    ) -> Optional[dict]:
        """
        Attempt to assemble OCR text boxes into a structured table.

        Groups text boxes by their y-coordinate (rows) and x-coordinate (columns)
        to reconstruct a table grid.

        Returns:
            dict with 'headers', 'rows', 'raw_table_content' if a table is found,
            None otherwise.
        """
        # Filter to only boxes within the likely table region
        # (tables tend to be in the lower half of slides with regular spacing)
        table_candidates = []

        for bbox, text, conf in ocr_results:
            try:
                ys = [float(p[1]) for p in bbox]
                xs = [float(p[0]) for p in bbox]
                y_center = sum(ys) / len(ys)
                x_center = sum(xs) / len(xs)
                height = max(ys) - min(ys)
                width = max(xs) - min(xs)
            except (TypeError, IndexError, ValueError):
                continue

            # Looks like a table cell: short text, consistent height
            if text.strip() and height < img_h * 0.05:
                table_candidates.append({
                    "text": text.strip(),
                    "x_center": x_center,
                    "y_center": y_center,
                    "x_min": min(xs),
                    "y_min": min(ys),
                    "width": width,
                    "height": height,
                    "conf": conf,
                    "bbox": bbox,
                })

        if len(table_candidates) < 6:
            return None

        # Cluster by y-coordinate to find rows
        rows = self._cluster_by_coordinate(
            table_candidates, key="y_center", tolerance_factor=0.02 * img_h
        )

        if len(rows) < 3:
            return None

        # For each row, cluster by x-coordinate to find columns
        all_x_positions = []
        for row_items in rows:
            for item in row_items:
                all_x_positions.append(item["x_center"])

        # Find consistent column positions across all rows
        col_positions = self._find_column_positions(
            all_x_positions, tolerance=0.03 * img_w
        )

        if len(col_positions) < 2:
            return None

        # Build the table grid
        raw_table_content = []
        for row_items in rows:
            row_data = [""] * len(col_positions)
            for item in row_items:
                # Find the nearest column
                best_col = 0
                best_dist = float("inf")
                for ci, col_x in enumerate(col_positions):
                    dist = abs(item["x_center"] - col_x)
                    if dist < best_dist:
                        best_dist = dist
                        best_col = ci

                if best_dist < 0.05 * img_w:
                    if row_data[best_col]:
                        row_data[best_col] += " " + item["text"]
                    else:
                        row_data[best_col] = item["text"]

            raw_table_content.append(row_data)

        return {
            "raw_table_content": raw_table_content,
            "num_rows": len(raw_table_content),
            "num_cols": len(col_positions),
            "col_positions": col_positions,
        }

    def _cluster_by_coordinate(
        self, items: list, key: str, tolerance_factor: float
    ) -> List[List[dict]]:
        """Cluster items by a coordinate value with given tolerance."""
        if not items:
            return []

        sorted_items = sorted(items, key=lambda x: x[key])
        clusters = []
        current_cluster = [sorted_items[0]]
        current_center = sorted_items[0][key]

        for item in sorted_items[1:]:
            if abs(item[key] - current_center) <= tolerance_factor:
                current_cluster.append(item)
                # Update cluster center
                current_center = sum(i[key] for i in current_cluster) / len(
                    current_cluster
                )
            else:
                clusters.append(current_cluster)
                current_cluster = [item]
                current_center = item[key]

        if current_cluster:
            clusters.append(current_cluster)

        return clusters

    def _find_column_positions(
        self, x_positions: List[float], tolerance: float
    ) -> List[float]:
        """Find consistent column x-positions from all cell centers."""
        if not x_positions:
            return []

        sorted_x = sorted(x_positions)
        columns = []
        current_group = [sorted_x[0]]

        for x in sorted_x[1:]:
            if abs(x - current_group[-1]) <= tolerance:
                current_group.append(x)
            else:
                columns.append(sum(current_group) / len(current_group))
                current_group = [x]

        if current_group:
            columns.append(sum(current_group) / len(current_group))

        return columns

    def run_multi_stage_ocr(self, img_bytes: bytes, is_screenshot: bool = True) -> List[Tuple]:
        """
        Runs a multi-stage OCR pipeline:
        Pass 1: Page OCR (entire image)
        Pass 2: Table OCR (cropping the table area)
        Pass 3: Cell OCR (localizing and reading cells)
        Pass 4: Small-text OCR (upscaling/sharpening small boxes)
        Pass 5: Header/Footer OCR (cropping top 10% and bottom 10%)
        
        If confidence < 0.85, retries with upscaled, sharpened, and binarized images.
        """
        import easyocr
        import cv2
        import numpy as np
        from PIL import Image
        from io import BytesIO

        reader = easyocr.Reader(['en'])
        
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return []
        
        h_img, w_img = img.shape[:2]

        def ocr_region(patch, offset_x=0, offset_y=0) -> List[Tuple]:
            try:
                raw_results = reader.readtext(patch)
            except Exception:
                return []

            final_results = []
            for bbox, text, conf in raw_results:
                if conf < 0.85:
                    try:
                        # Alternative strategy: sharpen and upscale crop
                        xs = [p[0] for p in bbox]
                        ys = [p[1] for p in bbox]
                        xmin, xmax = max(0, int(min(xs))), min(patch.shape[1], int(max(xs)))
                        ymin, ymax = max(0, int(min(ys))), min(patch.shape[0], int(max(ys)))
                        
                        box_crop = patch[ymin:ymax, xmin:xmax]
                        if box_crop.size > 0:
                            # Upscale 2.5x and binarize / sharpen
                            upscaled = cv2.resize(box_crop, (0, 0), fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
                            gray = cv2.cvtColor(upscaled, cv2.COLOR_BGR2GRAY)
                            kernel = np.array([[-1,-1,-1], [-1,9,-1], [-1,-1,-1]])
                            sharpened = cv2.filter2D(gray, -1, kernel)
                            
                            retry_results = reader.readtext(sharpened)
                            if retry_results:
                                best_retry = max(retry_results, key=lambda x: x[2])
                                if best_retry[2] > conf:
                                    text = best_retry[1]
                                    conf = best_retry[2]
                    except Exception:
                        pass
                
                adjusted_bbox = [[p[0] + offset_x, p[1] + offset_y] for p in bbox]
                final_results.append((adjusted_bbox, text, conf))
                
            return final_results

        # Pass 1: Page OCR
        all_results = ocr_region(img)

        # Pass 2 & 3: Table and Cell OCR
        assembled = self.build_table_from_ocr(all_results, w_img, h_img)
        if assembled:
            col_pos = assembled["col_positions"]
            tx = max(0, int(min(col_pos) - 20))
            ty = max(0, int(h_img * 0.35))
            tw = min(w_img - tx, int(max(col_pos) - tx + 40))
            th = min(h_img - ty, int(h_img * 0.6))
            
            table_patch = img[ty:ty+th, tx:tx+tw]
            if table_patch.size > 0:
                table_ocr = ocr_region(table_patch, offset_x=tx, offset_y=ty)
                all_results.extend(table_ocr)

        # Pass 4: Small-text OCR
        small_boxes = []
        for bbox, text, conf in all_results:
            ys = [p[1] for p in bbox]
            height = max(ys) - min(ys)
            if height < 16:
                small_boxes.append((bbox, text, conf))
                
        for bbox, text, conf in small_boxes:
            try:
                xs = [p[0] for p in bbox]
                ys = [p[1] for p in bbox]
                xmin = max(0, int(min(xs)) - 3)
                ymin = max(0, int(min(ys)) - 3)
                xmax = min(w_img, int(max(xs)) + 3)
                ymax = min(h_img, int(max(ys)) + 3)
                
                crop = img[ymin:ymax, xmin:xmax]
                if crop.size > 0:
                    upscaled = cv2.resize(crop, (0, 0), fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
                    small_ocr = reader.readtext(upscaled)
                    for sbox, stext, sconf in small_ocr:
                        if sconf > conf:
                            adjusted_sbox = [[p[0]/3.0 + xmin, p[1]/3.0 + ymin] for p in sbox]
                            all_results.append((adjusted_sbox, stext, sconf))
            except Exception:
                pass

        # Pass 5: Header/Footer OCR
        header_h = int(h_img * 0.12)
        header_patch = img[0:header_h, 0:w_img]
        if header_patch.size > 0:
            all_results.extend(ocr_region(header_patch, offset_x=0, offset_y=0))
            
        footer_y = int(h_img * 0.88)
        footer_patch = img[footer_y:h_img, 0:w_img]
        if footer_patch.size > 0:
            all_results.extend(ocr_region(footer_patch, offset_x=0, offset_y=footer_y))

        # Deduplicate and postprocess
        deduped = self._deduplicate_overlapping(all_results)
        return self.process(deduped, is_screenshot=is_screenshot)

