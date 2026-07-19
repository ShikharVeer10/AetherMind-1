from models.document_model import SemanticSlideDescriptionModel, SlideModel


class SemanticSlideService:
    def analyze_slide(self, slide: SlideModel) -> SemanticSlideDescriptionModel:
        semantic_flow = (
            slide.semantic_flow.overall_flow if slide.semantic_flow else ""
        )
        summary = (
            slide.semantic_flow.plain_english_summary
            if slide.semantic_flow and slide.semantic_flow.plain_english_summary
            else (slide.slide_summary if slide.slide_summary else "")
        )
        image_prompt = (
            slide.semantic_flow.image_generation_prompt
            if slide.semantic_flow and slide.semantic_flow.image_generation_prompt
            else self._build_image_prompt(slide)
        )
        visual_inventory_summary = self._build_visual_inventory_summary(slide)
        relationship_summary = self._build_relationship_summary(slide)
        image_depiction_summary = self._build_image_depiction_summary(slide)
        slide_archetype = self._infer_slide_archetype(slide)
        flowchart_summary = self._build_flowchart_summary(slide)

        return SemanticSlideDescriptionModel(
            semantic_flow=semantic_flow,
            step_by_step_meaning=[
                step
                for step in (
                    slide.semantic_flow.step_by_step_explanation
                    if slide.semantic_flow
                    else []
                )
            ],
            conceptual_layers=[
                layer
                for layer in (
                    slide.semantic_flow.conceptual_layers
                    if slide.semantic_flow
                    else []
                )
            ],
            visual_design_details=[
                detail
                for detail in (
                    slide.semantic_flow.visual_design_details
                    if slide.semantic_flow
                    else []
                )
            ],
            plain_english_summary=summary,
            image_generation_prompt=image_prompt,
            visual_inventory_summary=visual_inventory_summary,
            relationship_summary=relationship_summary,
            image_depiction_summary=image_depiction_summary,
            slide_archetype=slide_archetype,
            flowchart_summary=flowchart_summary,
        )

    def _build_image_prompt(self, slide: SlideModel) -> str:
        from services.semantic_flow_service import (
            SemanticFlowService,
            _collect_image_summaries,
            _parse_image_summary_sections,
        )

        combined = _collect_image_summaries(slide)
        parsed = _parse_image_summary_sections(combined)
        return SemanticFlowService()._build_reconstruction_image_prompt(
            slide,
            SemanticFlowService()._element_label_lookup(slide),
            combined,
            parsed,
        )

    def _build_visual_inventory_summary(self,slide: SlideModel,) -> str:
        if not slide.visual_inventory:
            return ""

        v = slide.visual_inventory

        return (
            f"{v.total_elements} total elements, "
            f"{v.text_box_count} text boxes, "
            f"{v.shape_count} shapes, "
            f"{v.arrow_count} arrows, "
            f"{v.image_count} images, "
            f"{v.table_count} tables, "
            f"{v.chart_count} charts."
        )
    
    def _build_relationship_summary(self,slide: SlideModel,) -> str:
        if not slide.relationships:
            return ""
        relationship_types = {}
        for rel in slide.relationships:
            relationship_types.setdefault(
            rel.relationship_type,
            0,
        )
        relationship_types[
            rel.relationship_type
        ] += 1
        return ", ".join(
        f"{count} {rtype}"
        for rtype, count in relationship_types.items()
        )
    

    def _build_image_depiction_summary(self, slide):

        summaries = []

        for element in slide.elements:

            if element.element_type == "image":
                continue

            image_summary = element.metadata.get(
                "image_summary"
            )

            if image_summary:
                summaries.append(image_summary)

        return "\n".join(summaries)
    
    def _infer_slide_archetype(self,slide: SlideModel,) -> str:

        if not slide.visual_inventory:
            return "general"

        v = slide.visual_inventory

        if v.arrow_count + v.connector_count > 3:
            return "flowchart"

        if v.table_count > 0:
            return "table_slide"

        if v.chart_count > 0:
            return "chart_slide"

        if v.image_count > 3:
            return "image_heavy"

        return "general"
    
    def _build_flowchart_summary(self,slide: SlideModel,) -> str:
        if not slide.relationships:
            return ""

        connector_count = len(
        [
            r
            for r in slide.relationships
            if r.relationship_type == "connector"
        ]
    )

        if connector_count == 0:
            return ""

        return (
            f"Flow structure detected with "
            f"{connector_count} connectors."
    )