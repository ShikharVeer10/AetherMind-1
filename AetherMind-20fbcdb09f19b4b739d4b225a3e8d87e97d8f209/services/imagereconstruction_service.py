from models.document_model import ImageReconstructionModel
from models.document_model import SlideModel


class ImageReconstructionService:

    def analyze_slide(self,slide: SlideModel) -> ImageReconstructionModel:
        reconstruction = ImageReconstructionModel()
        reconstruction.layout_description = (self._build_layout_description(slide))
        reconstruction.color_palette = (self._extract_color_palette(slide))
        reconstruction.object_location = (self._extract_object_locations(slide))
        reconstruction.connector_layout = (self._extract_connector_layout(slide))
        reconstruction.object_inventory = (self._extract_object_inventory(slide))
        reconstruction.visual_hierarchy = (self._build_visual_hierarchy(slide))
        reconstruction.layout_regions = (self._extract_layout_regions(slide))
        reconstruction.design_style = (self._detect_design_style(slide))
        reconstruction.recreation_prompt = (self._build_recreation_prompt(slide))
        return reconstruction

    def _build_layout_description(self,slide: SlideModel) -> str:

        if slide.layout_structure:
            return (f"Layout type is {slide.layout_structure.layout_type}")

        return "Mixed presentation layout"

    def _extract_color_palette(self,slide: SlideModel) -> list[str]:
        colors = set()
        for element in slide.elements:

            if (element.style and element.style.background_color):
                colors.add(element.style.background_color)

            if (element.style and element.style.text_color):
                colors.add(element.style.text_color)

        return list(colors)

    def _extract_object_locations(self,slide: SlideModel) -> list[str]:

        locations = []
        width = 12192000.0
        height = 6858000.0
        for e in slide.elements:
            if e.position:
                width = max(width, e.position.x + e.position.width)
                height = max(height, e.position.y + e.position.height)

        for element in slide.elements:
            if element.position:
                left_pct = (element.position.x / width) * 100
                top_pct = (element.position.y / height) * 100
                w_pct = (element.position.width / width) * 100
                h_pct = (element.position.height / height) * 100
                location = (
                    f"Element '{element.element_id}' ({element.element_type}) is positioned at: "
                    f"left: {left_pct:.1f}%, top: {top_pct:.1f}%, width: {w_pct:.1f}%, height: {h_pct:.1f}%"
                )
            else:
                location = f"Element '{element.element_id}' ({element.element_type}) has undefined position"
            locations.append(location)

        return locations

    def _extract_connector_layout(self,slide: SlideModel) -> list[str]:
        connectors = []
        for relationship in slide.relationships:
            label_str = f" labeled '{relationship.label}'" if relationship.label else ""
            connectors.append(f"Arrow connection: '{relationship.source_element_id}' points to '{relationship.target_element_id}'{label_str}")
        return connectors

    def _extract_object_inventory(self,slide: SlideModel) -> list[str]:
        inventory = []
        for element in slide.elements:
            desc = f"ID: {element.element_id} | Type: {element.element_type}"
            if element.text:
                desc += f" | Text content: '{element.text.strip().replace('\n', ' ')}'"
            if element.element_type == "image":
                img_sum = element.metadata.get("image_summary") or element.metadata.get("summary")
                if img_sum:
                    desc += f" | Visual details: {img_sum}"
            if element.style and element.style.background_color:
                desc += f" | Background color: {element.style.background_color}"
            if element.style and element.style.text_color:
                desc += f" | Text color: {element.style.text_color}"
            inventory.append(desc)

        return inventory

    def _build_visual_hierarchy(self,slide: SlideModel) -> list[str]:
        hierarchy = []
        if slide.title:
            hierarchy.append(f"Primary Title: {slide.title}")
        for element in slide.elements:
            if element.text:
                hierarchy.append(f"Content: {element.text}")
        return hierarchy

    def _extract_layout_regions(self,slide: SlideModel) -> list[str]:
        if not slide.layout_structure:
            return []
        regions = []
        for region in slide.layout_structure.regions:
            regions.append(f"{region.name}")

        return regions

    def _detect_design_style(self,slide: SlideModel) -> str:
        if (slide.flowchart and slide.flowchart.is_flowchart):
            return "flowchart"
        if (slide.diagram_understanding and slide.diagram_understanding.is_diagram):
            return "diagram"
        return "presentation"

    def _build_recreation_prompt(self,slide: SlideModel) -> str:
        title = slide.title or "Untitled Slide"
        width = 12192000.0
        height = 6858000.0
        for e in slide.elements:
            if e.position:
                width = max(width, e.position.x + e.position.width)
                height = max(height, e.position.y + e.position.height)

        prompt_lines = [
            f"Generate a presentation slide with the title '{title}'.",
            f"Overall Design Style: {self._detect_design_style(slide)} slide layout."
        ]

        if slide.semantic_flow:
            if slide.semantic_flow.overall_flow:
                prompt_lines.append(f"Visual flow concept: {slide.semantic_flow.overall_flow}")
            if slide.semantic_flow.storytelling_structure:
                prompt_lines.append(f"Storytelling/Narrative Structure: {slide.semantic_flow.storytelling_structure}")
            if slide.semantic_flow.reading_order:
                prompt_lines.append(f"Verbatim Reading Order: {' -> '.join(slide.semantic_flow.reading_order)}")

        if getattr(slide, "semantic_regions", None):
            prompt_lines.append("\n--- Slide Semantic Regions and Layout Panels ---")
            for r in slide.semantic_regions:
                prompt_lines.append(f"- Region '{r.name}' (Role: {r.semantic_role}): {r.purpose}. Contents: {r.contents}")

        if slide.semantic_flow and slide.semantic_flow.semantic_relationships:
            prompt_lines.append("\n--- Semantic Relationships and Visual Logic ---")
            for rel in slide.semantic_flow.semantic_relationships:
                desc = rel.get('description', '') if isinstance(rel, dict) else getattr(rel, 'description', '')
                prompt_lines.append(f"- Relation: {desc}")

        colors = self._extract_color_palette(slide)
        if colors:
            prompt_lines.append(f"Color theme uses the following hex codes: {', '.join(colors)}.")

        prompt_lines.append("\n--- Slide Layout Elements (Positioned on a 100% x 100% canvas) ---")
        for element in slide.elements:
            elem_desc = f"- Element '{element.element_id}' ({element.element_type}):"
            if element.position:
                left_pct = (element.position.x / width) * 100
                top_pct = (element.position.y / height) * 100
                w_pct = (element.position.width / width) * 100
                h_pct = (element.position.height / height) * 100
                elem_desc += f" Positioned at left: {left_pct:.1f}%, top: {top_pct:.1f}%, width: {w_pct:.1f}%, height: {h_pct:.1f}%."
            else:
                elem_desc += " Positioned at default layout coords."

            if element.text:
                elem_desc += f" Text: '{element.text.strip().replace('\n', ' ')}'."
            if element.element_type == "image":
                img_sum = element.metadata.get("image_summary") or element.metadata.get("summary")
                if img_sum:
                    elem_desc += f" Content depiction: {img_sum}."
            if element.style and element.style.background_color:
                elem_desc += f" Background color: {element.style.background_color}."
            if element.style and element.style.text_color:
                elem_desc += f" Text color: {element.style.text_color}."

            prompt_lines.append(elem_desc)

        if slide.relationships:
            prompt_lines.append("\n--- Connections and Relationships ---")
            for relationship in slide.relationships:
                label_str = f" with label '{relationship.label}'" if relationship.label else ""
                prompt_lines.append(f"- Arrow connector from element '{relationship.source_element_id}' pointing directly to '{relationship.target_element_id}'{label_str}.")

        prompt_lines.append("\nRecreate this slide perfectly matching the coordinates, elements, contents, and visual hierarchy described above.")

        return "\n".join(prompt_lines)