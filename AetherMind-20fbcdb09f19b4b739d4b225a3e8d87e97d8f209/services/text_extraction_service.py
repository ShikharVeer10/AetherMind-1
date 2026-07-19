
from typing import List
from models.document_model import DocumentElementModel, TextPointModel
class TextExtractionService:
    def extract(self, elements: List[DocumentElementModel]) -> List[TextPointModel]:
        ordered = sorted(elements, key=lambda e: (e.position.y, e.position.x))
        points: List[TextPointModel] = []
        for element in ordered:
            if element.paragraphs:
                for para in element.paragraphs:
                    points.append(
                        TextPointModel(
                            element_id=element.element_id,
                            level=para.level,
                            text=para.text,
                        )
                    )
                continue
            if element.text:
                for line in element.text.splitlines():
                    cleaned = line.strip()
                    if cleaned:
                        points.append(
                            TextPointModel(
                                element_id=element.element_id,
                                level=0,
                                text=cleaned,
                            )
                        )

        return points
