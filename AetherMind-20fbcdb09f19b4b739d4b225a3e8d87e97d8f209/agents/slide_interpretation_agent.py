import json
import os
from typing import Optional

import requests
from pydantic_ai import Agent

from models.document_model import SemanticFlowModel

_slide_interpretation_agent = None

_RECONSTRUCTION_SYSTEM_PROMPT = (
    "You are an expert management consulting analyst specializing in top-tier (Deloitte, McKinsey, BCG) presentation decks.\n"
    "Your task is NOT just to extract text or summarize. Your goal is to understand the slide exactly as a consultant would "
    "to produce a high-fidelity Semantic Slide Graph and a reconstruction blueprint.\n\n"
    "FOR EVERY SLIDE, IDENTIFY:\n"
    "1. main_business_message: The strategic takeaway.\n"
    "2. primary_insight: The analytical 'so what'.\n"
    "3. narrative_structure: How the story is told (e.g., problem-solution, progression).\n"
    "4. executive_summary: A concise professional summary of the slide's purpose and findings.\n"
    "5. visual_hierarchy: Primary, secondary, and tertiary focuses and the attention flow.\n"
    "6. semantic_sections: Breakdown of the slide into functional sections (e.g., Findings Panel, Recommendation Box).\n"
    "7. charts_and_tables: Detailed purpose, business questions, and insights for every graph/table.\n"
    "8. semantic_text_enrichments: For EVERY distinct text element on the slide, produce a semantic enrichment entry.\n\n"
    "SEMANTIC TEXT ENRICHMENT RULES:\n"
    "For each text element on the slide (title, heading, body paragraph, bullet point, label, badge, footer, etc.):\n"
    "- original_text: The exact verbatim text as it appears on the slide.\n"
    "- semantic_meaning: What this text communicates conceptually — the underlying idea, not the exact words.\n"
    "- communication_goal: Why this text exists — what it is trying to achieve (e.g., 'introduce the topic', 'provide evidence', 'call to action').\n"
    "- educational_intent: What the reader should learn or understand from this text.\n"
    "- tone: The tone of the text (e.g., 'professional', 'instructional', 'persuasive', 'neutral').\n"
    "- hierarchy_role: The structural role (e.g., 'title', 'heading', 'subheading', 'body', 'bullet', 'label', 'footer', 'badge').\n"
    "- approximate_word_count: The word count of the original text.\n\n"
    "The semantic enrichment is used so that another LLM can REWRITE the text in different words while preserving:\n"
    "- The same meaning and educational intent\n"
    "- The same tone and reading difficulty\n"
    "- Approximately the same text length (so it fits the same layout)\n"
    "- The same number of bullet points and heading hierarchy\n\n"
    "OUTPUT STYLE EXAMPLE (match this professional depth):\n"
    "slide_intent: 'findings'\n"
    "overall_flow: 'Labor cost fragmentation across divisions reveals significant inefficiency in core procurement processes.'\n"
    "executive_summary: 'Analysis indicates that 45% of FTEs performing HR work are located outside the HR division, creating a risk of efficiency loss.'\n"
    "sections: [\n"
    "  {\n"
    "    \"section_type\": \"findings_panel\",\n"
    "    \"importance\": \"high\",\n"
    "    \"message\": \"Procurement labor cost is $1.35M more than allocated personnel budget.\",\n"
    "    \"supporting_elements\": [\"chart_1\", \"text_box_2\"]\n"
    "  }\n"
    "]\n\n"
    "CRITICAL EXTRACTION RULES:\n"
    "- Think about WHY each element exists on the slide.\n"
    "- Capture all quantitative (numbers, metrics) and qualitative information.\n"
    "- Preserve context, hierarchy, and business intent.\n"
    "- Produce semantic_text_enrichments for EVERY text element — never skip any.\n"
    "- image_generation_prompt must be a visually descriptive, diffusion-optimized prompt (e.g., for DALL-E 3) to recreate the slide's layout, theme, and key text headings. DO NOT include massive lists of exact text or coordinates, as image generators will hallucinate.\n"
)

_JSON_SCHEMA_HINT = (
    "{\n"
    '  "overall_flow": "string (Main Business Message)",\n'
    '  "executive_summary": "string",\n'
    '  "visual_structure": "string",\n'
    '  "slide_intent": "string",\n'
    '  "storytelling_structure": "string (Narrative Structure)",\n'
    '  "sections": [\n'
    '    {\n'
    '      "section_type": "string (e.g., findings_panel, recommendation_box, methodology_summary)",\n'
    '      "importance": "string (high, medium, low)",\n'
    '      "message": "string (The core section message)",\n'
    '      "supporting_elements": ["string (IDs of elements or charts)"]\n'
    '    }\n'
    '  ],\n'
    '  "visual_hierarchy": {"primary_focus": "string", "secondary_focus": "string", "tertiary_focus": "string", "attention_flow": "string"},\n'
    '  "semantic_relationships": [{"source": "string", "target": "string", "relationship_type": "string", "description": "string"}],\n'
    '  "image_generation_prompt": "string (DALL-E Prompt)",\n'
    '  "reading_order": ["string"],\n'
    '  "plain_english_summary": "string",\n'
    '  "step_by_step_explanation": ["string"],\n'
    '  "conceptual_layers": ["string"],\n'
    '  "visual_design_details": ["string"],\n'
    '  "slide_archetype": "string",\n'
    '  "semantic_text_enrichments": [\n'
    '    {\n'
    '      "original_text": "string (Exact verbatim text from the slide)",\n'
    '      "semantic_meaning": "string (What this text communicates conceptually)",\n'
    '      "communication_goal": "string (Why this text exists — its purpose)",\n'
    '      "educational_intent": "string (What the reader should learn)",\n'
    '      "tone": "string (e.g., professional, instructional, persuasive)",\n'
    '      "hierarchy_role": "string (e.g., title, heading, body, bullet, label, footer, badge)",\n'
    '      "approximate_word_count": "integer"\n'
    '    }\n'
    '  ],\n'
    '  "semantic_section_enrichments": [\n'
    '    {\n'
    '      "section_id": "string",\n'
    '      "section_title": "string",\n'
    '      "section_purpose": "string",\n'
    '      "section_importance": "string (high, medium, low)"\n'
    '    }\n'
    '  ],\n'
    '  "charts": [\n'
    '    {\n'
    '      "chart_id": "string",\n'
    '      "purpose": "string",\n'
    '      "business_question": "string",\n'
    '      "insight": "string",\n'
    '      "chart_type": "string",\n'
    '      "data": {} \n'
    '    }\n'
    '  ],\n'
    '  "table_intelligence": [{"table_id": "string", "merged_cells": [], "nested_headers": [], "semantic_roles": {}}]\n'
    "}"
)


def _get_slide_interpretation_agent() -> Agent:
    global _slide_interpretation_agent
    if _slide_interpretation_agent is None:
        _slide_interpretation_agent = Agent(
            model="google:gemini-2.0-flash",
            output_type=SemanticFlowModel,
            system_prompt=_RECONSTRUCTION_SYSTEM_PROMPT,
        )
    return _slide_interpretation_agent


def _element_label_lookup(slide) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for element in slide.elements:
        label = (element.text or "").strip().replace("\n", " ")
        if not label and element.paragraphs:
            label = " ".join(
                p.text.strip() for p in element.paragraphs if p.text
            ).strip()
        lookup[element.element_id] = label or f"[{element.element_id}]"
    return lookup


def _build_reconstruction_context(slide) -> str:
    """Assemble structural extraction data for the interpretation prompt."""
    sections: list[str] = []
    labels = _element_label_lookup(slide)

    if getattr(slide, "diagram_understanding", None):
        du = slide.diagram_understanding
        if du.flow_description:
            sections.append(f"--- Diagram Flow Description ---\n{du.flow_description}")
        if du.summary:
            sections.append(f"--- Diagram Understanding ---\n{du.summary}")
        if du.nodes:
            node_lines = []
            for node in du.nodes:
                text = node.get("text") or labels.get(node.get("element_id", ""), "")
                node_lines.append(
                    f"  - [{node.get('type', 'unknown')}] "
                    f"{labels.get(node.get('element_id', ''), node.get('element_id', ''))}"
                    f"{f': {text}' if text and text != labels.get(node.get('element_id', ''), '') else ''}"
                )
            sections.append("--- Diagram Nodes ---\n" + "\n".join(node_lines))
        if du.edges:
            edge_lines = []
            for edge in du.edges:
                src = labels.get(edge.get("source", ""), edge.get("source", ""))
                tgt = labels.get(edge.get("target", ""), edge.get("target", ""))
                line = f'  - "{src}" → "{tgt}" ({edge.get("type", "unknown")})'
                if edge.get("label"):
                    line += f' [label: {edge["label"]}]'
                edge_lines.append(line)
            sections.append("--- Diagram Edges ---\n" + "\n".join(edge_lines))

    if getattr(slide, "flowchart", None) and slide.flowchart.is_flowchart:
        fc = slide.flowchart
        fc_lines = [
            f"Flowchart: {fc.box_count} box(es), {fc.arrow_count} arrow(s)"
        ]
        for box in fc.boxes:
            text = (box.get("text") or labels.get(box.get("element_id", ""), "")).strip()
            fc_lines.append(f"  Box: {text or box.get('element_id', '')}")
        for rel in fc.relationships:
            src = labels.get(rel.source_element_id, rel.source_element_id)
            tgt = labels.get(rel.target_element_id, rel.target_element_id)
            line = f'  Flow: "{src}" → "{tgt}"'
            if rel.label:
                line += f' [{rel.label}]'
            fc_lines.append(line)
        if fc.reading_order:
            order_labels = [
                labels.get(eid, eid) for eid in fc.reading_order
            ]
            fc_lines.append("  Reading order: " + " → ".join(order_labels))
        sections.append("--- Flowchart Structure ---\n" + "\n".join(fc_lines))

    if getattr(slide, "layout_structure", None):
        layout = slide.layout_structure
        layout_lines = [f"Layout type: {layout.layout_type}"]
        for region in layout.regions or []:
            layout_lines.append(f"  Region '{region.name}': {len(region.element_ids)} element(s)")
        sections.append("--- Layout Regions ---\n" + "\n".join(layout_lines))

    if getattr(slide, "relationships", None):
        connector_rels = [
            r for r in slide.relationships
            if r.relationship_type == "connector"
        ]
        if connector_rels:
            rel_lines = []
            for rel in connector_rels:
                src = labels.get(rel.source_element_id, rel.source_element_id)
                tgt = labels.get(rel.target_element_id, rel.target_element_id)
                line = f'  "{src}" → "{tgt}"'
                if rel.label:
                    line += f' [connector label: {rel.label}]'
                rel_lines.append(line)
            sections.append("--- Connector Relationships ---\n" + "\n".join(rel_lines))

    if getattr(slide, "chart_understandings", None):
        chart_lines = []
        for cu in slide.chart_understandings:
            parts = [f"--- Chart Extraction: {cu.title or 'Untitled'} ---"]
            parts.append(f"  Type: {cu.chart_type}")
            parts.append(f"  Insight: {cu.insight}")
            parts.append(f"  Business Question: {cu.business_question}")
            parts.append(f"  Purpose: {cu.purpose}")
            if cu.categories:
                parts.append(f"  Categories: {', '.join(cu.categories)}")
            if cu.series:
                for s in cu.series:
                    parts.append(f"  Series '{s.name}': {s.values} (color: {s.color})")
            if cu.units:
                parts.append(f"  Units: {cu.units}")
            chart_lines.append("\n".join(parts))
        if chart_lines:
            sections.append("\n\n".join(chart_lines))

    # Element-level visual details
    elem_lines = []
    for element in slide.elements:
        if element.element_type in {"arrow", "connector"}:
            continue
        label = labels.get(element.element_id, element.element_id)
        parts = [f"  - [{element.element_type}] \"{label}\""]
        if hasattr(element, "style") and element.style:
            if element.style.background_color:
                parts.append(f"    fill: {element.style.background_color}")
            if element.style.text_color:
                parts.append(f"    text colour: {element.style.text_color}")
            if element.style.font_name:
                size = f" {element.style.font_size}pt" if element.style.font_size else ""
                parts.append(f"    font: {element.style.font_name}{size}")
            if element.style.bold:
                parts.append("    bold: yes")
        if hasattr(element, "shape_type") and element.shape_type:
            parts.append(f"    shape: {element.shape_type}")
        if hasattr(element, "position") and element.position:
            left_pct = round(100 * element.position.x / 12192000, 1)
            top_pct = round(100 * element.position.y / 6858000, 1)
            w_pct = round(100 * element.position.width / 12192000, 1)
            h_pct = round(100 * element.position.height / 6858000, 1)
            parts.append(f"    position: left {left_pct}%, top {top_pct}%, width {w_pct}%, height {h_pct}%")
        elem_lines.append("\n".join(parts))
    if elem_lines:
        sections.append(
            "--- Element Visual Details (position, style, shape) ---\n"
            + "\n".join(elem_lines)
        )

    return "\n\n".join(sections)


class SlideInterpretationAgent:
    async def interpret_slide(
        self,
        slide,
        image_summaries: str = "",
    ) -> Optional[SemanticFlowModel]:
        text_lines: list[str] = []
        if getattr(slide, "text_points", None):
            for point in slide.text_points:
                text_lines.append(f"  [L{point.level}] {point.text}")
        else:
            for element in slide.elements:
                if element.paragraphs:
                    for para in element.paragraphs:
                        text_lines.append(f"  [L{para.level}] {para.text}")
                elif element.text:
                    text_lines.append(f"  {element.text}")

        slide_text = "\n".join(text_lines) if text_lines else "(no text)"

        hf_info = ""
        if getattr(slide, "header_footer", None):
            hf = slide.header_footer
            hf_parts = []
            if hf.header_text:
                hf_parts.append(f'Header: "{hf.header_text}"')
            if hf.footer_text:
                hf_parts.append(f'Footer: "{hf.footer_text}"')
            if hf.slide_number_text:
                hf_parts.append(f"Slide Number: {hf.slide_number_text}")
            if hf.date_text:
                hf_parts.append(f"Date: {hf.date_text}")
            if hf_parts:
                hf_info = "\n".join(hf_parts)

        context_outline = ""
        if getattr(slide, "context", None) and getattr(slide.context, "outline", None):
            context_outline = slide.context.outline
        elif getattr(slide, "layout_structure", None):
            layout_type = slide.layout_structure.layout_type
            context_outline = f"Layout Type: {layout_type}."

        reconstruction_context = _build_reconstruction_context(slide)

        prompt = f"""\
Slide {slide.slide_number}
Title: {slide.title or '(none)'}
{hf_info or '(no header/footer detected)'}
{slide_text}
{context_outline or '(no layout context)'}
{reconstruction_context or '(no structural extraction data)'}
{image_summaries or '(no image summaries)'}

Produce a reconstruction-oriented SemanticFlowModel. Do not summarize away structure.
The image_generation_prompt must be a concise, DALL-E 3 optimized prompt to recreate this slide.

CRITICAL: You MUST produce a "semantic_text_enrichments" array containing one entry for EVERY
distinct text element on this slide. For each entry, provide:
- original_text: the exact verbatim text
- semantic_meaning: what the text communicates conceptually
- communication_goal: why this text exists on the slide
- educational_intent: what the reader should learn from it
- tone: the text's tone (professional, instructional, etc.)
- hierarchy_role: its structural role (title, heading, body, bullet, label, footer, badge)
- approximate_word_count: the word count of the original text

Also produce "semantic_section_enrichments" for each logical section of the slide.
"""

        enable_summaries = os.getenv("ENABLE_SUMMARIES", "true").lower() in {"1", "true"}
        if not enable_summaries:
            print("[SlideInterpretationAgent] ENABLE_SUMMARIES is false. Bypassing LLM and using rule-based SemanticFlowService.")
            from services.semantic_flow_service import SemanticFlowService
            return SemanticFlowService().analyze_slide(slide, image_summaries=image_summaries)

        # Try Ollama first
        skip_ollama = os.getenv("SKIP_OLLAMA", "false").lower() in {"1", "true"}
        if not skip_ollama:
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            try:
                resp = requests.get(f"{ollama_host}/api/tags", timeout=2)
                if resp.status_code == 200:
                    models = [m["name"] for m in resp.json().get("models", [])]
                    target_model = "llama3.2"
                    if "llama3.2:latest" in models or "llama3.2" in models:
                        target_model = "llama3.2"
                    elif models:
                        target_model = models[0]

                    json_prompt = (
                        f"{prompt}\n\n"
                        "CRITICAL: Return your response ONLY as a raw JSON object matching this schema. "
                        "Do NOT wrap in markdown code blocks. Do NOT include any extra text.\n"
                        f"Schema:\n{_JSON_SCHEMA_HINT}"
                    )

                    payload = {
                        "model": target_model,
                        "prompt": json_prompt,
                        "system": _RECONSTRUCTION_SYSTEM_PROMPT,
                        "stream": False,
                        "format": "json",
                    }
                    print(f"[SlideInterpretationAgent] Using local Ollama model: {target_model}...")
                    response = requests.post(
                        f"{ollama_host}/api/generate",
                        json=payload,
                        timeout=120,
                    )
                    if response.status_code == 200:
                        res_text = response.json().get("response", "").strip()
                        if res_text:
                            parsed = json.loads(res_text)
                            return SemanticFlowModel(**parsed)
            except Exception as e:
                print(f"[SlideInterpretationAgent] Ollama analysis failed: {e}")

        # Cloud fallbacks requiring API keys have been removed. Exclusively relying on local Ollama or rule-based semantic analysis.

        print("[SlideInterpretationAgent] No LLM API succeeded. Using rule-based SemanticFlowService.")
        from services.semantic_flow_service import SemanticFlowService

        return SemanticFlowService().analyze_slide(slide, image_summaries=image_summaries)
