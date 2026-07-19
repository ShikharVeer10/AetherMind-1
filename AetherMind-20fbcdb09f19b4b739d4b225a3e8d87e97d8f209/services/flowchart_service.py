"""
Detects whether a slide contains a flowchart and, if so, extracts:
    - Box count and box details (text, position)
    - Arrow/connector count
    - Relationship graph between boxes
    - Reading order (topological sort of the directed graph)
"""

from typing import Dict, List, Set
from models.document_model import (
    DocumentElementModel,
    FlowchartModel,
    RelationshipModel,
)


_MIN_BOXES = 2
_MIN_ARROWS = 1


class FlowchartService:

    def analyse(
        self,
        elements: List[DocumentElementModel],
        relationships: List[RelationshipModel],
    ) -> FlowchartModel:
        """
        Determine if the slide looks like a flowchart and, if so,
        build a FlowchartModel with counts + directed graph.
        """
        box_types = {"shape", "text_box", "placeholder", "unknown"}
        arrow_types = {"arrow", "connector", "freeform"}

        boxes = [
            e for e in elements
            if e.element_type in box_types
        ]
        arrows = [
            e for e in elements
            if e.element_type in arrow_types
        ]

        is_flowchart = (
            len(boxes) >= _MIN_BOXES and len(arrows) >= _MIN_ARROWS
        )

        box_details = [
            {
                "element_id": b.element_id,
                "text": b.text,
                "x": b.position.x,
                "y": b.position.y,
            }
            for b in boxes
        ]

        arrow_details = [
            {
                "element_id": a.element_id,
                "text": a.text,
                "type": a.element_type,
            }
            for a in arrows
        ]

        box_ids = {b.element_id for b in boxes}
        flow_rels = [
            r for r in relationships
            if r.source_element_id in box_ids
            and r.target_element_id in box_ids
        ]

        reading_order = self._topological_sort(box_ids, flow_rels, elements)
        decision_nodes = self._detect_decision_nodes(boxes)

        start_nodes, end_nodes = (
            self._detect_start_end_nodes(
                box_ids,
                flow_rels,
            )
        )

        flow_type = self._detect_flow_type(box_ids,flow_rels,)

        relationship_mapping = (self._build_relationship_mapping(boxes,flow_rels,))

        reading_order_labels = (self._build_reading_order_labels(reading_order,boxes,))

        process_summary = (self._generate_process_summary(reading_order_labels))

        return FlowchartModel(is_flowchart=is_flowchart,box_count=len(boxes),arrow_count=len(arrows),decision_node_count=len(decision_nodes),start_nodes=start_nodes,end_nodes=end_nodes,flow_type=flow_type,boxes=box_details,arrows=arrow_details,relationships=flow_rels,relationship_mapping=relationship_mapping,reading_order=reading_order,reading_order_labels=reading_order_labels,process_summary=process_summary,)

    def _detect_decision_nodes(self,boxes: List[DocumentElementModel]) -> list[str]:

        decision_nodes = []

        for box in boxes:

            text = (box.text or "").lower()

            if (
            "?" in text
            or "decision" in text
            or "approve" in text
            or "valid" in text
        ):
                decision_nodes.append(box.element_id)

        return decision_nodes
    
    def _detect_start_end_nodes(self,box_ids,flow_rels,boxes,):
        incoming = {}
        outgoing = {}

        for box_id in box_ids:
            incoming[box_id] = 0
            outgoing[box_id] = 0

        for rel in flow_rels:
            outgoing[rel.source_element_id] += 1
            incoming[rel.target_element_id] += 1

        start_nodes = [
            n for n in box_ids
            if incoming[n] == 0
        ]

        end_nodes = [
            n for n in box_ids
            if outgoing[n] == 0
        ]
        return start_nodes, end_nodes



    @staticmethod
    def _topological_sort(node_ids: Set[str],edges: List[RelationshipModel],elements: List[DocumentElementModel] = None,) -> List[str]:
        adj: Dict[str, List[str]] = {nid: [] for nid in node_ids}
        in_degree: Dict[str, int] = {nid: 0 for nid in node_ids}
        for edge in edges:
            src, tgt = edge.source_element_id, edge.target_element_id
            if src in adj:
                adj[src].append(tgt)
            if tgt in in_degree:
                in_degree[tgt] += 1
        queue = sorted(
            [nid for nid, deg in in_degree.items() if deg == 0]
        )
        result: List[str] = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            for neighbour in adj.get(node, []):
                in_degree[neighbour] -= 1
                if in_degree[neighbour] == 0:
                    queue.append(neighbour)

        remaining = [nid for nid in node_ids if nid not in result]
        if remaining and elements:
            pos_lookup = {
                e.element_id: (e.position.y, e.position.x)
                for e in elements
            }
            remaining.sort(key=lambda nid: pos_lookup.get(nid, (0, 0)))
        result.extend(remaining)

        return result

    def _detect_decision_nodes(self,boxes: List[DocumentElementModel],) -> List[str]:
        decision_nodes = []
        keywords = {
        "decision",
        "approve",
        "reject",
        "valid",
        "invalid",
        "yes",
        "no",
        }
        for box in boxes:
            text = (box.text or "").lower()
            if "?" in text:
                decision_nodes.append(box.element_id)
                continue
            if any(keyword in text for keyword in keywords):
                decision_nodes.append(box.element_id)
        return decision_nodes


    def _detect_start_end_nodes(self,box_ids: Set[str],flow_rels: List[RelationshipModel],):
        incoming = {box_id: 0 for box_id in box_ids}
        outgoing = {box_id: 0 for box_id in box_ids}
        for rel in flow_rels:
            outgoing[rel.source_element_id] += 1
            incoming[rel.target_element_id] += 1
        start_nodes = [
            node
            for node in box_ids
                if incoming[node] == 0
            ]
        end_nodes = [
            node
            for node in box_ids
            if outgoing[node] == 0
        ]
        return start_nodes, end_nodes
    
    def _detect_flow_type(self,box_ids: Set[str],flow_rels: List[RelationshipModel],) -> str:

        outgoing = {box_id: 0 for box_id in box_ids}

        for rel in flow_rels:
            outgoing[rel.source_element_id] += 1

        if any(count > 1 for count in outgoing.values()):
            return "branching"

        if len(flow_rels) >= len(box_ids):
            return "cyclic"

        return "linear"

    def _build_relationship_mapping(self,boxes: List[DocumentElementModel],flow_rels: List[RelationshipModel],):

        mapping = []

        for rel in flow_rels:

            source_text = next((box.text for box in boxes if box.element_id == rel.source_element_id),rel.source_element_id,)

            target_text = next(
            (
                box.text
                for box in boxes
                if box.element_id == rel.target_element_id
            ),
            rel.target_element_id,
        )

        mapping.append(
            {
                "from": source_text,
                "to": target_text,
                "type": rel.relationship_type,
            }
        )

        return mapping

    def _build_reading_order_labels(
    self,
    reading_order,
    boxes,
):

        labels = []

        for node_id in reading_order:

            box = next(
            (
                b
                for b in boxes
                if b.element_id == node_id
            ),
            None,
        )

        if box:
            labels.append(box.text or node_id)

        return labels
    
    def _generate_process_summary(
    self,
    reading_order_labels,
):

        labels = [
            label
            for label in reading_order_labels
                if label
        ]
        if len(labels) < 2:
            return ""
        return (
        "Process flow: "
        + " -> ".join(labels)
        )


    def _detect_flow_type(self,flow_rels,boxes):
        "linear"
        "branching"
        "cyclic"
        "hub_spoke"
        "timeline"

        relationship_mapping = []
        for rel in flow_rels:
            source = next(
        (
            b.text
            for b in boxes
            if b.element_id == rel.source_element_id
        ),
        rel.source_element_id
    )

        target = next(
        (
            b.text
            for b in boxes
            if b.element_id == rel.target_element_id
        ),
        rel.target_element_id
    )

        relationship_mapping.append({
        "from": source,
        "to": target,
        "type": rel.relationship_type,
    })
