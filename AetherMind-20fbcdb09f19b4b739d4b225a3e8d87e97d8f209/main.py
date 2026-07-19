import argparse
import asyncio
import json
import os
from collections import Counter
from pathlib import Path
from services.extraction_service import ExtractionService

def main():
    parser = argparse.ArgumentParser(description="AetherMind Document Extraction & Reconstruction Engine")
    parser.add_argument("document_path", nargs="?", default=None, help="Path to input presentation, PDF, or image document")
    parser.add_argument("--output-dir", default="output", help="Directory for output files")
    parser.add_argument("--validate", action="store_true", help="Render reconstructed PDF/image and evaluate visual alignment scores")
    parser.add_argument("--first-page-only", action="store_true", help="Extract and process only the first page")
    parser.add_argument("--fast", action="store_true", help="Run fast diagnostic mode by disabling LLM summaries and image summaries")
    parser.add_argument("--report", action="store_true", help="Generate an E2E statistics execution report (e2e_report.json)")
    
    args = parser.parse_args()
    document_path = args.document_path
    if not document_path:
        print("Enterprise Document Extraction Agent")
        document_path = input("Document Path: ").strip()

    document_path = document_path.strip('\'"')
    document_path = document_path.rstrip(".,;")
    if not document_path:
        raise ValueError("Path cannot be empty")

    is_url = document_path.startswith(("http://", "https://"))
    if not is_url:
        document_path_object = Path(document_path)
        if not document_path_object.exists():
            raise FileNotFoundError(f"Document not found: {document_path}")


    if args.fast:
        enable_summaries = False
        enable_image_summaries = False
        print("[main] Fast mode enabled: Disabling LLM summaries and image summaries.")
    else:
        enable_summaries = os.getenv("ENABLE_SUMMARIES", "true").lower() in {"1", "true"}
        enable_image_summaries = (
            os.getenv("ENABLE_IMAGE_SUMMARIES", "true").lower() in {"1", "true"}
        )

    output_dir_obj = Path(args.output_dir).resolve()
    output_dir_obj.mkdir(parents=True, exist_ok=True)
    extraction_service = ExtractionService(
        document_path=document_path,
        enable_summaries=enable_summaries,
        enable_image_summaries=enable_image_summaries,
    )

    print("Starting Document Extraction...")
    target_pages = [1] if args.first_page_only else None
    extracted_document = asyncio.run(
        extraction_service.extract_document(target_pages=target_pages)
    )
    print("Document Extraction Completed.")
    extracted_json_dir = output_dir_obj / "extracted_json"
    json_path_str = extraction_service.export_to_json(
        extracted_document=extracted_document,
        output_directory=str(extracted_json_dir)
    )
    json_path = Path(json_path_str)
    print(f"Extracted document JSON blueprint saved to: {json_path}")

    # 2. Optionally render PDF/Image and run Validation
    if args.validate:
        print("\n--- STEP 2: Running Deterministic Form Renderer ---")
        from services.form_renderer import FormRenderer
        from services.extraction_validator import ExtractionValidator
        with open(json_path, "r", encoding="utf-8") as f:
            json_data = json.load(f)
        payload = json_data.get("document", json_data)
        input_stem = Path(document_path).stem if not is_url else "downloaded_document"
        input_suffix = Path(document_path).suffix.lower() if not is_url else ".pptx"
        
        original_img_path = None
        if input_suffix == ".pdf":
            try:
                import fitz
                doc = fitz.open(document_path)
                page = doc[0]
                pix = page.get_pixmap(matrix=fitz.Matrix(96.0/72.0, 96.0/72.0), alpha=False)
                original_img_path = str(output_dir_obj / "original_page_1.png")
                pix.save(original_img_path)
                print(f"Extracted original PDF page 1 to image: {original_img_path}")
            except Exception as e:
                print(f"Could not extract original PDF page to image: {e}")
        elif input_suffix in {".png", ".jpg", ".jpeg"}:
            original_img_path = document_path

        # Render reconstructed PDF and image
        reconstructed_pdf_path = output_dir_obj / f"{input_stem}_reconstructed.pdf"
        reconstructed_img_path = output_dir_obj / f"{input_stem}_reconstructed.png"
        
        renderer = FormRenderer()
        try:
            img = renderer.render_to_image(payload)
            if img:
                img.save(reconstructed_img_path)
                print(f"Reconstructed slide image saved to: {reconstructed_img_path}")
            renderer.render_to_pdf(payload, reconstructed_pdf_path)
            print(f"Reconstructed slide PDF saved to: {reconstructed_pdf_path}")
        except Exception as e:
            print(f"Rendering reconstructed slide failed: {e}")

        # Evaluate Visual & Content Similarity (Validation)
        if original_img_path and reconstructed_img_path.exists():
            print("\n--- STEP 3: Evaluating Reconstruction Quality ---")
            validator = ExtractionValidator()
            try:
                scores = validator.evaluate_page(str(original_img_path), str(reconstructed_img_path))
                print("Validation Reconstruction Similarity Scores:")
                for metric, score in scores.items():
                    print(f"  - {metric}: {score}")
            except Exception as e:
                print(f"Validation comparison failed: {e}")

    if args.report:
        print("\n--- STEP 4: Generating E2E Execution Report ---")
        elements = [element for slide in extracted_document.slides for element in slide.elements]
        form_payloads = [
            element.form_reconstruction_payload
            for element in elements
            if element.form_reconstruction_payload
        ]
        form_document = form_payloads[0].get("document") if form_payloads else None

        def _payload_count(elems, attribute):
            return sum(bool(getattr(elem, attribute, None)) for elem in elems)

        report = {
            "input": str(Path(document_path).resolve()) if not is_url else document_path,
            "document_type": extracted_document.document_type,
            "slides": len(extracted_document.slides),
            "elements": len(elements),
            "element_types": dict(Counter(element.element_type for element in elements)),
            "payloads": {
                "forms": len(form_payloads),
                "dashboards": _payload_count(elements, "dashboard_reconstruction_payload"),
                "charts": _payload_count(elements, "chart_reconstruction_payload"),
                "images": _payload_count(elements, "image_reconstruction_payload"),
                "tables": sum(bool(element.table_reconstruction) for element in elements),
            },
            "form_schema_valid": bool(
                form_document
                and form_document.get("units") == "pixels"
                and isinstance(form_document.get("elements"), list)
            ),
            "form_element_count": len(form_document.get("elements", [])) if form_document else 0,
            "export_path": str(json_path.resolve()),
        }
        
        report_path = output_dir_obj / "e2e_report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"E2E report generated and saved to: {report_path}")

if __name__ == "__main__":
    main()