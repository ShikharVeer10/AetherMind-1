from typing import List
from models.document_model import (
    DocumentElementModel,
    LayoutStructureModel,
    RegionModel,
    FlowchartModel,
)

# Standard 16:9 slide dimensions in EMUs
_SLIDE_WIDTH = 12_192_000
_SLIDE_HEIGHT = 6_858_000

_HEADER_CUTOFF = 0.18
_FOOTER_CUTOFF = 0.85
_LEFT_RIGHT_SPLIT = 0.50


class LayoutAnalysisService:

    def __init__(self,slide_width: float = _SLIDE_WIDTH,slide_height: float = _SLIDE_HEIGHT):
        self.slide_width = slide_width
        self.slide_height = slide_height

    def analyse(self,elements: List[DocumentElementModel],flowchart: FlowchartModel,) -> LayoutStructureModel:
        """
        Classify layout type and segment elements into named regions.
        """
        if not elements:
            return LayoutStructureModel(layout_type="blank")

        header_cut_y = self.slide_height * _HEADER_CUTOFF
        footer_cut_y = self.slide_height * _FOOTER_CUTOFF
        mid_x = self.slide_width * _LEFT_RIGHT_SPLIT

        header_ids: List[str] = []
        footer_ids: List[str] = []
        left_body_ids: List[str] = []
        right_body_ids: List[str] = []

        for e in elements:
            cy = e.position.y + e.position.height / 2
            cx = e.position.x + e.position.width / 2

            if cy < header_cut_y:
                header_ids.append(e.element_id)
            elif cy > footer_cut_y:
                footer_ids.append(e.element_id)
            elif cx < mid_x:
                left_body_ids.append(e.element_id)
            else:
                right_body_ids.append(e.element_id)

        regions = []
        if header_ids:
            regions.append(RegionModel(
                name="header",
                x_start=0, y_start=0,
                x_end=self.slide_width, y_end=header_cut_y,
                element_ids=header_ids,
            ))
        if left_body_ids:
            regions.append(RegionModel(
                name="body_left",
                x_start=0, y_start=header_cut_y,
                x_end=mid_x, y_end=footer_cut_y,
                element_ids=left_body_ids,
            ))
        if right_body_ids:
            regions.append(RegionModel(
                name="body_right",
                x_start=mid_x, y_start=header_cut_y,
                x_end=self.slide_width, y_end=footer_cut_y,
                element_ids=right_body_ids,
            ))
        if footer_ids:
            regions.append(RegionModel(
                name="footer",
                x_start=0, y_start=footer_cut_y,
                x_end=self.slide_width, y_end=self.slide_height,
                element_ids=footer_ids,
            ))

        layout_type = self._classify(
            elements=elements,
            left_body_ids=left_body_ids,
            right_body_ids=right_body_ids,
            flowchart=flowchart,
        )

        return LayoutStructureModel(
            layout_type=layout_type,
            regions=regions,
        )



    @staticmethod
    def _classify(
        elements: List[DocumentElementModel],
        left_body_ids: List[str],
        right_body_ids: List[str],
        flowchart: FlowchartModel,
    ) -> str:
        text_elements = [e for e in elements if e.text]

        if flowchart.is_flowchart:
            return "flowchart"
        has_tables = any(e.element_type == "table" for e in elements)
        has_images = any(e.element_type == "image" for e in elements)
        if len(text_elements) <= 2 and not has_tables and not has_images:
            return "title_slide"

        if left_body_ids and right_body_ids:
            return "two_column"

        shape_or_image = [
            e for e in elements
            if e.element_type in ("image", "shape", "chart")
        ]
        if len(shape_or_image) > len(text_elements):
            return "diagram"

        return "single_column"
