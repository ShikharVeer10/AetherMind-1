from typing import List
from models.document_model import DocumentElementModel, PositionMapModel
class PositionMappingService:
    def build(self, elements: List[DocumentElementModel]) -> List[PositionMapModel]:
        return [
            PositionMapModel(
                element_id=e.element_id,
                element_type=e.element_type,
                x=e.position.x,
                y=e.position.y,
                width=e.position.width,
                height=e.position.height,
            )
            for e in elements
        ]
