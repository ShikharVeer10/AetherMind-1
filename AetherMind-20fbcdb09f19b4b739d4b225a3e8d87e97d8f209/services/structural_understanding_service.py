
from typing import List
from models.document_model import SlideModel
from agents.structural_understanding_agents import (
    SlideArchetypeDetectionAgent,
    RegionSegmentationAgent,
    LayoutGraphAgent,
    CapabilityMapAgent,
    GovernanceFrameworkAgent,
    ProcessFlowAgent,
    DashboardExtractionAgent,
    VisualHierarchyAgent,
    ReadingOrderAgent,
    SemanticRelationshipAgent,
    SpanOfControlAgent
)

class UniversalStructuralUnderstandingService:
    def __init__(self):
        self.archetype_agent = SlideArchetypeDetectionAgent()
        self.region_agent = RegionSegmentationAgent()
        self.layout_graph_agent = LayoutGraphAgent()
        self.capability_agent = CapabilityMapAgent()
        self.governance_agent = GovernanceFrameworkAgent()
        self.process_agent = ProcessFlowAgent()
        self.dashboard_agent = DashboardExtractionAgent()
        self.hierarchy_agent = VisualHierarchyAgent()
        self.reading_order_agent = ReadingOrderAgent()
        self.semantic_rel_agent = SemanticRelationshipAgent()
        self.soc_agent = SpanOfControlAgent()

    def analyze_slide(self, slide: SlideModel) -> SlideModel:
        slide.slide_archetype = self.archetype_agent.run(slide)
        slide.semantic_regions = self.region_agent.run(slide)
        slide.layout_graph = self.layout_graph_agent.run(slide)
        slide.capability_map = self.capability_agent.run(slide)
        slide.governance_framework = self.governance_agent.run(slide)
        slide.process_flow = self.process_agent.run(slide)
        slide.dashboard = self.dashboard_agent.run(slide)
        soc_data = self.soc_agent.run(slide)
        if soc_data:
            if not slide.governance_framework:
                from models.document_model import GovernanceFrameworkModel
                slide.governance_framework = GovernanceFrameworkModel()
            slide.governance_framework.layers.extend(soc_data)
        
        slide.visual_hierarchy = self.hierarchy_agent.run(slide)
        slide.reading_order = self.reading_order_agent.run(slide)
        semantic_rels = self.semantic_rel_agent.run(slide)
        if semantic_rels:
            slide.relationships.extend(semantic_rels)
            
        return slide
