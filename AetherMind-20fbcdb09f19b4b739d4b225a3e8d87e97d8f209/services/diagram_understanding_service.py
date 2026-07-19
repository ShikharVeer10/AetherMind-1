from typing import Dict, List

from models.document_model import (
    DiagramUnderstandingModel,
    DocumentElementModel,
    FlowchartModel,
    RelationshipModel,
)

_SLIDE_WIDTH_EMU = 12192000.0
_SLIDE_HEIGHT_EMU = 6858000.0


class DiagramUnderstandingService:
    def analyse(
        self,
        elements: List[DocumentElementModel],
        relationships: List[RelationshipModel],
        flowchart: FlowchartModel,
    ) -> DiagramUnderstandingModel:

        relationships = relationships or []
        elements = elements or []

        if flowchart is None:
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



        semantic_nodes = self._semantic_nodes(elements, flowchart)
        nodes = [
            {
                "element_id": e.element_id,
                "type": e.element_type,
                "text": e.text,
            }
            for e in semantic_nodes
        ]
        connector_edges = [
            {
                "type": r.relationship_type,
                "source": r.source_element_id,
                "target": r.target_element_id,
                "label": r.label,
            }
            for r in relationships
            if r.relationship_type == "connector"
        ]
        edges = connector_edges or [
            {
                "type": r.relationship_type,
                "source": r.source_element_id,
                "target": r.target_element_id,
                "label": r.label,
            }
            for r in relationships
        ]

        is_diagram = flowchart.is_flowchart or any(
            e.element_type in {"shape", "image", "chart"} for e in elements
        )
        diagram_type = (
            "flowchart" if flowchart.is_flowchart
            else "diagram" if is_diagram
            else "none"
        )
        element_lookup: Dict[str, str] = {
            e.element_id: (e.text or "").strip().replace("\n", " ") or f"[{e.element_id}]"
            for e in elements
        }

        flow_description = self._build_flow_description(
            flowchart, element_lookup, relationships
        )
        summary = self._build_summary(
            is_diagram=is_diagram,
            diagram_type=diagram_type,
            flowchart=flowchart,
            nodes=nodes,
            edges=edges,
            element_lookup=element_lookup,
            flow_description=flow_description,
            elements=elements,
            relationships=relationships,
        )

        return DiagramUnderstandingModel(
            is_diagram=is_diagram,
            diagram_type=diagram_type,
            node_count=len(nodes),
            edge_count=len(edges),
            nodes=nodes,
            edges=edges,
            flow_description=flow_description,
            summary=summary,
        )

    def _semantic_nodes(
        self,
        elements: List[DocumentElementModel],
        flowchart: FlowchartModel,
    ) -> List[DocumentElementModel]:
        """Prefer flowchart boxes over all non-connector elements to avoid inflated counts."""
        if flowchart and flowchart.is_flowchart and flowchart.boxes:
            box_ids = {b["element_id"] for b in flowchart.boxes}
            return [e for e in elements if e.element_id in box_ids]

        return [
            e for e in elements
            if e.element_type not in {"arrow", "connector", "group"}
        ]

    def _build_flow_description(
        self,
        flowchart: FlowchartModel,
        element_lookup: Dict[str, str],
        relationships: List[RelationshipModel],
    ) -> str:
        if not flowchart.is_flowchart:
            return ""

        parts: List[str] = []

        if flowchart.reading_order:
            flow_steps = []
            for i, eid in enumerate(flowchart.reading_order, start=1):
                label = element_lookup.get(eid, eid)
                flow_steps.append(f"Step {i}: {label}")
            parts.append(" → ".join(flow_steps))

        connector_rels = [
            r for r in (flowchart.relationships or relationships)
            if r.relationship_type == "connector"
        ] or (flowchart.relationships or [])

        branch_lines: List[str] = []
        for rel in connector_rels:
            src = element_lookup.get(rel.source_element_id, rel.source_element_id)
            tgt = element_lookup.get(rel.target_element_id, rel.target_element_id)
            if rel.label:
                branch_lines.append(f"{rel.label} → {tgt}")
            elif "?" in src:
                branch_lines.append(f"{src}: branches to {tgt}")
            else:
                branch_lines.append(f"{src} → {tgt}")

        if branch_lines:
            parts.append("Branches: " + "; ".join(branch_lines))

        return " | ".join(parts)

    def _region_label(self, element: DocumentElementModel) -> str:
        cx = element.position.x + element.position.width / 2
        cy = element.position.y + element.position.height / 2
        x_pct = cx / _SLIDE_WIDTH_EMU
        y_pct = cy / _SLIDE_HEIGHT_EMU

        if y_pct < 0.2:
            return "top"
        if y_pct > 0.8:
            return "bottom"
        if x_pct < 0.4:
            return "left"
        if x_pct > 0.6:
            return "right"
        return "center"

    def _build_layout_blueprint(
        self,
        elements: List[DocumentElementModel],
        element_lookup: Dict[str, str],
    ) -> str:
        regions: Dict[str, List[str]] = {
            "left": [],
            "right": [],
            "top": [],
            "bottom": [],
            "center": [],
        }

        for element in elements:
            if element.element_type in {"arrow", "connector"}:
                continue
            label = element_lookup.get(element.element_id, "")
            if label.startswith("["):
                continue
            regions[self._region_label(element)].append(label)

        lines: List[str] = []
        for name in ("left", "right", "top", "bottom", "center"):
            items = regions[name]
            if items:
                lines.append(f"{name.capitalize()} section: {'; '.join(items)}")
        return "; ".join(lines) if lines else ""

    def _build_decision_structure(
        self,
        elements: List[DocumentElementModel],
        element_lookup: Dict[str, str],
        relationships: List[RelationshipModel],
    ) -> str:
        decisions = [
            element_lookup[e.element_id]
            for e in elements
            if e.text and "?" in e.text
        ]
        if not decisions:
            return ""

        lines: List[str] = []
        for decision in decisions:
            lines.append(f"Decision: {decision}")
            decision_id = next(
                (eid for eid, label in element_lookup.items() if label == decision),
                None,
            )
            if not decision_id:
                continue
            for rel in relationships:
                if rel.source_element_id != decision_id:
                    continue
                tgt = element_lookup.get(rel.target_element_id, rel.target_element_id)
                if rel.label:
                    lines.append(f"  {rel.label} → {tgt}")
                else:
                    lines.append(f"  → {tgt}")

        return " ".join(lines)

    def _build_summary(
        self,
        is_diagram: bool,
        diagram_type: str,
        flowchart: FlowchartModel,
        nodes: list,
        edges: list,
        element_lookup: Dict[str, str],
        flow_description: str,
        elements: List[DocumentElementModel],
        relationships: List[RelationshipModel],
    ) -> str:
        summary_parts: List[str] = []

        if not is_diagram:
            summary_parts.append("No diagram detected.")
            return " ".join(summary_parts)

        exact_texts = [
            element_lookup[e.element_id]
            for e in elements
            if element_lookup.get(e.element_id, "").startswith("[") is False
            and element_lookup.get(e.element_id, "")
        ]
        if exact_texts:
            summary_parts.append(
                "[Exact Text] " + " | ".join(dict.fromkeys(exact_texts)) + "."
            )

        flow_rels = (
            flowchart.relationships if flowchart.is_flowchart and flowchart.relationships
            else relationships
        )
        decision_structure = self._build_decision_structure(
            elements, element_lookup, flow_rels
        )
        if decision_structure:
            summary_parts.append(f"[Decision Structure] {decision_structure}.")

        box_count = flowchart.box_count if flowchart.is_flowchart else len(nodes)
        arrow_count = flowchart.arrow_count if flowchart.is_flowchart else 0
        summary_parts.append(
            f"[Counts] {diagram_type.capitalize()} with "
            f"{box_count} box(es), {arrow_count} arrow(s), "
            f"{len(nodes)} node(s), and {len(edges)} relationship(s)."
        )

        if edges:
            edge_descriptions = []
            for e in edges:
                src_label = element_lookup.get(e["source"], e["source"])
                tgt_label = element_lookup.get(e["target"], e["target"])
                rel_type = e["type"]
                desc = f'"{src_label}" → "{tgt_label}" ({rel_type})'
                if e.get("label"):
                    desc += f' [label: {e["label"]}]'
                edge_descriptions.append(desc)
            summary_parts.append(
                "[Connections] " + "; ".join(edge_descriptions) + "."
            )

        if flow_description:
            summary_parts.append(f"[Flow] {flow_description}.")

        layout_blueprint = self._build_layout_blueprint(elements, element_lookup)
        if layout_blueprint:
            summary_parts.append(f"[Layout Blueprint] {layout_blueprint}.")

        if flowchart.is_flowchart:
            first_label = element_lookup.get(
                flowchart.reading_order[0], ""
            ) if flowchart.reading_order else ""
            last_label = element_lookup.get(
                flowchart.reading_order[-1], ""
            ) if flowchart.reading_order else ""
            if first_label and last_label and first_label != last_label:
                summary_parts.append(
                    f'[Interpretation] Process begins with "{first_label}" '
                    f'and concludes with "{last_label}", through {box_count} stage(s).'
                )
            else:
                summary_parts.append(
                    f"[Interpretation] Flowchart with {box_count} step(s)."
                )
        else:
            node_labels = [
                element_lookup.get(n["element_id"], n["element_id"])
                for n in nodes
                if not element_lookup.get(n["element_id"], "").startswith("[")
            ]
            if node_labels:
                summary_parts.append(
                    f"[Diagram Structure] Components: {'; '.join(node_labels)}."
                )

        return " ".join(summary_parts)
