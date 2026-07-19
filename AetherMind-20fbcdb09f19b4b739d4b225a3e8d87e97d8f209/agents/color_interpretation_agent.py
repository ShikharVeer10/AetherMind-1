import os
import json
from typing import Optional, List, Dict, Any
from google import genai
from google.genai import types
from models.document_model import ColorPaletteModel, SlideModel
from services.color_semantic_service import ColorSemanticService

_COLOR_INTERPRETATION_PROMPT = """
Analyze the provided image and its context to create a precise semantic mapping of colors.
Identify:
1. The dominant color palette (Hex codes).
2. Legend mappings (which color represents which series/category).
3. The semantic purpose of each major color (e.g., #0099A8 is "India Gen Zs", #84BD3A is "Global Millennials").
4. High-level branding or theme colors.

Output the result as a JSON object matching the ColorPaletteModel schema.
"""

class ColorInterpretationAgent:
    def __init__(self):
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.service = ColorSemanticService()

    async def interpret_colors(self, image_bytes: bytes, slide_context: str = "") -> ColorPaletteModel:
        import requests
        import base64
        palette = self.service.extract_palette(image_bytes)
        try:
            img_b64 = base64.b64encode(image_bytes).decode("ascii")
            target_model = os.getenv("OLLAMA_VISION_MODEL", "moondream")
            
            payload = {
                "model": target_model,
                "prompt": _COLOR_INTERPRETATION_PROMPT + f"\nSLIDE_CONTEXT: {slide_context}\nOutput MUST be raw JSON.",
                "images": [img_b64],
                "stream": False,
                "format": "json"
            }
            
            response = requests.post(f"{self.ollama_host}/api/generate", json=payload, timeout=120)
            if response.status_code == 200:
                raw_json = response.json().get("response", "").strip()
                start_idx = raw_json.find('{')
                end_idx = raw_json.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    raw_json = raw_json[start_idx:end_idx+1]
                llm_palette = ColorPaletteModel.model_validate_json(raw_json)
                for label in llm_palette.semantic_labels:
                     palette.legend_mapping[label.hex_color] = label.label
                palette.semantic_labels = llm_palette.semantic_labels
                if llm_palette.dominant_colors:
                    palette.dominant_colors = llm_palette.dominant_colors
                    
        except Exception as e:
            print(f"[ColorInterpretationAgent] Local reasoning failed: {e}")
        
        return palette
