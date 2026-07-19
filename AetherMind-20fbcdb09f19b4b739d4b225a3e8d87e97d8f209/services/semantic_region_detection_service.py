from typing import List, Any, Dict
from models.document_model import (
    SlideModel, 
    DocumentElementModel, 
    SemanticRegionModel, 
    PositionModel,
    LayoutGraphModel
)

class SemanticRegionDetectionService:
    def detect_regions(self, slide: SlideModel) -> List[SemanticRegionModel]:
        elements = slide.elements
        if not elements:
            return []

        regions = []
        regions.extend(self._detect_structural_regions(elements))
        regions.extend(self._detect_visual_panels(elements))

        # Estimate layout boundaries dynamically
        width = 12192000.0
        height = 6858000.0
        for e in elements:
            if e.position:
                width = max(width, e.position.x + e.position.width)
                height = max(height, e.position.y + e.position.height)

        # 1. Callout Boxes & Highlighted Regions
        for element in elements:
            if element.element_type in ("shape", "text_box", "placeholder"):
                text = (element.text or "").strip()
                if not text:
                    continue
                
                has_bg = False
                has_border = False
                if element.style:
                    if element.style.background_color and element.style.background_color.lower() not in ("#ffffff", "#000000", "none"):
                        has_bg = True
                if element.metadata.get("border_color"):
                    has_border = True
                
                shape_type_str = str(element.shape_type).lower()
                is_callout_shape = "callout" in shape_type_str or "balloon" in shape_type_str
                
                if is_callout_shape or (has_bg and has_border) or (has_bg and len(text) < 150):
                    role = "callout_box" if is_callout_shape else "highlighted_region"
                    purpose = f"Highlights key information: '{text[:60]}...'"
                    regions.append(SemanticRegionModel(
                        name=f"{role}_{element.element_id}",
                        semantic_role=role,
                        purpose=purpose,
                        position=element.position,
                        contents=[text]
                    ))

        # 2. Sidebars (Width < 35% of slide, Height > 40% of slide, positioned on extreme left/right)
        for element in elements:
            if element.position:
                el_w = element.position.width / width
                el_h = element.position.height / height
                el_x = element.position.x / width
                
                if el_w < 0.35 and el_h > 0.4 and (el_x < 0.25 or el_x > 0.65):
                    text = (element.text or "").strip()
                    if text:
                        regions.append(SemanticRegionModel(
                            name=f"sidebar_{element.element_id}",
                            semantic_role="sidebar",
                            purpose=f"Provides supplementary sidebar content: '{text[:60]}...'",
                            position=element.position,
                            contents=[text]
                        ))

        # 3. Findings, Recommendations, and Executive Summary Panels
        for element in elements:
            text = (element.text or "").strip()
            if not text:
                continue
                
            text_lower = text.lower()
            role = None
            purpose = ""
            
            if "finding" in text_lower or "result" in text_lower or "observation" in text_lower or "metrics" in text_lower:
                role = "findings_panel"
                purpose = "Presents data observations or findings"
            elif "recommend" in text_lower or "next step" in text_lower or "proposal" in text_lower or "should" in text_lower or "action item" in text_lower:
                role = "recommendation_panel"
                purpose = "Outlines recommendations or action items"
            elif "executive summary" in text_lower or "key takeaway" in text_lower or "summary" in text_lower or "overview" in text_lower:
                role = "executive_summary_panel"
                purpose = "Summarizes core slide content"
                
            if role:
                already_captured = False
                for r in regions:
                    if r.name == f"{role}_{element.element_id}":
                        already_captured = True
                        break
                if not already_captured:
                    regions.append(SemanticRegionModel(
                        name=f"{role}_{element.element_id}",
                        semantic_role=role,
                        purpose=purpose,
                        position=element.position,
                        contents=[text]
                    ))

        return regions

    def build_layout_graph(self, elements: List[DocumentElementModel], regions: List[SemanticRegionModel]) -> LayoutGraphModel:
        nodes = []
        edges = []
        for e in elements:
            nodes.append({
                "id": e.element_id,
                "type": e.element_type,
                "label": e.text[:50] if e.text else e.element_type
            })
        for r in regions:
            nodes.append({
                "id": f"region_{r.name}",
                "type": "region",
                "label": r.name
            })
        for r in regions:
            for e_id in r.contents:
                edges.append({
                    "source": f"region_{r.name}",
                    "target": e_id,
                    "relation": "contains"
                })
        sorted_elements = sorted(elements, key=lambda x: (x.position.y, x.position.x))
        for i in range(len(sorted_elements) - 1):
            edges.append({
                "source": sorted_elements[i].element_id,
                "target": sorted_elements[i+1].element_id,
                "relation": "precedes_in_reading_order"
            })
            
        return LayoutGraphModel(nodes=nodes, edges=edges)

    def _detect_structural_regions(self, elements: List[DocumentElementModel]) -> List[SemanticRegionModel]:
        regions = []
        title_elements = [e for e in elements if "title" in str(e.metadata.get("name", "")).lower()]
        if title_elements:
            regions.append(SemanticRegionModel(
                name="Title Region",
                semantic_role="header",
                purpose="Defines slide topic",
                position=title_elements[0].position,
                contents=[e.element_id for e in title_elements]
            ))
        return regions
    def _detect_visual_panels(self, elements: List[DocumentElementModel]) -> List[SemanticRegionModel]:
        if not elements:
            return []
        sorted_x = sorted(elements, key=lambda e: e.position.x)
        gaps = []
        for i in range(len(sorted_x) - 1):
            gap = sorted_x[i+1].position.x - (sorted_x[i].position.x + sorted_x[i].position.width)
            if gap > 500000: # Approx 0.5 inches
                gaps.append(i)
                
        regions = []
        if len(gaps) == 1:
            # 2-panel layout
            left_elems = sorted_x[:gaps[0]+1]
            right_elems = sorted_x[gaps[0]+1:]
            
            if left_elems:
                regions.append(self._create_region_from_elements("Left Panel", left_elems))
            if right_elems:
                regions.append(self._create_region_from_elements("Right Panel", right_elems))
                
        return regions

    def _create_region_from_elements(self, name: str, elements: List[DocumentElementModel]) -> SemanticRegionModel:
        min_x = min(e.position.x for e in elements)
        min_y = min(e.position.y for e in elements)
        max_x = max(e.position.x + e.position.width for e in elements)
        max_y = max(e.position.y + e.position.height for e in elements)
        
        return SemanticRegionModel(
            name=name,
            semantic_role="content_panel",
            purpose="Groups related content vertically",
            position=PositionModel(x=min_x, y=min_y, width=max_x-min_x, height=max_y-min_y),
            contents=[e.element_id for e in elements]
        )
