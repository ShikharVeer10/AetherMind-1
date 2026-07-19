
from models.document_model import TableReconstructionModel
from typing import List, Any, Dict


class TableService:

    def to_markdown(self, table_data: List[List[str]]) -> str:
        if not table_data:
            return ""

        escaped = [
            [str(cell).replace("\n", "<br>").replace("|", "\\|") for cell in row]
            for row in table_data
        ]

        header = "| " + " | ".join(escaped[0]) + " |"
        separator = "| " + " | ".join("---" for _ in escaped[0]) + " |"

        lines = [header, separator]
        for row in escaped[1:]:
            # Pad row if it has fewer cells than the header
            while len(row) < len(escaped[0]):
                row.append("")
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)

    def analyze_structure(self, table_data: List[List[str]]) -> dict:
        import re
        if not table_data:
            return {}

        num_rows = len(table_data)
        num_cols = max(len(row) for row in table_data) if num_rows > 0 else 0
        padded_table_data = [row + [""] * (num_cols - len(row)) for row in table_data]

        header_depth = 0
        for i in range(min(4, num_rows)):
            row_str = "".join(padded_table_data[i]).strip()
            if i < num_rows - 1:
                unique_cells = len(set(c for c in padded_table_data[i] if c.strip()))
                if unique_cells < num_cols * 0.5:
                    header_depth = i + 1
                else:
                    break
        
        is_pivot = False
        if num_rows > 1 and num_cols > 1:
            first_col_headers = sum(1 for r in range(header_depth, num_rows) if padded_table_data[r][0].strip())
            if first_col_headers > (num_rows - header_depth) * 0.8:
                is_pivot = True

        section_rows = []
        for i in range(header_depth, num_rows):
            non_empty = [c.strip() for c in padded_table_data[i] if c.strip()]
            if len(non_empty) == 1 and i < num_rows - 1:
                section_rows.append(i)

        all_text = " ".join([" ".join(r) for r in padded_table_data]).lower()
        is_financial = any(kw in all_text for kw in {"revenue", "ebitda", "profit", "budget", "cost", "total", "variance"})
        has_numeric_density = sum(1 for r in padded_table_data for c in r if re.search(r'\d', c)) > (num_rows * num_cols * 0.4)
        has_subtotals = any("subtotal" in "".join(row).lower() for row in padded_table_data)
        has_totals = any("total" in "".join(row).lower() and "subtotal" not in "".join(row).lower() for row in padded_table_data)

        return {
            "header_depth": header_depth or 1,
            "is_pivot_structure": is_pivot,
            "section_rows": section_rows,
            "is_asymmetric": "merged_cells" in locals() or header_depth > 1, # Heuristic
            "is_financial_table": is_financial,
            "has_numeric_density": has_numeric_density,
            "has_subtotals": has_subtotals,
            "has_totals": has_totals,
            "dimensions": {"rows": num_rows, "cols": num_cols},
            "table_archetype": self._infer_archetype(header_depth, is_pivot, section_rows, is_financial)
        }

    def _infer_archetype(self, header_depth, is_pivot, section_rows, is_financial) -> str:
        if is_pivot and header_depth > 1: return "complex_cross_tab"
        if section_rows: return "sectioned_report"
        if is_pivot: return "matrix_comparison"
        if is_financial: return "financial_statement"
        return "standard_list"

    def generate_semantic_context(self, table_data: List[List[str]]) -> dict:
        if not table_data:
            return {}

        structure = self.analyze_structure(table_data)
        strategy = []
        if structure["table_archetype"] == "complex_cross_tab":
            strategy.append("Recreate as a multi-tier hierarchical matrix. Map the top {d} rows as spanning headers.".format(d=structure["header_depth"]))
        if structure["is_pivot_structure"]:
            strategy.append("The first column contains primary row identifiers; treat as Y-axis headers.")     
        if structure["section_rows"]:
            strategy.append("This table contains mid-table section headers at rows {r}. These should span the full width.".format(r=structure["section_rows"]))
        strategy.append("Apply the specific background colors and text weights defined in the 'cells' metadata to ensure visual parity.")

        return {
            "archetype": structure["table_archetype"],
            "structural_summary": "A {a} with {r} rows and {c} columns.".format(a=structure["table_archetype"], r=structure["dimensions"]["rows"], c=structure["dimensions"]["cols"]),
            "reconstruction_strategy": " ".join(strategy),
            "key_insights": self.generate_key_insights(table_data),
            "logical_reading_order": "column-major" if structure["is_pivot_structure"] else "row-major"        
        }
    def generate_interpretation(self, table_data: List[List[str]]) -> str:
        """
        Generate a semantic interpretation of the table content and structure.
        """
        if not table_data:
            return "Empty table."

        struct = self.analyze_structure(table_data)
        interpretation_parts = []

        table_type = "standard table"
        if struct.get("is_financial_table"):
            table_type = "audit-style financial table"
        elif struct.get("is_comparison_table"):
            table_type = "comparison table"

        interpretation_parts.append(f"This is a {table_type}.")

        headers = [c.strip() for c in table_data[0] if c.strip()]
        if headers:
            interpretation_parts.append(f"It contains columns for: {', '.join(headers)}.")

        if struct.get("has_nested_headers"):
            interpretation_parts.append("The table uses a nested header structure for multi-level category organization.")
        if struct.get("has_grouped_rows"):
            interpretation_parts.append("The table has rows grouped into sections.")
        if struct.get("has_subtotals"):
            interpretation_parts.append("The table contains subtotal rows for intermediate sums.")
        if struct.get("has_totals"):
            interpretation_parts.append("The table contains overall totals or summary rows.")

        row_identifiers = []
        for row in table_data[1:]:
            if row and row[0].strip():
                row_str = row[0].strip().lower()
                if "total" not in row_str and "sum" not in row_str:
                    row_identifiers.append(row[0].strip())
        if row_identifiers:
            interpretation_parts.append(f"Row items include: {', '.join(row_identifiers[:6])}.")

        insights = self.generate_key_insights(table_data)
        if insights:
            interpretation_parts.append(f"Key insights: {' '.join(insights)}")
        return " ".join(interpretation_parts)

    
    def generate_key_insights(self,table_data: List[List[str]]) -> List[str]:

        insights = []

        if not table_data:
            return insights

        headers = [
        c.strip()
        for c in table_data[0]
        if c.strip()
    ]

        if headers:
            insights.append(
            f"The table contains {len(headers)} key dimensions."
        )

        if len(table_data) > 1:
            insights.append(
            f"The table compares {len(table_data)-1} entities."
        )

        structure = self.analyze_structure(table_data)

        if structure.get("is_financial_table"):
            insights.append(
            "The table contains financial reporting information."
        )

        if structure.get("is_comparison_table"):
            insights.append(
            "The table is structured for side-by-side comparison."
        )
            

        return insights
    
    def infer_table_title(
    self,
    table_data: List[List[str]]
) -> str:
        headers = [
        c.strip()
        for c in table_data[0]
        if c.strip()
    ]
        if headers:
            return f"Table showing {', '.join(headers[:3])}"
        return "Untitled Table"


    def build_render_model(self, table_data, table_structure):

        if not table_data:
            return {}

        rows = len(table_data)
        cols = max(len(r) for r in table_data)

        cells = []

        for row_idx, row in enumerate(table_data):

            for col_idx in range(cols):

                value = ""

                if col_idx < len(row):
                    value = row[col_idx]

                cell_type = "data"

                if row_idx == 0:
                    cell_type = "header"

                if (table_structure.get("has_grouped_rows") and row_idx in table_structure.get("grouped_row_indices",[])):
                    cell_type = "group_header"

                cells.append(
                    {
                        "row": row_idx,
                        "column": col_idx,
                        "text": value,
                        "cell_type": cell_type,
                        "row_span": 1,
                        "col_span": 1,

                        "fill_color": None,
                        "font_size": None,
                        "font_color": None,

                        "bold": row_idx == 0,

                        "horizontal_alignment": "center",

                        "border_top": True,
                        "border_bottom": True,
                        "border_left": True,
                        "border_right": True,
                    }
                )

        return {
            "table_type": (
                "financial"
                if table_structure.get(
                    "is_financial_table"
                )
                else (
                    "comparison"
                    if table_structure.get(
                        "is_comparison_table"
                    )
                    else "generic"
                )
            ),

            "rows": rows,
            "columns": cols,

            "layout": {
                "header_rows": [0],
                "group_rows": table_structure.get(
                    "grouped_row_indices",
                    []
            ),
            "total_rows": table_structure.get(
                "total_rows",
                []
            ),
            "subtotal_rows": table_structure.get(
                "subtotal_rows",
                []
            ),
        },
        "cells": cells,
        "structure": table_structure,
    }

    def classify_table(self, table_data: List[List[str]]) -> str:
        import re
        if not table_data:
            return "unknown"
            
        all_text = " ".join([" ".join(row) for row in table_data]).lower()
        
        if any(kw in all_text for kw in {"revenue", "ebitda", "profit", "budget", "cost", "total", "balance sheet", "income statement", "cash flow", "audited", "financials"}):
            return "financial_table"
        if any(kw in all_text for kw in {"procurement", "supply", "quantity", "unit price", "part number", "part no", "manufacturer", "supplier", "line item", "invoice"}):
            return "procurement_table"
        if any(kw in all_text for kw in {"inventory", "stock", "warehouse", "sku", "qty", "reorder", "bin number", "serial number"}):
            return "inventory_table"
        if any(kw in all_text for kw in {"compliance", "regulation", "standard", "clause", "requirement", "policy", "law", "statute", "iso", "fda", "epa", "osha"}):
            return "regulatory_table"
        if any(kw in all_text for kw in {"specification", "technical", "parameter", "range", "tolerance", "min", "max", "output", "voltage", "current", "system requirement"}):
            return "technical_table"
        if any(kw in all_text for kw in {"first name", "last name", "address", "phone", "email", "date of birth", "ssn", "signature", "checkbox", "fill in", "applicant"}):
            return "form_table"
        if any(kw in all_text for kw in {"schedule", "agenda", "time", "date", "speaker", "session", "milestone", "deadline", "duration"}):
            return "schedule_table"
        if any(kw in all_text for kw in {"evaluation", "criteria", "weight", "score", "rating", "matrix", "pivot"}):
            return "matrix_table"
            
        structure = self.analyze_structure(table_data)
        if structure.get("is_pivot_structure"):
            return "matrix_table"
            
        if len(table_data) > 0 and len(table_data[0]) > 0:
            return "simple_table"
            
        return "unknown"

    def detect_section_headers(self, table_data: List[List[str]]) -> List[Dict[str, Any]]:
        if not table_data:
            return []
        
        section_rows = []
        num_cols = max(len(row) for row in table_data) if table_data else 0
        
        for r_idx, row in enumerate(table_data):
            row_str = " ".join([str(c) for c in row]).strip()
            non_empty = [str(c).strip() for c in row if str(c).strip()]
            
            is_section = False
            label = ""
            
            import re
            markers = r"\b(DoD|BoP|TOTAL|VA|IHS|FAR|DFARS|SUBTOTAL|SECTION|APPENDIX|SUMMARY)\b"
            if re.search(markers, row_str, re.IGNORECASE):
                is_section = True
                label = row_str
            elif len(non_empty) == 1 and r_idx > 0:
                is_section = True
                label = non_empty[0]
                
            if is_section:
                section_rows.append({
                    "row_index": r_idx,
                    "label": label,
                    "columns_spanned": num_cols
                })
                
        return section_rows

    def validate_table_structure(self, reconstruction: Any) -> Dict[str, Any]:
        validation_report = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "metrics": {}
        }
        
        if not reconstruction:
            validation_report["valid"] = False
            validation_report["errors"].append("Reconstruction object is null.")
            return validation_report
            
        row_count = reconstruction.row_count
        column_count = reconstruction.column_count
        cells = reconstruction.cells
        
        if row_count <= 0:
            validation_report["errors"].append("Row count is zero or negative.")
            validation_report["valid"] = False
        if column_count <= 0:
            validation_report["errors"].append("Column count is zero or negative.")
            validation_report["valid"] = False
            
        covered_cells = 0
        empty_cell_count = 0
        for cell in cells:
            covered_cells += cell.row_span * cell.column_span
            if not cell.text.strip():
                empty_cell_count += 1
                
        expected_cells = row_count * column_count
        if covered_cells != expected_cells:
            validation_report["warnings"].append(
                f"Geometry mismatch: grid cells covered {covered_cells} vs expected {expected_cells}."
            )
            
        header_rows = getattr(reconstruction.table_render_model, "header_rows", [])
        if not header_rows and row_count > 0:
            validation_report["warnings"].append("No header rows defined.")
            
        pagination = getattr(reconstruction, "pagination_metadata", {})
        if pagination:
            if pagination.get("role") == "continuation" and not pagination.get("previous_page_table_id"):
                validation_report["errors"].append("Pagination link: Continuation table missing origin reference.")
                validation_report["valid"] = False
                
        validation_report["metrics"] = {
            "row_count": row_count,
            "column_count": column_count,
            "total_cells": len(cells),
            "empty_cell_count": empty_cell_count,
            "section_header_count": len(getattr(reconstruction, "section_headers", [])),
            "merged_cell_regions": len(reconstruction.merged_cells)
        }
        
        return validation_report

    def detect_multipage_tables(self, document_model: Any) -> None:
        all_tables = []
        for slide in document_model.slides:
            for elem in slide.elements:
                if elem.element_type == "table" and elem.table_reconstruction:
                    all_tables.append((slide.slide_number, elem))
                    
        all_tables.sort(key=lambda t: t[0])
        
        for i in range(len(all_tables) - 1):
            p1, t1 = all_tables[i]
            p2, t2 = all_tables[i+1]
            
            if p2 == p1 + 1:
                rec1 = t1.table_reconstruction
                rec2 = t2.table_reconstruction
                
                if rec1.column_count == rec2.column_count and rec1.column_count > 0:
                    h1 = [str(h).strip().lower() for h in rec1.headers]
                    h2 = [str(h).strip().lower() for h in rec2.headers]
                    
                    matching_headers = sum(1 for h in h2 if h in h1)
                    header_similarity = matching_headers / len(h2) if h2 else 0.0
                    
                    if header_similarity > 0.8:
                        rec1.pagination_metadata = {
                            "is_continuation": True,
                            "next_page_table_id": rec2.table_id,
                            "next_page_number": p2,
                            "role": "origin",
                            "repeated_headers": rec1.headers
                        }
                        rec2.pagination_metadata = {
                            "is_continuation": True,
                            "previous_page_table_id": rec1.table_id,
                            "previous_page_number": p1,
                            "role": "continuation",
                            "repeated_headers": rec2.headers
                        }

    def build_reconstruction_payload(
        self,
        table_id: str,
        raw_table_content: List[List[str]],
        table_structure: dict,
        table_render_model: dict,
        table_semantics: dict,
        is_visual: bool,
        table_geometry: dict = None,
        raw_table_styles: List[List[Any]] = None,
        row_heights: List[float] = None,
        column_widths: List[float] = None
    ) -> "TableReconstructionModel":
        from models.document_model import (
            TableReconstructionModel,
            TableCellModel,
            TableSemanticStructureModel,
            TableRenderModel,
            BorderModel
        )

        if not raw_table_content:
            return None

        num_rows = len(raw_table_content)
        num_cols = max(len(r) for r in raw_table_content) if num_rows > 0 else 0
        rows_indices = list(range(num_rows))
        cols_indices = list(range(num_cols))

        headers = [c.strip() for c in raw_table_content[0]] if num_rows > 0 else []
        row_headers = [r[0].strip() for r in raw_table_content[1:] if len(r) > 0] if num_rows > 1 else []

        merged_cells_data = table_structure.get("merged_cells", [])
        table_x = float((table_geometry or {}).get("x", 0))
        table_y = float((table_geometry or {}).get("y", 0))
        table_width = float((table_geometry or {}).get("width", 0))
        table_height = float((table_geometry or {}).get("height", 0))
        
        # Exact vs normalized calculation
        if not row_heights and num_rows > 0:
            row_heights = [table_height / num_rows] * num_rows if table_height else [0.0] * num_rows
        if not column_widths and num_cols > 0:
            column_widths = [table_width / num_cols] * num_cols if table_width else [0.0] * num_cols

        cells = []
        for r_idx, row in enumerate(raw_table_content):
            for c_idx, text in enumerate(row):
                role = "data"
                importance = "normal"
                row_span = 1
                column_span = 1
                for mc in merged_cells_data:
                    if mc.get("row") == r_idx and mc.get("column") == c_idx:
                        row_span = mc.get("row_span", 1)
                        column_span = mc.get("column_span", 1)
                        break
                bg_color = None
                f_size = None
                f_weight = "normal"
                f_style = "normal"
                align = "left"
                v_align = "center"
                text_color = None
                font_name = None

                if raw_table_styles and r_idx < len(raw_table_styles) and c_idx < len(raw_table_styles[r_idx]):
                    style = raw_table_styles[r_idx][c_idx]
                    if style:
                        bg_color = style.background_color
                        f_size = style.font_size
                        font_name = getattr(style, "font_name", None)
                        if style.bold:
                            f_weight = "bold"
                        if getattr(style, "italic", False):
                            f_style = "italic"
                        if getattr(style, "text_color", None):
                            text_color = style.text_color
                        if getattr(style, "alignment", None):
                            align = style.alignment
                        if getattr(style, "vertical_alignment", None):
                            v_align = style.vertical_alignment

                if r_idx == 0:
                    role = "header"
                    importance = "high"
                elif c_idx == 0:
                    role = "row_header"

                cell_geometry = {}
                if table_geometry:
                    cell_geometry = {
                        "x": table_x + sum(column_widths[:c_idx]),
                        "y": table_y + sum(row_heights[:r_idx]),
                        "width": sum(column_widths[c_idx : c_idx + column_span]),
                        "height": sum(row_heights[r_idx : r_idx + row_span]),
                    }

                # Setup borders (reconstruction-grade)
                b_top = BorderModel(width=1.0, color="#000000")
                b_bottom = BorderModel(width=1.0, color="#000000")
                b_left = BorderModel(width=1.0, color="#000000")
                b_right = BorderModel(width=1.0, color="#000000")

                cells.append(TableCellModel(
                    row=r_idx,
                    column=c_idx,
                    text=text.strip(),
                    row_span=row_span,
                    column_span=column_span,
                    background_color=bg_color,
                    font_size=f_size,
                    font_weight=f_weight,
                    alignment=align,
                    vertical_alignment=v_align,
                    role=role,
                    importance=importance,
                    semantic_meaning=table_semantics.get("key_insights", [""])[0] if table_semantics.get("key_insights") else "",
                    cell_geometry=cell_geometry,
                    style=raw_table_styles[r_idx][c_idx] if raw_table_styles and r_idx < len(raw_table_styles) and c_idx < len(raw_table_styles[r_idx]) else None,
                    border_top=b_top,
                    border_bottom=b_bottom,
                    border_left=b_left,
                    border_right=b_right,
                    is_empty=not text.strip()
                ))

        semantic_structure = TableSemanticStructureModel(
            comparison_dimension=headers if table_structure.get("is_comparison_table") else [],
            evaluation_dimension=row_headers if table_structure.get("is_comparison_table") else [],
            decision_dimension=[]
        )

        render_model = TableRenderModel(
            layout_type="matrix" if table_structure.get("is_comparison_table") else "grid",
            header_rows=[0] if num_rows > 0 else [],
            body_rows=list(range(1, num_rows)),
            grouped_columns=table_structure.get("grouped_column_indices", []),
            grouped_rows=table_structure.get("grouped_row_indices", []),
            merged_regions=merged_cells_data,
            visual_hierarchy=["header"] + (["summary"] if table_structure.get("has_totals") else [])
        )

        classification = self.classify_table(raw_table_content)
        sections = self.detect_section_headers(raw_table_content)

        payload = TableReconstructionModel(
            table_id=table_id,
            table_type=table_semantics.get("archetype", "standard"),
            visual_table=is_visual,
            rows=rows_indices,
            columns=cols_indices,
            row_count=num_rows,
            column_count=num_cols,
            headers=headers,
            row_headers=row_headers,
            cells=cells,
            merged_cells=merged_cells_data,
            semantic_structure=semantic_structure,
            table_geometry=table_geometry or {},
            table_render_model=render_model,
            functional_equivalence_requirements=["Preserve identical row/column count", "Maintain precise cell spanning"],
            reconstruction_strategy=table_semantics.get("reconstruction_strategy", ""),
            interpretation_guide=self._build_lossless_guide(table_semantics, table_structure),
            row_heights=row_heights,
            column_widths=column_widths,
            table_classification=classification,
            section_headers=sections,
            pagination_metadata={}
        )

        # Run verification / validation
        validation = self.validate_table_structure(payload)
        if not validation["valid"]:
            print(f"[TableService] Structure Validation ERRORS for {table_id}: {validation['errors']}")
        elif validation["warnings"]:
            print(f"[TableService] Structure Validation WARNINGS for {table_id}: {validation['warnings']}")
        else:
            print(f"[TableService] Structure Validation PASSED for {table_id}. Metrics: {validation['metrics']}")

        return payload

    def _build_lossless_guide(self, semantics: dict, structure: dict) -> str:
        return (
            "LOSSLESS RECONSTRUCTION GUIDE: Use the 'cells' array for content and visual metadata. "
            "Refer to 'row_span' and 'column_span' for merged regions. "
            "Archetype: {a}. Hierarchy: {d}-level header.".format(
                a=semantics.get("archetype", "standard"),
                d=structure.get("header_depth", 1)
            )
        )