from typing import List, Optional, Dict, Any
from models.document_model import (
    SlideModel,
    SlideArchetypeModel,
    SemanticRegionModel,
    LayoutGraphModel,
    CapabilityMapModel,
    GovernanceFrameworkModel,
    ProcessFlowModel,
    DashboardModel,
    VisualHierarchyModel,
    RelationshipModel
)

class SlideArchetypeDetectionAgent:
    def run(self, slide: SlideModel) -> SlideArchetypeModel:
        ARCHETYPES = [
            "title_slide", "agenda_slide", "executive_summary", "comparison_slide", 
            "dashboard_slide", "capability_map", "governance_model", "organization_chart", 
            "process_flow", "timeline", "recommendation_slide", "infographic_slide", 
            "matrix_slide", "quadrant_slide", "scorecard_slide", "heatmap", 
            "operating_model", "architecture_diagram", "roadmap", "table-centric_slide", 
            "image-centric_slide", "hybrid_slide"
        ]
        
        archetype = "hybrid_slide"
        confidence = 0.4
        
        inv = slide.visual_inventory
        title_lower = (slide.title or "").lower()
        text_content_lower = " ".join([p.text.lower() for p in slide.text_points])
        
        if any(k in title_lower for k in ["agenda", "contents"]):
            archetype = "agenda_slide"
            confidence = 0.8
        elif slide.slide_number == 1 or "deloitte" in title_lower:
            archetype = "title_slide"
            confidence = 0.7
            
        elif any(k in title_lower for k in ["capability", "maturity", "framework"]):
            archetype = "capability_map"
            confidence = 0.7
        elif any(k in title_lower for k in ["governance", "committee", "structure", "reporting"]):
            archetype = "governance_model"
            confidence = 0.7
        elif any(k in title_lower for k in ["operating model", "target state"]):
            archetype = "operating_model"
            confidence = 0.8
            
        elif any(k in title_lower for k in ["process", "flow", "workflow", "step"]):
            archetype = "process_flow"
            confidence = 0.7
        elif any(k in title_lower for k in ["roadmap", "timeline", "horizon", "plan"]):
            archetype = "roadmap"
            confidence = 0.8
            
        elif any(k in title_lower for k in ["dashboard", "kpi", "metrics", "status"]):
            archetype = "dashboard_slide"
            confidence = 0.7
        elif any(k in title_lower for k in ["scorecard", "assessment"]):
            archetype = "scorecard_slide"
            confidence = 0.7
        elif inv and inv.chart_count > 0:
            archetype = "dashboard_slide"
            confidence = 0.6
        elif inv and inv.table_count > 0:
            if "matrix" in title_lower or "comparison" in title_lower:
                archetype = "matrix_slide"
            else:
                archetype = "table-centric_slide"
            confidence = 0.7
            
        elif any(k in title_lower for k in ["executive summary", "key observations"]):
            archetype = "executive_summary"
            confidence = 0.8
        elif any(k in title_lower for k in ["recommendation", "next steps", "opportunity"]):
            archetype = "recommendation_slide"
            confidence = 0.8
            
        return SlideArchetypeModel(slide_archetype=archetype, confidence=confidence)

class RegionSegmentationAgent:
    def run(self, slide: SlideModel) -> List[SemanticRegionModel]:
        from services.semantic_region_detection_service import SemanticRegionDetectionService
        service = SemanticRegionDetectionService()
        return service.detect_regions(slide)

class LayoutGraphAgent:
    def run(self, slide: SlideModel) -> LayoutGraphModel:
        from services.semantic_region_detection_service import SemanticRegionDetectionService
        service = SemanticRegionDetectionService()
        return service.build_layout_graph(slide.elements, slide.semantic_regions)

class CapabilityMapAgent:
    def run(self, slide: SlideModel) -> Optional[CapabilityMapModel]:
        if not slide.slide_archetype or slide.slide_archetype.slide_archetype != "capability_map":
            if not any(k in (slide.title or "").lower() for k in ["capability", "maturity", "taxonomy", "levels"]):
                return None
            
        model = CapabilityMapModel()
        domains = []
        capabilities = []
        
        for element in slide.elements:
            if element.element_type == "shape" and element.position.width > 2000000:
                domains.append({"id": element.element_id, "name": element.text or "Domain"})
            elif element.element_type in ["text_box", "shape"] and element.position.width <= 2000000:
                capabilities.append({"id": element.element_id, "name": element.text or "Capability"})
                
        model.domains = domains
        model.capabilities = capabilities
        return model

class GovernanceFrameworkAgent:
    def run(self, slide: SlideModel) -> Optional[GovernanceFrameworkModel]:
        if not slide.slide_archetype or slide.slide_archetype.slide_archetype != "governance_model":
            if not any(k in (slide.title or "").lower() for k in ["governance", "organization", "committee", "structure"]):
                return None
                
        model = GovernanceFrameworkModel()
        entities = []
        for element in slide.elements:
            if element.element_type in ["text_box", "shape"]:
                entities.append({"id": element.element_id, "label": element.text or "Entity", "y": element.position.y})
        
        entities.sort(key=lambda x: x["y"])
        layers = []
        if entities:
            current_layer = {"y_start": entities[0]["y"], "entities": []}
            for e in entities:
                if e["y"] - current_layer["y_start"] > 1000000:
                    layers.append(current_layer)
                    current_layer = {"y_start": e["y"], "entities": []}
                current_layer["entities"].append(e["id"])
            layers.append(current_layer)
            
        model.layers = layers
        model.entities = entities
        return model

class ProcessFlowAgent:
    def run(self, slide: SlideModel) -> Optional[ProcessFlowModel]:
        if not slide.slide_archetype or slide.slide_archetype.slide_archetype not in ["process_flow", "roadmap"]:
             if not any(k in (slide.title or "").lower() for k in ["process", "flow", "workflow", "step", "cycle", "journey"]):
                return None
                
        model = ProcessFlowModel()
        nodes = []
        for element in slide.elements:
            if element.element_type in ["text_box", "shape"]:
                nodes.append({"id": element.element_id, "text": element.text})
        model.nodes = nodes
        
        model.edges = [{"source": r.source_element_id, "target": r.target_element_id} for r in slide.relationships if r.relationship_type == "connector"]
        
        sorted_nodes = sorted(nodes, key=lambda n: next((e.position.x for e in slide.elements if e.element_id == n["id"]), 0))
        model.sequence = [n["id"] for n in sorted_nodes]
        
        return model

class DashboardExtractionAgent:
    def run(self, slide: SlideModel) -> Optional[DashboardModel]:
        is_dash = False
        if slide.slide_archetype and slide.slide_archetype.slide_archetype in ["dashboard_slide", "scorecard_slide"]:
            is_dash = True
        
        # Check for recurring NMSU dashboard keywords
        dashboard_keywords = ["fragmentation", "cost", "fte", "location", "labor", "centralization", "shared services"]
        if not is_dash and not any(k in (slide.title or "").lower() for k in dashboard_keywords):
            return None
                
        model = DashboardModel()
        panels = []
        metrics = []
        
        # If we have chart understandings from Vision LLM, they are primary for dashboards
        if slide.chart_understandings:
            for chart in slide.chart_understandings:
                # Map chart data to dashboard metrics or panels
                metrics.append({
                    "id": chart.chart_id,
                    "type": "chart_data",
                    "chart_type": chart.chart_type,
                    "title": chart.title,
                    "series": [s.model_dump() for s in chart.series],
                    "categories": chart.categories,
                    "units": chart.units
                })

        import re
        # Fallback/Supplemental regex for NMSU report values
        number_pattern = re.compile(r"^\d+(\.\d+)?$")
        scale_pattern = re.compile(r"^\(\d+\)$")
        cost_pattern = re.compile(r"^\$\d+(\.\d+)?[KM]?$")
        
        for element in slide.elements:
            if element.text:
                text = element.text.strip()
                if number_pattern.match(text) or scale_pattern.match(text) or cost_pattern.match(text):
                    metrics.append({
                        "id": element.element_id, 
                        "value": text,
                        "position": element.position.model_dump(),
                        "type": "scalar_metric"
                    })
            
            if element.element_type == "shape" and element.position.width > 2000000:
                panels.append({
                    "id": element.element_id,
                    "label": element.text or "Panel",
                    "bounds": element.position.model_dump()
                })
                
        model.panels = panels
        model.metrics = metrics
        return model

class SpanOfControlAgent:
    def run(self, slide: SlideModel) -> List[Dict[str, Any]]:
        if not any(k in (slide.title or "").lower() for k in ["span of control", "management layer", "soc"]):
            return []
        if slide.chart_understandings:
            for chart in slide.chart_understandings:
                if chart.chart_type == "span_of_control_pyramid" or "span of control" in (chart.title or "").lower():
                    # Transform chart series into layer data
                    layers = []
                    # Assuming categories are layers and series[0] isAvg SoC
                    for idx, cat in enumerate(chart.categories):
                        soc_val = chart.series[0].values[idx] if len(chart.series) > 0 and len(chart.series[0].values) > idx else "N/A"
                        mgr_count = chart.series[1].values[idx] if len(chart.series) > 1 and len(chart.series[1].values) > idx else "0"
                        layers.append({
                            "layer_label": f"Layer {cat}",
                            "avg_soc": soc_val,
                            "number_of_managers": mgr_count
                        })
                    return layers

        # Preference 2: Positional text extraction (Legacy/Fallback)
        layers = []
        text_elements = [e for e in slide.elements if e.text and e.element_type in ["text_box", "shape"]]
        text_elements.sort(key=lambda e: e.position.y)
        
        for e in text_elements:
            if "layer" in e.text.lower():
                layers.append({"layer_label": e.text, "y": e.position.y, "data": []})
        
        for e in text_elements:
            val = e.text.strip()
            if any(char.isdigit() for char in val) and "layer" not in val.lower():
                for layer in layers:
                    if abs(layer["y"] - e.position.y) < 500000:
                        layer["data"].append(val)
                        
        return layers

class VisualHierarchyAgent:
    def run(self, slide: SlideModel) -> VisualHierarchyModel:
        primary = []
        secondary = []
        tertiary = []
        
        sorted_elements = sorted(slide.elements, key=lambda e: (e.position.width * e.position.height), reverse=True)
        
        if sorted_elements:
            primary.append(sorted_elements[0].element_id)
            if len(sorted_elements) > 1:
                secondary.append(sorted_elements[1].element_id)
            if len(sorted_elements) > 2:
                tertiary.append(sorted_elements[2].element_id)
                
        return VisualHierarchyModel(
            primary_focus=primary,
            secondary_focus=secondary,
            tertiary_focus=tertiary
        )

class ReadingOrderAgent:
    def run(self, slide: SlideModel) -> List[str]:
        sorted_elements = sorted(slide.elements, key=lambda e: (e.position.y, e.position.x))
        return [e.element_id for e in sorted_elements]

class SemanticRelationshipAgent:
    def run(self, slide: SlideModel) -> List[RelationshipModel]:
        return []
