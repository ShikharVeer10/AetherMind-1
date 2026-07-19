class TableExtractionAgent:
    def run(self, slide_model):
        markdowns = []
        for element in slide_model.elements:
            if hasattr(element, "table_markdown"):
                markdown = getattr(
                    element,
                    "table_markdown",
                    None
                )
                if markdown:
                    markdowns.append(markdown)
        return markdowns

    def generate_reconstruction_prompts(self, slide_model) -> list[str]:
        """
        Generates a highly descriptive, reconstruction-grade blueprint prompt 
        for every table on the slide, suitable to be passed directly to an LLM.
        """
        prompts = []
        for element in slide_model.elements:
            if element.element_type == "table":
                rec = getattr(element, "table_reconstruction", None)
                if not rec:
                    continue
                
                lines = [
                    f"TABLE RECONSTRUCTION BLUEPRINT ({rec.table_id})",
                    f"Archetype/Classification: {rec.table_classification.upper()}",
                    f"Dimensions: {rec.row_count} rows x {rec.column_count} columns",
                    f"Table bounding box: x={rec.table_geometry.get('x')}, y={rec.table_geometry.get('y')}, width={rec.table_geometry.get('width')}, height={rec.table_geometry.get('height')}",
                ]
                
                if rec.row_heights:
                    lines.append(f"Row Heights (pixels): {', '.join(str(round(h, 2)) for h in rec.row_heights)}")
                if rec.column_widths:
                    lines.append(f"Column Widths (pixels): {', '.join(str(round(w, 2)) for w in rec.column_widths)}")
                    
                if rec.section_headers:
                    lines.append("Section Header/Divider Rows:")
                    for sh in rec.section_headers:
                        lines.append(f"  - Row {sh['row_index']}: \"{sh['label']}\"")
                        
                if rec.pagination_metadata:
                    pag = rec.pagination_metadata
                    if pag.get("role") == "continuation":
                        lines.append(f"Pagination: CONTINUATION of page {pag.get('previous_page_number')} table ({pag.get('previous_page_table_id')})")
                    else:
                        lines.append(f"Pagination: ORIGIN, continued on page {pag.get('next_page_number')} table ({pag.get('next_page_table_id')})")
                        
                lines.append("Verbatim Cells List (with span and style metadata):")
                for cell in rec.cells:
                    span = f", spans {cell.row_span}x{cell.column_span}" if (cell.row_span > 1 or cell.column_span > 1) else ""
                    style = f", font_weight={cell.font_weight}, bg={cell.background_color or 'none'}, align={cell.alignment}"
                    val = cell.text if cell.text.strip() else "(empty)"
                    lines.append(f"  - Cell ({cell.row}, {cell.column}){span}{style}: \"{val}\"")
                    
                prompts.append("\n".join(lines))
                
        return prompts