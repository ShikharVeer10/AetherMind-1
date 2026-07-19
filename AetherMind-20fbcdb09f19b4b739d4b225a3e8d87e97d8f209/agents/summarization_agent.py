class SummarizationAgent:

    system_prompt = ("Generate a detailed reconstruction-grade slide summary.")

    async def summarize_slide(self,slide,context_outline: str = "",image_summaries: str = "",) -> str:
        text_lines = []
        if getattr(slide, "text_points", None):
            for point in slide.text_points:
                text_lines.append(
                    f"[L{point.level}] {point.text}"
                )
        else:
            for element in slide.elements:
                if getattr(element, "paragraphs", None):
                    for para in element.paragraphs:
                        text_lines.append(f"[L{para.level}] {para.text}")
                elif getattr(element, "text", None):
                    text_lines.append(element.text)

        hf_info = ""

        if getattr(slide, "header_footer", None):
            hf = slide.header_footer
            hf_parts = []

            if getattr(hf, "header_text", None):
                hf_parts.append(f'Header: "{hf.header_text}"')

            if getattr(hf, "footer_text", None):
                hf_parts.append(f'Footer: "{hf.footer_text}"')

            if getattr(hf, "slide_number_text", None):
                hf_parts.append(f"Slide Number: {hf.slide_number_text}")

            if getattr(hf, "date_text", None):
                hf_parts.append(f"Date: {hf.date_text}")

            hf_info = "\n".join(hf_parts)

        return self._build_fallback(
            slide,
            text_lines,
            image_summaries,
            hf_info,
        )

    @staticmethod
    def _build_fallback(slide,text_lines,image_summaries,hf_info,) -> str:

        title = slide.title or "(Untitled Slide)"
        summary = []
        summary.append(" Slide Title")
        summary.append(title)
        summary.append("\nExtracted Text")
        if text_lines:
            summary.extend(text_lines)
        else:
            summary.append("No text detected.")

        summary.append("\nVisual Summary")

        if getattr(slide, "visual_inventory", None):
            inventory = slide.visual_inventory
            summary.append(f"Shapes: {getattr(inventory, 'shape_count', 0)}")
            summary.append(f"Images: {getattr(inventory, 'image_count', 0)}")
            summary.append(f"Tables: {getattr(inventory, 'table_count', 0)}")
            summary.append(f"Arrows: {getattr(inventory, 'arrow_count', 0)}")
        if image_summaries:
            summary.append("\n### Image Descriptions")
            summary.append(image_summaries)
        if hf_info:
            summary.append("\n### Header/Footer")
            summary.append(hf_info)

        return "\n".join(summary)