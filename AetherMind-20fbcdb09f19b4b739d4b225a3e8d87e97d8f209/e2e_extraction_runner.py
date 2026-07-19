import argparse
import asyncio
import json
import os
from collections import Counter
from pathlib import Path

from services.extraction_service import ExtractionService


def _payload_count(elements, attribute):
    return sum(bool(getattr(element, attribute, None)) for element in elements)


async def run(input_path: str, output_dir: str, first_page_only: bool) -> dict:
    target = Path(output_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)
    os.chdir(target)

    service = ExtractionService(
        input_path,
        enable_summaries=False,
        enable_image_summaries=False,
    )
    document = await service.extract_document(
        target_pages=[1] if first_page_only else None
    )
    export_path = service.export_to_json(extracted_document=document)
    elements = [element for slide in document.slides for element in slide.elements]
    form_payloads = [
        element.form_reconstruction_payload
        for element in elements
        if element.form_reconstruction_payload
    ]
    form_document = form_payloads[0].get("document") if form_payloads else None

    report = {
        "input": str(Path(input_path).resolve()),
        "document_type": document.document_type,
        "slides": len(document.slides),
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
        "form_element_count": len(form_document.get("elements", []))
        if form_document
        else 0,
        "export_path": str(Path(export_path).resolve()),
    }
    report_path = target / "e2e_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_path", nargs="?", default=None)
    parser.add_argument("output_dir", nargs="?", default=None)
    parser.add_argument("--first-page-only", action="store_true")
    args = parser.parse_args()

    input_path = args.input_path or input("Please enter the input file path: ").strip()
    output_dir = args.output_dir or "c:/Users/shikh/AetherMind/output"

    print(
        "E2E_RESULT="
        + json.dumps(
            asyncio.run(
                run(input_path, output_dir, args.first_page_only)
            )
        )
    )


if __name__ == "__main__":
    main()
