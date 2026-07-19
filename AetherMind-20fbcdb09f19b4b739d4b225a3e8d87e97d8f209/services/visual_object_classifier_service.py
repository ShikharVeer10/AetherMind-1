from typing import List
from models.document_model import DocumentElementModel, VisualObjectClass

class VisualObjectClassifierService:
    def classify_elements(self, elements: List[DocumentElementModel]) -> None:
        for element in elements:
            text_content = (element.text or "").lower()
            name = str(element.metadata.get("name", "")).lower()
            
            chart_keywords = [
                "chart", "plot", "axis", "legend", "series", "data points", 
                "centralization", "shared services", "fragmentation", 
                "labor cost", "soc", "span of control", "fte", "funding type",
                "horizontal bar", "stacked bar", "pie", "donut", "ring",
                "survey result", "percentage of respondents", "agree", "disagree"
            ]
            
            is_potential_chart = (
                element.element_type == "chart" or 
                any(k in text_content for k in chart_keywords) or
                any(k in name for k in chart_keywords)
            )
            
            numeric_density = text_content.count("%") + text_content.count("$")
            is_survey_result = "percentage selecting" in text_content or " respondents " in text_content or "agree" in text_content
            
            # If it's an image element and has chart-like keywords in metadata or surrounding text
            if element.element_type == "image":
                 if any(k in name for k in chart_keywords) or numeric_density > 2:
                      element.metadata["visual_class"] = VisualObjectClass(classification="chart", confidence=0.8).model_dump()
                      element.element_type = "chart"
                      continue

            if is_potential_chart or (numeric_density > 3 and is_survey_result):
                # Only classify as chart if it is a visual object/image, not a raw text box
                if element.element_type == "image":
                    element.metadata["visual_class"] = VisualObjectClass(classification="chart", confidence=0.9).model_dump()
                    element.element_type = "chart" 
                    continue

            if element.element_type == "table" or "table" in text_content:
                # Be aggressive: if it's full of percentages, it's a chart data grid
                if numeric_density >= 2 or ("percent" in text_content or "survey" in text_content):
                     element.metadata["visual_class"] = VisualObjectClass(classification="chart", confidence=0.9).model_dump()
                     element.element_type = "chart"
                     element.metadata["semantic_role"] = "chart"
                elif "axis" in text_content or "legend" in text_content or "series" in text_content:
                     element.metadata["visual_class"] = VisualObjectClass(classification="chart", confidence=0.9).model_dump()
                     element.element_type = "chart"
                     element.metadata["semantic_role"] = "chart"
                else:
                     element.metadata["visual_class"] = VisualObjectClass(classification="table", confidence=0.8).model_dump()
                     element.metadata["semantic_role"] = "table"
            elif "dashboard" in text_content:
                element.metadata["visual_class"] = VisualObjectClass(classification="dashboard", confidence=0.7).model_dump()
            elif "diagram" in text_content or "flow" in text_content:
                element.metadata["visual_class"] = VisualObjectClass(classification="diagram", confidence=0.7).model_dump()
            else:
                element.metadata["visual_class"] = VisualObjectClass(classification="mixed_content", confidence=0.5).model_dump()

