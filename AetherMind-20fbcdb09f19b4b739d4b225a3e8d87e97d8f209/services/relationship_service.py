from typing import List
from models.document_model import DocumentElementModel, RelationshipModel
_PROXIMITY_THRESHOLD = 500_000


class RelationshipService:

    def detect(self, elements: List[DocumentElementModel]) -> List[RelationshipModel]:
        relationships: List[RelationshipModel] = []

        connectors = [
            e for e in elements if e.element_type in {"arrow", "connector"}
        ]
        boxes = [
            e for e in elements
            if e.element_type not in {"arrow", "connector"}
        ]

        for connector in connectors:
            linked = self._find_connector_targets(connector, boxes)
            if linked:
                relationships.append(linked)

        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:

                if self._is_contained(a, b):
                    relationships.append(
                    RelationshipModel(
                    relationship_type="contains",
                    source_element_id=b.element_id,
                    target_element_id=a.element_id,
                )
            )

                elif self._is_contained(b, a):
                    relationships.append(
                        RelationshipModel(
                        relationship_type="contains",
                        source_element_id=a.element_id,
                        target_element_id=b.element_id,
                    )
                )
                elif self._is_hierarchy(a, b):
                    relationships.append(
                        RelationshipModel(
                            relationship_type="hierarchy",
                            source_element_id=a.element_id,
                            target_element_id=b.element_id,
                            confidence=0.8,
                        )
                    )

                elif self._is_hierarchy(b, a):
                    relationships.append(
                        RelationshipModel(
                            relationship_type="hierarchy",
                            source_element_id=b.element_id,
                            target_element_id=a.element_id,
                            confidence=0.8,
                        )
                    )

                elif self._is_proximate(a, b):
                    relationships.append(
                        RelationshipModel(
                            relationship_type="proximity",
                            source_element_id=a.element_id,
                            target_element_id=b.element_id,
                            confidence=0.7,
                        )   
                    )

            return relationships

    @staticmethod
    def _infer_semantic_relationship(
        source: DocumentElementModel,
        target: DocumentElementModel,
        connector: DocumentElementModel,
    )    -> str:
        label = (connector.text or "").strip().lower()

        if label in {"yes", "no"}:
            return "decision"

        if label in {"next", "continue"}:
            return "process_flow"

        if "cause" in label:
            return "cause_effect"

        if "approve" in label:
            return "decision"

        if "reject" in label:
            return "decision"

        return "flow"

    @staticmethod
    def _connector_direction(begin, end) -> str:
        dx = end[0] - begin[0]
        dy = end[1] - begin[1]

        if abs(dx) > abs(dy):
            return "left_to_right" if dx > 0 else "right_to_left"

        return "top_to_bottom" if dy > 0 else "bottom_to_top"

    @staticmethod
    def _center(element: DocumentElementModel):
        cx = element.position.x + element.position.width / 2
        cy = element.position.y + element.position.height / 2
        return cx, cy

    def _find_connector_targets(self,connector: DocumentElementModel,boxes: List[DocumentElementModel],) -> RelationshipModel | None:
        endpoints = connector.metadata.get("connector_endpoints", {})
        if not endpoints:
            return None

        begin = (endpoints.get("begin_x"), endpoints.get("begin_y"))
        end = (endpoints.get("end_x"), endpoints.get("end_y"))

        if begin[0] is None or begin[1] is None or end[0] is None or end[1] is None:
            return None

        source = self._closest_box(begin, boxes)
        target = self._closest_box(end, boxes)

        if source and target and source.element_id != target.element_id:
            direction = self._connector_direction(begin, end)

            semantic_relation = self._infer_semantic_relationship(
                source,
                target,
                connector,
            )

            return RelationshipModel(
                relationship_type="connector",
                source_element_id=source.element_id,
                target_element_id=target.element_id,
                label=connector.text,
                semantic_relation=semantic_relation,
                direction=direction,
                confidence=0.95,
            )
            return None

    def _closest_box(self, point, boxes):
        best = None
        best_dist = float("inf")
        for box in boxes:
            cx, cy = self._center(box)
            dist = ((point[0] - cx) ** 2 + (point[1] - cy) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best = box
        return best

    @staticmethod
    def _is_contained(inner: DocumentElementModel, outer: DocumentElementModel) -> bool:
        return (
            inner.position.x >= outer.position.x
            and inner.position.y >= outer.position.y
            and (inner.position.x + inner.position.width)
            <= (outer.position.x + outer.position.width)
            and (inner.position.y + inner.position.height)
            <= (outer.position.y + outer.position.height)
        )

    @staticmethod
    def _is_hierarchy(parent: DocumentElementModel,child: DocumentElementModel,) -> bool:
        parent_center_x = (parent.position.x + parent.position.width / 2)
        child_center_x = (child.position.x + child.position.width / 2)
        # Same vertical column
        same_column = abs(parent_center_x - child_center_x) < 100000
        # Child below parent
        below_parent = child.position.y > parent.position.y

        return same_column and below_parent




    @staticmethod
    def _is_proximate(a: DocumentElementModel, b: DocumentElementModel) -> bool:
        a_cx = a.position.x + a.position.width / 2
        a_cy = a.position.y + a.position.height / 2
        b_cx = b.position.x + b.position.width / 2
        b_cy = b.position.y + b.position.height / 2
        dist = ((a_cx - b_cx) ** 2 + (a_cy - b_cy) ** 2) ** 0.5
        return dist < _PROXIMITY_THRESHOLD
    

    @staticmethod
    def _is_hierarchy(parent: DocumentElementModel,child: DocumentElementModel,)-> bool:
        parent_center_x = parent.position.x + parent.position.width / 2
        child_center_x = child.position.x + child.position.width / 2
        same_column = abs(parent_center_x - child_center_x) < 100000
        below_parent = child.position.y > parent.position.y
        return same_column and below_parent