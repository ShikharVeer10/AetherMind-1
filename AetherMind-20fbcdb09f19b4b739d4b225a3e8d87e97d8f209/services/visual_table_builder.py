class VisualTableBuilder:
    def build(self, visual_table):
        rows = visual_table["rows"]
        max_cols = max(len(row) for row in rows)
        return {
            "row_count": len(rows),
            "column_count": max_cols,
            "rows": rows,
            "reading_order": rows,
            "layout_type": "grid"
        }