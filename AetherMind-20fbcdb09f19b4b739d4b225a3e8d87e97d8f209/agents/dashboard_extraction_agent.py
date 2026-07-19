from models.document_model import SlideModel, DashboardModel

class DashboardExtractionAgent:
    def run(self, slide_model: SlideModel) -> DashboardModel:
        text_content = " ".join([e.text for e in slide_model.elements if e.text]).lower()
        if "dashboard" not in text_content and len(slide_model.chart_understandings) < 2:
            return None
            
        panels = []
        for element in slide_model.elements:
            if element.element_type in ["chart", "table"]:
                panels.append({
                    "id": element.element_id,
                    "type": element.element_type,
                    "bbox": {
                        "x": element.position.x,
                        "y": element.position.y,
                        "width": element.position.width,
                        "height": element.position.height
                    }
                })
        
        if not panels:
            return None
            
        return DashboardModel(
            panels=panels,
            metrics=[],  # Can be populated by LLM
            relationships=[] # Can be populated by LLM
        )
