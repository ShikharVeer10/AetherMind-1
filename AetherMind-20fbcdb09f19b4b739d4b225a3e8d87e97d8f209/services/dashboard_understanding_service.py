from typing import List, Optional
from models.document_model import SlideModel, DashboardModel

class DashboardUnderstandingService:
    def extract_dashboard(self, slide: SlideModel) -> Optional[DashboardModel]:
        # This ties into the existing DashboardExtractionAgent logic
        from agents.structural_understanding_agents import DashboardExtractionAgent
        agent = DashboardExtractionAgent()
        return agent.run(slide)
