from types import SimpleNamespace

from agents.form_extraction_agent import EMU_PER_PIXEL, FormExtractionAgent


def _position(x, y, width, height):
    return SimpleNamespace(x=x, y=y, width=width, height=height)


def _element(element_id, element_type, position, **values):
    defaults = {
        "element_id": element_id,
        "element_type": element_type,
        "position": position,
        "metadata": {},
        "style": None,
        "text": None,
        "raw_table_content": None,
        "table_reconstruction": None,
    }
    defaults.update(values)
    return SimpleNamespace(**defaults)


def test_fallback_uses_absolute_pixels_and_preserves_empty_table_cells(monkeypatch):
    monkeypatch.setattr("agents.form_extraction_agent._get_form_agent", lambda: None)
    slide = SimpleNamespace(
        slide_number=2,
        background_color="#ffffff",
        elements=[
            _element(
                "title",
                "text_box",
                _position(EMU_PER_PIXEL * 10, EMU_PER_PIXEL * 20, EMU_PER_PIXEL * 30, EMU_PER_PIXEL * 8),
                text="Exact  text\nline 2",
                metadata={"z_order": 3},
            ),
            _element(
                "table",
                "table",
                _position(0, EMU_PER_PIXEL * 40, EMU_PER_PIXEL * 100, EMU_PER_PIXEL * 20),
                raw_table_content=[["A", ""], ["", "D"]],
            ),
        ],
    )
    agent = FormExtractionAgent(
        {"slide_width": EMU_PER_PIXEL * 200, "slide_height": EMU_PER_PIXEL * 100}
    )

    result = agent.run(slide)

    assert result["document"]["units"] == "pixels"
    assert result["document"]["page_width"] == 200
    assert result["document"]["page_height"] == 100
    title = next(item for item in result["document"]["elements"] if item["id"] == "title")
    assert title["x"] == 10
    assert title["y"] == 20
    assert title["page_number"] == 2
    assert title["text"] == "Exact  text\nline 2"
    table = next(item for item in result["document"]["elements"] if item["id"] == "table")
    assert table["row_count"] == 2
    assert table["column_count"] == 2
    assert len(table["cells"]) == 4
    assert [cell["text"] for cell in table["cells"]] == ["A", "", "", "D"]
    assert len(table["grid_lines"]) == 6


def test_line_contains_bbox_and_endpoint_geometry(monkeypatch):
    monkeypatch.setattr("agents.form_extraction_agent._get_form_agent", lambda: None)
    slide = SimpleNamespace(
        slide_number=1,
        background_color=None,
        elements=[_element("line-1", "line", _position(5, 10, 40, 1))],
    )

    result = FormExtractionAgent().run(slide)
    line = result["document"]["elements"][0]

    assert (line["x"], line["y"], line["width"], line["height"]) == (5, 10, 40, 1)
    assert (line["x1"], line["y1"], line["x2"], line["y2"]) == (5, 10, 45, 11)
    assert line["stroke_width"] == 1


def test_image_page_keeps_native_pixel_dimensions(monkeypatch):
    monkeypatch.setattr("agents.form_extraction_agent._get_form_agent", lambda: None)
    slide = SimpleNamespace(
        slide_number=1,
        background_color=None,
        elements=[
            _element(
                "page-image",
                "image",
                _position(0, 0, 960, 1280),
                metadata={"__image_bytes": b"image-data"},
            )
        ],
    )

    result = FormExtractionAgent().run(slide)

    assert result["document"]["page_width"] == 960
    assert result["document"]["page_height"] == 1280
    assert result["document"]["elements"][0]["image_hash"]


def test_table_preserves_merged_cells_and_skips_covered_slots(monkeypatch):
    monkeypatch.setattr("agents.form_extraction_agent._get_form_agent", lambda: None)
    slide = SimpleNamespace(
        slide_number=1,
        background_color="#ffffff",
        elements=[
            _element(
                "merged-table",
                "table",
                _position(0, 0, 200, 40),
                raw_table_content=[["Title", ""], ["", ""]],
                table_merged_cells=[
                    {"row": 0, "column": 0, "row_span": 2, "column_span": 2}
                ],
            )
        ],
    )

    result = FormExtractionAgent().run(slide)
    table = result["document"]["elements"][0]

    assert table["row_count"] == 2
    assert table["column_count"] == 2
    assert len(table["cells"]) == 1
    assert table["cells"][0]["rowspan"] == 2
    assert table["cells"][0]["colspan"] == 2
    assert table["cells"][0]["width"] == 200
    assert table["cells"][0]["height"] == 40


def test_checkbox_state_is_preserved(monkeypatch):
    monkeypatch.setattr("agents.form_extraction_agent._get_form_agent", lambda: None)
    slide = SimpleNamespace(
        slide_number=1,
        background_color=None,
        elements=[
            _element(
                "cb-1",
                "checkbox",
                _position(10, 10, 12, 12),
                metadata={"is_checked": True, "z_order": 1},
            )
        ],
    )

    result = FormExtractionAgent().run(slide)
    checkbox = result["document"]["elements"][0]

    assert checkbox["type"] == "checkbox"
    assert checkbox["checked"] is True


def test_page_metadata_is_populated(monkeypatch):
    monkeypatch.setattr("agents.form_extraction_agent._get_form_agent", lambda: None)
    slide = SimpleNamespace(
        slide_number=1,
        background_color="#ffffff",
        elements=[
            _element("text", "text_box", _position(0, 0, 100, 50), text="A")
        ],
    )

    result = FormExtractionAgent(
        {"slide_width": EMU_PER_PIXEL * 200, "slide_height": EMU_PER_PIXEL * 100}
    ).run(slide)
    document = result["document"]

    assert document["page_orientation"] == "landscape"
    assert document["units"] == "pixels"
    assert document["scan_rotation"] == 0


def test_form_renderer_deterministic():
    from services.form_renderer import FormRenderer
    payload = {
        "page_width": 200,
        "page_height": 100,
        "background_color": "#ffffff",
        "lines": [
            {"x1": 10, "y1": 20, "x2": 50, "y2": 20, "stroke_width": 2, "stroke_color": "#000000"}
        ],
        "rectangles": [
            {"x": 10, "y": 30, "width": 40, "height": 20, "stroke_width": 1, "stroke_color": "#ff0000", "fill_color": "#00ff00"}
        ],
        "checkboxes": [
            {"x": 10, "y": 60, "width": 15, "height": 15, "checked": True}
        ],
        "text_blocks": [
            {"x": 60, "y": 20, "width": 100, "height": 30, "text": "Hello World", "font_size": 12, "text_color": "#0000ff"}
        ]
    }
    renderer = FormRenderer()
    img = renderer.render_to_image(payload)
    assert img.size == (200, 100)
    # Check that background color is correct (e.g. top-left pixel is white)
    assert img.getpixel((0, 0)) == (255, 255, 255)


def test_line_and_checkbox_extraction_from_image_fallback(monkeypatch):
    import base64
    from PIL import Image, ImageDraw
    from io import BytesIO

    monkeypatch.setattr("agents.form_extraction_agent._get_form_agent", lambda: None)
    
    # Create an image containing a line and a checkbox outline
    img = Image.new("RGB", (200, 100), "#ffffff")
    draw = ImageDraw.Draw(img)
    # Draw horizontal line
    draw.line([10, 20, 100, 20], fill="#000000", width=2)
    # Draw square checkbox
    draw.rectangle([10, 40, 25, 55], outline="#000000", width=1)
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    img_bytes = buf.getvalue()
    
    slide = SimpleNamespace(
        slide_number=1,
        background_color="#ffffff",
        image_base64="data:image/png;base64," + base64.b64encode(img_bytes).decode("ascii"),
        elements=[]
    )
    
    agent = FormExtractionAgent()
    result = agent.run(slide)
    
    doc = result["document"]
    # Check lines
    assert len(doc["lines"]) > 0
    # Check checkboxes
    assert len(doc["checkboxes"]) > 0


def test_extraction_validator(tmp_path):
    from services.extraction_validator import ExtractionValidator
    from PIL import Image

    # Create two slightly different images
    img1 = Image.new("RGB", (100, 100), "#ffffff")
    img2 = Image.new("RGB", (100, 100), "#ffffff")
    
    # Draw a line in img1
    from PIL import ImageDraw
    draw1 = ImageDraw.Draw(img1)
    draw1.line([0, 50, 100, 50], fill="#000000", width=2)
    
    p1 = tmp_path / "img1.png"
    p2 = tmp_path / "img2.png"
    img1.save(p1)
    img2.save(p2)
    
    scores = ExtractionValidator.compare_images(str(p1), str(p2))
    assert "ssim" in scores
    assert "layout_similarity" in scores
    assert "border_similarity" in scores
    assert "passed" in scores


def test_extraction_service_url(monkeypatch, tmp_path):
    from services.extraction_service import ExtractionService
    import requests

    class DummyResponse:
        def __init__(self):
            self.headers = {"content-type": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}
        def raise_for_status(self):
            pass
        def iter_content(self, chunk_size=8192):
            with open("AetherMind_Speaker_Presentation_Detailed.pptx", "rb") as f:
                yield f.read()

    def mock_get(url, stream=True, timeout=60):
        return DummyResponse()

    monkeypatch.setattr(requests, "get", mock_get)

    service = ExtractionService("https://example.com/some/presentation.pptx")
    assert service.document_extension == ".pptx"

    import asyncio
    document_model = asyncio.run(service.extract_document())
    assert document_model is not None

    json_path = service.export_to_json(document_model, output_directory=str(tmp_path))
    assert "presentation_reconstruction.json" in str(json_path)

