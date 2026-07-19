from models.document_model import (
    SlideModel,
    SlideContextModel,
    TextPointModel,
    PositionMapModel,
)


class SlideContextService:

    def build_context(
        self,
        slide: SlideModel,
    ) -> SlideContextModel:

        text_points = self._extract_text_points(slide)

        position_mapping = self._extract_position_mapping(slide)

        outline = self._build_outline(slide)

        return SlideContextModel(
            header_footer=slide.header_footer,
            title=slide.title,
            visual_inventory=slide.visual_inventory,
            layout_structure=slide.layout_structure,
            flowchart=slide.flowchart,
            text_points=text_points,
            position_mapping=position_mapping,
            relationship_mapping=slide.relationships,
            diagram_understanding=slide.diagram_understanding,
            image_understanding=slide.image_understanding,
            semantic_flow=slide.semantic_flow,
            outline=outline,
        )

    def _extract_text_points(
        self,
        slide: SlideModel,
    ) -> list[TextPointModel]:

        points = []

        for element in slide.elements:

            if not element.text:
                continue

            if element.paragraphs:

                for paragraph in element.paragraphs:

                    if not paragraph.text.strip():
                        continue

                    points.append(
                        TextPointModel(
                            element_id=element.element_id,
                            level=paragraph.level,
                            text=paragraph.text.strip(),
                        )
                    )

            else:

                points.append(
                    TextPointModel(
                        element_id=element.element_id,
                        level=0,
                        text=element.text.strip(),
                    )
                )

        return points

    def _extract_position_mapping(
        self,
        slide: SlideModel,
    ) -> list[PositionMapModel]:

        mappings = []

        for element in slide.elements:

            mappings.append(
                PositionMapModel(
                    element_id=element.element_id,
                    element_type=element.element_type,
                    x=element.position.x,
                    y=element.position.y,
                    width=element.position.width,
                    height=element.position.height,
                )
            )

        return mappings

    def _build_outline(
        self,
        slide: SlideModel,
    ) -> str:

        sections = []

        if slide.title:
            sections.append(
                f"Title: {slide.title}"
            )

        if slide.visual_inventory:

            inventory = slide.visual_inventory

            sections.append(
                (
                    f"Visual Structure: "
                    f"{inventory.title_count} title(s), "
                    f"{inventory.shape_count} shape(s), "
                    f"{inventory.arrow_count} arrow(s), "
                    f"{inventory.connector_count} connector(s), "
                    f"{inventory.image_count} image(s), "
                    f"{inventory.table_count} table(s), "
                    f"{inventory.chart_count} chart(s)"
                )
            )

        if slide.flowchart and slide.flowchart.is_flowchart:

            sections.append(
                (
                    f"Flowchart detected with "
                    f"{slide.flowchart.box_count} boxes and "
                    f"{slide.flowchart.arrow_count} arrows."
                )
            )

            if slide.flowchart.process_summary:

                sections.append(
                    slide.flowchart.process_summary
                )

        if slide.semantic_flow:

            if slide.semantic_flow.plain_english_summary:

                sections.append(
                    slide.semantic_flow.plain_english_summary
                )

        elif slide.slide_summary:

            sections.append(
                slide.slide_summary
            )

        if slide.image_understanding:

            if slide.image_understanding.scene_description:

                sections.append(
                    "Image Depiction: "
                    + slide.image_understanding.scene_description
                )

        return "\n".join(sections)