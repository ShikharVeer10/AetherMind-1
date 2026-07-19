from collections import defaultdict
from typing import List, Dict, Any


class FlexibleTableDetector:
    def detect_visual_tables(self, elements: List[Any]) -> List[Dict[str, Any]]:
        text_elements = [
            e for e in elements
            if e.element_type == "text_box" and e.text and e.text.strip()
        ]
        if len(text_elements) < 3:
            return []
        text_elements.sort(key=lambda x: x.position.y)

        rows = []
        current_row = []
        Y_TOLERANCE = 150000.0  

        for element in text_elements:
            if not current_row:
                current_row.append(element)
            else:
                # Use center-y for more robust row grouping than just top-y
                curr_center_y = element.position.y + element.position.height / 2
                prev_element = current_row[-1]
                prev_center_y = prev_element.position.y + prev_element.position.height / 2
                
                if abs(curr_center_y - prev_center_y) <= Y_TOLERANCE:
                    current_row.append(element)
                else:
                    rows.append(current_row)
                    current_row = [element]

        if current_row:
            rows.append(current_row)

        if len(rows) < 2:
            return []
        tables = []
        current_table_rows = []
        MAX_ROW_GAP = 600000.0  

        for i, row in enumerate(rows):
            if not current_table_rows:
                current_table_rows.append(row)
            else:
                prev_row_bottom = max([e.position.y + e.position.height for e in current_table_rows[-1]])
                current_row_top = min([e.position.y for e in row])

                if (current_row_top - prev_row_bottom) <= MAX_ROW_GAP:
                    current_table_rows.append(row)
                else:
                    if self._is_likely_table(current_table_rows):
                        tables.append(current_table_rows)
                    current_table_rows = [row]

        if self._is_likely_table(current_table_rows):
            tables.append(current_table_rows)
        detected_tables = []
        for table_idx, table_rows in enumerate(tables):
            all_elements = [e for row in table_rows for e in row]
            grid_info = self._reconstruct_grid(all_elements)
            
            if not grid_info:
                continue

            min_x = min(e.position.x for e in all_elements)
            min_y = min(e.position.y for e in all_elements)
            max_x = max(e.position.x + e.position.width for e in all_elements)
            max_y = max(e.position.y + e.position.height for e in all_elements)

            detected_tables.append({
                "table_type": "visual_grid",
                "rows": grid_info["rows_data"],
                "styles": grid_info["cell_styles"],
                "merged_cells": grid_info["merged_cells"],
                "num_rows": grid_info["num_rows"],
                "num_cols": grid_info["num_cols"],
                "consumed_ids": grid_info["consumed_ids"],
                "bbox": {
                    "x": min_x,
                    "y": min_y,
                    "width": max_x - min_x,
                    "height": max_y - min_y
                }
            })

        return detected_tables

    def detect_chart_regions(self, elements: List[Any]) -> List[Dict[str, Any]]:
        potential_chart_elements = [
            e for e in elements
            if (e.element_type in {"text_box", "image", "chart"}) and (e.text or e.element_type in {"image", "chart"})
        ]
        if not potential_chart_elements:
            return []
        potential_chart_elements.sort(key=lambda x: x.position.y)
        v_blocks = self._split_elements_by_gap(potential_chart_elements, "y", gap_threshold=400000.0)
        
        final_clusters = []
        for v_block in v_blocks:
            v_block.sort(key=lambda x: x.position.x)
            h_blocks = self._split_elements_by_gap(v_block, "x", gap_threshold=500000.0)
            
            for h_block in h_blocks:
                # Pass 3: Fine-grained Vertical Split (isolate tightly packed vertical charts)
                h_block.sort(key=lambda x: x.position.y)
                f_blocks = self._split_elements_by_gap(h_block, "y", gap_threshold=150000.0)
                final_clusters.extend(f_blocks)

        regions = []
        for i, cluster_elems in enumerate(final_clusters):
            text = " ".join([e.text for e in cluster_elems if e.text]).lower()
            
            # Stricter validation for chart regions
            digit_count = sum(c.isdigit() for c in text)
            has_percent = "%" in text
            has_image = any(e.element_type in {"image", "chart"} for e in cluster_elems)
            word_count = len(text.split())
            
            # Avoid single numbers (like page numbers) or very short snippets
            if digit_count < 2 and not has_percent and not has_image:
                continue
            if word_count < 3 and not has_image:
                continue
            if "@" in text or "copyright" in text or "all rights reserved" in text:
                continue

            # Catch headers that belong to charts
            chart_keywords = ["interest", "factors", "pursuing", "path", "level", "score", "rate", "index", "agree", "disagree"]
            is_likely_chart = has_percent or has_image or digit_count >= 3 or any(k in text for k in chart_keywords)
            
            if not is_likely_chart:
                continue

            min_x = min(e.position.x for e in cluster_elems)
            min_y = min(e.position.y for e in cluster_elems)
            max_x = max(e.position.x + e.position.width for e in cluster_elems)
            max_y = max(e.position.y + e.position.height for e in cluster_elems)
            
            # Adaptive padding: more padding for small regions
            padding = 60000.0 if (max_x - min_x) < 2000000.0 else 30000.0
            
            regions.append({
                "bbox": {
                    "x": max(0, min_x - padding), 
                    "y": max(0, min_y - padding), 
                    "width": (max_x - min_x) + 2*padding, 
                    "height": (max_y - min_y) + 2*padding
                },
                "consumed_ids": [e.element_id for e in cluster_elems],
                "text_content": text,
                "region_id": f"chart_region_{i}",
                "chart_type": self._infer_preliminary_type(text)
            })
        return regions

    def _split_elements_by_gap(self, elements: List[Any], axis: str, gap_threshold: float) -> List[List[Any]]:
        if not elements: return []
        blocks = []
        current_block = [elements[0]]
        
        for i in range(1, len(elements)):
            prev = current_block[-1]
            curr = elements[i]
            
            if axis == "y":
                prev_val = prev.position.y + prev.position.height
                curr_val = curr.position.y
            else:
                prev_val = prev.position.x + prev.position.width
                curr_val = curr.position.x
                
            if (curr_val - prev_val) <= gap_threshold:
                current_block.append(curr)
            else:
                blocks.append(current_block)
                current_block = [curr]
        blocks.append(current_block)
        return blocks

    def _infer_preliminary_type(self, text: str) -> str:
        if "bar" in text or "%" in text: return "bar_chart"
        if "line" in text or "trend" in text: return "line_chart"
        if "pie" in text or "share" in text: return "pie_chart"
        if "box" in text or "whisker" in text: return "box_plot"
        return "chart"

    def _is_likely_table(self, table_rows: List[List[Any]]) -> bool:
        """Heuristic to check if a group of rows is likely a table."""
        if len(table_rows) < 2:
            return False
        
        has_multi_col = any(len(row) > 1 for row in table_rows)
        if not has_multi_col:
            return False

        total_cells = sum(len(row) for row in table_rows)
        if total_cells < 4:
            return False

        # Chart-avoidance heuristic:
        all_text = " ".join([e.text for row in table_rows for e in row if e.text]).strip()
        if not all_text:
            return False

        words = all_text.split()
        pct_count = sum(1 for w in words if "%" in w or (w.replace(".", "").isdigit() and len(w) <= 3))

        # If > 70% of "cells" are just numbers/percentages, it's probably a chart
        if pct_count / len(words) > 0.7 and total_cells < 12:
            return False

        return True

    def _reconstruct_grid(self, elements: List[Any]) -> Dict[str, Any]:
        if not elements:
            return {}
        merged_elements = self._merge_adjacent_spans(elements)
        x_points = []
        y_points = []
        for e in merged_elements:
            x_points.extend([e.position.x, e.position.x + e.position.width])
            y_points.extend([e.position.y, e.position.y + e.position.height])
        grid_x = self._cluster_coordinates(x_points, 80000.0)
        grid_y = self._cluster_coordinates(y_points, 80000.0)

        num_cols = len(grid_x) - 1
        num_rows = len(grid_y) - 1
        
        if num_cols <= 0 or num_rows <= 0:
            return {}
        logical_grid = [[[] for _ in range(num_cols)] for _ in range(num_rows)]
        
        for e in merged_elements:
            cx = e.position.x + e.position.width / 2
            cy = e.position.y + e.position.height / 2
            
            col_idx = -1
            for i in range(num_cols):
                if grid_x[i] <= cx <= grid_x[i+1]:
                    col_idx = i
                    break
            
            row_idx = -1
            for i in range(num_rows):
                if grid_y[i] <= cy <= grid_y[i+1]:
                    row_idx = i
                    break
            if col_idx == -1:
                col_idx = min(range(num_cols), key=lambda i: abs(cx - (grid_x[i] + grid_x[i+1])/2))
            if row_idx == -1:
                row_idx = min(range(num_rows), key=lambda i: abs(cy - (grid_y[i] + grid_y[i+1])/2))
            SPAN_THRESHOLD = 50000.0 # ~0.05 inch
            
            start_col = col_idx
            end_col = col_idx
            for i in range(num_cols + 1):
                if grid_x[i] > e.position.x + SPAN_THRESHOLD and grid_x[i] < (e.position.x + e.position.width) - SPAN_THRESHOLD:
                    pass # We will use the start_col/row logic to fill merged_cells later
            
            # For lossless extraction, we first place it in its primary logical cell
            logical_grid[row_idx][col_idx].append(e)

        merged_cells = []
        rows_data = []
        cell_styles = []
        
        for r in range(num_rows):
            row_vals = []
            row_styles = []
            for c in range(num_cols):
                cell_elements = logical_grid[r][c]
                cell_elements.sort(key=lambda x: (x.position.y, x.position.x))
                
                text = "\n".join([elem.text.strip() for elem in cell_elements if elem.text])
                row_vals.append(text)
                style = None
                if cell_elements:
                    style = cell_elements[0].style
                row_styles.append(style)
            
            rows_data.append(row_vals)
            cell_styles.append(row_styles)

        for e in merged_elements:
            r_start = -1; r_end = -1; c_start = -1; c_end = -1
            
            for i in range(num_rows):
                if grid_y[i] <= e.position.y + SPAN_THRESHOLD: r_start = i
                if grid_y[i+1] >= (e.position.y + e.position.height) - SPAN_THRESHOLD:
                    r_end = i
                    if r_start != -1: break
            
            for i in range(num_cols):
                if grid_x[i] <= e.position.x + SPAN_THRESHOLD: c_start = i
                if grid_x[i+1] >= (e.position.x + e.position.width) - SPAN_THRESHOLD:
                    c_end = i
                    if c_start != -1: break
            
            if r_start != -1 and r_end != -1 and c_start != -1 and c_end != -1:
                row_span = (r_end - r_start) + 1
                col_span = (c_end - c_start) + 1
                if row_span > 1 or col_span > 1:
                    merged_cells.append({
                        "row": r_start,
                        "column": c_start,
                        "row_span": row_span,
                        "column_span": col_span
                    })
        all_mapped_elements = [el for r in range(num_rows) for c in range(num_cols) for el in logical_grid[r][c]]
        if len(all_mapped_elements) != len(merged_elements):
             print(f"[FlexibleTableDetector] WARNING: Lossless mapping mismatch. Mapped {len(all_mapped_elements)} vs Input {len(merged_elements)}")
        unique_merged = []
        covered_cells = set()
        for mc in merged_cells:
            if (mc["row"], mc["column"]) in covered_cells:
                continue
            unique_merged.append(mc)
            for r in range(mc["row"], mc["row"] + mc["row_span"]):
                for c in range(mc["column"], mc["column"] + mc["column_span"]):
                    covered_cells.add((r, c))

        return {
            "rows": list(range(num_rows)),
            "columns": list(range(num_cols)),
            "rows_data": rows_data,
            "cell_styles": cell_styles,
            "merged_cells": unique_merged,
            "num_rows": num_rows,
            "num_cols": num_cols,
            "consumed_ids": [eid for e in merged_elements for eid in (getattr(e, "original_ids", [e.element_id]))],
            "row_heights": [grid_y[i+1] - grid_y[i] for i in range(num_rows)],
            "column_widths": [grid_x[i+1] - grid_x[i] for i in range(num_cols)],
            "grid_x": grid_x,
            "grid_y": grid_y,
        }

    def _merge_adjacent_spans(self, elements: List[Any]) -> List[Any]:
        """PDF artifact cleanup: merges spans that are visually part of the same word/number."""
        if not elements: return []
        sorted_elements = sorted(elements, key=lambda e: (e.position.y, e.position.x))
        merged = []
        if not sorted_elements: return []
        
        curr = sorted_elements[0]
        from copy import deepcopy
        curr = curr.model_copy(deep=True)
        curr.original_ids = [curr.element_id]
        X_TOL = 40000.0
        Y_TOL = 20000.0
        
        for i in range(1, len(sorted_elements)):
            nxt = sorted_elements[i]
            # If horizontally adjacent and vertically aligned
            if (abs(nxt.position.y - curr.position.y) < Y_TOL and 
                (nxt.position.x - (curr.position.x + curr.position.width)) < X_TOL):
                # Merge
                curr.text += nxt.text
                new_width = (nxt.position.x + nxt.position.width) - curr.position.x
                curr.position.width = new_width
                curr.original_ids.append(nxt.element_id)
            else:
                merged.append(curr)
                curr = nxt.model_copy(deep=True)
                curr.original_ids = [curr.element_id]
        merged.append(curr)
        return merged

    def _refine_grid_lines(self, clusters: List[float], all_coords: List[float]) -> List[float]:
        if not clusters: return []
        refined = []
        for c in clusters:
            near = [coord for coord in all_coords if abs(coord - c) < 150000.0]
            if near:
                refined.append(sum(near) / len(near))
            else:
                refined.append(c)
        return sorted(list(set(refined)))

    def _cluster_coordinates(self, coords: List[float], tolerance: float) -> List[float]:
        if not coords:
            return []
        vals = sorted(list(set(coords)))
        if not vals:
            return []
            
        clusters = []
        if vals:
            current_cluster = [vals[0]]
            for i in range(1, len(vals)):
                if vals[i] - vals[i-1] <= tolerance:
                    current_cluster.append(vals[i])
                else:
                    clusters.append(sum(current_cluster) / len(current_cluster))
                    current_cluster = [vals[i]]
            clusters.append(sum(current_cluster) / len(current_cluster))
            
        return sorted(clusters)