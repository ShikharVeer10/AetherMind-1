
from typing import Dict, List, Any, Optional
from models.document_model import DocumentElementModel, TableReconstructionModel, TableCellModel, TableRenderModel

class AdvancedTableIntelligenceService:
    def analyze_table(self, element: DocumentElementModel) -> TableReconstructionModel:
        if element.element_type != "table":
            return None
            
        from services.table_service import TableService
        table_svc = TableService()
        
        raw_table_content = element.raw_table_content or []
        table_structure = element.table_structure or table_svc.analyze_structure(raw_table_content)
        table_render_model = element.table_render_model or table_svc.build_render_model(raw_table_content, table_structure)
        table_semantics = element.table_semantic_interpretation or table_svc.generate_semantic_context(raw_table_content)
        
        # Get raw table styles if any, or default None
        raw_table_styles = getattr(element, "table_styles", None) or getattr(element, "raw_table_styles", None)
        
        # If element is visual_grid, we might have exact heights/widths
        visual_grid = element.metadata.get("visual_grid") or {}
        row_heights = visual_grid.get("row_heights")
        column_widths = visual_grid.get("column_widths")
        
        # Geometry
        table_geometry = element.table_geometry or {
            "x": element.position.x if element.position else 0.0,
            "y": element.position.y if element.position else 0.0,
            "width": element.position.width if element.position else 0.0,
            "height": element.position.height if element.position else 0.0,
        }

        # Call build_reconstruction_payload
        reconstruction = table_svc.build_reconstruction_payload(
            table_id=element.element_id,
            raw_table_content=raw_table_content,
            table_structure=table_structure,
            table_render_model=table_render_model,
            table_semantics=table_semantics,
            is_visual=True,
            table_geometry=table_geometry,
            raw_table_styles=raw_table_styles,
            row_heights=row_heights,
            column_widths=column_widths
        )
        
        return reconstruction

    def _detect_hierarchy(self, raw_content: List[List[Any]]) -> List[Dict[str, Any]]:
        return []

    def _identify_matrix_relationships(self, raw_content: List[List[Any]]) -> List[Dict[str, Any]]:
        return []
