
from typing import Optional
from models.document_model import FlowchartModel

from models.document_model import (
    HeaderFooterModel,
    SlideModel,
    VisualInventoryModel,
)

from agents.extraction_agents import (
    ContextAssemblyAgent,
    DiagramUnderstandingAgent,
    FlowchartAnalysisAgent,
    HeaderFooterAgent,
    LayoutStructureAgent,
    PositionMappingAgent,
    RelationshipMappingAgent,
    TextExtractionAgent,
    VisualInventoryAgent,
)
from agents.table_extraction_agent import TableExtractionAgent
from agents.visual_intelligence_agent import VisualIntelligenceAgent

from services.semantic_region_detection_service import SemanticRegionDetectionService

class AgentOrchestrator:
    def __init__(
        self,
        summarization_agent=None,
        image_summarization_agent=None,
        presentation_metadata=None,
    ):
        self.summarization_agent = summarization_agent
        self.image_summarization_agent = image_summarization_agent
        self.presentation_metadata = presentation_metadata or {}
        self.last_slide_title = None

        self.text_agent = TextExtractionAgent()
        self.header_footer_agent = HeaderFooterAgent()
        self.inventory_agent = VisualInventoryAgent()
        self.layout_agent = LayoutStructureAgent()
        self.position_agent = PositionMappingAgent()
        self.relationship_agent = RelationshipMappingAgent()
        self.flowchart_agent = FlowchartAnalysisAgent()
        self.diagram_agent = DiagramUnderstandingAgent()
        self.table_agent = TableExtractionAgent()
        self.visual_intelligence_agent = VisualIntelligenceAgent()
        self.context_agent = ContextAssemblyAgent()
        self.semantic_region_service = SemanticRegionDetectionService()
        self._expected_integrity = None

    def _validate_page_integrity(self, slide_model, step_name: str):
        meta = getattr(slide_model, "metadata", None)
        if not meta:
            raise ValueError(f"[{step_name}] Missing integrity metadata!")
        required_keys = {"document_id", "page_number", "image_hash", "processing_timestamp", "pipeline_version"}
        for key in required_keys:
            if key not in meta:
                raise ValueError(f"[{step_name}] Missing key in integrity metadata: {key}")
        if not hasattr(self, "_expected_integrity") or self._expected_integrity is None:
            self._expected_integrity = {k: meta[k] for k in required_keys}
        for k in required_keys:
            if meta[k] != self._expected_integrity[k]:
                raise ValueError(
                    f"[{step_name}] Page integrity violation! "
                    f"Metadata key '{k}' changed from '{self._expected_integrity[k]}' to '{meta[k]}'"
                )

    def _save_intermediate_log(self, data, doc_id: str, page_num: int, stage_name: str):
        try:
            import json
            from pathlib import Path
            log_dir = Path("output/intermediate_logs") / doc_id / f"page_{page_num}"
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / f"{stage_name}.json"
            with open(log_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False,
                          default=lambda o: o.model_dump() if hasattr(o, "model_dump") else str(o))
            print(f"    [Orchestrator] Saved intermediate log to {log_file}")
        except Exception as e:
            print(f"    [Orchestrator] Failed to save intermediate log for {stage_name}: {e}")

    async def process_slide(self, slide_model: SlideModel, raw_slide) -> SlideModel:

        import time
        import hashlib
        from services.extraction_service import compute_page_hash
        
        processing_timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        pipeline_version = "2.0.0"
        
        if self.presentation_metadata and self.presentation_metadata.get("document_id"):
            doc_id = self.presentation_metadata["document_id"]
        else:
            doc_id = hashlib.sha256(str(getattr(slide_model, "title", "doc")).encode()).hexdigest()
            
        img_hash = compute_page_hash(slide_model, raw_slide)
        
        if not slide_model.metadata:
            slide_model.metadata = {}
            
        slide_model.metadata["document_id"] = doc_id
        slide_model.metadata["page_number"] = slide_model.slide_number
        slide_model.metadata["image_hash"] = img_hash
        slide_model.metadata["processing_timestamp"] = processing_timestamp
        slide_model.metadata["pipeline_version"] = pipeline_version
        
        # Store unique processing ID for Multi-Agent Synchronization (Requirement 7)
        slide_model.metadata["processing_id"] = f"{doc_id}_page_{slide_model.slide_number}"
        
        # Reset expected integrity for this process run
        self._expected_integrity = None
        self._validate_page_integrity(slide_model, "Start of process_slide")

        if slide_model.title:
            self.last_slide_title = slide_model.title

        print("    [Orchestrator] Step 0: Semantic regions and layout graph...")
        slide_model.semantic_regions = self.semantic_region_service.detect_regions(slide_model)
        slide_model.layout_graph = self.semantic_region_service.build_layout_graph(slide_model.elements, slide_model.semantic_regions)
        self._validate_page_integrity(slide_model, "After Step 0: Semantic regions")

        # 1) Exact text extraction (verbatim)

        print("    [Orchestrator] Step 1: Text extraction...")
        slide_model.text_points = self.text_agent.run(slide_model)
        self._validate_page_integrity(slide_model, "After Step 1: Text extraction")
        self._save_intermediate_log(slide_model.text_points, doc_id, slide_model.slide_number, "OCR")

        # 2) Header/footer extraction
        print("    [Orchestrator] Step 2: Header/footer...")
        header_footer = self.header_footer_agent.run(raw_slide)
        self._validate_page_integrity(slide_model, "After Step 2: Header/footer")

        # 3) Visual inventory counts
        print("    [Orchestrator] Step 3: Visual inventory...")
        visual_inventory = self.inventory_agent.run(slide_model)
        self._validate_page_integrity(slide_model, "After Step 3: Visual inventory")

        # 4) Layout structure identification
        print("    [Orchestrator] Step 4: Layout structure...")
        layout = self.layout_agent.run(slide_model)
        self._validate_page_integrity(slide_model, "After Step 4: Layout structure")
        self._save_intermediate_log(layout, doc_id, slide_model.slide_number, "Layout_Detection")

        # 5) Position mapping
        print("    [Orchestrator] Step 5: Position mapping...")
        position_mapping = self.position_agent.run(slide_model)
        self._validate_page_integrity(slide_model, "After Step 5: Position mapping")
        self._save_intermediate_log(position_mapping, doc_id, slide_model.slide_number, "Coordinate_Extraction")

        # 6) Relationship mapping
        print("    [Orchestrator] Step 6: Relationship mapping...")
        relationships = self.relationship_agent.run(slide_model) or []
        slide_model.relationships = relationships
        self._validate_page_integrity(slide_model, "After Step 6: Relationship mapping")

        # 7) Flowchart analysis
        print("    [Orchestrator] Step 7: Flowchart analysis skipped")


        flowchart = FlowchartModel(
            is_flowchart=False,
            box_count=0,
            arrow_count=0,
            decision_node_count=0,
            start_nodes=[],
            end_nodes=[],
            flow_type="none",
            boxes=[],
            arrows=[],
            relationships=[],
            relationship_mapping=[],
            reading_order=[],
            reading_order_labels=[],
            process_summary=None,
        )
        print("    [Orchestrator] Step 9: Image summaries...")
        image_summary_text = await self._run_image_summaries(slide_model)

        print("    [Orchestrator] Step 8: Diagram understanding...")
        diagram_understanding= self.diagram_agent.run(
            slide_model,
            relationships,
            flowchart
        )

        # 10) Slide context
        print("    [Orchestrator] Step 10: Slide context...")

        context = self.context_agent.run(
            title=slide_model.title,
            header_footer=header_footer or HeaderFooterModel(),
            inventory=visual_inventory or VisualInventoryModel(),
            layout=layout,
            flowchart=flowchart,
            text_points=slide_model.text_points,
            position_mapping=position_mapping,
            relationships=relationships or [],
            diagram_understanding=diagram_understanding
        )
        print("    [Orchestrator] Step 10.5: Visual Object Classification...")
        from services.visual_object_classifier_service import VisualObjectClassifierService
        from services.chart_detection_service import ChartDetectionService
        from services.chart_understanding_service import ChartUnderstandingService
        from services.chart_reconstruction_service import ChartReconstructionService
        
        visual_classifier = VisualObjectClassifierService()
        visual_classifier.classify_elements(slide_model.elements)
        
        chart_detector = ChartDetectionService()
        chart_service = ChartUnderstandingService()
        chart_reconstructor = ChartReconstructionService()

        # Initialize chart_understandings once if not already present
        if not hasattr(slide_model, "chart_understandings") or slide_model.chart_understandings is None:
            slide_model.chart_understandings = []

        if raw_slide and hasattr(raw_slide, "get_pixmap"):
            import fitz
            from services.flexible_table_detector import FlexibleTableDetector
            ftd = FlexibleTableDetector()
            
            # 1. Capture regions identified by the grouping heuristic
            chart_regions = ftd.detect_chart_regions(slide_model.elements)
            scale = 12700.0
            
            for region in chart_regions:
                bbox = region["bbox"]
                clip = (bbox["x"]/scale, bbox["y"]/scale, (bbox["x"]+bbox["width"])/scale, (bbox["y"]+bbox["height"])/scale)
                try:
                    pix = raw_slide.get_pixmap(clip=clip, matrix=fitz.Matrix(3, 3))
                    img_bytes = pix.tobytes("jpeg")
                    from models.document_model import DocumentElementModel, PositionModel, VisualObjectClass
                    chart_elem = DocumentElementModel(
                        element_id=f"slide_{slide_model.slide_number}_chart_region_{len(slide_model.chart_understandings) + 1}",
                        element_type="chart",
                        text=region["text_content"],
                        paragraphs=[],
                        position=PositionModel(**bbox),
                        metadata={
                            "visual_class": VisualObjectClass(classification="chart", confidence=0.95).model_dump(),
                            "__image_bytes": img_bytes,
                            "detected_chart_type": region.get("chart_type", "horizontal_bar_chart")
                        }
                    )
                    slide_model.elements.append(chart_elem)
                    
                    # Build slide context for better chart extraction (titles, demographics, etc)
                    slide_context = f"Slide Title: {slide_model.title or 'Unknown'}\n"
                    slide_context += "Slide Text:\n" + "\n".join([e.text for e in slide_model.elements if e.text])
                    
                    chart_info = chart_service.extract_understanding(chart_elem, slide_context=slide_context)
                    chart_elem.chart_understanding = chart_info
                    slide_model.chart_understandings.append(chart_info)
                    chart_elem.metadata["chart_reconstruction"] = chart_reconstructor.build_reconstruction_data(chart_info)

                    for eid in region["consumed_ids"]:
                        for el in slide_model.elements:
                            if el.element_id == eid: el.metadata["part_of_chart"] = chart_elem.element_id
                except Exception as e: 
                    print(f"    [Orchestrator] PDF Chart region capture failed: {e}")

            # 2. Capture individual elements upgraded to 'chart' (e.g. from tables)
            for element in slide_model.elements:
                vclass = element.metadata.get("visual_class", {})
                if isinstance(vclass, dict) and vclass.get("classification") == "chart":
                    if not element.metadata.get("__image_bytes"):
                        pos = element.position
                        clip = (pos.x/scale, pos.y/scale, (pos.x+pos.width)/scale, (pos.y+pos.height)/scale)
                        try:
                            pix = raw_slide.get_pixmap(clip=clip, matrix=fitz.Matrix(3, 3))
                            element.metadata["__image_bytes"] = pix.tobytes("jpeg")
                        except Exception: pass

        print("\nELEMENT INVENTORY")
        for e in slide_model.elements:
            print(
                e.element_id,
                e.element_type,
                e.text[:50] if e.text else ""
            )
        print(" END ELEMENT INVENTORY\n")
        print("    [Orchestrator] Step 10.6: Chart Detection and Understanding...")
        from services.flexible_table_detector import FlexibleTableDetector
        table_detector = FlexibleTableDetector()

        # Identify visual tables from text boxes
        visual_tables = table_detector.detect_visual_tables(slide_model.elements)
        for table in visual_tables:
            # Create a virtual table element
            table_id = f"visual_table_{len(slide_model.elements)}"
            from models.document_model import DocumentElementModel, PositionModel
            table_elem = DocumentElementModel(
                element_id=table_id,
                element_type="table",
                text=f"Detected Table: {table['num_rows']}x{table['num_cols']}",
                paragraphs=[],
                position=PositionModel(**table['bbox']),
                metadata={
                    "is_visual_table": True,
                    "consumed_ids": table['consumed_ids'],
                    "visual_grid": table
                }
            )
            # Sync to element properties for extraction services
            table_elem.raw_table_content = table['rows']
            table_elem.table_merged_cells = table['merged_cells']
            consumed_set = set(table['consumed_ids'])
            for e in slide_model.elements:
                if e.element_id in consumed_set:
                    e.metadata["part_of_table"] = table_id

            slide_model.elements.append(table_elem)

        chart_detector.detect_charts(slide_model.elements)
        chart_elements = [
            e for e in slide_model.elements
            if e.metadata.get("is_chart") is True
        ]
        print(f"[Chart Detection] Found {len(chart_elements)} charts")
        for c in chart_elements:
            print(
                f"[Chart Detection] {c.element_id} | "
                f"{c.metadata.get('detected_chart_type')} | "
                f"{c.text[:100] if c.text else 'NO_TEXT'}"
            )
        
        # Process any charts that haven't been processed yet (e.g. native PPTX charts)
        processed_chart_ids = {c.chart_id for c in slide_model.chart_understandings}
        
        for element in slide_model.elements:
            vclass = element.metadata.get("visual_class", {})
            if isinstance(vclass, dict) and vclass.get("classification") == "chart":
                if element.element_id in processed_chart_ids:
                    continue
                
                element.element_type = "chart" # Ensure it's treated as a chart
                chart_info = chart_service.extract_understanding(element)
                element.chart_understanding = chart_info
                slide_model.chart_understandings.append(chart_info)
                element.metadata["chart_reconstruction"] = chart_reconstructor.build_reconstruction_data(chart_info)
                processed_chart_ids.add(element.element_id)

        print("    [Orchestrator] Step 11: Table extraction and semantics...")
        table_markdowns = self.table_agent.run(slide_model)
        self._validate_page_integrity(slide_model, "After Step 11: Table extraction")
        self._save_intermediate_log(table_markdowns, doc_id, slide_model.slide_number, "Table_Extraction")
        
        from services.semantic_table_service import SemanticTableService
        from services.advanced_table_intelligence_service import AdvancedTableIntelligenceService
        table_sem_service = SemanticTableService()
        advanced_table_service = AdvancedTableIntelligenceService()

        for element in slide_model.elements:
            if element.element_type == "table":
                vclass = element.metadata.get("visual_class", {})
                if isinstance(vclass, dict) and vclass.get("classification") != "table":
                    # If classified as something else, skip table analysis
                    continue
                element.table_semantics = table_sem_service.analyze_table_semantics(element)
                element.table_reconstruction = advanced_table_service.analyze_table(element)

        print("    [Orchestrator] Step 11.5: Universal Structural Understanding...")
        from services.structural_understanding_service import UniversalStructuralUnderstandingService
        struct_service = UniversalStructuralUnderstandingService()
        slide_model = struct_service.analyze_slide(slide_model)
        self._validate_page_integrity(slide_model, "After Step 11.5: Universal Structural Understanding")

        print("    [Orchestrator] Step 11.6: Form, Dashboard, and Reconstruction Payloads...")
        from agents.form_extraction_agent import FormExtractionAgent
        from agents.dashboard_extraction_agent import DashboardExtractionAgent
        from services.color_mapping_service import ColorMappingService

        form_agent = FormExtractionAgent(self.presentation_metadata)
        dashboard_agent = DashboardExtractionAgent()
        color_mapping_service = ColorMappingService()

        extracted_form = form_agent.run(slide_model, raw_page=raw_slide, metadata=slide_model.metadata)
        self._validate_page_integrity(slide_model, "After Form Extraction")
        self._save_intermediate_log(extracted_form, doc_id, slide_model.slide_number, "LLM_Structured_Output")

        dashboard_data = dashboard_agent.run(slide_model)
        if dashboard_data:
            slide_model.dashboard = dashboard_data
            for element in slide_model.elements:
                element.dashboard_reconstruction_payload = {
                    "panels": dashboard_data.panels,
                    "metrics": dashboard_data.metrics,
                    "relationships": dashboard_data.relationships
                }

        if extracted_form:
            # Build a comprehensive reconstruction payload from the rich form extraction
            payload = extracted_form.copy()
            payload["reconstruction_instructions"] = (
                "You are a deterministic document reconstruction engine.\n\n"
                "Your task is NOT to create a visually appealing document.\n\n"
                "Your task is to recreate the exact original scanned page represented by the JSON.\n\n"
                "Rules:\n\n"
                "1. Reconstruct ONLY elements explicitly present in the JSON.\n"
                "2. Never infer missing content.\n"
                "3. Never modernize the layout.\n"
                "4. Never improve typography.\n"
                "5. Never create dashboards, presentations, infographics, charts, icons, or visual embellishments.\n"
                "6. Treat the JSON as an OCR reconstruction target.\n"
                "7. Preserve all OCR text exactly as written.\n"
                "8. Preserve all coordinates exactly.\n"
                "9. Preserve page aspect ratio exactly.\n"
                "10. Preserve all table boundaries.\n"
                "11. Preserve all horizontal and vertical lines.\n"
                "12. Preserve merged cells.\n"
                "13. Preserve checkboxes and radio buttons.\n"
                "14. Preserve font sizes relative to bounding boxes.\n"
                "15. Preserve the exact source background color or texture.\n"
                "16. Preserve every extracted fill, text, and border color.\n"
                "17. Never substitute a generic monochrome visual style.\n"
                "18. Do not reinterpret the document meaning.\n"
                "19. Do not summarize.\n"
                "20. Do not correct spelling.\n"
                "21. Do not hallucinate missing fields.\n"
                "22. Draw every object strictly from its bounding box.\n\n"
                "Output:\n"
                "An exact document reconstruction matching the source form at pixel level."
            )
            
            # Save the final JSON page-level payload (Requirement 6)
            self._save_intermediate_log(payload, doc_id, slide_model.slide_number, "Final_JSON")

            # Also save to the extracted_forms output directory
            try:
                import json
                from pathlib import Path
                forms_dir = Path("output/extracted_forms")
                forms_dir.mkdir(parents=True, exist_ok=True)
                form_file = forms_dir / f"form_page_{slide_model.slide_number}.json"
                with open(form_file, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2, ensure_ascii=False,
                             default=lambda o: o.model_dump() if hasattr(o, "model_dump") else str(o))
                print(f"    [Orchestrator] Saved form extraction to {form_file}")
            except Exception as e:
                print(f"    [Orchestrator] Could not save form extraction file: {e}")

            # Attach form data to ALL elements (not just the first)
            # so the reconstruction pipeline has access regardless of which element it reads
            for element in slide_model.elements:
                if element.element_type in ["text_box", "image", "chart", "table"]:
                    element.form_data = extracted_form
                    element.form_reconstruction_payload = payload
                    break  # Attach to first matching element for the main payload

        for element in slide_model.elements:
            if element.chart_understanding:
                cmap = color_mapping_service.extract_color_mapping(element.chart_understanding)
                element.chart_reconstruction_payload = {
                    "type": element.chart_understanding.chart_type,
                    "series": [s.model_dump() for s in element.chart_understanding.series],
                    "colors": list(cmap.values()),
                    "axes": {k: v.model_dump() for k, v in element.chart_understanding.axes.items()},
                    "data_labels": element.chart_understanding.data_labels,
                }

        print("    [Orchestrator] Final assembly...")
        slide_model.header_footer = header_footer or HeaderFooterModel()
        slide_model.visual_inventory = visual_inventory or VisualInventoryModel()
        slide_model.layout_structure = layout
        slide_model.context = context
        slide_model.table_markdowns = table_markdowns or []
        slide_model.position_mapping = position_mapping
        slide_model.diagram_understanding = diagram_understanding
        slide_model.flowchart = flowchart

        print("    [Orchestrator] Step 12: Semantic services...")
        from services.image_understanding_service import ImageUnderstandingService
        from services.imagereconstruction_service import ImageReconstructionService
        from services.semantic_slide_service import SemanticSlideService
        from services.semantic_region_detection_service import SemanticRegionDetectionService

        img_und_service = ImageUnderstandingService()
        slide_model.image_understanding = img_und_service.analyze_slide(slide_model)

        img_rec_service = ImageReconstructionService()
        slide_model.image_reconstruction = img_rec_service.analyze_slide(slide_model)
        sem_region_service = SemanticRegionDetectionService()
        slide_model.semantic_regions = sem_region_service.detect_regions(slide_model)

        print("    [Orchestrator] Step 12.1: Slide interpretation (semantic flow)...")
        from agents.slide_interpretation_agent import SlideInterpretationAgent
        from services.semantic_flow_service import SemanticFlowService

        try:
            interpretation_agent = SlideInterpretationAgent()
            slide_model.semantic_flow = await interpretation_agent.interpret_slide(
                slide_model,
                image_summaries=image_summary_text or "",
            )
        except Exception as e:
            print(f"    [Orchestrator] Slide interpretation failed: {e}")
            slide_model.semantic_flow = SemanticFlowService().analyze_slide(
                slide_model,
                image_summaries=image_summary_text or "",
            )

        print("    [Orchestrator] Step 12.2: Semantic slide extraction...")
        from agents.semantic_slide_extraction_agent import SemanticSlideExtractionAgent
        semantic_agent = SemanticSlideExtractionAgent(self.presentation_metadata)
        slide_model.semantic_slide_extraction = semantic_agent.run(slide_model, raw_slide=raw_slide)
        self._validate_page_integrity(slide_model, "After Step 12.2: Semantic slide extraction")

        if slide_model.semantic_flow:
            slide_model.slide_summary = SemanticFlowService().format_structured_output(
                slide_model.semantic_flow
            )
            slide_model.business_message = slide_model.semantic_flow.overall_flow
            slide_model.communication_intent = slide_model.semantic_flow.slide_intent
            slide_model.reading_order = slide_model.semantic_flow.reading_order

            if slide_model.semantic_flow.semantic_text_enrichments:
                slide_model.semantic_text_enrichments = slide_model.semantic_flow.semantic_text_enrichments
            if slide_model.semantic_flow.semantic_section_enrichments:
                slide_model.semantic_section_enrichments = slide_model.semantic_flow.semantic_section_enrichments
            if slide_model.semantic_flow.semantic_equivalence_targets:
                slide_model.semantic_equivalence_targets = slide_model.semantic_flow.semantic_equivalence_targets
    
            from models.document_model import SemanticSlideGraphModel
            vh_attention = []
            if slide_model.semantic_flow.visual_hierarchy:
                vh_val = slide_model.semantic_flow.visual_hierarchy.get("attention_flow", "")
                if vh_val:
                    vh_attention = [vh_val]
            
            slide_model.semantic_graph = SemanticSlideGraphModel(
                slide_intent=slide_model.semantic_flow.slide_intent or "",
                executive_summary=slide_model.semantic_flow.executive_summary or "",
                visual_structure=slide_model.semantic_flow.visual_structure or "",
                sections=slide_model.semantic_flow.sections,
                relationships=slide_model.relationships,
                charts=slide_model.chart_understandings,
                visual_hierarchy=vh_attention
            )

            if slide_model.semantic_flow.slide_archetype:
                from models.document_model import SlideArchetypeModel
                slide_model.slide_archetype = SlideArchetypeModel(
                    slide_archetype=slide_model.semantic_flow.slide_archetype,
                    confidence=0.95  # LLM reasoning is high confidence
                )
            if slide_model.semantic_flow.capability_map_data:
                from models.document_model import CapabilityMapModel
                slide_model.capability_map = CapabilityMapModel(**slide_model.semantic_flow.capability_map_data)
            
            if slide_model.semantic_flow.governance_data:
                from models.document_model import GovernanceFrameworkModel
                slide_model.governance_framework = GovernanceFrameworkModel(**slide_model.semantic_flow.governance_data)
                
            if slide_model.semantic_flow.process_flow_data:
                from models.document_model import ProcessFlowModel
                slide_model.process_flow = ProcessFlowModel(**slide_model.semantic_flow.process_flow_data)
                
            if slide_model.semantic_flow.dashboard_data:
                from models.document_model import DashboardModel
                slide_model.dashboard = DashboardModel(**slide_model.semantic_flow.dashboard_data)

            if slide_model.semantic_flow.table_intelligence:
                for llm_table in slide_model.semantic_flow.table_intelligence:
                    tid = llm_table.get("table_id")
                    for element in slide_model.elements:
                        if element.element_id == tid and element.table_reconstruction:
                            if "merged_cells" in llm_table:
                                element.table_reconstruction.merged_cells = llm_table["merged_cells"]
                            if "nested_headers" in llm_table:
                                element.table_reconstruction.hierarchy = llm_table["nested_headers"]

            if slide_model.semantic_flow.visual_hierarchy:
                from models.document_model import VisualHierarchyModel
                vh = slide_model.semantic_flow.visual_hierarchy
                slide_model.visual_hierarchy = VisualHierarchyModel(
                    primary_focus=[vh.get("primary_focus")] if vh.get("primary_focus") else [],
                    secondary_focus=[vh.get("secondary_focus")] if vh.get("secondary_focus") else [],
                    tertiary_focus=[vh.get("tertiary_focus")] if vh.get("tertiary_focus") else []
                )
        print("    [Orchestrator] Step 12.5: Slide summary generation...")
        if not slide_model.slide_summary:
            slide_summary = await self._run_slide_summary(
                slide_model, context.outline, image_summary_text or ""
            )
            if slide_summary:
                slide_model.slide_summary = slide_summary

        sem_slide_service = SemanticSlideService()
        slide_model.semantic_slide_description = sem_slide_service.analyze_slide(slide_model)

        # Apply layout-preserving semantic rewriting of all slide text elements
        print("    [Orchestrator] Running layout-preserving slide rewriting...")
        from services.slide_rewriter_service import SlideRewriterService
        await SlideRewriterService().rewrite_slide(slide_model)

        # 13) Slide Reconstruction Context
        print("    [Orchestrator] Step 13: Slide reconstruction context...")

        from services.slide_reconstruction_service import SlideReconstructionService
        recon_service = SlideReconstructionService()    
        recon_context = recon_service.build_context(slide_model,presentation_metadata=self.presentation_metadata)
        slide_model.slide_reconstruction_context = recon_context
        if not slide_model.business_message:
            slide_model.business_message = recon_context.business_message
        if not slide_model.communication_intent:
            slide_model.communication_intent = recon_context.communication_intent
        if not slide_model.functional_equivalence_requirements:
            slide_model.functional_equivalence_requirements = recon_context.functional_equivalence_requirements
        if not slide_model.reading_order:
            slide_model.reading_order = recon_context.reading_order

        # 14) Unified Visual Intelligence & High-Fidelity Blueprint
        print("    [Orchestrator] Step 14: Unified Visual Intelligence Extraction...")
        if raw_slide and hasattr(raw_slide, "get_pixmap"):
            try:
                # Capture full slide image for global visual reasoning
                pix = raw_slide.get_pixmap(matrix=fitz.Matrix(2, 2))
                slide_bytes = pix.tobytes("jpeg")
                
                # Global High-Fidelity Blueprint
                slide_model.high_fidelity_blueprint = await self.visual_intelligence_agent.extract_visual_blueprint(
                    slide_bytes, 
                    context=f"Title: {slide_model.title}\nSummary: {slide_model.slide_summary}"
                )
                
                if slide_model.high_fidelity_blueprint:
                    print(f"    [Orchestrator] Successfully extracted high-fidelity blueprint for identical reconstruction.")
                    # Sync color palette back to slide model for legacy support
                    slide_model.color_palette = slide_model.high_fidelity_blueprint.color_palette

            except Exception as e:
                print(f"    [Orchestrator] High-fidelity visual intelligence failed: {e}")

        self._validate_page_integrity(slide_model, "End of process_slide")
        return slide_model

    async def _run_image_summaries(self, slide_model: SlideModel) -> Optional[str]:
        if not self.image_summarization_agent:
            return ""
        text_lines = []
        if getattr(slide_model, "text_points", None):
            for p in slide_model.text_points:
                if getattr(p, "text", None):
                    text_lines.append(p.text)
        
        slide_text = "\n".join(text_lines) if text_lines else None
        slide_title = getattr(slide_model, "title", None) or self.last_slide_title

        summaries = []
        for element in slide_model.elements:
            if element.element_type != "image":
                continue
            image_bytes = element.metadata.get("__image_bytes")
            if not image_bytes:
                continue
            try:
                desc = await self.image_summarization_agent.summarize_image(
                    image_bytes,
                    slide_title=slide_title,
                    slide_text=slide_text,
                )
            except Exception:
                desc = None
            if desc:
                element.metadata["image_summary"] = desc
                summaries.append(desc)

        return "\n\n".join(summaries)


    async def _run_slide_summary(self,slide_model: SlideModel,context_outline: str,image_summaries: str,) -> Optional[str]:
        if not self.summarization_agent:
            return None
        try:
            return await self.summarization_agent.summarize_slide(
                slide_model,
                context_outline=context_outline,
                image_summaries=image_summaries,
            )
        except Exception:
            return None
