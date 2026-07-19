from collections import defaultdict
import fitz
class LayoutStructureService:
    def extract_layout_regions(self, page):
        drawings = page.get_drawings()
        text_dict = page.get_text("dict")
        horizontal_lines = []
        vertical_lines = []
        for drawing in drawings:
            for item in drawing["items"]:
                if item[0] != "l":
                    continue
                p1 = item[1]
                p2 = item[2]
                x1, y1 = p1.x, p1.y
                x2, y2 = p2.x, p2.y
                if abs(y1 - y2) < 2:
                    horizontal_lines.append((x1, y1, x2, y2))
                elif abs(x1 - x2) < 2:
                    vertical_lines.append((x1, y1, x2, y2))

        text_blocks = []

        for block in text_dict.get("blocks", []):

            if block.get("type") != 0:
                continue

            bbox = block["bbox"]

            text = ""

            for line in block.get("lines", []):

                for span in line.get("spans", []):

                    text += span.get("text", "")

            text = text.strip()

            if text:

                text_blocks.append(
                    {
                        "bbox": bbox,
                        "text": text,
                    }
                )

        return {
            "horizontal_lines": horizontal_lines,
            "vertical_lines": vertical_lines,
            "text_blocks": text_blocks,
        }

    def build_grid_structure(self, page):

        layout = self.extract_layout_regions(page)

        horizontal = sorted(
            layout["horizontal_lines"],
            key=lambda x: x[1]
        )

        vertical = sorted(
            layout["vertical_lines"],
            key=lambda x: x[0]
        )

        cells = []

        for block in layout["text_blocks"]:

            bbox = block["bbox"]

            cells.append(
                {
                    "bbox": {
                        "x": bbox[0],
                        "y": bbox[1],
                        "width": bbox[2] - bbox[0],
                        "height": bbox[3] - bbox[1],
                    },
                    "text": block["text"],
                }
            )

        return {
            "region_type": "grid",
            "rows": len(horizontal),
            "columns": len(vertical),
            "cells": cells,
        }