from typing import Dict, List, Any
from models.document_model import TableSemanticsModel


class SemanticTableService:

    def analyze_table_semantics(self, table_element: Any) -> TableSemanticsModel:
        semantics = TableSemanticsModel()
        if not hasattr(table_element, "raw_table_content") or not table_element.raw_table_content:
            return semantics
        raw_content = table_element.raw_table_content
        if not raw_content:
            return semantics
        if len(raw_content) > 0:
            semantics.headers = [str(c) for c in raw_content[0]]
        if len(raw_content) > 1:
            semantics.sub_headers = [str(c) for c in raw_content[1]]
        if hasattr(table_element, "table_merged_cells") and table_element.table_merged_cells:
            semantics.merged_cells = table_element.table_merged_cells

        return semantics

    def build_table_json(self, table_cells: List[Dict], table_bbox: Dict) -> Dict:
        rows = {}
        cols = {}

        for cell in table_cells:
            row = cell["row"]
            col = cell["col"]
            rows[row] = True
            cols[col] = True

        return {
            "table_type": "semantic_table",
            "bbox": table_bbox,
            "row_count": len(rows),
            "column_count": len(cols),
            "cells": table_cells
        }

    def analyze_visual_table(self, visual_table):
        rows = visual_table["rows"]
        return {
            "summary":
                f"{len(rows)} rows detected",

            "table_category":
                "consulting_framework",

            "confidence":
                0.8
        }