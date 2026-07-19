"""
Counts all visual elements on a slide, grouped by element_type.
"""

from typing import List
from models.document_model import DocumentElementModel, VisualInventoryModel


class VisualInventoryService:

    def count(
        self, elements: List[DocumentElementModel]
    ) -> VisualInventoryModel:
        """Iterate elements and tally by type."""
        counts = {
            "text_box": 0,
            "shape": 0,
            "arrow": 0,
            "connector": 0,
            "image": 0,
            "table": 0,
            "group": 0,
            "chart": 0,
            "placeholder": 0,
            "unknown": 0,
            "title": 0,
            "header": 0,
            "footer": 0,
            "figure": 0,
            "icon": 0,
        }

        for element in elements:
            t = element.element_type
            if t in counts:
                counts[t] += 1
            else:
                counts["unknown"] += 1
            if getattr(element, "is_title", False):
                counts["title"] += 1
            if t in {"icon"}:
                counts["icon"] += 1
            if t in {"smartart", "diagram"}:
                counts["figure"] += 1

        return VisualInventoryModel(
            text_box_count=counts["text_box"],
            shape_count=counts["shape"],
            arrow_count=counts["arrow"],
            connector_count=counts["connector"],
            image_count=counts["image"],
            table_count=counts["table"],
            group_count=counts["group"],
            chart_count=counts["chart"],
            placeholder_count=counts["placeholder"],
            unknown_count=counts["unknown"],title_count=counts["title"],
            header_count=counts["header"],
            footer_count=counts["footer"],
            figure_count=counts["figure"],
            icon_count=counts["icon"],
            slide_type=self._infer_slide_type(counts),
            total_elements=len(elements),
        )
    

    def _infer_slide_type(self,counts: dict) -> str:
        if counts["table"] > 0:
            return "table_slide"

        if counts["chart"] > 0:
            return "chart_slide"

        if counts["arrow"] + counts["connector"] > 3:
            return "flowchart"

        if counts["image"] > 3:
            return "image_heavy"

        return "general"
