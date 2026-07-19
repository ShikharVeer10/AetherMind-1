import os
import json
from typing import Optional, List, Dict, Any
import requests
import base64
from models.document_model import HighFidelityBlueprintModel, ColorPaletteModel
from services.color_semantic_service import ColorSemanticService

_UNIVERSAL_RECONSTRUCTION_PROMPT = """
You are a Senior Staff Visual Intelligence Engineer. Your task is to analyze the provided image and generate a HIGH-FIDELITY RECONSTRUCTION BLUEPRINT.

This blueprint must be precise enough that an LLM can use it to regenerate an IDENTICAL image.

### 1. Identify Content Type
Determine if this is a:
- **Consulting Dashboard**: Multiple charts (bar, donut, stacked), tables, and insights.
- **Structured Form**: Government/Procurement form with fields, checkboxes, and signature blocks.
- **Complex Diagram**: Flowcharts, capability maps, or process flows.

### 2. Layout & Hierarchy
- Map the absolute and relative positioning of all major blocks.
- Define alignment anchors (e.g., "Left pane takes 40% width, Right pane takes 60%").
- Preserve the exact grouping of elements.

### 3. Exhaustive Data Extraction
- **FOR CHARTS**: Extract every series name, every value (absolute/percentage), and every color. Map colors precisely to labels.
- **FOR FORMS**: Map every field label to its value. Capture checkbox states (checked/unchecked/partial). Identify signature areas.
- **FOR TABLES**: Extract full row/column data, including nested headers and merged cells.

### 4. Visual Styles
- Identify background colors, border styles, and font emphasis (bold/italic).
- Reference the global color palette for all data series.

### 5. Reconstruction Instructions
- Provide a set of "Developer Hints" for near-identical recreation.

OUTPUT: Return a raw JSON object matching the HighFidelityBlueprintModel schema.
"""

class VisualIntelligenceAgent:
    def __init__(self):
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.color_service = ColorSemanticService()

    async def extract_visual_blueprint(self, image_bytes: bytes, context: str = "") -> Optional[HighFidelityBlueprintModel]:
        """
        Segmented high-fidelity visual extraction for small local models.
        """
        try:
            palette = self.color_service.extract_palette(image_bytes)
            print("[VisualIntelligenceAgent] Discovering layout sections...")
            sections = await self._discover_sections(image_bytes)
            print(f"[VisualIntelligenceAgent] Extracting details for {len(sections)} sections...")
            visual_components = []
            for section in sections:
                details = await self._extract_section_details(image_bytes, section)
                if details:
                    visual_components.append(details)
            blueprint_data = {
                "layout_type": "consulting_dashboard" if len(sections) > 1 else "structured_form",
                "color_palette": palette,
                "visual_components": visual_components,
                "layout_hierarchy": {"sections": sections},
                "reconstruction_instructions": "Maintain the grid layout as described in hierarchy.",
                "raw_data_summary": f"Extracted {len(visual_components)} components from {len(sections)} sections."
            }

            return HighFidelityBlueprintModel(**blueprint_data)
                
        except Exception as e:
            print(f"[VisualIntelligenceAgent] Extraction failed: {e}")
            return None

    async def _discover_sections(self, image_bytes: bytes) -> List[str]:
        img_b64 = base64.b64encode(image_bytes).decode("ascii")
        prompt = "Identify the 3-5 major visual sections of this image (e.g. Header, Left Table, Right Chart, Footer). List them clearly as a bulleted list."
        payload = {"model": "moondream", "prompt": prompt, "images": [img_b64], "stream": False}
        try:
            resp = requests.post(f"{self.ollama_host}/api/generate", json=payload, timeout=60)
            res_text = resp.json().get("response", "")
            
            # Parse bullet points
            import re
            sections = re.findall(r'(?:^|\n)[*\-•\d\.]+\s*(.+)', res_text)
            if not sections:
                # Fallback: Split by newline
                sections = [s.strip() for s in res_text.split('\n') if len(s.strip()) > 5]
            
            return sections[:5] if sections else ["Main Content"]
        except: return ["Main Content"]

    async def _extract_section_details(self, image_bytes: bytes, section_name: str) -> Dict[str, Any]:
        """Extract high-precision data for a specific section using plain text parsing fallback."""
        img_b64 = base64.b64encode(image_bytes).decode("ascii")
        prompt = f"Focus ONLY on the '{section_name}'. Extract every number, percentage, label, and color mapping. List them clearly. Be exhaustive."
        
        payload = {"model": "moondream", "prompt": prompt, "images": [img_b64], "stream": False}
        try:
            resp = requests.post(f"{self.ollama_host}/api/generate", json=payload, timeout=90)
            res_text = resp.json().get("response", "")
            return {"section": section_name, "raw_extraction": res_text}
        except: return {"section": section_name, "error": "Extraction failed"}

    def _repair_json(self, s: str) -> str:
        """Fixes common truncation and quote issues in local model JSON."""
        s = s.strip()
        if not s: return "{}"
        
        # Isolate JSON
        start = s.find('{')
        end = s.rfind('}')
        if start != -1:
            if end == -1 or end < start:
                s = s[start:] + "}"
            else:
                s = s[start:end+1]

        if s.count('"') % 2 != 0:
            s += '"'
        open_b = s.count('{')
        close_b = s.count('}')
        while open_b > close_b:
            s += '}'
            close_b += 1
            
        # Balance brackets
        open_sq = s.count('[')
        close_sq = s.count(']')
        while open_sq > close_sq:
            s += ']'
            close_sq += 1
            
        return s

    def _heuristic_recovery(self, s: str) -> Dict[str, Any]:
        """Extracts key values using regex when JSON structure is too broken."""
        import re
        data = {}
        # Try to find common keys
        for key in ["layout_type", "reconstruction_instructions", "raw_data_summary"]:
            match = re.search(f'"{key}"\\s*:\\s*"([^"]+)"', s)
            if match:
                data[key] = match.group(1)
        return data
