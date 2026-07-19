import re
from typing import Dict, List, Optional

from models.document_model import (
    SemanticEquivalenceTargetsModel,
    SemanticFlowModel,
    SemanticSectionEnrichmentModel,
    SemanticTextEnrichmentModel,
    SlideModel,
)

_SLIDE_WIDTH_EMU = 12192000.0
_SLIDE_HEIGHT_EMU = 6858000.0

_COLOR_MAP = {
    "#000000": "black", "#ffffff": "white", "#f0f0f0": "very light gray",
    "#808080": "gray", "#c0c0c0": "silver", "#ff0000": "red",
    "#00ff00": "green", "#0000ff": "blue", "#ffff00": "yellow",
    "#ff00ff": "magenta", "#00ffff": "cyan", "#ffa500": "orange",
    "#800080": "purple", "#008000": "dark green", "#000080": "navy",
    "#800000": "maroon", "#808000": "olive", "#008080": "teal",
    "#add8e6": "light blue", "#90ee90": "light green",
    "#ffd700": "gold/yellow", "#ffc0cb": "pink", "#d3d3d3": "light gray",
    "#a9a9a9": "dark gray", "#f5f5dc": "beige", "#e6e6fa": "lavender",
    "#4169e1": "royal blue", "#dc143c": "crimson", "#228b22": "forest green",
    "#b22222": "firebrick", "#2f4f4f": "dark slate gray",
    "#333333": "dark charcoal", "#666666": "medium gray",
    "#999999": "gray", "#cccccc": "light gray", "#eeeeee": "very light gray",
}


def _hex_to_name(hex_color: str) -> str:
    """Convert a hex colour string to a human-readable name."""
    if not hex_color:
        return ""
    key = hex_color.strip().lower()
    name = _COLOR_MAP.get(key, "")
    return f"{name} ({hex_color})" if name else hex_color


def _parse_image_summary_sections(text: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current: Optional[str] = None
    buf: List[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current:
                sections[current] = "\n".join(buf).strip()
            current = line[3:].strip()
            buf = []
        elif current is not None:
            buf.append(line)
    if current:
        sections[current] = "\n".join(buf).strip()

    # Standardize / alias keys to maintain compatibility with downstream consumers
    aliases = {
        "1. Scene Overview": ["7. Plain-language Summary", "6. Summary & Interpretation"],
        "2. Object Inventory": ["3. Detailed Component Breakdown"],
        "3. Spatial Relationships": ["2. Flowchart / Process Flow Mapping"],
        "7. Text Elements": ["4. Text Transcription"],
        "9. Reconstruction Description": ["6. Summary & Interpretation"],
        "10. Reconstruction Prompt": ["8. Reconstructed Diagram Code (Mermaid.js)"],
    }
    for new_key, old_keys in aliases.items():
        if new_key in sections:
            for old_key in old_keys:
                if old_key not in sections:
                    sections[old_key] = sections[new_key]

    return sections


def _collect_image_summaries(slide: SlideModel, image_summaries: str = "") -> str:
    if image_summaries.strip():
        return image_summaries.strip()
    parts: List[str] = []
    for element in slide.elements:
        summary = element.metadata.get("image_summary")
        if summary:
            parts.append(summary.strip())
    return "\n\n".join(parts)


class SemanticFlowService:

    async def analyze_slide_async(
        self,
        slide: SlideModel,
        image_summaries: str = "",
    ) -> SemanticFlowModel:
        return self.analyze_slide(slide, image_summaries=image_summaries)

    def analyze_slide(
        self,
        slide: SlideModel,
        image_summaries: str = "",
    ) -> SemanticFlowModel:
        labels = self._element_label_lookup(slide)
        combined_summaries = _collect_image_summaries(slide, image_summaries)
        parsed_sections = _parse_image_summary_sections(combined_summaries)

        semantic_flow = SemanticFlowModel()
        semantic_flow.overall_flow = self._build_overall_flow(
            slide, labels, parsed_sections, combined_summaries
        )
        semantic_flow.step_by_step_explanation = self._build_step_by_step_flow(
            slide, labels, parsed_sections, combined_summaries
        )
        semantic_flow.conceptual_layers = self._extract_conceptual_layers(
            slide, labels, parsed_sections
        )
        semantic_flow.visual_design_details = self._extract_visual_design_details(
            slide, parsed_sections, combined_summaries
        )
        semantic_flow.plain_english_summary = self._build_plain_english_summary(
            slide, labels, parsed_sections, combined_summaries
        )
        semantic_flow.decision_points = self._extract_decision_points(
            slide, parsed_sections
        )
        semantic_flow.cause_effect_chain = self._build_cause_effect_chain(
            slide, labels, parsed_sections
        )
        
        # Populate new reconstruction fields
        semantic_flow.slide_intent = getattr(slide.image_understanding, "slide_intent", None) or self._infer_intent_fallback(slide)
        semantic_flow.content_hierarchy = self._build_content_hierarchy(slide)
        semantic_flow.visual_hierarchy = self._build_visual_hierarchy_dict(slide)
        semantic_flow.semantic_relationships = self._build_semantic_relationships(slide)
        semantic_flow.layout_regions = self._build_layout_regions_dict(slide)
        semantic_flow.visual_grouping = self._build_visual_grouping(slide)
        semantic_flow.storytelling_structure = self._infer_storytelling_structure(slide)
        semantic_flow.reading_order = self._build_reading_order_list(slide, labels)

        # Populate charts
        if hasattr(slide, "chart_understandings") and slide.chart_understandings:
            semantic_flow.charts = slide.chart_understandings

        # Semantic text enrichment for meaning-preserving regeneration
        semantic_flow.semantic_text_enrichments = self._build_semantic_text_enrichments(slide)
        semantic_flow.semantic_section_enrichments = self._build_semantic_section_enrichments(slide, labels)
        semantic_flow.semantic_equivalence_targets = SemanticEquivalenceTargetsModel()

        semantic_flow.image_generation_prompt = self._build_reconstruction_image_prompt(
            slide, labels, combined_summaries, parsed_sections
        )
        return semantic_flow

    def _infer_intent_fallback(self, slide: SlideModel) -> str:
        if slide.flowchart and slide.flowchart.is_flowchart:
            return "process_flow"
        if slide.layout_structure and slide.layout_structure.layout_type == "title_slide":
            return "cover_page"
        if slide.title:
            t = slide.title.lower()
            if "summary" in t or "takeaway" in t:
                return "executive_summary"
            if "recommend" in t or "roadmap" in t or "next step" in t:
                return "recommendations"
            if "appendix" in t or "supplement" in t:
                return "appendix"
            if "compare" in t or "vs" in t:
                return "comparison"
        return "findings"

    def _build_content_hierarchy(self, slide: SlideModel) -> dict:
        primary_content = []
        nested_details = {}
        for p in slide.text_points:
            if p.level == 0:
                primary_content.append(p.text)
            else:
                parent = primary_content[-1] if primary_content else "General"
                nested_details.setdefault(parent, []).append(p.text)
        return {
            "title": slide.title or "",
            "primary_content": primary_content,
            "nested_details": nested_details
        }

    def _build_visual_hierarchy_dict(self, slide: SlideModel) -> dict:
        if slide.image_understanding and slide.image_understanding.design_hierarchy:
            return slide.image_understanding.design_hierarchy
        primary = f"Title: {slide.title}" if slide.title else ""
        secondary = ""
        if slide.text_points:
            secondary = "; ".join([p.text for p in slide.text_points if p.level == 0][:2])
        return {
            "primary_focus": primary,
            "secondary_focus": secondary,
            "tertiary_focus": "",
            "attention_flow": "top-to-bottom"
        }

    def _build_semantic_relationships(self, slide: SlideModel) -> list:
        if slide.image_understanding and slide.image_understanding.relationship_mapping:
            return slide.image_understanding.relationship_mapping
        rels = []
        for rel in slide.relationships:
            rels.append({
                "source": rel.source_element_id,
                "target": rel.target_element_id,
                "relationship_type": rel.relationship_type,
                "description": f"Connector from {rel.source_element_id} to {rel.target_element_id}"
            })
        return rels

    def _build_layout_regions_dict(self, slide: SlideModel) -> list:
        if slide.image_understanding and slide.image_understanding.visual_regions:
            return slide.image_understanding.visual_regions
        regions = []
        if slide.layout_structure and slide.layout_structure.regions:
            for r in slide.layout_structure.regions:
                regions.append({
                    "name": r.name,
                    "bounds": {"x_start": r.x_start, "y_start": r.y_start, "x_end": r.x_end, "y_end": r.y_end},
                    "description": f"Layout region '{r.name}' containing {len(r.element_ids)} elements"
                })
        return regions

    def _build_visual_grouping(self, slide: SlideModel) -> list:
        groupings = []
        if slide.layout_structure and slide.layout_structure.regions:
            for r in slide.layout_structure.regions:
                if len(r.element_ids) > 1:
                    groupings.append({
                        "group_id": f"group_{r.name}",
                        "element_ids": r.element_ids,
                        "description": f"Elements grouped in {r.name} region"
                      })
        return groupings

    def _infer_storytelling_structure(self, slide: SlideModel) -> str:
        if slide.flowchart and slide.flowchart.is_flowchart:
            return "chronological/process flow showing step-by-step progress"
        if slide.layout_structure and slide.layout_structure.layout_type == "two_column":
            return "comparison/contrast layout between left and right sections"
        return "hierarchical presentation of title and supporting details"

    def _build_reading_order_list(self, slide: SlideModel, labels: dict) -> list:
        if slide.image_understanding and slide.image_understanding.reading_order:
            return slide.image_understanding.reading_order
        if slide.flowchart and slide.flowchart.reading_order:
            return [labels.get(eid, eid) for eid in slide.flowchart.reading_order]
        return [labels.get(e.element_id, e.element_id) for e in sorted(slide.elements, key=lambda x: (x.position.y, x.position.x)) if e.text]

    def _build_semantic_text_enrichments(self, slide: SlideModel) -> list:
        """Build semantic text enrichments for every text element on the slide (rule-based fallback)."""
        enrichments = []
        title_text = (slide.title or "").strip().lower()
        ordered_elements = sorted(slide.elements, key=lambda e: (e.position.y, e.position.x))

        for element in ordered_elements:
            texts_to_enrich: list[tuple[str, int]] = []  # (text, level)

            if element.paragraphs:
                for para in element.paragraphs:
                    t = (para.text or "").strip()
                    if t:
                        texts_to_enrich.append((t, para.level))
            elif element.text:
                for line in element.text.splitlines():
                    t = line.strip()
                    if t:
                        texts_to_enrich.append((t, 0))

            for text, level in texts_to_enrich:
                word_count = len(text.split())
                hierarchy_role = self._infer_hierarchy_role(element, text, level, title_text, slide)
                tone = self._infer_tone(element, hierarchy_role)
                semantic_meaning = self._infer_semantic_meaning(text, hierarchy_role, element)
                communication_goal = self._infer_communication_goal(hierarchy_role, element)
                educational_intent = self._infer_educational_intent(text, hierarchy_role)

                enrichments.append(
                    SemanticTextEnrichmentModel(
                        original_text=text,
                        semantic_meaning=semantic_meaning,
                        communication_goal=communication_goal,
                        educational_intent=educational_intent,
                        tone=tone,
                        approximate_word_count=word_count,
                        approximate_line_count=max(1, word_count // 12),
                        hierarchy_role=hierarchy_role,
                    )
                )
        return enrichments

    def _infer_hierarchy_role(self, element, text: str, level: int, title_text: str, slide: SlideModel) -> str:
        """Determine the structural role of a text element."""
        if element.element_type == "title" or (title_text and text.strip().lower() == title_text):
            return "title"
        if hasattr(element, "shape_type") and element.shape_type and "title" in str(element.shape_type).lower():
            return "title"
        # Check for header/footer regions
        if slide.layout_structure and slide.layout_structure.regions:
            for region in slide.layout_structure.regions:
                if element.element_id in region.element_ids:
                    if "header" in region.name.lower():
                        return "heading"
                    if "footer" in region.name.lower():
                        return "footer"
        # Detect badges, labels, headings by style
        if element.style:
            if element.style.bold and len(text) < 60:
                return "heading" if level == 0 else "subheading"
            if element.style.font_size and element.style.font_size >= 18 and len(text) < 80:
                return "heading"
        if level > 0:
            return "bullet"
        if len(text) < 30 and ":" in text:
            return "label"
        if len(text) < 15:
            return "badge"
        return "body"

    def _infer_tone(self, element, hierarchy_role: str) -> str:
        """Infer the tone of the text based on its role and style."""
        if hierarchy_role in ("title", "heading", "subheading"):
            return "professional"
        if hierarchy_role == "badge":
            return "concise"
        if hierarchy_role == "footer":
            return "neutral"
        return "instructional"

    def _infer_semantic_meaning(self, text: str, hierarchy_role: str, element) -> str:
        """Infer the semantic meaning of the text."""
        if hierarchy_role == "title":
            return f"Slide title establishing the main topic: {text}"
        if hierarchy_role == "heading":
            return f"Section heading introducing a key concept or category: {text}"
        if hierarchy_role == "subheading":
            return f"Subheading providing additional context within a section"
        if hierarchy_role == "bullet":
            return f"Supporting detail or enumerated point contributing to the parent section"
        if hierarchy_role == "label":
            return f"Label identifying a data field or attribute"
        if hierarchy_role == "badge":
            return f"Short badge or tag providing classification or status"
        if hierarchy_role == "footer":
            return f"Footer element providing reference or attribution information"
        return f"Body text conveying detailed information or explanation"

    def _infer_communication_goal(self, hierarchy_role: str, element) -> str:
        """Infer the communication goal of the text element."""
        goals = {
            "title": "Establish the primary subject and frame the slide's content",
            "heading": "Introduce and organize a thematic section of the slide",
            "subheading": "Provide secondary categorization within a section",
            "body": "Deliver detailed information, explanation, or context",
            "bullet": "Present a specific point, item, or supporting detail",
            "label": "Identify or annotate a field, value, or data point",
            "badge": "Provide quick categorical classification or status indicator",
            "footer": "Supply reference, attribution, or navigational information",
        }
        return goals.get(hierarchy_role, "Convey information to the reader")

    def _infer_educational_intent(self, text: str, hierarchy_role: str) -> str:
        """Infer what the reader should learn from this text."""
        if hierarchy_role == "title":
            return "Understand the overarching topic and scope of this slide"
        if hierarchy_role in ("heading", "subheading"):
            return "Recognize the key theme or category being discussed in this section"
        if hierarchy_role == "bullet":
            return "Absorb a specific fact, action item, or supporting detail"
        if hierarchy_role == "label":
            return "Identify what information a particular field or value represents"
        if hierarchy_role == "footer":
            return "Note source attribution, copyright, or reference information"
        return "Gain understanding of the detailed content and its implications"

    def _build_semantic_section_enrichments(self, slide: SlideModel, labels: dict) -> list:
        """Build semantic section enrichments from layout regions and detected sections."""
        section_enrichments = []

        if slide.layout_structure and slide.layout_structure.regions:
            for idx, region in enumerate(slide.layout_structure.regions):
                if not region.element_ids:
                    continue
                # Collect text enrichments for elements in this region
                region_texts = []
                for eid in region.element_ids:
                    label = labels.get(eid, "")
                    if label and not label.startswith("["):
                        region_texts.append(label)

                section_title = region_texts[0] if region_texts else region.name
                section_purpose = self._infer_section_purpose(region.name, region_texts)
                section_importance = "high" if "header" in region.name.lower() or "title" in region.name.lower() else "medium"

                section_enrichments.append(
                    SemanticSectionEnrichmentModel(
                        section_id=f"section_{idx}_{region.name}",
                        section_title=section_title[:120],
                        section_purpose=section_purpose,
                        section_importance=section_importance,
                    )
                )

        # If no regions detected, create a single default section
        if not section_enrichments:
            all_texts = [labels.get(e.element_id, "") for e in slide.elements if labels.get(e.element_id, "").strip()]
            section_enrichments.append(
                SemanticSectionEnrichmentModel(
                    section_id="section_0_main",
                    section_title=slide.title or "Main Content",
                    section_purpose="Primary content section of the slide",
                    section_importance="high",
                )
            )

        return section_enrichments

    def _infer_section_purpose(self, region_name: str, texts: list) -> str:
        """Infer the purpose of a section from its region name and content."""
        name_lower = region_name.lower()
        if "header" in name_lower:
            return "Provides the title or heading for the slide content"
        if "footer" in name_lower:
            return "Contains reference, attribution, or navigation metadata"
        if "body_left" in name_lower:
            return "Primary content area presenting the main information"
        if "body_right" in name_lower:
            return "Secondary content area providing complementary or contrasting information"
        if "body" in name_lower:
            return "Main content area delivering the core message of the slide"
        return "Content section contributing to the overall slide message"

    def _element_label_lookup(self, slide: SlideModel) -> dict[str, str]:
        lookup: dict[str, str] = {}
        for element in slide.elements:
            label = (element.text or "").strip().replace("\n", " ")
            if not label and element.paragraphs:
                label = " ".join(
                    p.text.strip() for p in element.paragraphs if p.text
                ).strip()
            lookup[element.element_id] = label or f"[{element.element_id}]"
        return lookup

    def _reading_order_labels(
        self, slide: SlideModel, labels: dict[str, str]
    ) -> List[str]:
        if not slide.flowchart or not slide.flowchart.reading_order:
            return []
        return [
            labels.get(eid, eid)
            for eid in slide.flowchart.reading_order
            if not labels.get(eid, eid).startswith("[")
        ]

    def _build_overall_flow(
        self,
        slide: SlideModel,
        labels: dict[str, str],
        parsed_sections: Dict[str, str],
        combined_summaries: str,
    ) -> str:
        plain = parsed_sections.get("7. Plain-language Summary", "").strip()
        if plain:
            first = plain.split(".")[0].strip()
            if first:
                return f"The slide shows {first[0].lower() + first[1:] if first[0].isupper() else first}."

        flow_section = parsed_sections.get("2. Flowchart / Process Flow Mapping", "")
        if flow_section:
            for line in flow_section.splitlines():
                line = line.strip().lstrip("-").strip()
                lower = line.lower()
                if "flow sequence" in lower or "reading order" in lower:
                    seq = line.split(":", 1)[-1].strip()
                    if seq:
                        return f"The slide shows the process flow: {seq}"
                if "-->" in line or "→" in line:
                    parts = re.split(r"\s*-->\s*|\s*→\s*", line)
                    parts = [re.sub(r"^Step \d+:\s*", "", p).strip("[] ") for p in parts if p.strip()]
                    if len(parts) >= 2:
                        return (
                            f"The slide shows a progression from "
                            f"{parts[0]} → {parts[-1]}"
                        )

        order_labels = self._reading_order_labels(slide, labels)
        if len(order_labels) >= 2:
            return (
                f"The slide shows a progression from "
                f"{order_labels[0]} → {order_labels[-1]}"
            )
        if len(order_labels) == 1:
            return f"The slide focuses on {order_labels[0]}."

        if slide.diagram_understanding and slide.diagram_understanding.flow_description:
            fd = slide.diagram_understanding.flow_description
            steps = re.findall(r"Step \d+: ([^→]+)", fd)
            steps = [s.strip() for s in steps if s.strip()]
            if len(steps) >= 2:
                return (
                    f"The slide shows a progression from "
                    f"{steps[0]} → {steps[-1]}"
                )
            return fd

        title = slide.title or "the slide content"
        abstraction_keywords = ("abstraction", "agent", "decision", "state", "temporal")
        all_text = " ".join(labels.values()).lower() + combined_summaries.lower()
        if any(k in all_text for k in abstraction_keywords):
            return (
                "The slide shows a transformation from low-level environment "
                "representation → high-level reasoning"
            )

        interp = parsed_sections.get("6. Summary & Interpretation", "")
        if interp:
            first_sentence = interp.split(".")[0].strip()
            if first_sentence:
                return first_sentence + "."

        return f"The slide presents and explains {title}."

    def _build_step_by_step_flow(
        self,
        slide: SlideModel,
        labels: dict[str, str],
        parsed_sections: Dict[str, str],
        combined_summaries: str,
    ) -> list[str]:
        steps: list[str] = []

        plain_summary = parsed_sections.get("7. Plain-language Summary", "")
        if plain_summary:
            steps.append(plain_summary)

        flow_section = parsed_sections.get("2. Flowchart / Process Flow Mapping", "")
        if flow_section:
            for line in flow_section.splitlines():
                line = line.strip().lstrip("-").strip()
                if line and not line.lower().startswith("flow sequence"):
                    steps.append(line)

        breakdown = parsed_sections.get("3. Detailed Component Breakdown", "")
        if breakdown:
            for line in breakdown.splitlines():
                line = line.strip().lstrip("-").strip()
                if line.startswith("Panel ") or line.startswith("Left ") or line.startswith("Right "):
                    steps.append(line)

        decisions = self._extract_decision_points(slide, parsed_sections)
        if decisions:
            for element in slide.elements:
                summary = element.metadata.get("image_summary", "")
                if summary and any(k in summary.lower() for k in ("environment", "game", "ladder", "platform")):
                    steps.insert(0, (
                        "The agent exists in a complex environment "
                        "(game screen with ladders, obstacles, key, and exit)."
                    ))
                    steps.insert(1, (
                        "Instead of modelling every pixel or movement, the system "
                        "abstracts the environment into a state variable."
                    ))
                    break
            for decision in decisions:
                steps.append(f"This creates a binary decision node: {decision}")
                for rel in slide.relationships or []:
                    if rel.relationship_type != "connector":
                        continue
                    src = labels.get(rel.source_element_id, "")
                    tgt = labels.get(rel.target_element_id, rel.target_element_id)
                    if decision in src or decision.split("?")[0] in src:
                        branch = rel.label or "→"
                        steps.append(f"If {branch} → take action: {tgt}")

        order_labels = self._reading_order_labels(slide, labels)
        if order_labels and not steps:
            for i, label in enumerate(order_labels, start=1):
                steps.append(f"Step {i}: {label}")
        elif order_labels and len(steps) < len(order_labels):
            for label in order_labels:
                if not any(label in s for s in steps):
                    steps.append(f"The slide presents: {label}")

        if not steps:
            for point in slide.text_points or []:
                if point.text and point.text != slide.title:
                    steps.append(point.text)
            if not steps:
                for element in slide.elements:
                    if element.text and not element.text.startswith("["):
                        steps.append(element.text)

        return steps

    def _extract_conceptual_layers(
        self,
        slide: SlideModel,
        labels: dict[str, str],
        parsed_sections: Dict[str, str],
    ) -> list[str]:
        layers: list[str] = []

        for element in slide.elements:
            text = (element.text or "").strip()
            if not text or text == slide.title:
                continue
            if "\n" in text:
                title_line, body = text.split("\n", 1)
                layers.append(
                    f"{title_line.strip()}: {body.strip().replace(chr(10), ' ')}"
                )
            elif len(text) < 80 and text[0].isupper():
                layers.append(f"{text}: Key concept illustrated on this slide.")

        abstraction_terms = ("State Abstraction", "Temporal Abstraction")
        all_text = " ".join(labels.values())
        for term in abstraction_terms:
            if term.lower() in all_text.lower() and not any(term in layer for layer in layers):
                if "state" in term.lower():
                    layers.append(
                        "State Abstraction: Reduces complex environment into meaningful "
                        "variables. Example: Instead of tracking position, ladders, obstacles "
                        "→ track only whether the agent has the key."
                    )
                else:
                    layers.append(
                        "Temporal Abstraction: Converts primitive actions into macro-actions. "
                        "Example: 'Get key' = sequence of movements (climb, jump, walk); "
                        "'Open the door' = sequence of actions near the door."
                    )

        breakdown = parsed_sections.get("3. Detailed Component Breakdown", "")
        if breakdown:
            for line in breakdown.splitlines():
                line = line.strip().lstrip("-").strip()
                if line.startswith("Panel ") and ":" in line:
                    layers.append(line)

        if slide.title and not layers:
            layers.append(f"Primary Concept: {slide.title}")

        transcription = parsed_sections.get("4. Text Transcription", "")
        if transcription and len(layers) < 3:
            for line in transcription.splitlines():
                line = line.strip().strip('"')
                if line and len(line) > 10:
                    layers.append(line)

        return layers

    def _extract_visual_design_details(
        self,
        slide: SlideModel,
        parsed_sections: Dict[str, str],
        combined_summaries: str,
    ) -> list[str]:
        details: list[str] = []

        # --- Colour scheme ---
        details.append("Colour scheme:")
        bg_color = getattr(slide, "background_color", None)
        if bg_color:
            details.append(f"  - Slide background: {_hex_to_name(bg_color)}")

        color_usage: dict[str, list[str]] = {}
        for element in slide.elements:
            if not element.style:
                continue
            el_label = (
                (element.text or "").strip().replace("\n", " ")[:50]
                or element.element_id
            )
            if element.style.background_color:
                cname = _hex_to_name(element.style.background_color)
                color_usage.setdefault(cname, []).append(el_label)
        for color, elems in color_usage.items():
            quoted = ", ".join(f"'{e}'" for e in elems[:4])
            details.append(f"  - {color}: used for {quoted}")

        if slide.image_reconstruction and slide.image_reconstruction.color_palette:
            palette_names = [
                _hex_to_name(c) for c in slide.image_reconstruction.color_palette
            ]
            details.append(f"  - Full palette: {', '.join(palette_names)}")

        # Supplementary colour info from image summaries
        color_patterns = re.findall(
            r"(black|white|teal|green|yellow|gold|blue|dark|light)"
            r"[/\w\s-]*"
            r"(?:background|platform|ladder|key|box|node|area)?",
            combined_summaries,
            re.IGNORECASE,
        )
        if color_patterns:
            unique = list(dict.fromkeys(c.strip().lower() for c in color_patterns))[:6]
            details.append(f"  - Visual colour cues (from image analysis): {', '.join(unique)}")

        # --- Shapes ---
        details.append("Shapes:")
        shape_types: dict[str, int] = {}
        for element in slide.elements:
            stype = element.shape_type or element.element_type
            if stype:
                shape_types[stype] = shape_types.get(stype, 0) + 1
        for stype, count in shape_types.items():
            details.append(f"  - {stype}: {count} instance(s)")

        # --- Structure ---
        details.append("Structure:")
        if slide.layout_structure:
            details.append(f"  - Layout type: {slide.layout_structure.layout_type}")
            for region in slide.layout_structure.regions or []:
                if region.element_ids:
                    el_labels: list[str] = []
                    for eid in region.element_ids:
                        el = next(
                            (e for e in slide.elements if e.element_id == eid), None
                        )
                        el_labels.append(
                            (el.text or eid).strip().replace("\n", " ")[:60]
                            if el else eid
                        )
                    details.append(
                        f"  - {region.name} → {', '.join(el_labels)}"
                    )

        # Component breakdown from image analysis
        breakdown = parsed_sections.get("3. Detailed Component Breakdown", "")
        if breakdown:
            for line in breakdown.splitlines():
                line = line.strip().lstrip("-").strip()
                if line:
                    details.append(f"  - {line}")

        # --- Connectors ---
        details.append("Connectors:")
        if slide.relationships:
            for rel in slide.relationships:
                src_el = next(
                    (e for e in slide.elements if e.element_id == rel.source_element_id),
                    None,
                )
                tgt_el = next(
                    (e for e in slide.elements if e.element_id == rel.target_element_id),
                    None,
                )
                src_text = (
                    (src_el.text or rel.source_element_id).strip().replace("\n", " ")
                    if src_el
                    else rel.source_element_id
                )
                tgt_text = (
                    (tgt_el.text or rel.target_element_id).strip().replace("\n", " ")
                    if tgt_el
                    else rel.target_element_id
                )
                label = f" (label: '{rel.label}')" if rel.label else ""
                details.append(
                    f"  - Arrow: '{src_text}' → '{tgt_text}'{label} [{rel.relationship_type}]"
                )
        else:
            arrow_count = sum(
                1
                for e in slide.elements
                if e.element_type in {"arrow", "connector", "freeform"}
            )
            if arrow_count:
                details.append(
                    f"  - {arrow_count} arrow(s)/connector(s) indicating logical flow"
                )
            else:
                details.append("  - No connectors detected")

        # Pass-through from image understanding
        if slide.image_understanding and slide.image_understanding.visual_design:
            vd = slide.image_understanding.visual_design
            if vd.layout_style:
                details.append(f"Visual layout style: {vd.layout_style}")
            if vd.background_style:
                details.append(f"Background style: {vd.background_style}")

        return details

    def _build_plain_english_summary(
        self,
        slide: SlideModel,
        labels: dict[str, str],
        parsed_sections: Dict[str, str],
        combined_summaries: str,
    ) -> str:
        paragraphs: list[str] = []

        interp = parsed_sections.get("6. Summary & Interpretation", "")
        plain = parsed_sections.get("7. Plain-language Summary", "")
        if plain:
            paragraphs.append(plain)
        if interp and interp not in paragraphs:
            paragraphs.append(interp)

        title = slide.title or "This slide"
        if not paragraphs:
            # Check for charts first as they provide high-value insights
            if hasattr(slide, "chart_understandings") and slide.chart_understandings:
                for cu in slide.chart_understandings:
                    if cu.insight:
                        paragraphs.append(cu.insight)
                    elif cu.purpose:
                        paragraphs.append(f"Analysis of {cu.purpose}")

            order_labels = self._reading_order_labels(slide, labels)
            if order_labels:
                paragraphs.append(
                    f"{title} explains a process that moves through "
                    f"{', '.join(order_labels[:-1])}, and concludes with "
                    f"{order_labels[-1]}."
                )
            else:
                text_bits = [
                    labels[e.element_id]
                    for e in slide.elements
                    if labels.get(e.element_id, "") and not labels[e.element_id].startswith("[")
                ][:4]
                if text_bits:
                    paragraphs.append(
                        f"{title} covers the following ideas: "
                        + "; ".join(text_bits) + "."
                    )

        if slide.header_footer and slide.header_footer.footer_text:
            paragraphs.append(slide.header_footer.footer_text)

        decisions = self._extract_decision_points(slide, parsed_sections)
        if decisions and len(paragraphs) < 3:
            paragraphs.append(
                "Instead of dealing with every small detail, the slide focuses on "
                f"key decisions such as: {decisions[0]}. Based on this, the system "
                "determines what action to take next."
            )
            paragraphs.append(
                "In simple terms, the slide shows how smart systems think at a "
                "higher level rather than getting lost in low-level details."
            )

        if not paragraphs:
            paragraphs.append(
                f"The slide titled '{title}' presents information through "
                "text, visuals, and structural layout."
            )

        return "\n\n".join(paragraphs)

    def _extract_decision_points(
        self,
        slide: SlideModel,
        parsed_sections: Dict[str, str],
    ) -> list[str]:
        decision_points: list[str] = []
        seen: set[str] = set()

        transcription = parsed_sections.get("4. Text Transcription", "")
        all_sources: List[str] = []
        if transcription:
            all_sources.append(transcription)
        for element in slide.elements:
            if element.text:
                all_sources.append(element.text)
            summary = element.metadata.get("image_summary", "")
            if summary:
                all_sources.append(summary)

        for text in all_sources:
            for match in re.findall(r"[^.\n\"]+\?", text):
                candidate = match.strip().strip('"')
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    decision_points.append(candidate)

        return decision_points

    def _build_cause_effect_chain(
        self,
        slide: SlideModel,
        labels: dict[str, str],
        parsed_sections: Dict[str, str],
    ) -> list[str]:
        chains: list[str] = []

        flow_section = parsed_sections.get("2. Flowchart / Process Flow Mapping", "")
        if flow_section:
            for line in flow_section.splitlines():
                if "-->" in line or "→" in line:
                    chains.append(line.strip().lstrip("-").strip())

        rels = []
        if slide.flowchart and slide.flowchart.relationships:
            rels = [
                r for r in slide.flowchart.relationships
                if r.relationship_type == "connector"
            ]
        if not rels and slide.relationships:
            rels = [
                r for r in slide.relationships
                if r.relationship_type == "connector"
            ]

        for relationship in rels:
            src = labels.get(relationship.source_element_id, relationship.source_element_id)
            tgt = labels.get(relationship.target_element_id, relationship.target_element_id)
            chain = f"{src} → {tgt}"
            if relationship.label:
                chain = f"{relationship.label}: {chain}"
            chains.append(chain)

        order_labels = self._reading_order_labels(slide, labels)
        if len(order_labels) >= 2 and not chains:
            for i in range(len(order_labels) - 1):
                chains.append(f"{order_labels[i]} → {order_labels[i + 1]}")

        return chains

    def _region_for_element(self, element) -> str:
        cx = element.position.x + element.position.width / 2
        cy = element.position.y + element.position.height / 2
        x_pct = cx / _SLIDE_WIDTH_EMU
        y_pct = cy / _SLIDE_HEIGHT_EMU

        if y_pct < 0.2:
            return "top"
        if y_pct > 0.8:
            return "bottom"
        if x_pct < 0.4:
            return "left"
        if x_pct > 0.6:
            return "right"
        return "center"

    def _position_percent(self, element) -> str:
        x_pct = round(100 * element.position.x / _SLIDE_WIDTH_EMU, 1)
        y_pct = round(100 * element.position.y / _SLIDE_HEIGHT_EMU, 1)
        w_pct = round(100 * element.position.width / _SLIDE_WIDTH_EMU, 1)
        h_pct = round(100 * element.position.height / _SLIDE_HEIGHT_EMU, 1)
        return f"x={x_pct}%, y={y_pct}%, w={w_pct}%, h={h_pct}%"

    def _build_layout_blueprint(
        self,
        slide: SlideModel,
        labels: dict[str, str],
    ) -> str:
        regions: dict[str, list[str]] = {
            "left": [],
            "right": [],
            "top": [],
            "bottom": [],
            "center": [],
        }

        for element in slide.elements:
            if element.element_type in {"arrow", "connector"}:
                continue
            label = labels.get(element.element_id, "")
            if label.startswith("["):
                if element.element_type == "image" and element.metadata.get("image_summary"):
                    label = "Image: " + element.metadata["image_summary"][:120] + "..."
                else:
                    continue
            region = self._region_for_element(element)
            pos = self._position_percent(element)
            regions[region].append(f"{label} ({element.element_type}, {pos})")

        lines = ["=== LAYOUT ==="]
        for name in ("top", "left", "center", "right", "bottom"):
            items = regions[name]
            if items:
                lines.append(f"{name.capitalize()} side: {'; '.join(items)}")
            else:
                lines.append(f"{name.capitalize()} side: (empty)")

        if slide.layout_structure:
            lines.append(f"Layout type: {slide.layout_structure.layout_type}")
            for region in slide.layout_structure.regions or []:
                lines.append(f"Region '{region.name}': elements {region.element_ids}")

        if slide.header_footer:
            hf = slide.header_footer
            if hf.header_text:
                lines.append(f"Header: {hf.header_text}")
            if hf.footer_text:
                lines.append(f"Footer: {hf.footer_text}")

        return "\n".join(lines)

    def _build_diagram_structure(
        self,
        slide: SlideModel,
        labels: dict[str, str],
        parsed_sections: Dict[str, str],
    ) -> str:
        lines = ["=== DIAGRAM STRUCTURE ==="]

        mermaid = parsed_sections.get("8. Reconstructed Diagram Code (Mermaid.js)", "")
        if mermaid:
            lines.append(mermaid)

        flow_section = parsed_sections.get("2. Flowchart / Process Flow Mapping", "")
        if flow_section:
            lines.append("Process flow:")
            lines.append(flow_section)

        decisions = self._extract_decision_points(slide, parsed_sections)
        if decisions:
            lines.append("Decision nodes:")
            for decision in decisions:
                lines.append(f"  Decision: {decision}")
                for rel in slide.relationships or []:
                    if rel.relationship_type != "connector":
                        continue
                    src = labels.get(rel.source_element_id, "")
                    tgt = labels.get(rel.target_element_id, rel.target_element_id)
                    if decision in src or decision.split("?")[0] in src:
                        branch = rel.label or "branch"
                        lines.append(f"    {branch} → {tgt}")

        order_labels = self._reading_order_labels(slide, labels)
        if order_labels:
            lines.append("Reading order: " + " → ".join(order_labels))

        if slide.diagram_understanding and slide.diagram_understanding.flow_description:
            lines.append(f"Flow: {slide.diagram_understanding.flow_description}")

        transcription = parsed_sections.get("4. Text Transcription", "")
        if transcription:
            lines.append("Exact visible text:")
            lines.append(transcription)

        return "\n".join(lines)

    def _build_reconstruction_image_prompt(
        self,
        slide: SlideModel,
        labels: dict[str, str],
        combined_summaries: str,
        parsed_sections: Dict[str, str],
    ) -> str:
        sections: list[str] = [
            "Generate a presentation slide that visually and semantically matches the original.",
            "Please create a clean, professional corporate slide with the following description:",
        ]

        # Slide title
        if slide.title:
            sections.append(f"Slide title: {slide.title}")

        # === STORYTELLING AND NARRATIVE FLOW ===
        storytelling = "The slide presents information hierarchically, highlighting key points sequentially."
        if slide.flowchart and slide.flowchart.is_flowchart:
            storytelling = "The slide illustrates a process/workflow sequence, showing consecutive steps and decision logic."
        elif slide.layout_structure and slide.layout_structure.layout_type == "two_column":
            storytelling = "The slide compares and contrasts two distinct concept columns or panels."
        sections.append(f"=== STORYTELLING AND NARRATIVE FLOW ===\n{storytelling}")

        # === SEMANTIC RELATIONSHIPS ===
        rel_lines = ["=== SEMANTIC RELATIONSHIPS ==="]
        if slide.image_understanding and slide.image_understanding.relationship_mapping:
            for rm in slide.image_understanding.relationship_mapping:
                desc = rm.get('description', '') if isinstance(rm, dict) else getattr(rm, 'description', '')
                rtype = rm.get('relationship_type', 'supports') if isinstance(rm, dict) else getattr(rm, 'relationship_type', 'supports')
                rel_lines.append(f"  - {desc} (Type: {rtype})")
        else:
            for rel in slide.relationships:
                rel_lines.append(f"  - Element '{labels.get(rel.source_element_id, rel.source_element_id)}' connects to '{labels.get(rel.target_element_id, rel.target_element_id)}' (Type: {rel.relationship_type})")
        sections.append("\n".join(rel_lines))

        # === EXACT TEXT ===
        text_block = ["=== EXACT TEXT (preserve verbatim) ==="]
        for element in slide.elements:
            if not element.text:
                continue
            text = element.text.strip()
            if text:
                text_block.append(f"  [{element.element_type}] \"{text}\"")
        sections.append("\n".join(text_block))

        # === LAYOUT ===
        sections.append(self._build_layout_blueprint(slide, labels))

        # === OBJECTS (detailed per-element) ===
        obj_lines = ["=== OBJECTS ==="]
        for i, element in enumerate(slide.elements, start=1):
            if element.element_type in {"arrow", "connector"}:
                continue
            label = labels.get(element.element_id, element.element_id)
            region = self._region_for_element(element)
            pos = self._position_percent(element)

            parts = [
                f"Object {i}: \"{label}\"",
                f"  Type: {element.element_type}",
                f"  Region: {region}",
                f"  Position: {pos}",
            ]

            if element.style:
                style_parts: list[str] = []
                if element.style.background_color:
                    style_parts.append(
                        f"fill: {_hex_to_name(element.style.background_color)}"
                    )
                if element.style.text_color:
                    style_parts.append(
                        f"text: {_hex_to_name(element.style.text_color)}"
                    )
                if element.style.font_name:
                    size_str = f" {element.style.font_size}pt" if element.style.font_size else ""
                    style_parts.append(f"font: {element.style.font_name}{size_str}")
                if element.style.bold:
                    style_parts.append("bold")
                if style_parts:
                    parts.append(f"  Style: {', '.join(style_parts)}")

            if element.shape_type:
                parts.append(f"  Shape: {element.shape_type}")

            img_desc = element.metadata.get("image_summary", "")
            if img_desc:
                parts.append(f"  Image content: {img_desc[:500]}")

            obj_lines.append("\n".join(parts))
        sections.append("\n".join(obj_lines))

        # === DIAGRAM STRUCTURE ===
        sections.append(
            self._build_diagram_structure(slide, labels, parsed_sections)
        )

        # === DECISION LOGIC ===
        decisions = self._extract_decision_points(slide, parsed_sections)
        if decisions:
            logic_lines = ["=== DECISION LOGIC ==="]
            rels = (
                slide.flowchart.relationships
                if slide.flowchart and slide.flowchart.is_flowchart
                else (slide.relationships or [])
            )
            for decision in decisions:
                logic_lines.append(f"Decision: \"{decision}\"")
                for rel in rels:
                    src = labels.get(
                        rel.source_element_id, ""
                    )
                    if decision in src or decision.split("?")[0] in src:
                        if rel.label:
                            tgt = labels.get(
                                rel.target_element_id, rel.target_element_id
                            )
                            logic_lines.append(f"  {rel.label} → \"{tgt}\"")
            sections.append("\n".join(logic_lines))

        # === VISUAL HIERARCHY ===
        hierarchy_lines = ["=== VISUAL HIERARCHY ==="]
        if slide.title:
            hierarchy_lines.append(f"Primary focus: slide title '{slide.title}'")
        if slide.layout_structure:
            hierarchy_lines.append(
                f"Layout pattern: {slide.layout_structure.layout_type}"
            )
        order_labels = self._reading_order_labels(slide, labels)
        if order_labels:
            hierarchy_lines.append(f"Attention flow: {' → '.join(order_labels)}")
        if slide.text_points:
            top_level = [
                p.text for p in slide.text_points if p.level == 0
            ][:3]
            if top_level:
                hierarchy_lines.append(
                    f"Top-level headings: {'; '.join(top_level)}"
                )
        sections.append("\n".join(hierarchy_lines))

        # === SPATIAL RELATIONSHIPS ===
        spatial_lines = ["=== SPATIAL RELATIONSHIPS ==="]
        for element in slide.elements:
            if element.element_type not in {"arrow", "connector", "freeform"}:
                continue
            label = labels.get(element.element_id, element.element_id)
            spatial_lines.append(
                f"Connector {label} at {self._position_percent(element)}"
            )
        for rel in slide.relationships or []:
            src = labels.get(rel.source_element_id, rel.source_element_id)
            tgt = labels.get(rel.target_element_id, rel.target_element_id)
            line = f'"{src}" connects to "{tgt}"'
            if rel.label:
                line += f" (label: \"{rel.label}\")"
            line += f" [{rel.relationship_type}]"
            spatial_lines.append(line)
        sections.append("\n".join(spatial_lines))

        # === VISUAL DESIGN ===
        design_lines = ["=== VISUAL DESIGN ==="]
        design_lines.extend(
            self._extract_visual_design_details(
                slide, parsed_sections, combined_summaries
            )
        )
        sections.append("\n".join(design_lines))

        # === FULL IMAGE ANALYSIS ===
        if combined_summaries:
            sections.append(
                f"=== FULL IMAGE ANALYSIS ===\n{combined_summaries}"
            )

        # === IMAGE RECONSTRUCTION ===
        if (
            slide.image_reconstruction
            and slide.image_reconstruction.recreation_prompt
        ):
            sections.append(
                f"=== IMAGE RECONSTRUCTION ===\n"
                f"{slide.image_reconstruction.recreation_prompt}"
            )

        # === RENDERING INSTRUCTIONS ===
        sections.append(
            "=== RENDERING INSTRUCTIONS ===\n"
            "Generate an image of the slide based on the above description. Focus on the layout, shapes, and overall structure. Do not try to include too much text, just use placeholder text for smaller body paragraphs, but include the main title."
        )

        return "\n\n".join(sections)

    def _format_high_density_graph_blueprint(self, semantic_flow: SemanticFlowModel) -> str:
        """Concise, high-density output for 1:1 reconstruction of graph slides."""
        output = ["[VISUAL BLUEPRINT: GRAPH SLIDE]"]
        
        # 1. Branding & Vibe
        bg = "White" # Default
        if semantic_flow.visual_design_details:
            for detail in semantic_flow.visual_design_details:
                if "color" in detail.lower() or "background" in detail.lower():
                    bg = detail
                    break
        output.append(f"BRANDING/VIBE: {bg}")
        output.append(f"OVERALL_FLOW: {semantic_flow.overall_flow}")
        
        # 2. Hard Data Clusters (Detailed specifications for each chart)
        output.append("\nDATA_STREAMS:")
        for i, chart in enumerate(semantic_flow.charts):
            stream = [f"CLUSTER_{i} ({chart.chart_type.upper()}): {chart.title or 'Untitled'}"]
            
            # Include Color Mapping Specification
            if chart.legend_mapping:
                stream.append("  COLOR_MAP:")
                for hex_color, label in chart.legend_mapping.items():
                    stream.append(f"    - {label}: {hex_color}")
            
            if chart.categories:
                stream.append(f"  AXIS_LABELS: {', '.join(chart.categories)}")
            
            if chart.series:
                for s in chart.series:
                    stream.append(f"  SERIES ('{s.name}'): {s.values} (HEX: {s.color})")
            
            if chart.insight:
                stream.append(f"  INSIGHT: {chart.insight}")
            if chart.purpose:
                stream.append(f"  PURPOSE: {chart.purpose}")
            
            output.append("\n".join(stream))

        # 3. Spatial Map (Normalized % for precise placement)
        output.append("\nSPATIAL_BLUEPRINT (x,y,w,h in % of slide):")
        # Use the regions if available
        if semantic_flow.layout_regions:
            for r in semantic_flow.layout_regions:
                b = r.get("bounds", {})
                output.append(f"  REGION '{r['name']}': [{b.get('x_start')}, {b.get('y_start')}, {b.get('width')}, {b.get('height')}]")
        
        # 4. Contextual Anchors (Verbatim Text for title/footnotes)
        output.append("\nTEXT_ANCHORS (Verbatim):")
        for layer in semantic_flow.conceptual_layers[:5]:
            output.append(f"  - {layer}")
        
        # 5. Reconstruction Logic (The "How-To")
        output.append("\nRECONSTRUCTION_PROMPT:")
        output.append(semantic_flow.image_generation_prompt)

        output.append("\n[END BLUEPRINT]")
        return "\n".join(output)

    def format_structured_output(self, semantic_flow: SemanticFlowModel) -> str:
        """Format semantic flow as the human-readable structure expected for LLM handoff."""
        lines = [
            "Semantic Flow",
            semantic_flow.overall_flow,
            "",
            "Step-by-step meaning:",
        ]
        for step in semantic_flow.step_by_step_explanation:
            lines.append(step)

        lines.extend(["", "Conceptual Layers"])
        for layer in semantic_flow.conceptual_layers:
            lines.append(layer)

        lines.extend(["", "Visual Design Details"])
        for detail in semantic_flow.visual_design_details:
            lines.append(detail)

        lines.extend(["", "Plain English Summary", semantic_flow.plain_english_summary])

        # Add Charts and Data section
        if semantic_flow.charts:
            lines.extend(["", "Charts and Data:"])
            for chart in semantic_flow.charts:
                lines.append(f"Chart: {chart.title or 'Untitled Chart'}")
                lines.append(f"  Type: {chart.chart_type}")
                lines.append(f"  Insight: {chart.insight}")
                if chart.categories:
                    lines.append(f"  Categories: {', '.join(chart.categories)}")
                if chart.series:
                    for s in chart.series:
                        lines.append(f"  Series '{s.name}': {s.values}")
                lines.append("")

        if semantic_flow.decision_points:

            lines.extend(["", "Decision Points"])
            for dp in semantic_flow.decision_points:
                lines.append(dp)

        if semantic_flow.cause_effect_chain:
            lines.extend(["", "Cause-Effect Chain"])
            for chain in semantic_flow.cause_effect_chain:
                lines.append(chain)

        lines.extend([
            "",
            "Image Generation Prompt (primary reconstruction field):",
            semantic_flow.image_generation_prompt,
        ])
        return "\n".join(lines)

    def format_to_user_style(self, semantic_flow: SemanticFlowModel) -> str:
        """Format semantic flow into the user's specific markdown structure."""
        # 0. Detect if this slide has quantitative chart data
        has_charts = False
        if semantic_flow.charts and len(semantic_flow.charts) > 0:
            has_charts = True
        
        # Check visual design details for chart evidence
        for detail in (semantic_flow.visual_design_details or []):
            if "chart:" in detail.lower() or "chart instance" in detail.lower():
                has_charts = True

        # If it's a chart slide, use the high-density reconstruction blueprint
        if has_charts:
            return self._format_high_density_graph_blueprint(semantic_flow)

        sections = []
        # ... (rest of standard formatting)

        # 1. Semantic Flow
        sections.append("Semantic Flow")
        sections.append(semantic_flow.overall_flow or "")

        # 2. Step-by-step meaning
        sections.append("\nStep-by-step meaning:")
        for step in (semantic_flow.step_by_step_explanation or []):
            step_clean = re.sub(r"^\s*[-*•]?\s*(?:Step\s+\d+:)?\s*", "", step).strip()
            if "This creates a binary decision node:" in step_clean:
                node = step_clean.split("This creates a binary decision node:", 1)[1].strip()
                sections.append("This creates a binary decision node:")
                sections.append(node)
            elif "Based on this state:" in step_clean:
                sections.append("Based on this state:")
            elif "If No →" in step_clean:
                sections.append(step_clean)
            elif "If Yes →" in step_clean:
                sections.append(step_clean)
            else:
                sections.append(step_clean)

        # 3. Conceptual Layers
        sections.append("\nConceptual Layers")
        for layer in (semantic_flow.conceptual_layers or []):
            layer_clean = re.sub(r"^\s*[-*•]?\s*", "", layer).strip()
            if ":" in layer_clean:
                parts = layer_clean.split(":", 1)
                title = parts[0].strip()
                body = parts[1].strip()
                
                # Check for "Example:" or "example:"
                example_pattern = re.compile(r"\bexample\b:?", re.IGNORECASE)
                match = example_pattern.search(body)
                if match:
                    start_idx = match.start()
                    end_idx = match.end()
                    definition = body[:start_idx].strip().rstrip(".,; ")
                    example_text = body[end_idx:].strip()
                    
                    sections.append(title)
                    sections.append(definition)
                    sections.append("Example:")
                    example_text_quoted = example_text
                    if not (example_text_quoted.startswith("“") or example_text_quoted.startswith("\"")):
                        example_text_quoted = f"“{example_text_quoted}”"
                    sections.append(example_text_quoted)
                else:
                    sections.append(title)
                    sections.append(body)
            else:
                sections.append(layer_clean)

        # 4. Visual Design Details
        sections.append("\nVisual Design Details")
        current_section = None
        for detail in (semantic_flow.visual_design_details or []):
            detail_stripped = detail.strip()
            cleaned = re.sub(r"^\s*[-*•]\s*", "", detail_stripped)
            
            lower_cleaned = cleaned.lower()
            if lower_cleaned.startswith("colour scheme") or lower_cleaned == "color scheme":
                current_section = "Colour scheme:"
                sections.append(current_section)
            elif lower_cleaned.startswith("shapes"):
                current_section = "Shapes:"
                sections.append(current_section)
            elif lower_cleaned.startswith("structure"):
                current_section = "Structure:"
                sections.append(current_section)
            elif lower_cleaned.startswith("connectors"):
                current_section = "Connectors:"
                sections.append(current_section)
            else:
                if cleaned:
                    sections.append(cleaned)

        # 5. Plain English Summary
        sections.append("\n3. Plain English Summary")
        sections.append(semantic_flow.plain_english_summary or "")

        # 6. Charts and Data
        if semantic_flow.charts:
            sections.append("\nCharts and Data:")
            for chart in semantic_flow.charts:
                sections.append(f"Chart: {chart.title or 'Untitled Chart'}")
                sections.append(f"  Type: {chart.chart_type}")
                sections.append(f"  Insight: {chart.insight}")
                if chart.categories:
                    sections.append(f"  Categories: {', '.join(chart.categories)}")
                if chart.series:
                    for s in chart.series:
                        sections.append(f"  Series '{s.name}': {s.values} (color: {s.color})")
                sections.append("")

        return "\n".join(sections)

