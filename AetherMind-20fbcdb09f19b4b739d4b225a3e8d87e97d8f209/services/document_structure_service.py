from typing import List, Dict, Any, Optional
from models.document_model import DocumentModel, SlideModel,DocumentStructureModel

class DocumentStructureService:
    def analyze_document(self, doc: DocumentModel) -> DocumentStructureModel:
        if not doc or not doc.slides:
            return DocumentStructureModel(
                presentation_type="unknown",
                document_role="unknown",
                narrative_flow="Empty document."
            )

        slide_roles = []
        slide_sequence = []
        executive_summary_slides = []
        methodology_slides = []
        findings_slides = []
        recommendation_slides = []
        appendix_slides = []
        is_financial = False
        is_research = False
        is_consulting = False

        for slide in doc.slides:
            intent = "findings"  
            if slide.image_understanding and slide.image_understanding.slide_intent:
                intent = slide.image_understanding.slide_intent
            elif slide.semantic_flow and slide.semantic_flow.slide_intent:
                intent = slide.semantic_flow.slide_intent
            else:
                if slide.flowchart and slide.flowchart.is_flowchart:
                    intent = "process_flow"
                elif slide.layout_structure and slide.layout_structure.layout_type == "title_slide":
                    intent = "cover_page"
                elif slide.title:
                    t = slide.title.lower()
                    if "summary" in t or "takeaway" in t:
                        intent = "executive_summary"
                    elif "recommend" in t or "next step" in t or "roadmap" in t:
                        intent = "recommendations"
                    elif "appendix" in t or "supplement" in t:
                        intent = "appendix"
                    elif "compare" in t or "vs" in t:
                        intent = "comparison"
            
            slide_roles.append(intent)
            slide_sequence.append(intent)
            slide_no = slide.slide_number

            if intent == "executive_summary":
                executive_summary_slides.append(slide_no)
            elif intent == "methodology":
                methodology_slides.append(slide_no)
            elif intent in {"findings", "dashboard", "comparison", "research_report"}:
                findings_slides.append(slide_no)
            elif intent == "recommendations":
                recommendation_slides.append(slide_no)
            elif intent == "appendix":
                appendix_slides.append(slide_no)
            content_text = ""
            if slide.title:
                content_text += slide.title + " "
            for elem in slide.elements:
                if elem.text:
                    content_text += elem.text + " "
            
            content_lower = content_text.lower()
            if any(w in content_lower for w in ("audit", "financial", "revenue", "profit", "ebitda", "consolidated")):
                is_financial = True
            if any(w in content_lower for w in ("methodology", "research", "abstract", "literature", "findings")):
                is_research = True
            if any(w in content_lower for w in ("recommendation", "roadmap", "strategy", "deliverable", "proposal")):
                is_consulting = True
        sections = []
        current_section_name = None
        current_start = 1

        for idx, role in enumerate(slide_roles, start=1):
            sec_name = self._map_role_to_section_name(role)
            if current_section_name is None:
                current_section_name = sec_name
                current_start = idx
            elif sec_name != current_section_name:
                sections.append({
                    "section_name": current_section_name,
                    "slide_range": [current_start, idx - 1],
                    "description": f"This section covers {current_section_name.lower()}."
                })
                current_section_name = sec_name
                current_start = idx
        if current_section_name:
            sections.append({
                "section_name": current_section_name,
                "slide_range": [current_start, len(doc.slides)],
                "description": f"This section covers {current_section_name.lower()}."
            })
        doc_role = "Enterprise Presentation"
        if is_financial:
            doc_role = "Financial Audit Report"
        elif is_consulting:
            doc_role = "Consulting Report"
        elif is_research:
            doc_role = "Research Paper / Report"
        narrative_parts = [f"This document is classified as a {doc_role} consisting of {len(doc.slides)} slides."]
        for sec in sections:
            r = sec["slide_range"]
            slides_str = f"Slide {r[0]}" if r[0] == r[1] else f"Slides {r[0]}-{r[1]}"
            narrative_parts.append(f"It features a {sec['section_name']} in {slides_str}.")
            
        narrative_flow = " ".join(narrative_parts)

        return DocumentStructureModel(
            presentation_type=doc_role,
            document_role=doc_role,
            slide_sequence=slide_sequence,
            total_sections=len(sections),
            section_breaks=[],
            executive_summary_slides=executive_summary_slides,
            methodology_slides=methodology_slides,
            findings_slides=findings_slides,
            recommendation_slides=recommendation_slides,
            appendix_slides=appendix_slides,
            narrative_flow=narrative_flow,
            sections=sections,
            document_summary=(
                f"{doc_role} consisting of "
                f"{len(doc.slides)} slides and "
                f"{len(sections)} major sections."
            )
        )

    @staticmethod
    def _map_role_to_section_name(role: str) -> str:
        mapping = {
            "cover_page": "Title Section",
            "executive_summary": "Executive Summary Section",
            "methodology": "Methodology Section",
            "architecture_diagram": "Architecture & Structure Section",
            "process_flow": "Process & Workflow Section",
            "infographic": "Visual Overview Section",
            "comparison": "Comparison Section",
            "research_report": "Research Details Section",
            "findings": "Findings & Data Section",
            "recommendations": "Recommendations Section",
            "conclusion": "Conclusion Section",
            "appendix": "Appendix Section",
            "dashboard": "Dashboard & Metrics Section"
        }
        return mapping.get(role, "Findings & Data Section")
