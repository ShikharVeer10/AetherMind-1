import os
import json
import base64
import re
from typing import Any, Dict, Optional, List
from models.document_model import DocumentElementModel, ChartUnderstandingModel, ChartAxisModel, ChartSeriesModel, SlideModel

_CHART_EXTRACTION_PROMPT="""
You are an expert management consulting analyst specializing in top-tier (Deloitte, McKinsey, BCG) presentation decks. Your task is to analyze the provided chart image and extract its structure, data, and business strategic meaning with EXTREME precision so it can be recreated identically.

### 1. Strategic Context
- **purpose**: Define why this chart exists on the slide. What is its role in the narrative?
- **business_question**: What specific business question is this chart answering?
- **insight**: What is the primary analytical takeaway or "so what" of this chart?

### 2. High-Density Stacked Bar Charts (Critical)
Many charts in this set are horizontal stacked bar charts where each bar represents a 'Process' or 'Location' and each segment of the bar represents a 'Division' or 'Funding Type'.
- **Exhaustive Extraction**: You MUST extract EVERY segment of EVERY bar. Do not skip small segments or group them as 'Other' unless the chart explicitly does so.
- **Segment Order**: Preserve the exact left-to-right (or bottom-to-top) order of segments within each stack.
- **Values**: Extract the numerical values (absolute or percentage) for each segment. If not explicitly labeled, estimate the proportion based on the visual width of the segment.

### 3. Legend & Color Mapping (Critical)
- **Identical Colors**: Extract the exact or closest Hex color code for every series, bar, line, or category in the chart.
- **Label Mapping**: Create a precise mapping between Hex color codes (e.g. #0A4C54, #106030, #0A8EA0, #84BD3A) and their textual labels as mentioned in the legend below or next to the graphs.
- **Color Consistency**: The hex colors assigned to series values MUST exactly match the keys in the `legend_mapping` dictionary.

### 4. Axis & Scales
- **Units**: Identify the units (e.g., 'FTE', 'Cost ($K)', 'Percentage (%)', 'Number of Employees').
- **Scales**: Extract the min, max, and major tick marks for all axes.

### 5. Specialized Charts
- **Span of Control**: For 'Span of Control by Layer' charts, extract the Layer Number (1, 2, 3...) and the corresponding Avg. SoC value (e.g., 7.0, 4.8) and the Number of Managers.
- **Pie/Donut/Ring/Circular Charts**: Extract the exact segments, their values, and their associated legend labels. These are often used for "Percentage of respondents" metrics.

### 6. Demographic Analysis
Consulting slides often compare demographics (e.g., "India Gen Z", "Global Gen Z", "India millennials", "Global millennials"). 
- Ensure these demographic names are correctly mapped to their respective series and colors.
- If a legend exists at the bottom of the image, use it to resolve the mapping.

### Output Structure (JSON)
Provide the output strictly as a JSON object:
{
    "chart_type": "stacked_bar_chart | grouped_bar_chart | pie_chart | line_chart | span_of_control_pyramid | donut_chart | etc",
    "purpose": "Strategic purpose of the chart",
    "business_question": "The question this chart answers",
    "insight": "The primary analytical insight",
    "orientation": "horizontal | vertical",
    "stacking": "100_percent_stacked | stacked | grouped | none",
    "title": "Exact title text",
    "subtitle": "Exact subtitle text",
    "units": "The unit of measurement",
    "categories": ["Y-Axis labels for horizontal charts", "X-Axis labels for vertical charts"],
    "series": [
        {
            "name": "Series Name (from legend)",
            "color": "Hex color code (must match key in legend_mapping)",
            "values": [number_or_percentage_string, ...] // Corresponding to categories
        }
    ],
    "legend_mapping": {
        "#hex_color": "label_name"
    },
    "axes": {
        "x": {"min": 0, "max": 100, "ticks": ["0", "20", ...], "label": "X-axis title"},
        "y": {"min": 0, "max": 100, "ticks": ["A", "B", ...], "label": "Y-axis title"}
    },
    "data_labels_visible": true,
    "reconstruction_hints": "Specific instructions for identical visual reproduction, describing colors, legends, layout"
}

Do not include markdown blocks like ```json. Return ONLY the raw JSON string.
"""

_LOCAL_CHART_EXTRACTION_PROMPT="""
Look at this chart and list ALL the numbers, percentages, and labels you can read. 
Format your response as a simple list. Do not use JSON. Do not use code blocks.
Just write out the data you see, step by step.
"""
class ChartUnderstandingService:
    def extract_understanding(self, element: DocumentElementModel, slide_context: str = "") -> ChartUnderstandingModel:
        if element.metadata.get("chart_data"):
            return self.analyze_chart_element(element)
        chart_type = element.metadata.get("detected_chart_type", "horizontal_bar_chart")
        image_bytes = element.metadata.get("__image_bytes")
        
        extracted_data = None
        if image_bytes:
            try:
                extracted_data = self.call_vision_llm(image_bytes, slide_context)
                if extracted_data:
                    return self._parse_json_to_model(element.element_id, extracted_data)
            except Exception as e:
                print(f"[ChartUnderstanding] Failed parsing vision LLM response for {element.element_id}: {e}")
        if element.text:
            return self._heuristic_extraction(element, chart_type)

        return ChartUnderstandingModel(
            chart_id=element.element_id,
            chart_type=chart_type,
            title="Extraction has failed or no image detected",
        )

    def _heuristic_extraction(self, element, chart_type: str) -> ChartUnderstandingModel:
        text = element.text
        import re
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        title = lines[0] if lines else "Detected Chart"
        pcts = re.findall(r'(\d+(?:\.\d+)?%)', text)
        categories = [l for l in lines if not re.search(r'\d', l) and len(l) > 3]
        series = []
        if pcts:
            series.append(ChartSeriesModel(
                name="Data",
                values=pcts,
                color="#000000"
            ))

        return ChartUnderstandingModel(
            chart_id=element.element_id,
            chart_type=chart_type,
            title=title,
            insight="Extracted via text fallback due to Vision API limit.",
            categories=categories[:10],
            series=series,
            reconstruction_hints="Vision extraction failed. Reconstruct using text points: " + " ".join(lines[:10])
        )

    def call_vision_llm(self, image_bytes: bytes, slide_context: str = "") -> dict:
        import requests
        import base64
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        
        prompt_suffix = f"\n\nSLIDE_CONTEXT: {slide_context}" if slide_context else ""
        
        # Prioritize local Ollama vision models
        try:
            resp = requests.get(f"{ollama_host}/api/tags", timeout=2)
            if resp.status_code == 200:
                target_model = os.getenv("OLLAMA_VISION_MODEL", "moondream")
                img_b64 = base64.b64encode(image_bytes).decode("ascii")
                
                payload = {
                    "model": target_model,
                    "prompt": _CHART_EXTRACTION_PROMPT + prompt_suffix + "\nOutput MUST be raw JSON.",
                    "images": [img_b64],
                    "stream": False,
                    "format": "json"
                }
                
                print(f"[ChartUnderstanding] Calling local model {target_model}...")
                response = requests.post(f"{ollama_host}/api/generate", json=payload, timeout=300)
                if response.status_code == 200:
                    res_text = response.json().get("response", "").strip()
                    return self._clean_and_load_json(res_text)
        except Exception as e:
            print(f"[ChartUnderstanding] Local Ollama fallback failed: {e}")

        # Cloud fallbacks requiring API keys have been removed. Exclusively relying on local Ollama or offline fallback.
        return None

    def _clean_and_load_json(self, content: str) -> dict:
        content = content.strip()
        
        # Aggressively isolate JSON block to handle LLM babble
        start_idx = content.find('{')
        end_idx = content.rfind('}')
        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            content = content[start_idx:end_idx+1]
        
        try:
            return json.loads(content)
        except Exception as e:
            repaired = self._attempt_json_repair(content)
            if repaired:
                try:
                    return json.loads(repaired)
                except Exception:
                    pass
            raise e

    def _attempt_json_repair(self, s: str) -> Optional[str]:
        s = s.strip()
        if not s:
            return None
        if s.endswith(","):
            s = s[:-1].strip()
            
        braces = 0
        brackets = 0
        in_quote = False
        escaped = False
        
        repaired_chars = []
        for char in s:
            if escaped:
                escaped = False
                repaired_chars.append(char)
                continue
            if char == '\\':
                escaped = True
                repaired_chars.append(char)
                continue
            if char == '"':
                in_quote = not in_quote
            if not in_quote:
                if char == '{':
                    braces += 1
                elif char == '}':
                    braces -= 1
                elif char == '[':
                    brackets += 1
                elif char == ']':
                    brackets -= 1
            repaired_chars.append(char)
            
        repaired = "".join(repaired_chars)
        if in_quote:
            repaired += '"'
        while brackets > 0:
            repaired += ']'
            brackets -= 1
        while braces > 0:
            repaired += '}'
            braces -= 1
            
        return repaired

    def _parse_json_to_model(self, element_id: str, data: dict) -> ChartUnderstandingModel:
        series_models = []
        for s in data.get("series", []):
            series_models.append(ChartSeriesModel(
                name=s.get("name", ""),
                values=s.get("values", []),
                color=s.get("color")
            ))

        axes_models = {}
        for axis_key, axis_data in data.get("axes", {}).items():
            axes_models[axis_key] = ChartAxisModel(
                min=axis_data.get("min"),
                max=axis_data.get("max"),
                ticks=axis_data.get("ticks", []),
                label=axis_data.get("label"),
                axis_type=axis_data.get("axis_type", "linear")
            )

        return ChartUnderstandingModel(
            chart_id=element_id,
            chart_type=data.get("chart_type", "unknown_chart"),
            purpose=data.get("purpose", ""),
            business_question=data.get("business_question", ""),
            insight=data.get("insight", ""),
            orientation=data.get("orientation"),
            stacking=data.get("stacking"),
            title=data.get("title"),
            subtitle=data.get("subtitle"),
            units=data.get("units"),
            categories=data.get("categories", []),
            series=series_models,
            legend=data.get("legend", []),
            legend_mapping=data.get("legend_mapping", {}),
            axes=axes_models,
            data_labels=data.get("data_labels", []),
            data_labels_visible=data.get("data_labels_visible", False),
            reconstruction_hints=data.get("reconstruction_hints")
        )

    def analyze_chart_element(
        self,
        element: DocumentElementModel,
        slide: Optional[SlideModel] = None
    ) -> ChartUnderstandingModel:
        chart_info = ChartUnderstandingModel(chart_id=element.element_id)
        
        # 1. Check if there is native chart data extracted from PPTX
        raw_data = element.metadata.get("chart_data")
        if raw_data:
            chart_info.raw_chart_data = raw_data
            chart_info.title = raw_data.get("title")
            
            # Extract dimensions and measures
            chart_info.dimensions = raw_data.get("categories", [])
            chart_info.measures = [s.get("name", "") for s in raw_data.get("series", [])]
            
            # Detect chart type
            chart_type_str = raw_data.get("chart_type", "").lower()
            if "bar" in chart_type_str or "column" in chart_type_str:
                chart_info.chart_type = "bar_chart"
            elif "line" in chart_type_str:
                chart_info.chart_type = "line_chart"
            elif "pie" in chart_type_str or "doughnut" in chart_type_str:
                chart_info.chart_type = "pie_chart"
            elif "stacked" in chart_type_str:
                chart_info.chart_type = "stacked_chart"
            else:
                chart_info.chart_type = "bar_chart"  # default fallback

            # Analyze trends, anomalies, and comparisons
            self._analyze_numerical_data(raw_data, chart_info)
        
        # 2. Check if we can extract chart reasoning from slide text/summaries
        if slide:
            self._extract_from_slide_context(element, slide, chart_info)
            
        return chart_info

    def _analyze_numerical_data(self, raw_data: Dict[str, Any], chart_info: ChartUnderstandingModel):
        series = raw_data.get("series", [])
        categories = raw_data.get("categories", [])
        
        trends = []
        anomalies = []
        comparisons = []
        
        for s in series:
            name = s.get("name", "Series")
            values = s.get("values", [])
            # filter out non-numeric values
            num_values = [v for v in values if isinstance(v, (int, float))]
            if not num_values:
                continue
                
            # Basic Trend Detection
            if len(num_values) >= 2:
                first = num_values[0]
                last = num_values[-1]
                diff = last - first
                pct = (diff / first * 100) if first != 0 else 0
                if pct > 5:
                    trends.append(f"Series '{name}' shows an upward trend of {pct:.1f}% from {first} to {last}.")
                elif pct < -5:
                    trends.append(f"Series '{name}' shows a downward trend of {abs(pct):.1f}% from {first} to {last}.")
                else:
                    trends.append(f"Series '{name}' remains relatively stable around {first}.")
                    
            # Basic Anomalies (Outliers) Detection
            if len(num_values) >= 3:
                avg = sum(num_values) / len(num_values)
                variance = sum((x - avg) ** 2 for x in num_values) / len(num_values)
                std_dev = variance ** 0.5
                for idx, v in enumerate(num_values):
                    if std_dev > 0 and abs(v - avg) > 2 * std_dev:
                        cat_label = categories[idx] if idx < len(categories) else f"index {idx}"
                        anomalies.append(f"Anomaly detected in '{name}' at {cat_label}: value {v} deviates significantly from the average {avg:.2f}.")

            # Comparisons
            if len(num_values) >= 1:
                max_val = max(num_values)
                min_val = min(num_values)
                max_idx = num_values.index(max_val)
                min_idx = num_values.index(min_val)
                
                max_cat = categories[max_idx] if max_idx < len(categories) else f"index {max_idx}"
                min_cat = categories[min_idx] if min_idx < len(categories) else f"index {min_idx}"
                
                comparisons.append(f"Series '{name}' peaks at {max_cat} with {max_val} and is lowest at {min_cat} with {min_val}.")

        chart_info.trends.extend(trends)
        chart_info.anomalies.extend(anomalies)
        chart_info.comparisons.extend(comparisons)

    def _extract_from_slide_context(self, element: DocumentElementModel, slide: SlideModel, chart_info: ChartUnderstandingModel):
        # Look for keywords in slide text and image summaries
        text_content = []
        if slide.title:
            text_content.append(slide.title)
        for e in slide.elements:
            if e.text:
                text_content.append(e.text)
                
        # Also check image summaries on the element or slide
        img_sum = element.metadata.get("image_summary") or element.metadata.get("summary")
        if img_sum:
            text_content.append(img_sum)
            
        combined_text = "\n".join(text_content).lower()
        
        # Infer chart type if not set
        if chart_info.chart_type == "none":
            if "bar chart" in combined_text or "column chart" in combined_text:
                chart_info.chart_type = "bar_chart"
            elif "line chart" in combined_text or "trend line" in combined_text:
                chart_info.chart_type = "line_chart"
            elif "pie chart" in combined_text or "donut chart" in combined_text:
                chart_info.chart_type = "pie_chart"
            elif "stacked" in combined_text:
                chart_info.chart_type = "stacked_chart"
            elif "dashboard" in combined_text:
                chart_info.chart_type = "dashboard"
            elif "kpi" in combined_text or "key performance indicator" in combined_text:
                chart_info.chart_type = "kpi_card"
            elif element.element_type == "chart":
                chart_info.chart_type = "bar_chart"  # default fallback for chart element
                
        # Extract title from text if missing
        if not chart_info.title:
            match = re.search(r'(?:chart|figure|graph)(?:\s+showing|\s+of)?\s+([^.\n]+)', combined_text)
            if match:
                chart_info.title = match.group(1).strip().capitalize()
            elif slide.title:
                chart_info.title = slide.title
