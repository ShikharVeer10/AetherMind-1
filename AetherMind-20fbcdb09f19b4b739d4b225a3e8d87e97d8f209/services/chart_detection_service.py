from typing import List,Dict,Any
from models.document_model import DocumentElementModel

class ChartDetectionService:
    CHART_KEYWORDS=[
        "chart showing",
        "graph showing",
        "percentage of",
        "historical trend",
        "projected growth",
        "year-over-year",
        "y-o-y",
        "survey results",
        "respondent profile",
        "market share %",
        "revenue growth",
        "performance metrics",
        "kpi dashboard",
        "donut chart",
        "ring chart",
        "circular chart"
    ]
    def detect_charts(self,elements:List[DocumentElementModel])->List[DocumentElementModel]:
        detected_charts=[]
        for element in elements:
            # If already classified as chart by visual object classifier, trust it
            if element.metadata.get("visual_class", {}).get("classification") == "chart":
                element.metadata["is_chart"] = True
                if not element.metadata.get("detected_chart_type"):
                    element.metadata["detected_chart_type"] = self._detect_chart_type(element)
                detected_charts.append(element)
                continue

            if self._is_chart(element):
                chart_type=self._detect_chart_type(element)
                element.metadata["detected_chart_type"] = chart_type
                element.metadata["is_chart"] = True
                detected_charts.append(element)

        return detected_charts

    def _is_chart(self,element: DocumentElementModel) -> bool:
        vclass = element.metadata.get("visual_class", {})
        if (isinstance(vclass, dict) and vclass.get("classification") == "chart"):
            return True
        
        text = (element.text or "").lower()
        
        # Avoid false positives for contact info or small snippets
        if "@" in text or "phone:" in text or len(text) < 20:
            return False

        keyword_hits = sum(keyword in text for keyword in self.CHART_KEYWORDS)
        # Require higher confidence for text-only detection
        if keyword_hits >= 1 and "%" in text and any(c.isdigit() for c in text):
            return True
        
        metadata = element.metadata or {}
        if metadata.get("contains_bars") and metadata.get("contains_axes"):
            return True
        return False

    def _detect_chart_type(self,element: DocumentElementModel) -> str:
        text = (element.text or "").lower()
        metadata = element.metadata or {}
        if metadata.get("chart_type"):
            return metadata["chart_type"]
        if "pie" in text:
            return "pie_chart"
        if ("line" in text or "trend" in text or "forecast" in text):
            return "line_chart"
        if "scatter" in text:
            return "scatter_plot"
        if ("stacked" in text or metadata.get("stacked")):
            return "stacked_bar_chart"
        if (metadata.get("legend_count", 0) > 1):
            return "grouped_bar_chart"
        if metadata.get("orientation") == "horizontal":
            return "horizontal_bar_chart"
        if metadata.get("orientation") == "vertical":
            return "vertical_bar_chart"
        return "bar_chart"

    def group_chart_regions(self,chart_elements: List[DocumentElementModel]) -> List[List[DocumentElementModel]]:
        groups = []
        used = set()
        for element in chart_elements:
            if element.element_id in used:
                continue
            group = [element]
            used.add(element.element_id)
            pos = element.position
            for other in chart_elements:
                if other.element_id in used:
                    continue
                other_pos = other.position
                x_distance = abs(pos.x - other_pos.x)
                y_distance = abs(pos.y - other_pos.y)
                if x_distance < 1500000 and y_distance < 1500000:
                    group.append(other)
                    used.add(other.element_id)
            groups.append(group)
        return groups
    def extract_chart_title(self,chart_group: List[DocumentElementModel]) -> str:
        title_candidates = []
        for element in chart_group:
            text = (element.text or "").strip()
            if not text:
                continue
            if len(text) > 15:
                title_candidates.append(text)
        if title_candidates:
            return title_candidates[0]
        return "Untitled Chart"
