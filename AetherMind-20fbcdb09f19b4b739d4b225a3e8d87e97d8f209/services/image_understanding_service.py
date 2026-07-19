from models.document_model import ImageUnderstandingModel
from models.document_model import SlideModel
from models.document_model import VisualDesignModel


class ImageUnderstandingService:
    def analyze_slide(self,slide: SlideModel) -> ImageUnderstandingModel:
        image_understanding = ImageUnderstandingModel()
        image_understanding.image_type = self._detect_image_type(slide)
        image_understanding.scene_description = (self._build_scene_description(slide))
        image_understanding.objects_detected = (self._extract_objects(slide))
        image_understanding.actions_detected = (self._extract_actions(slide))
        image_understanding.relationships = (self._extract_relationships(slide))
        image_understanding.semantic_meaning = (self._build_semantic_meaning(slide))
        image_understanding.visual_design = (self._build_visual_design(slide))
        image_understanding.dominant_colors = (self._extract_colors(slide))
        image_understanding.visual_elements = (self._extract_visual_elements(slide))
        image_understanding.llm_recreation_prompt = (self._build_recreation_prompt(slide))

        self._populate_reconstruction_fields(slide, image_understanding)

        return image_understanding

    def _detect_image_type(self,slide: SlideModel) -> str:
        if slide.flowchart and slide.flowchart.is_flowchart:
            return "flowchart"
        if slide.diagram_understanding and slide.diagram_understanding.is_diagram:
            return "diagram"

        image_count = sum(1 for element in slide.elements if element.element_type == "image")
        if image_count > 0:
            return "image_based_slide"
        return "content_slide"

    def _build_scene_description(self, slide: SlideModel) -> str:
        from services.semantic_flow_service import _collect_image_summaries, _parse_image_summary_sections

        combined = _collect_image_summaries(slide)
        if combined:
            sections = _parse_image_summary_sections(combined)
            plain = sections.get("7. Plain-language Summary", "")
            if plain:
                return plain
            breakdown = sections.get("3. Detailed Component Breakdown", "")
            if breakdown:
                return breakdown.replace("\n", " ")[:500]

        title = slide.title or "Untitled Slide"
        text_parts = [
            (element.text or "").strip()
            for element in slide.elements
            if element.text and element.element_type != "image"
        ]
        if text_parts:
            return f"Slide '{title}': " + "; ".join(text_parts[:4])

        image_count = sum(1 for element in slide.elements if element.element_type == "image")
        visual_count = sum(
            1 for element in slide.elements
            if element.element_type in {"shape", "text_box", "placeholder", "freeform", "image"}
        )
        return (
            f"Slide titled '{title}' contains "
            f"{image_count} image(s) and "
            f"{visual_count} visual element(s)."
        )

    def _extract_objects(self,slide: SlideModel) -> list[str]:
        objects = []

        for element in slide.elements:

            if element.text:

                objects.append(
                    element.text
                )

        return objects

    def _extract_actions(self, slide: SlideModel) -> list[str]:
        actions = []

        keywords = [
            "open",
            "close",
            "start",
            "stop",
            "create",
            "delete",
            "get",
            "send",
            "receive",
            "process"
        ]

        for element in slide.elements:

            if not element.text:
                continue

            text = element.text.lower()

            for keyword in keywords:

                if keyword in text:
                    actions.append(
                        element.text
                    )

        return actions

    def _extract_relationships(self, slide: SlideModel) -> list[str]:
        relationships = []

        for relationship in slide.relationships:

            relationships.append(
                f"{relationship.source_element_id}"
                f" -> "
                f"{relationship.target_element_id}"
            )

        return relationships

    def _build_semantic_meaning(self, slide: SlideModel) -> str:
        if slide.semantic_flow and slide.semantic_flow.overall_flow:
            return slide.semantic_flow.overall_flow

        from services.semantic_flow_service import _collect_image_summaries, _parse_image_summary_sections

        combined = _collect_image_summaries(slide)
        if combined:
            sections = _parse_image_summary_sections(combined)
            interp = sections.get("6. Summary & Interpretation", "")
            if interp:
                return interp

        if slide.diagram_understanding and slide.diagram_understanding.flow_description:
            return slide.diagram_understanding.flow_description

        if slide.flowchart and slide.flowchart.is_flowchart:
            return "The slide explains a process flow through connected stages."

        if slide.diagram_understanding and slide.diagram_understanding.is_diagram:
            return "The slide explains relationships between concepts."

        return "The slide presents information through visual and textual elements."

    def _build_visual_design(self,slide: SlideModel) -> VisualDesignModel:
        design = VisualDesignModel()
        design.background_style = (
            "presentation"
        )
        design.layout_style = (
            slide.layout_structure.layout_type
            if slide.layout_structure
            else "mixed"
        )

        design.primary_shapes = [
            element.element_type
            for element in slide.elements
        ]

        return design

    def _extract_colors(self,slide: SlideModel) -> list[str]:
        colors = set()
        for element in slide.elements:

            if (element.style and element.style.background_color):
                colors.add(element.style.background_color)
            if (element.style and element.style.text_color):
                colors.add(element.style.text_color)
        return list(colors)

    def _extract_visual_elements(self,slide: SlideModel) -> list[str]:
        visual_elements = []
        for element in slide.elements:
            visual_elements.append(element.element_type)
        return list(set(visual_elements))

    def _build_recreation_prompt(self,slide: SlideModel) -> str:
        if slide.semantic_flow and slide.semantic_flow.image_generation_prompt:
            return slide.semantic_flow.image_generation_prompt

        from services.semantic_flow_service import SemanticFlowService
        return SemanticFlowService().analyze_slide(slide).image_generation_prompt

    def _populate_reconstruction_fields(self, slide: SlideModel, image_understanding: ImageUnderstandingModel):
        import re
        from services.semantic_flow_service import _collect_image_summaries, _parse_image_summary_sections
        combined = _collect_image_summaries(slide)
        parsed = _parse_image_summary_sections(combined) if combined else {}

        # 1. Slide Intent
        intent = "findings"  # default fallback
        intent_text = parsed.get("1. Slide Intent", "").lower()
        valid_intents = {
            "cover_page", "executive_summary", "dashboard", "methodology",
            "architecture_diagram", "process_flow", "infographic", "comparison",
            "research_report", "findings", "recommendations", "conclusion", "appendix", "custom"
        }
        for vi in valid_intents:
            if vi in intent_text or vi.replace("_", " ") in intent_text:
                intent = vi
                break
        
        # Rule-based fallback if intent is default or not found
        if intent == "findings" or not intent:
            if slide.flowchart and slide.flowchart.is_flowchart:
                intent = "process_flow"
            elif slide.layout_structure and slide.layout_structure.layout_type == "title_slide":
                intent = "cover_page"
            elif slide.title:
                title_lower = slide.title.lower()
                if "summary" in title_lower or "takeaway" in title_lower:
                    intent = "executive_summary"
                elif "recommend" in title_lower or "next step" in title_lower or "roadmap" in title_lower:
                    intent = "recommendations"
                elif "appendix" in title_lower or "supplement" in title_lower:
                    intent = "appendix"
                elif "agenda" in title_lower or "table of contents" in title_lower:
                    intent = "methodology"
                elif "compare" in title_lower or "vs" in title_lower:
                    intent = "comparison"
        image_understanding.slide_intent = intent

        # 2. Visual Regions
        regions = []
        regions_text = parsed.get("2. Visual Regions", "")
        if regions_text and regions_text.strip() != "N/A":
            for line in regions_text.splitlines():
                line = line.strip().lstrip("-*•").strip()
                if line:
                    regions.append({"description": line})
        if not regions:
            # Fallback to layout structure regions
            if slide.layout_structure and slide.layout_structure.regions:
                for r in slide.layout_structure.regions:
                    regions.append({
                        "name": r.name,
                        "bounds": {"x_start": r.x_start, "y_start": r.y_start, "x_end": r.x_end, "y_end": r.y_end},
                        "element_ids": r.element_ids
                    })
        image_understanding.visual_regions = regions

        # 3. Illustration Inventory
        illustration_inv = []
        illustration_text = parsed.get("3. Illustration Inventory", "")
        if illustration_text and illustration_text.strip() != "N/A":
            current_item = {}
            for line in illustration_text.splitlines():
                line = line.strip()
                if line.startswith("-") or line.startswith("*") or line.startswith("•"):
                    if current_item:
                        illustration_inv.append(current_item)
                    current_item = {"description": line.lstrip("-*•").strip()}
                elif ":" in line and current_item:
                    parts = line.split(":", 1)
                    key = parts[0].strip().lower().replace(" ", "_")
                    val = parts[1].strip()
                    if key in ("position", "size", "purpose", "semantic_meaning"):
                        current_item[key] = val
            if current_item:
                illustration_inv.append(current_item)
        if not illustration_inv:
            # Fallback based on PPTX elements
            for element in slide.elements:
                if element.element_type in ("image", "shape", "chart"):
                    illustration_inv.append({
                        "element_id": element.element_id,
                        "position": f"x={element.position.x}, y={element.position.y}",
                        "size": f"width={element.position.width}, height={element.position.height}",
                        "purpose": f"Visual {element.element_type} element",
                        "semantic_meaning": element.text or f"Illustration of type {element.element_type}"
                    })
        image_understanding.illustration_inventory = illustration_inv

        # 4. Relationship Mapping
        rel_mapping = []
        rel_text = parsed.get("4. Relationship Mapping", "")
        if rel_text and rel_text.strip() != "N/A":
            for line in rel_text.splitlines():
                line = line.strip().lstrip("-*•").strip()
                if line:
                    rel_type = "supports"
                    for rt in ("supports", "explains", "compares", "contrasts", "groups", "summarizes", "influences", "depends_on"):
                        if rt in line.lower():
                            rel_type = rt
                            break
                    rel_mapping.append({"description": line, "relationship_type": rel_type})
        if not rel_mapping:
            for rel in slide.relationships:
                rel_mapping.append({
                    "source": rel.source_element_id,
                    "target": rel.target_element_id,
                    "relationship_type": rel.relationship_type,
                    "description": f"Connector points from {rel.source_element_id} to {rel.target_element_id}"
                })
        image_understanding.relationship_mapping = rel_mapping

        # 5. Design Hierarchy
        hierarchy = {"primary_focus": "", "secondary_focus": "", "tertiary_focus": "", "attention_flow": ""}
        hierarchy_text = parsed.get("5. Design Hierarchy", "")
        if hierarchy_text and hierarchy_text.strip() != "N/A":
            for line in hierarchy_text.splitlines():
                line = line.strip().lstrip("-*•").strip()
                for key in ("primary_focus", "secondary_focus", "tertiary_focus", "attention_flow"):
                    clean_key = key.replace("_", " ")
                    if line.lower().startswith(clean_key + ":") or line.lower().startswith(key + ":"):
                        hierarchy[key] = line.split(":", 1)[1].strip()
        if not any(hierarchy.values()):
            hierarchy["primary_focus"] = f"Title: {slide.title}" if slide.title else ""
            if slide.elements:
                non_titles = [e for e in slide.elements if e.text and e.text != slide.title]
                if non_titles:
                    hierarchy["secondary_focus"] = f"{non_titles[0].element_type}: {non_titles[0].text[:60]}"
            if slide.flowchart and slide.flowchart.reading_order:
                hierarchy["attention_flow"] = " -> ".join(slide.flowchart.reading_order)
        image_understanding.design_hierarchy = hierarchy

        # 6. Reading Order
        r_order = []
        ro_text = parsed.get("6. Reading Order", "")
        if ro_text and ro_text.strip() != "N/A":
            if "->" in ro_text or "→" in ro_text:
                parts = re.split(r'\s*->\s*|\s*→\s*', ro_text)
                r_order = [p.strip() for p in parts if p.strip()]
            else:
                for line in ro_text.splitlines():
                    line = line.strip().lstrip("-*•").strip()
                    if line:
                        r_order.append(line)
        if not r_order:
            if slide.flowchart and slide.flowchart.reading_order:
                r_order = slide.flowchart.reading_order
            else:
                r_order = [e.element_id for e in sorted(slide.elements, key=lambda x: (x.position.y, x.position.x))]
        image_understanding.reading_order = r_order