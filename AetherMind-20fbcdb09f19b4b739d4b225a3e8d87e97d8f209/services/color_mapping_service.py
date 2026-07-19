import json
from models.document_model import ChartUnderstandingModel

class ColorMappingService:
    def extract_color_mapping(self, chart: ChartUnderstandingModel) -> dict:
        """
        Ensures color mapping is preserved deterministically from chart series or legend mapping.
        """
        color_mapping = {}
        if chart.legend_mapping:
            for hex_color, label in chart.legend_mapping.items():
                color_mapping[label] = hex_color
                
        if chart.series:
            for s in chart.series:
                if s.color and s.name not in color_mapping:
                    color_mapping[s.name] = s.color
                    
        return color_mapping
