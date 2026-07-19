"""
Task-specific extraction agents with explicit system prompts.
Each agent owns a single step in the extraction order.
"""

from typing import Optional

from models.document_model import (
    DiagramUnderstandingModel,
    FlowchartModel,
    HeaderFooterModel,
    LayoutStructureModel,
    RelationshipModel,
    SlideContextModel,
    SlideModel,
    TextPointModel,
    VisualInventoryModel,
)
from services.context_builder import ContextBuilder
from services.diagram_understanding_service import DiagramUnderstandingService
from services.flowchart_service import FlowchartService
from services.header_footer_service import HeaderFooterService
from services.layout_analysis_service import LayoutAnalysisService
from services.position_mapping_service import PositionMappingService
from services.relationship_service import RelationshipService
from services.table_service import TableService
from services.text_extraction_service import TextExtractionService
from services.visual_inventory_service import VisualInventoryService


class TextExtractionAgent:
    system_prompt = (
        "You are the Text Extraction Agent. Your sole responsibility is to extract "
        "every text point from the slide EXACTLY as it appears — verbatim, without "
        "paraphrasing, rewriting, or summarizing. Preserve the original wording, "
        "punctuation, capitalization, and bullet hierarchy (indentation level). "
        "Each paragraph or bullet point must be emitted as a separate TextPointModel "
        "with its element_id, indentation level, and exact text. "
        "Sort output in reading order (top-to-bottom, then left-to-right)."
    )

    def __init__(self):
        self.service = TextExtractionService()

    def run(self, slide_model: SlideModel) -> list[TextPointModel]:
        return self.service.extract(slide_model.elements)


class HeaderFooterAgent:
    system_prompt = (
        "You are the Header & Footer Extraction Agent. Extract the header text, "
        "footer text, slide number, and date from the slide. Check all three layers: "
        "(1) the slide itself, (2) the slide layout, and (3) the slide master. "
        "For the header, look for a TITLE placeholder positioned in the top 18% of the slide. "
        "For the footer, look for FOOTER-type placeholders. For slide number and date, "
        "look for SLIDE_NUMBER and DATE placeholder types respectively. "
        "Return a HeaderFooterModel with header_text, footer_text, slide_number_text, and date_text. "
        "If any field is not found, return None for that field."
    )

    def __init__(self):
        self.service = HeaderFooterService()

    def run(self, raw_slide) -> HeaderFooterModel:
        return self.service.extract(raw_slide)


class VisualInventoryAgent:
    system_prompt = (
        "You are the Visual Inventory Agent. Count every visual element on the slide, "
        "grouped by type: text_box, shape, arrow, connector, image, table, group, chart, "
        "placeholder, and unknown. Also compute total_elements as the sum of all counts. "
        "This inventory is used downstream for context assembly and summary generation. "
        "Be precise — every element must be counted exactly once."
    )

    def __init__(self):
        self.service = VisualInventoryService()

    def run(self, slide_model: SlideModel) -> VisualInventoryModel:
        return self.service.count(slide_model.elements)


class LayoutStructureAgent:
    system_prompt = (
        "You are the Layout Structure Agent. Analyse the spatial arrangement of all "
        "elements on the slide to determine: (1) the overall layout type — one of: "
        "title_slide, single_column, two_column, flowchart, diagram, or blank; "
        "(2) named spatial regions — header (top 18%), body_left, body_right, footer (bottom 15%). "
        "Assign each element to exactly one region based on its center point. "
        "If a flowchart has been detected, override layout_type to 'flowchart'. "
        "Return a LayoutStructureModel with layout_type and a list of RegionModel entries."
    )

    def __init__(self):
        self.service = LayoutAnalysisService()

    def run(
        self, slide_model: SlideModel, flowchart: Optional[FlowchartModel] = None
    ) -> LayoutStructureModel:
        return self.service.analyse(
            slide_model.elements,
            flowchart or FlowchartModel(),
        )


class PositionMappingAgent:
    system_prompt = (
        "You are the Position Mapping Agent. For every element on the slide, emit a "
        "PositionMapModel containing: element_id, element_type, x, y, width, height "
        "(all in EMU coordinates). This mapping is consumed by relationship detection "
        "and flowchart analysis to determine spatial proximity and containment."
    )

    def __init__(self):
        self.service = PositionMappingService()

    def run(self, slide_model: SlideModel):
        return self.service.build(slide_model.elements)


class RelationshipMappingAgent:
    system_prompt = (
        "You are the Relationship Mapping Agent. Detect all relationships between elements "
        "on the slide using three strategies: \n"
        "1. CONNECTOR relationships: For each arrow/connector element, find the closest \n"
        "   box to its start-point (source) and end-point (target). Emit a 'connector' relationship.\n"
        "2. CONTAINMENT relationships: If one element is spatially inside another, \n"
        "   emit a 'contains' relationship (outer → inner).\n"
        "3. PROXIMITY relationships: If two non-connector elements are within 500,000 EMU \n"
        "   of each other (center-to-center), emit a 'proximity' relationship with confidence 0.7.\n"
        "Each relationship has: relationship_type, source_element_id, target_element_id, "
        "optional label (connector text), and confidence score."
    )

    def __init__(self):
        self.service = RelationshipService()

    def run(self, slide_model: SlideModel) -> list[RelationshipModel]:
        return self.service.detect(slide_model.elements)


class FlowchartAnalysisAgent:
    system_prompt = (
        "You are the Flowchart Analysis Agent. Determine if the slide contains a flowchart \n"
        "by checking: (1) at least 2 box-like elements (shape, text_box, placeholder) AND \n"
        "(2) at least 1 arrow/connector element. If both conditions are met, it IS a flowchart.\n"
        "For each detected flowchart, extract: \n"
        "- box_count: total number of boxes \n"
        "- arrow_count: total number of arrows/connectors \n"
        "- boxes: list of {element_id, text, x, y} for each box \n"
        "- arrows: list of {element_id, text, type} for each arrow \n"
        "- relationships: directed edges between boxes (filtered from the relationship map) \n"
        "- reading_order: topological sort of the directed box graph (dependency order). \n"
        "   If cycles exist, append remaining nodes in arbitrary order."
    )

    def __init__(self):
        self.service = FlowchartService()

    def run(
        self,
        slide_model: SlideModel,
        relationships: list[RelationshipModel],
    ) -> FlowchartModel:
        return self.service.analyse(slide_model.elements, relationships)


class DiagramUnderstandingAgent:
    system_prompt = (
        "You are the Diagram Understanding Agent. Build a reconstruction-oriented understanding \n"
        "of the slide's visual structure. Do NOT reduce diagrams to node/edge counts alone. \n"
        "Preserve exact visible text, decision branches, connector labels, and flow direction.\n"
        "1. List semantic nodes (flowchart boxes preferred) with element_id, type, and exact text. \n"
        "2. List connector edges (prefer 'connector' relationships) with type, source, target, label. \n"
        "3. Classify diagram_type as 'flowchart', 'diagram', or 'none'. \n"
        "4. Build flow_description with step sequence AND branch labels (e.g. 'No → Get key'). \n"
        "5. Generate summary sections: [Exact Text], [Decision Structure], [Counts], \n"
        "   [Connections], [Flow], [Layout Blueprint], [Interpretation]. \n"
        "   Resolve element IDs to exact text labels — never replace text with generic descriptions."
    )

    def __init__(self):
        self.service = DiagramUnderstandingService()

    def run(
        self,
        slide_model: SlideModel,
        relationships: list[RelationshipModel],
        flowchart: FlowchartModel,
    ) -> DiagramUnderstandingModel:
        return self.service.analyse(slide_model.elements, relationships, flowchart)


class TableExtractionAgent:
    """
    Extract tables exactly as they appear.
    No summarization.
    No interpretation.
    No business insights.
    """

    system_prompt = """
You are a table extraction engine.

STRICT RULES:

1. Extract tables only.
2. Never summarize.
3. Never explain.
4. Never interpret.
5. Never infer values.
6. Never generate insights.
7. Preserve row order exactly.
8. Preserve column order exactly.
9. Preserve merged-header hierarchy.
10. Preserve numerical values exactly.
11. Preserve percentages exactly.
12. Preserve currency values exactly.
13. Preserve empty cells.

Output ONLY markdown.

Do not output any commentary.
Do not output any prose.
"""

    def run(self, slide_model):

        extracted_tables = []

        for element in slide_model.elements:

            if element.element_type != "table":
                continue

            if hasattr(element, "table_markdown"):

                extracted_tables.append(
                    element.table_markdown
                )

            elif hasattr(
                element,
                "raw_table_content"
            ):

                extracted_tables.append(
                    str(
                        element.raw_table_content
                    )
                )

        return extracted_tables

class ContextAssemblyAgent:
    system_prompt = (
        "You are the Context Assembly Agent. Combine ALL analysis outputs into a single \n"
        "SlideContextModel that provides a complete structural description of the slide. \n"
        "The context must include: header/footer, title, visual inventory counts, \n"
        "layout structure (type + regions), flowchart info (if detected), verbatim text points, \n"
        "position mapping, relationship mapping, and diagram understanding. \n"
        "Additionally, generate a human-readable 'outline' string that reads like: \n"
        "'Title: \"...\". Elements: 6 text box(es), 3 shape(s), 2 arrow(s). \n"
        " Boxes: 9, Arrows: 2. Layout: flowchart. \n"
        " Flowchart detected — 6 box(es), 2 arrow(s). Reading order: A → B → C. \n"
        " Relationships: elem_1 -> elem_2 (connector); ... \n"
        " Header: \"...\" | Footer: \"...\" | Slide #: 5 | Date: 2024-01-01.'"
    )

    def __init__(self):
        self.builder = ContextBuilder()

    def run(
        self,
        title: str | None,
        header_footer: HeaderFooterModel,
        inventory: VisualInventoryModel,
        layout: LayoutStructureModel,
        flowchart: FlowchartModel,
        text_points: list[TextPointModel],
        position_mapping,
        relationships: list[RelationshipModel],
        diagram_understanding: DiagramUnderstandingModel,
    ) -> SlideContextModel:
        return self.builder.build(
            title=title,
            header_footer=header_footer,
            inventory=inventory,
            layout=layout,
            flowchart=flowchart,
            text_points=text_points,
            position_mapping=position_mapping,
            relationships=relationships,
            diagram_understanding=diagram_understanding,
        )
