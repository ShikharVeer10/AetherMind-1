import argparse
import asyncio
import json
import os
from pathlib import Path
from services.extraction_service import ExtractionService
from services.form_renderer import FormRenderer
from services.extraction_validator import ExtractionValidator


async def main():
    parser = argparse.ArgumentParser(description="End-to-end Form Extraction, Reconstruction, and Validation Pipeline")
    parser.add_argument("input_path", nargs="?", default=None, help="Path to input image/PDF document")
    parser.add_argument("--output-dir", default="c:/Users/shikh/AetherMind/output", help="Directory for intermediate files")
    parser.add_argument("--cache", action="store_true", help="Use cached extraction JSON if available")
    args = parser.parse_args()

    input_path = args.input_path or input("Please enter the input document path (PDF or Image): ").strip()
    if (input_path.startswith('"') and input_path.endswith('"')) or (
        input_path.startswith("'") and input_path.endswith("'")
    ):
        input_path = input_path[1:-1].strip()

    is_url = input_path.startswith(("http://", "https://"))
    if not is_url:
        input_path_obj = Path(input_path)
        if not input_path_obj.exists():
            print(f"Error: Input file not found at {input_path}")
            return
        input_stem = input_path_obj.stem
        input_suffix = input_path_obj.suffix.lower()
    else:
        from urllib.parse import urlparse
        parsed = urlparse(input_path)
        input_stem = Path(parsed.path).stem or "downloaded_document"
        input_suffix = Path(parsed.path).suffix.lower() or ".pptx"

    output_dir_obj = Path(args.output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    reconstruction_json_path = output_dir_obj / "extracted_json" / f"{input_stem}_reconstruction.json"

    # Compute current file's SHA256 hash (Requirement 3)
    current_hash = None
    temp_downloaded_path = None
    try:
        import hashlib
        import requests
        import tempfile
        h = hashlib.sha256()
        if is_url:
            print(f"Downloading and calculating hash for remote file: {input_path}")
            response = requests.get(input_path, stream=True, timeout=60)
            response.raise_for_status()
            
            # Save URL content to a temp file to avoid downloading again if cache is stale
            temp_download = tempfile.NamedTemporaryFile(delete=False, suffix=input_suffix)
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    temp_download.write(chunk)
                    h.update(chunk)
            temp_download.close()
            temp_downloaded_path = temp_download.name
            current_hash = h.hexdigest()
        else:
            with open(input_path, "rb") as f:
                while chunk := f.read(8192):
                    h.update(chunk)
            current_hash = h.hexdigest()
        print(f"Computed input file hash: {current_hash}")
    except Exception as e:
        print(f"Warning: Failed to calculate input hash ({e})")

    # Invalidate cache if input hash changed
    cache_valid = False
    if args.cache and reconstruction_json_path.exists():
        try:
            with open(reconstruction_json_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
            # Support both lightweight format and formatted document payload structure
            cached_hash = cached_data.get("document_hash") or cached_data.get("document", {}).get("document_hash")
            if cached_hash and current_hash and cached_hash == current_hash:
                cache_valid = True
                print(f"\n--- STEP 1: Using cached extraction JSON from {reconstruction_json_path} ---")
            else:
                print(f"\nCache invalidated! Document contents changed (Current Hash: {current_hash}, Cached Hash: {cached_hash}).")
        except Exception as e:
            print(f"Error checking cache validity: {e}")

    if not cache_valid:
        print("\n--- STEP 1: Running Lossless Geometry Extraction & Multi-stage OCR ---")
        # Use downloaded temp file to avoid downloading it again!
        extract_input = temp_downloaded_path if temp_downloaded_path else input_path
        service = ExtractionService(
            extract_input,
            enable_summaries=True,
            enable_image_summaries=False,
        )
        if is_url:
            # Keep original URL name for file name output matching
            service.document_path = input_path
            
        document = await service.extract_document()
        
        # Export to JSON
        reconstruction_json_path_str = service.export_to_json(
            extracted_document=document,
            output_directory=str(output_dir_obj / "extracted_json")
        )
        reconstruction_json_path = Path(reconstruction_json_path_str)
        print(f"Extracted document geometry saved to: {reconstruction_json_path}")

    # Cleanup temp download if it was created
    if temp_downloaded_path and os.path.exists(temp_downloaded_path):
        try:
            os.remove(temp_downloaded_path)
            print(f"Cleaned up temporary downloaded validation file: {temp_downloaded_path}")
        except Exception as e:
            print(f"Failed to remove temporary file {temp_downloaded_path}: {e}")

    # Load the JSON
    with open(reconstruction_json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)

    # Convert PDF page to image if input is a PDF (to allow visual validation comparison)
    original_img_path = None
    if input_suffix == ".pdf":
        import fitz
        doc = fitz.open(input_path)
        page = doc[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(96.0/72.0, 96.0/72.0), alpha=False)
        original_img_path = str(output_dir_obj / "original_page_1.png")
        pix.save(original_img_path)
        print(f"Extracted original PDF page 1 to image: {original_img_path}")
    else:
        original_img_path = input_path

    payload = json_data.get("document", json_data)

    # Crop the original image to slide bounds if it was cropped during extraction (visual alignment)
    crop_box = None
    images_list = payload.get("images") or []
    for img_item in images_list:
        meta = img_item.get("metadata")
        if meta and isinstance(meta, dict) and meta.get("crop_box"):
            crop_box = meta.get("crop_box")
            break

    if crop_box and original_img_path:
        try:
            from PIL import Image
            with Image.open(original_img_path) as orig_img:
                cropped_orig = orig_img.crop((crop_box[0], crop_box[1], crop_box[2], crop_box[3]))
                cropped_orig_path = str(output_dir_obj / "original_page_1_cropped.png")
                cropped_orig.save(cropped_orig_path)
                original_img_path = cropped_orig_path
                print(f"Cropped original validation image to match slide region: {original_img_path}")
        except Exception as e:
            print(f"Warning: Failed to crop original validation image: {e}")

    # Step 2: Render
    print("\n--- STEP 2: Running Deterministic Form Renderer ---")
    reconstructed_img_path = str(output_dir_obj / "reconstructed_page_1.png")
    reconstructed_pdf_path = str(output_dir_obj / "reconstructed_page_1.pdf")
    
    renderer = FormRenderer()
    # Handle single page or pages list from JSON
    payload = json_data.get("document", json_data)
    
    try:
        img = renderer.render_to_image(payload)
        img.save(reconstructed_img_path)
        print(f"Reconstructed PNG saved to: {reconstructed_img_path}")
        
        renderer.render_to_pdf(payload, reconstructed_pdf_path)
        print(f"Reconstructed PDF saved to: {reconstructed_pdf_path}")
    except Exception as e:
        print(f"Rendering failed: {e}")
        return

    # Step 3: Validate
    print("\n--- STEP 3: Running Automatic Visual Extraction Validation ---")
    scores = ExtractionValidator.compare_images(original_img_path, reconstructed_img_path)
    
    print("\nVALDIATION RESULTS:")
    print(f"  SSIM (Structural Similarity): {scores['ssim']:.4f}")
    print(f"  Layout Similarity:            {scores['layout_similarity']:.4f}")
    print(f"  Border & Gridline Similarity: {scores['border_similarity']:.4f}")
    print(f"  Checkbox Count Ratio:         {scores['checkbox_similarity']:.4f}")
    print(f"  Table Similarity Score:       {scores['table_similarity']:.4f}")
    
    if scores['passed'] > 0.5:
        print("\n[SUCCESS] Document Reconstruction Validation PASSED (Similarity >= 0.80)!")
    else:
        print("\n[FAILURE] Document Reconstruction Validation FAILED (Similarity < 0.80). Check rendering geometry.")


if __name__ == "__main__":
    asyncio.run(main())
