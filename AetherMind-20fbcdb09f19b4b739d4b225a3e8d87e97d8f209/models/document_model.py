from __future__ import annotations
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


from enum import Enum

class ReconstructionLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class PositionModel(BaseModel):
    x: float
    y: float
    width: float
    height: float


class StyleModel(BaseModel):
    font_size: Optional[float] = None
    font_name: Optional[str] = None
    bold: bool = False
    italic: bool = False
    text_color: Optional[str] = None
    background_color: Optional[str] = None
    alignment: Optional[str] = None
    vertical_alignment: Optional[str] = None
    underline: bool = False
    font_weight: Optional[str] = None
    line_spacing: Optional[float] = None
    letter_spacing: Optional[float] = None
    paragraph_spacing: Optional[float] = None
    anchor_point: Optional[str] = None
    border_color: Optional[str] = None
    border_thickness: Optional[float] = None
    border_style: Optional[str] = None
    border_radius: Optional[float] = None
    opacity: Optional[float] = None
    shadow: Optional[Dict[str, Any]] = None
    gradient: Optional[Dict[str, Any]] = None
    padding: Optional[Dict[str, float]] = None


class RunModel(BaseModel):
    text: str
    bold: bool = False
    italic: bool = False
    font_size: Optional[float] = None
    font_name: Optional[str] = None
    font_color: Optional[str] = None
    underline: bool = False
    font_weight: Optional[str] = None
    letter_spacing: Optional[float] = None


class ParagraphModel(BaseModel):
    level: int = 0
    text: str
    alignment: Optional[str] = None
    runs: List[RunModel] = Field(default_factory=list)
    line_spacing: Optional[float] = None
    paragraph_spacing_before: Optional[float] = None
    paragraph_spacing_after: Optional[float] = None
    indentation: Optional[float] = None
    list_type: Optional[str] = None
    bullet_character: Optional[str] = None
    number: Optional[str] = None


class RelationshipModel(BaseModel):
    relationship_type: str
    source_element_id: str
    target_element_id: str
    label: Optional[str] = None
    confidence: float = 1.0
    semantic_relation:Optional[str]=None
    direction:Optional[str]=None


class TextPointModel(BaseModel):
    element_id: str
    level: int = 0
    text: str


class PositionMapModel(BaseModel):
    element_id: str
    element_type: str
    x: float
    y: float
    width: float
    height: float


class DiagramUnderstandingModel(BaseModel):
    is_diagram: bool = False
    diagram_type: str = "none"
    node_count: int = 0
    edge_count: int = 0
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)
    semantic_relationships: List[Dict[str, Any]] = Field(default_factory=list)
    flow_description: str = ""
    summary: str = ""


class ChartAxisModel(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    ticks: List[str] = Field(default_factory=list)
    label: Optional[str] = None
    axis_type: str = "linear"

class ChartSeriesModel(BaseModel):
    name: str = ""
    values: List[Any] = Field(default_factory=list)
    color: Optional[str] = None

class ChartUnderstandingModel(BaseModel):
    chart_id: str = ""
    chart_type: str = "none"
    purpose: str = ""
    business_question: str = ""
    insight: str = ""
    orientation: Optional[str] = None
    stacking: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    units: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    series: List[ChartSeriesModel] = Field(default_factory=list)
    legend: List[str] = Field(default_factory=list)
    legend_mapping: Dict[str, str] = Field(default_factory=dict)
    axes: Dict[str, ChartAxisModel] = Field(default_factory=dict)
    data_labels: List[str] = Field(default_factory=list)
    data_labels_visible: bool = False
    reconstruction_hints: Optional[str] = None
    insights: List[str] = Field(default_factory=list)
    visual_relationships: List[str] = Field(default_factory=list)
    # Legacy fields
    measures: List[str] = Field(default_factory=list)
    dimensions: List[str] = Field(default_factory=list)
    trends: List[str] = Field(default_factory=list)
    anomalies: List[str] = Field(default_factory=list)
    comparisons: List[str] = Field(default_factory=list)
    raw_chart_data: Optional[Dict[str, Any]] = None

class VisualObjectClass(BaseModel):
    classification: str
    confidence: float


class TableSemanticsModel(BaseModel):
    headers: List[str] = Field(default_factory=list)
    sub_headers: List[str] = Field(default_factory=list)
    row_groups: List[Dict[str, Any]] = Field(default_factory=list)
    column_groups: List[Dict[str, Any]] = Field(default_factory=list)
    merged_cells: List[Dict[str, Any]] = Field(default_factory=list)


class BorderModel(BaseModel):
    width: float = 1.0
    style: str = "solid"  # "solid", "dashed", "dotted", "none"
    color: str = "#000000"


class TableCellModel(BaseModel):
    row: int
    column: int
    text: str
    row_span: int = 1
    column_span: int = 1
    background_color: Optional[str] = None
    font_size: Optional[float] = None
    font_weight: Optional[str] = None
    alignment: Optional[str] = None
    role: str = "data"
    importance: str = "normal"
    semantic_meaning: str = ""
    cell_geometry: Dict[str, float] = Field(default_factory=dict)
    style: Optional[StyleModel] = None
    
    # Reconstruction-grade properties
    border_top: Optional[BorderModel] = None
    border_bottom: Optional[BorderModel] = None
    border_left: Optional[BorderModel] = None
    border_right: Optional[BorderModel] = None
    vertical_alignment: Optional[str] = "center"
    is_empty: bool = False

class TableSemanticStructureModel(BaseModel):
    comparison_dimension: List[str] = Field(default_factory=list)
    evaluation_dimension: List[str] = Field(default_factory=list)
    decision_dimension: List[str] = Field(default_factory=list)

class TableRenderModel(BaseModel):
    layout_type: str = "grid"
    header_rows: List[int] = Field(default_factory=list)
    body_rows: List[int] = Field(default_factory=list)
    grouped_columns: List[int] = Field(default_factory=list)
    grouped_rows: List[int] = Field(default_factory=list)
    merged_regions: List[Dict[str, Any]] = Field(default_factory=list)
    visual_hierarchy: List[str] = Field(default_factory=list)

class TableReconstructionModel(BaseModel):
    table_id: str
    table_type: str = "standard"
    visual_table: bool = False
    rows: List[int] = Field(default_factory=list)
    columns: List[int] = Field(default_factory=list)
    cells: List[TableCellModel] = Field(default_factory=list)
    merged_cells: List[Dict[str, Any]] = Field(default_factory=list)
    hierarchy: List[Dict[str, Any]] = Field(default_factory=list)
    relationships: List[Dict[str, Any]] = Field(default_factory=list)
    # Metadata for legacy and enrichment
    row_count: int = 0
    column_count: int = 0
    headers: List[str] = Field(default_factory=list)
    row_headers: List[str] = Field(default_factory=list)
    semantic_structure: TableSemanticStructureModel = Field(default_factory=TableSemanticStructureModel)
    table_geometry: Dict[str, float] = Field(default_factory=dict)
    table_render_model: TableRenderModel = Field(default_factory=TableRenderModel)
    functional_equivalence_requirements: List[str] = Field(default_factory=list)
    reconstruction_strategy: str = ""
    interpretation_guide: str = ""
    
    # Extended properties
    row_heights: List[float] = Field(default_factory=list)
    column_widths: List[float] = Field(default_factory=list)
    table_classification: str = "unknown"
    section_headers: List[Dict[str, Any]] = Field(default_factory=list)
    pagination_metadata: Dict[str, Any] = Field(default_factory=dict)

class LayoutGraphModel(BaseModel):
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)

class SlideArchetypeModel(BaseModel):
    slide_archetype: str
    confidence: float = 0.0

class CapabilityMapModel(BaseModel):
    domains: List[Dict[str, Any]] = Field(default_factory=list)
    capabilities: List[Dict[str, Any]] = Field(default_factory=list)
    relationships: List[Dict[str, Any]] = Field(default_factory=list)

class GovernanceFrameworkModel(BaseModel):
    layers: List[Dict[str, Any]] = Field(default_factory=list)
    entities: List[Dict[str, Any]] = Field(default_factory=list)
    relationships: List[Dict[str, Any]] = Field(default_factory=list)

class ProcessFlowModel(BaseModel):
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)
    sequence: List[str] = Field(default_factory=list)
    decision_points: List[str] = Field(default_factory=list)

class DashboardModel(BaseModel):
    panels: List[Dict[str, Any]] = Field(default_factory=list)
    metrics: List[Dict[str, Any]] = Field(default_factory=list)
    relationships: List[Dict[str, Any]] = Field(default_factory=list)

class ColorSemanticModel(BaseModel):
    label: str
    hex_color: str
    purpose: str = "series_mapping" # "legend", "highlight", "background"
    confidence: float = 1.0

class ColorPaletteModel(BaseModel):
    dominant_colors: List[str] = Field(default_factory=list)
    legend_mapping: Dict[str, str] = Field(default_factory=dict) # hex -> label
    semantic_labels: List[ColorSemanticModel] = Field(default_factory=list)

class HighFidelityBlueprintModel(BaseModel):
    layout_type: str # "consulting_dashboard", "standard_form", "infographic", etc.
    global_style: Dict[str, Any] = Field(default_factory=dict) # background, theme, accent colors
    color_palette: ColorPaletteModel
    visual_components: List[Dict[str, Any]] = Field(default_factory=list) # Unified list of charts, forms, tables
    layout_hierarchy: Dict[str, Any] = Field(default_factory=dict) # relative positioning, alignment anchors
    reconstruction_instructions: str # Detailed natural language instructions for the LLM
    raw_data_summary: str # Comprehensive text/number dump optimized for regeneration

class FormLineModel(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    thickness: float = 1.0

class FormFieldModel(BaseModel):
    id: str
    label: str
    value: Optional[str] = None
    position: PositionModel
    field_type: str = "text" # "text", "checkbox", "radio", "signature", "date"
    block_number: Optional[str] = None
    is_checked: Optional[str] = "false" # "true", "false", "partial"

class FormTableModel(BaseModel):
    id: str
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    position: PositionModel

class FormModel(BaseModel):
    form_title: str
    form_number: Optional[str] = None
    sections: List[Dict[str, Any]] = Field(default_factory=list)
    fields: List[FormFieldModel] = Field(default_factory=list)
    tables: List[FormTableModel] = Field(default_factory=list)
    lines: List[FormLineModel] = Field(default_factory=list)
    signature_blocks: List[Dict[str, Any]] = Field(default_factory=list)
    checkboxes: List[Dict[str, Any]] = Field(default_factory=list)
    form_type: Optional[str] = None
    layout_hierarchy: Dict[str, Any] = Field(default_factory=dict)
    reconstruction_hints: str = ""

class SemanticRegionModel(BaseModel):
    name: str
    semantic_role: str
    purpose: str
    position: PositionModel
    contents: List[str] = Field(default_factory=list)


class DocumentElementModel(BaseModel):
    element_id: str
    element_type: str
    text: Optional[str] = None
    paragraphs: List[ParagraphModel] = Field(default_factory=list)
    position: PositionModel
    style: Optional[StyleModel] = None
    shape_type: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    table_markdown: Optional[str] = None
    raw_table_content: Optional[List[List[str]]] = None
    table_structure: Optional[Dict[str, Any]] = None
    table_semantics: Optional[TableSemanticsModel] = None
    table_visual_metadata: Optional[dict] = None
    table_render_model: Optional[TableRenderModel] = None
    table_semantic_interpretation: Optional[Dict[str, Any]] = None
    table_reconstruction: Optional[TableReconstructionModel] = None
    chart_understanding: Optional[ChartUnderstandingModel] = None
    chart_reconstruction_payload: Optional[Dict[str, Any]] = None
    dashboard_reconstruction_payload: Optional[Dict[str, Any]] = None
    form_reconstruction_payload: Optional[Dict[str, Any]] = None
    image_reconstruction_payload: Optional[Dict[str, Any]] = None
    reconstruction_level: ReconstructionLevel = ReconstructionLevel.HIGH
    table_title: Optional[str] = None
    table_purpose: Optional[str] = None
    table_insights: List[str] = Field(default_factory=list)
    table_geometry: dict = Field(default_factory=dict)
    table_styles: dict = Field(default_factory=dict)
    table_merged_cells: list = Field(default_factory=list)
    original_ids: List[str] = Field(default_factory=list)
    form_data: Optional[FormModel] = None

    # High-fidelity layout, visual hierarchy, group, list, and image properties
    parent: Optional[str] = None
    children: List[str] = Field(default_factory=list)
    layer: Optional[str] = None
    group_id: Optional[str] = None
    border_radius: Optional[float] = None
    shadow: Optional[Dict[str, Any]] = None
    gradient: Optional[Dict[str, Any]] = None
    opacity: Optional[float] = None
    line_spacing: Optional[float] = None
    letter_spacing: Optional[float] = None
    paragraph_spacing: Optional[float] = None
    anchor_point: Optional[str] = None
    underline: bool = False
    percentage_coordinates: Optional[Dict[str, float]] = None
    canvas_size: Optional[Dict[str, float]] = None
    stacking_order: Optional[int] = None
    bullet_character: Optional[str] = None
    indentation: Optional[float] = None
    level: Optional[int] = None
    number: Optional[str] = None
    caption: Optional[str] = None
    role: Optional[str] = None
    crop: Optional[Dict[str, float]] = None
    mask: Optional[str] = None


class HeaderFooterModel(BaseModel):
    header_text: Optional[str] = None
    footer_text: Optional[str] = None
    slide_number_text: Optional[str] = None
    date_text: Optional[str] = None
    confidentiality_label: Optional[str] = None
    header_type: Optional[str] = None
    footer_type: Optional[str] = None


class VisualInventoryModel(BaseModel):
    text_box_count: int
    shape_count: int
    arrow_count: int
    connector_count: int
    image_count: int
    table_count: int
    group_count: int
    chart_count: int
    placeholder_count: int
    unknown_count: int
    total_elements: int

    # NEW
    title_count: int = 0
    header_count: int = 0
    footer_count: int = 0
    figure_count: int = 0
    icon_count: int = 0

    slide_type: str | None = None


class RegionModel(BaseModel):
    name: str
    x_start: float = 0
    y_start: float = 0
    x_end: float = 0
    y_end: float = 0
    element_ids: List[str] = Field(default_factory=list)


class LayoutRegionModel(BaseModel):
    name: str
    element_ids: List[str] = Field(default_factory=list)


class LayoutStructureModel(BaseModel):
    layout_type: str = ""
    layout_pattern: str = ""
    regions: List[RegionModel] = Field(default_factory=list)


class FlowchartModel(BaseModel):
    is_flowchart: bool = False
    box_count: int = 0
    arrow_count: int = 0
    decision_node_count: int = 0
    start_nodes: List[str] = Field(default_factory=list)
    end_nodes: List[str] = Field(default_factory=list)
    flow_type: Optional[str] = None
    boxes: List[Dict[str, Any]] = Field(default_factory=list)
    arrows: List[Dict[str, Any]] = Field(default_factory=list)
    relationships: List[RelationshipModel] = Field(default_factory=list)
    relationship_mapping: List[Dict[str, Any]] = Field(default_factory=list)
    reading_order: List[str] = Field(default_factory=list)
    reading_order_labels: List[str] = Field(default_factory=list)
    process_summary: Optional[str] = None

class VisualDesignModel(BaseModel):
    color_scheme: List[str] = Field(default_factory=list)
    shapes: List[str] = Field(default_factory=list)
    connector_types: List[str] = Field(default_factory=list)
    layout_pattern: Optional[str] = None
    spatial_structure: Optional[str] = None
    background_style: Optional[str] = None
    layout_style: Optional[str] = None
    primary_shapes: List[str] = Field(default_factory=list)

class ImageUnderstandingModel(BaseModel):
    scene_description: str = ""
    business_meaning: Optional[str] = None
    visual_metaphors: List[str] = Field(default_factory=list)
    symbolic_meaning: List[str] = Field(default_factory=list)
    objects_detected: List[str] = Field(default_factory=list)
    actions_detected: List[str] = Field(default_factory=list)
    relationships: List[str] = Field(default_factory=list)
    semantic_meaning: str = ""
    visual_design: Optional[VisualDesignModel] = None
    image_type: str = ""
    dominant_colors: List[str] = Field(default_factory=list)
    visual_elements: List[str] = Field(default_factory=list)
    llm_recreation_prompt: str = ""
    slide_intent: Optional[str] = None
    visual_regions: List[Dict[str, Any]] = Field(default_factory=list)
    illustration_inventory: List[Dict[str, Any]] = Field(default_factory=list)
    relationship_mapping: List[Dict[str, Any]] = Field(default_factory=list)
    design_hierarchy: Optional[Dict[str, Any]] = None
    reading_order: List[str] = Field(default_factory=list)

class SemanticFlowModel(BaseModel):
    overall_flow: str = ""
    step_by_step_explanation: List[str] = Field(default_factory=list)
    conceptual_layers: List[str] = Field(default_factory=list)
    visual_design_details: List[str] = Field(default_factory=list)
    plain_english_summary: str = ""
    decision_points: List[str] = Field(default_factory=list)
    cause_effect_chain: List[str] = Field(default_factory=list)
    image_generation_prompt: str = ""
    slide_intent: Optional[str] = None
    executive_summary: str = ""
    visual_structure: str = ""
    content_hierarchy: Optional[Dict[str, Any]] = None
    visual_hierarchy: Optional[Dict[str, Any]] = None
    semantic_relationships: List[Dict[str, Any]] = Field(default_factory=list)
    layout_regions: List[Dict[str, Any]] = Field(default_factory=list)
    visual_grouping: List[Dict[str, Any]] = Field(default_factory=list)
    storytelling_structure: Optional[str] = None
    reading_order: List[str] = Field(default_factory=list)
    sections: List[SemanticSectionModel] = Field(default_factory=list)
    relationships: List[RelationshipModel] = Field(default_factory=list)
    charts: List[ChartUnderstandingModel] = Field(default_factory=list)
    tables: List[TableReconstructionModel] = Field(default_factory=list)

    # Semantic text enrichment for meaning-preserving regeneration
    semantic_text_enrichments: List["SemanticTextEnrichmentModel"] = Field(default_factory=list)
    semantic_section_enrichments: List["SemanticSectionEnrichmentModel"] = Field(default_factory=list)
    semantic_equivalence_targets: Optional["SemanticEquivalenceTargetsModel"] = None

    # LLM-derived structural metadata
    slide_archetype: Optional[str] = None
    capability_map_data: Optional[Dict[str, Any]] = None
    governance_data: Optional[Dict[str, Any]] = None
    process_flow_data: Optional[Dict[str, Any]] = None
    dashboard_data: Optional[Dict[str, Any]] = None
    table_intelligence: List[Dict[str, Any]] = Field(default_factory=list)

class SlideReconstructionContextModel(BaseModel):
    title: str = ""
    slide_type: str = ""
    purpose: str = ""
    domain: str = ""
    theme: str = ""
    design_style: str = ""
    mood: str = ""
    complexity: str = ""
    category: str = ""
    background_type: str = ""
    primary_color: str = ""
    secondary_color: str = ""
    gradient_direction: str = ""
    texture: str = ""
    patterns: str = ""
    effects: str = ""
    title_typography: str = ""
    body_typography: str = ""
    typography_color_palette: List[str] = Field(default_factory=list)
    layout_type: str = ""
    layout_pattern: str = ""
    canvas_ratio: str = "16:9"
    regions: List[str] = Field(default_factory=list)
    reading_order: List[str] = Field(default_factory=list)
    alignment: str = ""
    spacing: str = ""
    primary_focus: str = ""
    secondary_focus: str = ""
    tertiary_elements: str = ""
    attention_flow: str = ""
    visual_elements: List[Dict[str, Any]] = Field(default_factory=list)
    image_reconstructions: List[Dict[str, Any]] = Field(default_factory=list)
    element_relationships: List[str] = Field(default_factory=list)
    reconstruction_prompt: str = ""
    functional_equivalence_requirements: List[str] = Field(default_factory=list)
    business_message: Optional[str] = None
    communication_intent: Optional[str] = None

class SlideContextModel(BaseModel):
    header_footer: Optional[HeaderFooterModel] = None
    title: Optional[str] = None
    visual_inventory: Optional[VisualInventoryModel] = None
    layout_structure: Optional[LayoutStructureModel] = None
    flowchart: Optional[FlowchartModel] = None
    text_points: List[TextPointModel] = Field(default_factory=list)
    position_mapping: List[PositionMapModel] = Field(default_factory=list)
    relationship_mapping: List[RelationshipModel] = Field(default_factory=list)
    diagram_understanding: Optional[DiagramUnderstandingModel] = None
    outline: str = ""
    image_understanding:Optional[ImageUnderstandingModel]=None
    semantic_flow:Optional[SemanticFlowModel]=None
    exact_text_dump: List[Dict[str, Any]] = Field(default_factory=list)
    table_contexts: List[Dict[str, Any]] = Field(default_factory=list)
    image_depictions: List[str] = Field(default_factory=list)
    slide_structure_summary: Optional[str] = None
    semantic_text_enrichments: List["SemanticTextEnrichmentModel"] = Field(default_factory=list)


class ImageReconstructionModel(BaseModel):
    layout_description: str = ""
    color_palette: List[str] = Field(default_factory=list)
    object_location: List[str] = Field(default_factory=list)
    connector_layout: List[str] = Field(default_factory=list)
    recreation_prompt: str = ""
    object_inventory: List[str] = Field(default_factory=list)
    visual_hierarchy: List[str] = Field(default_factory=list)
    layout_regions: List[str] = Field(default_factory=list)
    design_style: str = ""

class SemanticSlideDescriptionModel(BaseModel):
    semantic_flow: str = ""
    step_by_step_meaning: List[str] = Field(default_factory=list)
    conceptual_layers: List[str] = Field(default_factory=list)
    visual_design_details: List[str] = Field(default_factory=list)
    plain_english_summary: str = ""
    image_generation_prompt:str=""
    visual_inventory_summary: str | None = None
    relationship_summary: str | None = None
    image_depiction_summary: Optional[str]
    slide_archetype: str | None = None
    flowchart_summary: str | None = None

class VisualHierarchyModel(BaseModel):
    primary_focus: List[str] = Field(default_factory=list)
    secondary_focus: List[str] = Field(default_factory=list)
    tertiary_focus: List[str] = Field(default_factory=list)

class SemanticSectionModel(BaseModel):
    section_type: str = ""
    importance: str = ""
    message: str = ""
    supporting_elements: List[str] = Field(default_factory=list)


class RewriteConstraintsModel(BaseModel):
    """Constraints governing how a text element may be rewritten during regeneration."""
    must_preserve_meaning: bool = True
    must_use_new_wording: bool = True
    must_not_copy_original_phrases: bool = True
    must_keep_same_reading_length: bool = True
    must_keep_same_tone: bool = True
    must_fit_same_layout: bool = True


class SemanticEquivalenceTargetsModel(BaseModel):
    """Quantitative targets for measuring regeneration quality."""
    semantic_equivalence_target: float = 1.0
    wording_similarity_target: str = "< 0.40"
    layout_similarity_target: str = "> 0.95"
    visual_similarity_target: str = "> 0.95"
    information_preservation_target: str = "> 0.98"


class SemanticTextEnrichmentModel(BaseModel):
    """Semantic enrichment for a single text element, enabling meaning-preserving rewriting."""
    original_text: str = ""
    semantic_meaning: str = ""
    communication_goal: str = ""
    educational_intent: str = ""
    tone: str = "professional"
    approximate_word_count: int = 0
    approximate_line_count: int = 0
    hierarchy_role: str = ""  # "title", "heading", "subheading", "body", "bullet", "label", "footer"
    rewrite_constraints: RewriteConstraintsModel = Field(default_factory=RewriteConstraintsModel)


class SemanticSectionEnrichmentModel(BaseModel):
    """Semantic enrichment for a logical section of the slide."""
    section_id: str = ""
    section_title: str = ""
    section_purpose: str = ""
    section_importance: str = "medium"  # "high", "medium", "low"
    contained_text_enrichments: List[SemanticTextEnrichmentModel] = Field(default_factory=list)
    semantic_equivalence_targets: SemanticEquivalenceTargetsModel = Field(default_factory=SemanticEquivalenceTargetsModel)


class SemanticSlideGraphModel(BaseModel):
    slide_intent: str = ""
    executive_summary: str = ""
    visual_structure: str = ""
    sections: List[SemanticSectionModel] = Field(default_factory=list)
    relationships: List[RelationshipModel] = Field(default_factory=list)
    charts: List[ChartUnderstandingModel] = Field(default_factory=list)
    tables: List[TableReconstructionModel] = Field(default_factory=list)
    visual_hierarchy: List[str] = Field(default_factory=list)

class SlideModel(BaseModel):
    slide_number: int
    title: Optional[str] = None
    background_color: Optional[str] = None
    layout_regions: list = []
    elements: List[DocumentElementModel] = Field(default_factory=list)
    images: List[Dict[str, Any]] = Field(default_factory=list)
    relationships: List[RelationshipModel] = Field(default_factory=list)
    header_footer: Optional[HeaderFooterModel] = None
    visual_inventory: Optional[VisualInventoryModel] = None
    semantic_slide_description: Optional[SemanticSlideDescriptionModel] = None
    layout_structure: Optional[LayoutStructureModel] = None
    flowchart: Optional[FlowchartModel] = None
    diagram_understanding: Optional[DiagramUnderstandingModel] = None
    image_understanding: Optional[ImageUnderstandingModel] = None
    context: Optional[SlideContextModel] = None
    semantic_flow: Optional[SemanticFlowModel] = None
    table_markdowns: List[str] = Field(default_factory=list)
    slide_summary: Optional[str] = None
    text_points: List[TextPointModel] = Field(default_factory=list)
    position_mapping: List[PositionMapModel] = Field(default_factory=list)
    image_reconstruction: Optional[ImageReconstructionModel] = None
    slide_reconstruction_context: Optional[SlideReconstructionContextModel] = None
    chart_understandings: List[ChartUnderstandingModel] = Field(default_factory=list)
    semantic_regions: List[SemanticRegionModel] = Field(default_factory=list)
    detected_tables: Optional[list] = []
    layout_graph: Optional[LayoutGraphModel] = None
    semantic_graph: Optional[SemanticSlideGraphModel] = None
    business_message: Optional[str] = None
    communication_intent: Optional[str] = None
    slide_purpose: Optional[str] = None
    visual_hierarchy: Optional[VisualHierarchyModel] = None
    reading_order: List[str] = Field(default_factory=list)
    functional_equivalence_requirements: List[str] = Field(default_factory=list)
    slide_archetype: Optional[SlideArchetypeModel] = None
    capability_map: Optional[CapabilityMapModel] = None
    governance_framework: Optional[GovernanceFrameworkModel] = None
    process_flow: Optional[ProcessFlowModel] = None
    dashboard: Optional[DashboardModel] = None
    color_palette: Optional[ColorPaletteModel] = None
    high_fidelity_blueprint: Optional[HighFidelityBlueprintModel] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    semantic_slide_extraction: Optional[Dict[str, Any]] = None

    # Semantic enrichment for meaning-preserving slide regeneration
    semantic_text_enrichments: List[SemanticTextEnrichmentModel] = Field(default_factory=list)
    semantic_section_enrichments: List[SemanticSectionEnrichmentModel] = Field(default_factory=list)
    semantic_equivalence_targets: Optional[SemanticEquivalenceTargetsModel] = None


class DocumentStructureModel(BaseModel):
    presentation_type: str = "unknown"
    document_role: str = "unknown"
    slide_sequence: List[str] = Field(default_factory=list)
    total_sections: int = 0
    section_breaks: List[int] = Field(default_factory=list)
    executive_summary_slides: List[int] = Field(default_factory=list)
    methodology_slides: List[int] = Field(default_factory=list)
    findings_slides: List[int] = Field(default_factory=list)
    recommendation_slides: List[int] = Field(default_factory=list)
    appendix_slides: List[int] = Field(default_factory=list)
    narrative_flow: str = ""
    document_summary: str = ""
    sections: List[Dict[str, Any]] = Field(default_factory=list)
    

class DocumentModel(BaseModel):
    document_name: str
    document_type: str
    total_slides: int
    slides: List[SlideModel] = Field(default_factory=list)
    relationships: List[RelationshipModel] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    presentation_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Top-level presentation metadata: author, slide dimensions, theme, etc.",
    )
    document_structure: Optional[Dict[str, Any]] = None


# Universal Form and Document Geometry Elements
class LineElement(BaseModel):
    id: str
    type: str = "line"
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0.0
    z_order: int = 0
    confidence: float = 1.0
    x1: float
    y1: float
    x2: float
    y2: float
    stroke_width: float = 1.0
    stroke_color: Optional[str] = None


class RectangleElement(BaseModel):
    id: str
    type: str = "rectangle"
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0.0
    z_order: int = 0
    confidence: float = 1.0
    stroke_width: Optional[float] = None
    stroke_color: Optional[str] = None
    fill_color: Optional[str] = None


class CheckboxElement(BaseModel):
    id: str
    type: str = "checkbox"
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0.0
    z_order: int = 0
    confidence: float = 1.0
    checked: bool = False
    stroke_width: Optional[float] = None
    stroke_color: Optional[str] = None
    fill_color: Optional[str] = None


class RadioButtonElement(BaseModel):
    id: str
    type: str = "radio_button"
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0.0
    z_order: int = 0
    confidence: float = 1.0
    selected: bool = False
    stroke_width: Optional[float] = None
    stroke_color: Optional[str] = None
    fill_color: Optional[str] = None


class TableCellElement(BaseModel):
    id: str
    type: str = "table_cell"
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0.0
    z_order: int = 0
    confidence: float = 1.0
    row: int
    column: int
    row_span: int = 1
    column_span: int = 1
    text: str = ""
    font_family: Optional[str] = None
    font_size: Optional[float] = None
    font_weight: Optional[str] = None
    font_style: Optional[str] = None
    alignment: Optional[str] = None
    text_color: Optional[str] = None
    fill_color: Optional[str] = None
    border_color: Optional[str] = None
    border_width: Optional[float] = None


class TableGridElement(BaseModel):
    id: str
    type: str = "table"
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0.0
    z_order: int = 0
    confidence: float = 1.0
    rows: int
    columns: int
    cells: List[TableCellElement] = Field(default_factory=list)
    grid_lines: List[LineElement] = Field(default_factory=list)
    stroke_width: Optional[float] = None
    stroke_color: Optional[str] = None
    fill_color: Optional[str] = None


class SignatureFieldElement(BaseModel):
    id: str
    type: str = "signature"
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0.0
    z_order: int = 0
    confidence: float = 1.0
    filled: bool = False
    stroke_width: Optional[float] = None
    stroke_color: Optional[str] = None
    fill_color: Optional[str] = None


class ImageElement(BaseModel):
    id: str
    type: str = "image"
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0.0
    z_order: int = 0
    confidence: float = 1.0
    image_hash: Optional[str] = None
    image_data: Optional[str] = None
    image_type: Optional[str] = None
    visual_description: Optional[str] = None


class FormSectionElement(BaseModel):
    id: str
    type: str = "section"
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0.0
    z_order: int = 0
    confidence: float = 1.0
    title: str
    elements: List[str] = Field(default_factory=list)
    stroke_width: Optional[float] = None
    stroke_color: Optional[str] = None
    fill_color: Optional[str] = None


class PageElement(BaseModel):
    id: str
    type: str = "page"
    x: float = 0.0
    y: float = 0.0
    width: float
    height: float
    rotation: float = 0.0
    z_order: int = 0
    confidence: float = 1.0
    page_number: int
    background_color: Optional[str] = None
    elements: List[Any] = Field(default_factory=list)



