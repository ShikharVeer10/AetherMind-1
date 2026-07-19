
from models.document_model import ChartUnderstandingModel

class ChartReconstructionService:
    def build_reconstruction_data(self, understanding: ChartUnderstandingModel) -> dict:
        if not understanding:
            return {}
            
        # 1. Build the Color Mapping Specification
        # This ensures demographics (e.g. "India Gen Z") consistently map to their colors.
        color_spec = []
        if understanding.legend_mapping:
            for hex_color, label in understanding.legend_mapping.items():
                color_spec.append(f"LABEL '{label}' -> COLOR: {hex_color}")
        elif understanding.series:
            for s in understanding.series:
                if s.color:
                    color_spec.append(f"SERIES '{s.name}' -> COLOR: {s.color}")

        # 2. Build the Data Table (Markdown format for LLM readability)
        data_rows = []
        if understanding.categories and understanding.series:
            header = ["Category"] + [s.name for s in understanding.series]
            data_rows.append(" | ".join(header))
            data_rows.append(" | ".join(["---"] * len(header)))
            for i, cat in enumerate(understanding.categories):
                row = [cat]
                for s in understanding.series:
                    val = s.values[i] if i < len(s.values) else "0"
                    row.append(str(val))
                data_rows.append(" | ".join(row))

        # 3. Compile the Final Reconstruction Blueprint
        blueprint = [
            f"[VISUAL SPECIFICATION: {understanding.chart_type.upper()}]",
            f"TITLE: {understanding.title or 'Untitled'}",
            f"SUBTITLE: {understanding.subtitle or 'None'}",
            f"UNITS: {understanding.units or 'Not specified'}",
            f"ORIENTATION: {understanding.orientation or 'vertical'}",
            f"STACKING: {understanding.stacking or 'none'}",
            "\nCOLOR_MAPPING_SPEC:",
            "\n".join(color_spec) if color_spec else "None",
            "\nQUANTITATIVE_DATA_TABLE:",
            "\n".join(data_rows) if data_rows else "No numerical data extracted",
            "\nRECONSTRUCTION_LOGIC:",
            understanding.reconstruction_hints or f"Render a {understanding.chart_type} following the layout and color spec above.",
            f"INSIGHT_TO_HIGHLIGHT: {understanding.insight or 'None'}"
        ]

        return {
            "chart_id": understanding.chart_id,
            "chart_type": understanding.chart_type,
            "blueprint_text": "\n".join(blueprint),
            "color_mapping": understanding.legend_mapping,
            "series_data": [s.model_dump() for s in understanding.series],
            "categories": understanding.categories,
            "metadata": {
                "purpose": understanding.purpose,
                "business_question": understanding.business_question,
                "insight": understanding.insight
            }
        }
