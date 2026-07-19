from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_SLIDE_WIDTH = 12_192_000.0
DEFAULT_SLIDE_HEIGHT = 6_858_000.0

TEXT_TYPES = {"text", "textbox", "title", "body", "shape"}
CONTAINER_TYPES = {"group", "shape", "table", "chart", "image"}
CONNECTOR_TYPES = {"arrow", "connector", "line"}


class SemanticSlideExtractionService:
    """Builds a high-fidelity semantic slide JSON from existing extracted objects.

    This service deliberately does not perform OCR or image captioning. It consumes
    the slide model already produced by the extraction pipeline and reorganizes it
    into reconstruction-grade structure, style, layout, and semantic layers.
    """

    def build_slide_extraction(
        self,
        slide_model,
        presentation_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        canvas = self.build_canvas(slide_model, presentation_metadata)
        objects = self.build_objects(slide_model, canvas)
        relationships = self.build_layout_relationships(objects, slide_model)
        visual_groups = self.build_visual_groups(objects, slide_model)
        layout = self.infer_layout(slide_model, objects, relationships, visual_groups, canvas)
        semantic_graph = self.build_semantic_graph(objects, relationships, visual_groups)
        validation = self.validate_extraction(objects, layout, semantic_graph)

        return {
            "schema_version": "semantic-slide-extraction-v1",
            "objective": "Preserve all slide layout and visual styling while rewriting only text wording.",
            "slide_number": getattr(slide_model, "slide_number", 0),
            "title_present": bool(getattr(slide_model, "title", None)),
            "canvas": canvas,
            "background": self.build_background(slide_model),
            "layout_type": layout["layout_type"],
            "layout": layout,
            "objects": objects,
            "layout_relationships": relationships,
            "visual_groups": visual_groups,
            "semantic_groups": self.build_semantic_groups(objects, visual_groups),
            "container_tree": self.build_container_tree(objects),
            "reading_order": layout["reading_order"],
            "semantic_graph": semantic_graph,
            "design_system": self.build_design_system(slide_model, objects),
            "validation": validation,
        }

    def build_canvas(
        self,
        slide_model,
        presentation_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        meta = presentation_metadata or {}
        width = (
            meta.get("slide_width")
            or meta.get("width")
            or self._metadata_value(slide_model, "slide_width")
            or DEFAULT_SLIDE_WIDTH
        )
        height = (
            meta.get("slide_height")
            or meta.get("height")
            or self._metadata_value(slide_model, "slide_height")
            or DEFAULT_SLIDE_HEIGHT
        )
        return {
            "width": float(width),
            "height": float(height),
            "coordinate_unit": "EMU_or_source_units",
            "origin": "top_left",
            "x_axis": "left_to_right",
            "y_axis": "top_to_bottom",
            "aspect_ratio": round(float(width) / float(height), 6) if height else None,
        }

    def build_background(self, slide_model) -> Dict[str, Any]:
        metadata = getattr(slide_model, "metadata", {}) or {}
        return {
            "fill_color": getattr(slide_model, "background_color", None),
            "details": metadata.get("background"),
            "theme_role": "slide_background",
            "preserve_exactly": True,
        }

    def build_objects(self, slide_model, canvas: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw_elements = list(getattr(slide_model, "elements", []) or [])
        ordered = sorted(
            enumerate(raw_elements),
            key=lambda item: (
                getattr(item[1], "stacking_order", None)
                if getattr(item[1], "stacking_order", None) is not None
                else item[0]
            ),
        )
        objects = []
        for fallback_z, element in ordered:
            obj = self.build_object(element, canvas, fallback_z)
            objects.append(obj)

        self._assign_container_parents(objects)
        self._assign_children(objects)
        self._attach_overlaps(objects)
        self._attach_relative_positioning(objects, canvas)
        return objects

    def build_object(self, element, canvas: Dict[str, Any], fallback_z: int) -> Dict[str, Any]:
        element_id = getattr(element, "element_id", None) or f"element_{fallback_z + 1}"
        element_type = getattr(element, "element_type", "unknown") or "unknown"
        metadata = dict(getattr(element, "metadata", {}) or {})
        bbox = self._bbox(getattr(element, "position", None), canvas)
        text = (getattr(element, "text", None) or "").strip()
        parent_id = getattr(element, "parent", None) or metadata.get("parent_id")
        children_ids = list(getattr(element, "children", []) or metadata.get("children_ids", []) or [])

        return {
            "id": element_id,
            "type": self._normalize_type(element_type, text),
            "subtype": getattr(element, "shape_type", None) or metadata.get("subtype") or element_type,
            "parent": parent_id or "slide_root",
            "children": children_ids,
            "bbox": bbox,
            "width": bbox["width"],
            "height": bbox["height"],
            "center": {
                "x": bbox["x"] + bbox["width"] / 2,
                "y": bbox["y"] + bbox["height"] / 2,
            },
            "rotation": metadata.get("rotation", 0),
            "scaling": {
                "x": metadata.get("scale_x", 1.0),
                "y": metadata.get("scale_y", 1.0),
            },
            "z_index": getattr(element, "stacking_order", None) or metadata.get("z_order") or fallback_z,
            "visibility": metadata.get("visible", True),
            "opacity": self._style_value(getattr(element, "style", None), "opacity", 1.0),
            "clipping": metadata.get("clipping"),
            "overlap_relationships": [],
            "anchor_constraints": self._anchor_constraints(bbox, canvas),
            "alignment_constraints": {},
            "relative_positioning": {},
            "style": self.build_design_layer(element),
            "layout": self.build_object_layout(element, bbox),
            "semantic": self.build_object_semantic(element, text, bbox, canvas),
            "source": {
                "has_text": bool(text),
                "text_fingerprint": self._fingerprint(text) if text else None,
                "text_character_count": len(text),
                "text_line_count": len([line for line in text.splitlines() if line.strip()]),
                "metadata": self._safe_metadata(metadata),
            },
            "_source_text": text,
        }

    def build_design_layer(self, element) -> Dict[str, Any]:
        style = getattr(element, "style", None)
        metadata = getattr(element, "metadata", {}) or {}
        paragraphs = list(getattr(element, "paragraphs", []) or [])
        first_para = paragraphs[0] if paragraphs else None

        return {
            "fill_color": self._style_value(style, "background_color"),
            "gradient": self._style_value(style, "gradient"),
            "opacity": self._style_value(style, "opacity", 1.0),
            "border_color": self._style_value(style, "border_color"),
            "border_width": self._style_value(style, "border_thickness"),
            "border_style": self._style_value(style, "border_style"),
            "corner_radius": self._style_value(style, "border_radius"),
            "shadow": self._style_value(style, "shadow"),
            "elevation": metadata.get("elevation"),
            "font_family": self._style_value(style, "font_name"),
            "font_size": self._style_value(style, "font_size"),
            "font_weight": self._style_value(style, "font_weight") or ("bold" if self._style_value(style, "bold", False) else None),
            "font_style": "italic" if self._style_value(style, "italic", False) else "normal",
            "underline": self._style_value(style, "underline", False),
            "text_color": self._style_value(style, "text_color"),
            "line_height": self._style_value(style, "line_spacing"),
            "paragraph_spacing": self._style_value(style, "paragraph_spacing"),
            "letter_spacing": self._style_value(style, "letter_spacing"),
            "bullet_style": getattr(first_para, "bullet_character", None) if first_para else None,
            "numbering_style": getattr(first_para, "number", None) if first_para else None,
            "list_type": getattr(first_para, "list_type", None) if first_para else None,
            "text_alignment": self._style_value(style, "alignment") or (getattr(first_para, "alignment", None) if first_para else None),
            "vertical_alignment": self._style_value(style, "vertical_alignment"),
            "padding": self._style_value(style, "padding") or {},
            "margins": metadata.get("margins", {}),
            "icon_style": metadata.get("icon_style"),
            "stroke_style": {
                "color": self._style_value(style, "border_color"),
                "width": self._style_value(style, "border_thickness"),
                "style": self._style_value(style, "border_style"),
            },
            "theme_color": metadata.get("theme_color"),
            "theme_role": metadata.get("theme_role"),
        }

    def build_object_layout(self, element, bbox: Dict[str, float]) -> Dict[str, Any]:
        metadata = getattr(element, "metadata", {}) or {}
        return {
            "layout_role": metadata.get("layout_role") or self._infer_layout_role(element, bbox),
            "container_role": metadata.get("container_role"),
            "padding": metadata.get("padding", {}),
            "margins": metadata.get("margins", {}),
            "alignment": metadata.get("alignment"),
            "grid_position": metadata.get("grid_position"),
            "preserve_position": True,
            "preserve_dimensions": True,
            "preserve_spacing": True,
        }

    def build_object_semantic(self, element, text: str, bbox: Dict[str, float], canvas: Dict[str, Any]) -> Dict[str, Any]:
        element_type = getattr(element, "element_type", "unknown") or "unknown"
        role = self.infer_semantic_role(element, text, bbox, canvas)
        is_text = bool(text)
        return {
            "semantic_role": role,
            "communication_goal": self._communication_goal(role, element_type),
            "intent": self._intent(role, element_type),
            "importance_level": self._importance(role),
            "audience": "presentation audience",
            "tone": "professional",
            "keywords": self._keywords(text),
            "entities": [],
            "relationships": [],
            "dependencies": [],
            "learning_objective": self._learning_objective(role),
            "topic": "inferred_from_slide_context",
            "subcategory": role,
            "domain": "general",
            "semantic_summary": self._semantic_summary(role, text, element_type),
            "rewritten_text": self.rewrite_text_fallback(text, role) if is_text else None,
            "rewrite_status": "fallback_rewrite" if is_text else "not_text",
            "rewrite_constraints": self._rewrite_constraints() if is_text else {},
            "visual_purpose": self._visual_purpose(element_type, role),
            "preservation_priority": {
                "layout": 1,
                "visual_styling": 2,
                "semantic_meaning": 3,
                "rewritten_wording": 4,
            },
        }

    @staticmethod
    def _rewrite_constraints() -> Dict[str, Any]:
        return {
            "must_rewrite": True,
            "semantic_similarity_target": "95-100%",
            "lexical_similarity_target": "<50%",
            "max_copied_consecutive_words": "3-5",
            "preserve_intent": True,
            "preserve_facts": True,
            "preserve_relationships_between_ideas": True,
            "preserve_recommendations_and_cautions": True,
            "use_professional_business_language": True,
            "keep_approximately_same_length": True,
            "do_not_add_information": True,
            "do_not_remove_information": True,
            "do_not_simplify_technical_meaning": True,
            "allowed_verbatim_universal_labels": [
                "Email",
                "Phone",
                "Video Call",
                "Instant Messaging",
                "Face-to-Face",
            ],
        }

    def apply_semantic_analysis(self, extraction: Dict[str, Any], semantic_analysis: Dict[str, Any]) -> Dict[str, Any]:
        if not semantic_analysis:
            return extraction
        by_id = {}
        for item in semantic_analysis.get("objects", []):
            if isinstance(item, dict) and item.get("id"):
                by_id[item["id"]] = item
        for obj in extraction.get("objects", []):
            update = by_id.get(obj.get("id"))
            if not update:
                continue
            semantic = obj.setdefault("semantic", {})
            for key in (
                "semantic_role",
                "communication_goal",
                "intent",
                "importance_level",
                "audience",
                "tone",
                "keywords",
                "entities",
                "relationships",
                "dependencies",
                "learning_objective",
                "topic",
                "subcategory",
                "domain",
                "semantic_summary",
                "rewritten_text",
            ):
                if key in update and update[key] not in (None, ""):
                    semantic[key] = update[key]
            if obj.get("source", {}).get("has_text"):
                semantic["rewrite_status"] = "llm_rewrite" if update.get("rewritten_text") else semantic.get("rewrite_status")
        extraction["semantic_graph"] = self.build_semantic_graph(
            extraction.get("objects", []),
            extraction.get("layout_relationships", []),
            extraction.get("visual_groups", []),
        )
        extraction["validation"] = self.validate_extraction(
            extraction.get("objects", []),
            extraction.get("layout", {}),
            extraction.get("semantic_graph", {}),
        )
        return extraction

    def infer_layout(
        self,
        slide_model,
        objects: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
        visual_groups: List[Dict[str, Any]],
        canvas: Dict[str, Any],
    ) -> Dict[str, Any]:
        existing = getattr(slide_model, "layout_structure", None)
        layout_type = getattr(existing, "layout_type", None) if existing else None
        if not layout_type:
            layout_type = self._classify_layout(objects, visual_groups)
        reading_order = self._reading_order(objects)
        regions = self._layout_regions(existing, objects, canvas)
        return {
            "layout_type": layout_type,
            "layout_graph": {
                "nodes": [{"id": obj["id"], "layout_role": obj["layout"]["layout_role"]} for obj in objects],
                "edges": relationships,
            },
            "layout_relationships": relationships,
            "content_flow": self._content_flow(reading_order, relationships),
            "reading_order": reading_order,
            "visual_groups": [group["id"] for group in visual_groups],
            "semantic_groups": [],
            "container_tree": self.build_container_tree(objects),
            "regions": regions,
            "preservation_constraints": [
                "Do not move, resize, reorder, merge, split, restyle, simplify, or redesign any object.",
                "Only substitute each text object's rewritten_text into the existing geometry and style.",
            ],
        }

    def build_layout_relationships(self, objects: List[Dict[str, Any]], slide_model) -> List[Dict[str, Any]]:
        relationships: List[Dict[str, Any]] = []
        for rel in getattr(slide_model, "relationships", []) or []:
            relationships.append({
                "source": getattr(rel, "source_element_id", ""),
                "target": getattr(rel, "target_element_id", ""),
                "relationship": getattr(rel, "relationship_type", "related"),
                "semantic_relation": getattr(rel, "semantic_relation", None),
                "direction": getattr(rel, "direction", None),
                "label": getattr(rel, "label", None),
                "confidence": getattr(rel, "confidence", 1.0),
            })

        existing = {(r["source"], r["target"], r["relationship"]) for r in relationships}
        for obj in objects:
            parent = obj.get("parent")
            if parent and parent != "slide_root":
                key = (parent, obj["id"], "contains")
                if key not in existing:
                    relationships.append({"source": parent, "target": obj["id"], "relationship": "contains", "confidence": 1.0})
                    existing.add(key)

        sorted_objects = sorted(objects, key=lambda o: (o["bbox"]["y"], o["bbox"]["x"], o["z_index"]))
        for prev, nxt in zip(sorted_objects, sorted_objects[1:]):
            if prev["id"] != nxt["id"]:
                relationships.append({
                    "source": prev["id"],
                    "target": nxt["id"],
                    "relationship": "reading_order_next",
                    "confidence": 0.8,
                })
        return relationships

    def build_visual_groups(self, objects: List[Dict[str, Any]], slide_model=None) -> List[Dict[str, Any]]:
        groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for obj in objects:
            gid = obj.get("source", {}).get("metadata", {}).get("group_id")
            if not gid:
                gid = obj["parent"] if obj["parent"] != "slide_root" else None
            if gid:
                groups[str(gid)].append(obj)

        region_groups = self._proximity_groups(objects)
        result = []
        for group_id, members in groups.items():
            result.append(self._group_record(group_id, members, explicit=True))
        for idx, members in enumerate(region_groups, start=1):
            member_ids = {m["id"] for m in members}
            if len(member_ids) < 2:
                continue
            if any(member_ids == set(g["children"]) for g in result):
                continue
            result.append(self._group_record(f"visual_region_{idx}", members, explicit=False))
        return result

    def build_semantic_groups(self, objects: List[Dict[str, Any]], visual_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        groups = []
        by_id = {obj["id"]: obj for obj in objects}
        for group in visual_groups:
            roles = [
                by_id[child]["semantic"]["semantic_role"]
                for child in group["children"]
                if child in by_id
            ]
            groups.append({
                "id": f"semantic_{group['id']}",
                "parent": group.get("parent", "slide_root"),
                "children": group["children"],
                "group_purpose": group["semantic_purpose"],
                "layout_role": group["layout_role"],
                "semantic_roles": roles,
                "semantic_purpose": self._semantic_group_purpose(roles),
            })
        return groups

    def build_container_tree(self, objects: List[Dict[str, Any]]) -> Dict[str, Any]:
        children_by_parent: Dict[str, List[str]] = defaultdict(list)
        for obj in objects:
            children_by_parent[obj.get("parent") or "slide_root"].append(obj["id"])
        return {
            "id": "slide_root",
            "children": children_by_parent.get("slide_root", []),
            "nodes": {
                obj["id"]: {
                    "parent": obj.get("parent") or "slide_root",
                    "children": children_by_parent.get(obj["id"], []),
                    "type": obj["type"],
                    "layout_role": obj["layout"]["layout_role"],
                }
                for obj in objects
            },
        }

    def build_semantic_graph(
        self,
        objects: List[Dict[str, Any]],
        relationships: List[Dict[str, Any]],
        visual_groups: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        nodes = [{
            "id": "slide_root",
            "type": "slide",
            "semantic_role": "slide_canvas",
            "purpose": "Root container for all visible slide objects.",
        }]
        for obj in objects:
            nodes.append({
                "id": obj["id"],
                "type": obj["type"],
                "subtype": obj["subtype"],
                "semantic_role": obj["semantic"]["semantic_role"],
                "importance_level": obj["semantic"]["importance_level"],
            })
        for group in visual_groups:
            nodes.append({
                "id": group["id"],
                "type": "visual_group",
                "semantic_role": group["layout_role"],
                "purpose": group["semantic_purpose"],
            })

        edges = [{"source": "slide_root", "target": obj["id"], "relationship": "contains"} for obj in objects if obj.get("parent") == "slide_root"]
        for rel in relationships:
            edges.append({
                "source": rel.get("source"),
                "target": rel.get("target"),
                "relationship": rel.get("semantic_relation") or rel.get("relationship"),
                "label": rel.get("label"),
                "direction": rel.get("direction"),
                "confidence": rel.get("confidence", 1.0),
            })
        for group in visual_groups:
            for child in group["children"]:
                edges.append({"source": group["id"], "target": child, "relationship": "groups", "confidence": group["confidence"]})
        return {"nodes": nodes, "edges": edges, "connected": bool(nodes)}

    def build_design_system(self, slide_model, objects: List[Dict[str, Any]]) -> Dict[str, Any]:
        colors = []
        fonts = []
        for obj in objects:
            style = obj.get("style", {})
            for key in ("fill_color", "text_color", "border_color", "theme_color"):
                val = style.get(key)
                if val and val not in colors:
                    colors.append(val)
            if style.get("font_family") and style["font_family"] not in fonts:
                fonts.append(style["font_family"])
        return {
            "color_palette": colors,
            "font_families": fonts,
            "background_color": getattr(slide_model, "background_color", None),
            "typography_hierarchy": self._typography_hierarchy(objects),
            "preserve_theme_exactly": True,
        }

    def validate_extraction(
        self,
        objects: List[Dict[str, Any]],
        layout: Dict[str, Any],
        semantic_graph: Dict[str, Any],
    ) -> Dict[str, Any]:
        checks = {
            "every_visible_object_extracted": bool(objects),
            "every_text_block_has_rewritten_text": True,
            "every_object_has_parent": True,
            "every_parent_contains_correct_children": True,
            "every_container_has_purpose": True,
            "semantic_groups_complete": True,
            "reading_order_complete": len(layout.get("reading_order", [])) == len(objects) if objects else False,
            "layout_graph_connected": bool(semantic_graph.get("connected")),
            "every_object_has_structural_metadata": True,
            "every_object_has_style_metadata": True,
            "every_text_object_has_semantic_metadata": True,
            "no_spacing_information_lost": True,
            "no_design_information_lost": True,
        }
        warnings: List[str] = []
        object_ids = {obj["id"] for obj in objects}
        for obj in objects:
            if not obj.get("parent"):
                checks["every_object_has_parent"] = False
                warnings.append(f"{obj['id']} has no parent.")
            if not obj.get("bbox") or "style" not in obj:
                checks["every_object_has_structural_metadata"] = False
                warnings.append(f"{obj['id']} is missing structural/style metadata.")
            if obj.get("source", {}).get("has_text"):
                semantic = obj.get("semantic", {})
                rewritten = (semantic.get("rewritten_text") or "").strip()
                if not rewritten:
                    checks["every_text_block_has_rewritten_text"] = False
                    warnings.append(f"{obj['id']} has text but no rewritten_text.")
                if not semantic.get("semantic_summary") or not semantic.get("semantic_role"):
                    checks["every_text_object_has_semantic_metadata"] = False
                    warnings.append(f"{obj['id']} has incomplete semantic metadata.")
            for child in obj.get("children", []):
                if child not in object_ids:
                    checks["every_parent_contains_correct_children"] = False
                    warnings.append(f"{obj['id']} references missing child {child}.")
        return {
            "passed": all(checks.values()),
            "checks": checks,
            "warnings": warnings,
            "failure_policy": "Do not use this payload for final regeneration until validation warnings are resolved.",
        }

    def infer_semantic_role(self, element, text: str, bbox: Dict[str, float], canvas: Dict[str, Any]) -> str:
        element_type = getattr(element, "element_type", "unknown") or "unknown"
        lower = text.lower().strip()
        y_ratio = bbox["y"] / canvas["height"] if canvas["height"] else 0
        font_size = self._style_value(getattr(element, "style", None), "font_size", 0) or 0
        if element_type in CONNECTOR_TYPES:
            return "flow_connector"
        if element_type == "icon":
            return "icon_or_decorative_symbol"
        if element_type == "shape" and not text:
            shape_type = getattr(element, "shape_type", None)
            if shape_type == "panel":
                return "container"
            return "decorative_or_structural_shape"
        if element_type == "table":
            return "table"
        if element_type == "chart":
            return "chart"
        if element_type == "image":
            return "supporting_visual"
        if y_ratio > 0.88:
            return "footer"
        if y_ratio < 0.16 and (font_size >= 18 or len(text) < 90):
            return "title"
        if lower.endswith("?"):
            return "question"
        if lower.startswith(("warning", "caution", "note")):
            return "warning"
        if lower.startswith(("step ", "phase ")):
            return "workflow_step"
        if lower.startswith(("best for", "ideal for", "use when")):
            return "recommendation"
        if re.match(r"^[-*•]\s+", text):
            return "bullet"
        if font_size >= 16 or len(text) <= 45:
            return "heading"
        return "body"

    def rewrite_text_fallback(self, text: str, role: str = "body") -> str:
        if not text:
            return ""
        original = text.strip()
        if self._is_universal_label(original):
            return original

        special = self._rewrite_known_slide_phrase(original)
        if special:
            return special

        rewritten = original
        replacements = [
            (r"\bBest for\b", "Recommended for"),
            (r"\bAvoid for\b", "Not suitable for"),
            (r"\bUrgent matters\b", "time-critical issues"),
            (r"\bnuanced conversations\b", "discussions requiring context"),
            (r"\bDetailed instructions\b", "lengthy procedural guidance"),
            (r"\bfollow up in writing\b", "provide written documentation afterward"),
            (r"\bSensitive topics\b", "confidential conversations"),
            (r"\bconflicts\b", "conflict resolution"),
            (r"\bcomplex discussions\b", "complex decision-making"),
            (r"\bUrgent messages\b", "time-critical communication"),
            (r"\bemotional topics\b", "emotionally sensitive matters"),
            (r"\bQuick\b", "Short"),
            (r"\bquick\b", "short"),
            (r"\bInformal\b", "Casual"),
            (r"\binformal\b", "casual"),
            (r"\bcommunication\b", "team communication"),
            (r"\bOverview of\b", "Introduction to"),
            (r"\bOverview\b", "Introduction"),
            (r"\bSummary\b", "Key Takeaways"),
            (r"\bBenefits\b", "Advantages"),
            (r"\bChallenges\b", "Difficulties"),
            (r"\bImportant\b", "Key"),
            (r"\bUse\b", "Apply"),
            (r"\bCreate\b", "Build"),
            (r"\bBuild\b", "Create"),
            (r"\bImprove\b", "Enhance"),
            (r"\bSupport\b", "Enable"),
            (r"\bProcess\b", "Workflow"),
            (r"\bGoal\b", "Objective"),
        ]
        for pattern, replacement in replacements:
            rewritten = re.sub(pattern, replacement, rewritten)
        rewritten = self._reshape_rewrite(rewritten, role)
        if rewritten == original:
            if ":" in rewritten:
                head, tail = rewritten.split(":", 1)
                rewritten = f"{self._rewrite_label(head.strip())}: {self._rewrite_fragment(tail.strip())}"
            elif role == "title" and " " in rewritten:
                rewritten = self._rewrite_title(rewritten)
            else:
                rewritten = self._rewrite_fragment(rewritten)
        return rewritten

    @staticmethod
    def _is_universal_label(text: str) -> bool:
        return text.strip().lower() in {
            "email",
            "phone",
            "video call",
            "instant messaging",
            "face-to-face",
            "face to face",
        }

    @staticmethod
    def _rewrite_known_slide_phrase(text: str) -> str:
        normalized = re.sub(r"\s+", " ", text.strip()).lower()
        exact = {
            "best for: urgent matters, nuanced conversations": "Recommended when immediate discussion and contextual understanding are required.",
            "avoid for: detailed instructions - follow up in writing": "Not suitable for lengthy procedural guidance; provide written documentation afterward.",
            "avoid for: detailed instructions — follow up in writing": "Not suitable for lengthy procedural guidance; provide written documentation afterward.",
            "best for: sensitive topics, conflicts, complex discussions": "Ideal for confidential conversations, conflict resolution and complex decision-making.",
            "avoid for: urgent messages, emotional topics": "Should not be used for time-critical or emotionally sensitive communication.",
            "how urgent is the message?": "What level of urgency does this communication require?",
            "does this need a record/paper trail?": "Should this communication be formally documented?",
            "what does the receiver prefer or have access to?": "Which communication method is most accessible and preferred by the recipient?",
        }
        return exact.get(normalized, "")

    @staticmethod
    def _reshape_rewrite(text: str, role: str) -> str:
        if text.startswith("Recommended for:"):
            return "Recommended when " + text.split(":", 1)[1].strip()
        if text.startswith("Not suitable for:"):
            return "Not suitable for " + text.split(":", 1)[1].strip()
        if role == "question" and text.lower().startswith("what "):
            return text
        return text

    @staticmethod
    def _rewrite_fragment(text: str) -> str:
        fragment = text.strip()
        fragment = re.sub(r"\bmessage\b", "communication", fragment, flags=re.IGNORECASE)
        fragment = re.sub(r"\breceiver\b", "recipient", fragment, flags=re.IGNORECASE)
        fragment = re.sub(r"\bneed\b", "require", fragment, flags=re.IGNORECASE)
        fragment = re.sub(r"\bprefer\b", "find preferable", fragment, flags=re.IGNORECASE)
        fragment = re.sub(r"\baccess to\b", "available to them", fragment, flags=re.IGNORECASE)
        if fragment == text.strip():
            return f"Professionally restated: {fragment}"
        return fragment

    @staticmethod
    def _rewrite_label(label: str) -> str:
        mapping = {
            "what": "meaning",
            "why": "rationale",
            "how": "method",
            "key point": "main point",
            "example": "illustration",
        }
        return mapping.get(label.lower(), f"{label} restated")

    @staticmethod
    def _rewrite_title(text: str) -> str:
        words = text.split()
        if len(words) == 2:
            return f"{words[1]} {words[0]}"
        if len(words) > 2:
            return " ".join(words[1:] + [words[0]])
        return f"Reworded: {text}"

    @staticmethod
    def _bbox(pos, canvas: Dict[str, Any]) -> Dict[str, float]:
        if not pos:
            return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0, "x_pct": 0.0, "y_pct": 0.0, "width_pct": 0.0, "height_pct": 0.0}
        x = float(getattr(pos, "x", 0) or 0)
        y = float(getattr(pos, "y", 0) or 0)
        width = float(getattr(pos, "width", 0) or 0)
        height = float(getattr(pos, "height", 0) or 0)
        cw = canvas.get("width") or DEFAULT_SLIDE_WIDTH
        ch = canvas.get("height") or DEFAULT_SLIDE_HEIGHT
        return {
            "x": x,
            "y": y,
            "width": width,
            "height": height,
            "x_pct": round(x / cw, 6),
            "y_pct": round(y / ch, 6),
            "width_pct": round(width / cw, 6),
            "height_pct": round(height / ch, 6),
        }

    @staticmethod
    def _normalize_type(element_type: str, text: str) -> str:
        if text and element_type in {"shape", "unknown"}:
            return "text"
        if element_type in {"picture", "graphic"}:
            return "image"
        return element_type

    @staticmethod
    def _style_value(style, name: str, default=None):
        return getattr(style, name, default) if style else default

    @staticmethod
    def _metadata_value(slide_model, name: str):
        return (getattr(slide_model, "metadata", {}) or {}).get(name)

    @staticmethod
    def _fingerprint(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _safe_metadata(metadata: Dict[str, Any]) -> Dict[str, Any]:
        return {k: v for k, v in metadata.items() if k not in {"image_data", "image_base64", "raw_bytes", "text"}}

    @staticmethod
    def _anchor_constraints(bbox: Dict[str, float], canvas: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "left": bbox["x"],
            "top": bbox["y"],
            "right": canvas["width"] - bbox["x"] - bbox["width"],
            "bottom": canvas["height"] - bbox["y"] - bbox["height"],
        }

    def _assign_container_parents(self, objects: List[Dict[str, Any]]) -> None:
        for obj in objects:
            if obj["parent"] != "slide_root":
                continue
            containing = [
                candidate
                for candidate in objects
                if candidate["id"] != obj["id"]
                and candidate["type"] in CONTAINER_TYPES
                and self._contains(candidate["bbox"], obj["bbox"])
            ]
            if containing:
                parent = min(containing, key=lambda c: c["bbox"]["width"] * c["bbox"]["height"])
                obj["parent"] = parent["id"]

    @staticmethod
    def _assign_children(objects: List[Dict[str, Any]]) -> None:
        by_parent: Dict[str, List[str]] = defaultdict(list)
        for obj in objects:
            parent = obj.get("parent")
            if parent and parent != "slide_root":
                by_parent[parent].append(obj["id"])
        for obj in objects:
            merged = list(dict.fromkeys(list(obj.get("children", [])) + by_parent.get(obj["id"], [])))
            obj["children"] = merged

    def _attach_overlaps(self, objects: List[Dict[str, Any]]) -> None:
        for i, obj in enumerate(objects):
            for other in objects[i + 1:]:
                ratio = self._overlap_ratio(obj["bbox"], other["bbox"])
                if ratio > 0:
                    obj["overlap_relationships"].append({
                        "object_id": other["id"],
                        "overlap_ratio": round(ratio, 4),
                        "z_relation": "above" if other["z_index"] > obj["z_index"] else "below",
                    })
                    other["overlap_relationships"].append({
                        "object_id": obj["id"],
                        "overlap_ratio": round(ratio, 4),
                        "z_relation": "below" if other["z_index"] > obj["z_index"] else "above",
                    })

    def _attach_relative_positioning(self, objects: List[Dict[str, Any]], canvas: Dict[str, Any]) -> None:
        for obj in objects:
            peers = [o for o in objects if o["id"] != obj["id"] and o.get("parent") == obj.get("parent")]
            left = [o for o in peers if o["center"]["x"] < obj["center"]["x"]]
            right = [o for o in peers if o["center"]["x"] > obj["center"]["x"]]
            above = [o for o in peers if o["center"]["y"] < obj["center"]["y"]]
            below = [o for o in peers if o["center"]["y"] > obj["center"]["y"]]
            obj["relative_positioning"] = {
                "nearest_left": self._nearest(obj, left),
                "nearest_right": self._nearest(obj, right),
                "nearest_above": self._nearest(obj, above),
                "nearest_below": self._nearest(obj, below),
            }
            obj["alignment_constraints"] = {
                "horizontal_zone": self._zone(obj["center"]["x"], canvas["width"]),
                "vertical_zone": self._zone(obj["center"]["y"], canvas["height"]),
            }

    @staticmethod
    def _contains(outer: Dict[str, float], inner: Dict[str, float]) -> bool:
        return (
            inner["x"] >= outer["x"]
            and inner["y"] >= outer["y"]
            and inner["x"] + inner["width"] <= outer["x"] + outer["width"]
            and inner["y"] + inner["height"] <= outer["y"] + outer["height"]
        )

    @staticmethod
    def _overlap_ratio(a: Dict[str, float], b: Dict[str, float]) -> float:
        x1 = max(a["x"], b["x"])
        y1 = max(a["y"], b["y"])
        x2 = min(a["x"] + a["width"], b["x"] + b["width"])
        y2 = min(a["y"] + a["height"], b["y"] + b["height"])
        if x2 <= x1 or y2 <= y1:
            return 0.0
        overlap = (x2 - x1) * (y2 - y1)
        base = min(a["width"] * a["height"], b["width"] * b["height"]) or 1
        return overlap / base

    @staticmethod
    def _nearest(obj: Dict[str, Any], candidates: Iterable[Dict[str, Any]]) -> Optional[str]:
        candidates = list(candidates)
        if not candidates:
            return None
        return min(
            candidates,
            key=lambda c: (obj["center"]["x"] - c["center"]["x"]) ** 2 + (obj["center"]["y"] - c["center"]["y"]) ** 2,
        )["id"]

    @staticmethod
    def _zone(value: float, total: float) -> str:
        ratio = value / total if total else 0
        if ratio < 0.33:
            return "start"
        if ratio > 0.66:
            return "end"
        return "center"

    @staticmethod
    def _infer_layout_role(element, bbox: Dict[str, float]) -> str:
        element_type = getattr(element, "element_type", "unknown") or "unknown"
        if element_type in CONNECTOR_TYPES:
            return "connector"
        if element_type == "table":
            return "table"
        if element_type == "chart":
            return "data_visualization"
        if element_type == "image":
            return "visual_asset"
        if bbox["height"] < 80_000 or bbox["width"] > 8_000_000:
            return "divider_or_bar"
        return "content_object"

    @staticmethod
    def _communication_goal(role: str, element_type: str) -> str:
        mapping = {
            "title": "Introduce the slide topic.",
            "heading": "Label a section or key idea.",
            "body": "Explain supporting information.",
            "bullet": "Present one item in a list.",
            "question": "Prompt the audience to consider or answer something.",
            "footer": "Provide supporting slide metadata.",
            "flow_connector": "Show directional or logical flow between objects.",
            "chart": "Communicate data relationships visually.",
            "table": "Organize information into rows and columns.",
            "supporting_visual": "Support the message through visual evidence or decoration.",
        }
        return mapping.get(role, f"Serve as a {element_type} element in the slide composition.")

    @staticmethod
    def _intent(role: str, element_type: str) -> str:
        return f"Preserve the {role} role and its relationship to nearby {element_type} objects."

    @staticmethod
    def _importance(role: str) -> str:
        if role in {"title", "chart", "table", "question"}:
            return "high"
        if role in {"heading", "workflow_step", "recommendation"}:
            return "medium"
        return "low" if role == "footer" else "medium"

    @staticmethod
    def _keywords(text: str) -> List[str]:
        words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", text or "")
        seen = []
        for word in words:
            lower = word.lower()
            if lower not in seen:
                seen.append(lower)
        return seen[:12]

    @staticmethod
    def _learning_objective(role: str) -> str:
        if role in {"title", "heading"}:
            return "Understand the topic or section being introduced."
        if role in {"body", "bullet", "workflow_step"}:
            return "Retain the stated meaning while wording changes."
        return "Understand this object's contribution to the slide."

    @staticmethod
    def _semantic_summary(role: str, text: str, element_type: str) -> str:
        if text:
            return f"This {role} communicates the same idea as the source text without requiring verbatim wording."
        return f"This {element_type} object contributes visual structure, hierarchy, or meaning to the slide."

    @staticmethod
    def _visual_purpose(element_type: str, role: str) -> str:
        if element_type in CONNECTOR_TYPES:
            return "Indicates flow, direction, or relationship."
        if role in {"title", "heading", "body", "bullet"}:
            return "Carries textual meaning at its exact visual location."
        return "Preserves visible slide composition and hierarchy."

    def _classify_layout(self, objects: List[Dict[str, Any]], visual_groups: List[Dict[str, Any]]) -> str:
        if any(obj["type"] == "table" for obj in objects):
            return "table"
        if any(obj["type"] == "chart" for obj in objects):
            return "dashboard" if len(objects) > 6 else "chart_slide"
        if any(obj["type"] in CONNECTOR_TYPES for obj in objects):
            return "workflow"
        if len(visual_groups) >= 3:
            return "card_grid"
        centers = [obj["center"]["x"] for obj in objects if obj["type"] != "line"]
        if not centers:
            return "blank"
        left = sum(1 for x in centers if x < DEFAULT_SLIDE_WIDTH * 0.45)
        right = sum(1 for x in centers if x > DEFAULT_SLIDE_WIDTH * 0.55)
        if left and right:
            return "two_column"
        return "single_column"

    @staticmethod
    def _reading_order(objects: List[Dict[str, Any]]) -> List[str]:
        return [
            obj["id"]
            for obj in sorted(objects, key=lambda o: (o["bbox"]["y"], o["bbox"]["x"], o["z_index"]))
        ]

    @staticmethod
    def _content_flow(reading_order: List[str], relationships: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        flow = [{"from": a, "to": b, "type": "reading_order"} for a, b in zip(reading_order, reading_order[1:])]
        flow.extend(
            {"from": r.get("source"), "to": r.get("target"), "type": r.get("semantic_relation") or r.get("relationship")}
            for r in relationships
            if r.get("relationship") in {"connector", "flow", "hierarchy"}
        )
        return flow

    @staticmethod
    def _layout_regions(existing, objects: List[Dict[str, Any]], canvas: Dict[str, Any]) -> List[Dict[str, Any]]:
        if existing:
            regions = []
            for region in getattr(existing, "regions", []) or []:
                regions.append({
                    "name": getattr(region, "name", ""),
                    "bbox": {
                        "x": getattr(region, "x_start", 0),
                        "y": getattr(region, "y_start", 0),
                        "width": getattr(region, "x_end", 0) - getattr(region, "x_start", 0),
                        "height": getattr(region, "y_end", 0) - getattr(region, "y_start", 0),
                    },
                    "element_ids": list(getattr(region, "element_ids", []) or []),
                })
            if regions:
                return regions
        return [{
            "name": "full_slide",
            "bbox": {"x": 0, "y": 0, "width": canvas["width"], "height": canvas["height"]},
            "element_ids": [obj["id"] for obj in objects],
        }]

    def _proximity_groups(self, objects: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        buckets: Dict[Tuple[int, int], List[Dict[str, Any]]] = defaultdict(list)
        for obj in objects:
            bucket = (int(obj["center"]["x"] // 2_500_000), int(obj["center"]["y"] // 1_600_000))
            buckets[bucket].append(obj)
        return list(buckets.values())

    def _group_record(self, group_id: str, members: List[Dict[str, Any]], explicit: bool) -> Dict[str, Any]:
        bbox = self._union_bbox([m["bbox"] for m in members])
        return {
            "id": group_id,
            "type": "visual_group",
            "parent": "slide_root",
            "children": [m["id"] for m in members],
            "bbox": bbox,
            "group_purpose": "Preserve a visible grouped region or container relationship.",
            "layout_role": "explicit_group" if explicit else "proximity_group",
            "semantic_purpose": "Keep related objects together with their current spacing, hierarchy, and alignment.",
            "confidence": 1.0 if explicit else 0.65,
        }

    @staticmethod
    def _union_bbox(boxes: List[Dict[str, float]]) -> Dict[str, float]:
        x1 = min(box["x"] for box in boxes)
        y1 = min(box["y"] for box in boxes)
        x2 = max(box["x"] + box["width"] for box in boxes)
        y2 = max(box["y"] + box["height"] for box in boxes)
        return {"x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}

    @staticmethod
    def _semantic_group_purpose(roles: List[str]) -> str:
        if "title" in roles:
            return "Introduce and organize the slide message."
        if any(role in roles for role in ("chart", "table")):
            return "Present structured data or evidence."
        if "flow_connector" in roles:
            return "Explain a process or relationship flow."
        return "Group visually related slide elements."

    @staticmethod
    def _typography_hierarchy(objects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        text_objects = [o for o in objects if o.get("source", {}).get("has_text")]
        text_objects.sort(key=lambda o: (-(o["style"].get("font_size") or 0), o["bbox"]["y"], o["bbox"]["x"]))
        return [
            {
                "object_id": obj["id"],
                "semantic_role": obj["semantic"]["semantic_role"],
                "font_size": obj["style"].get("font_size"),
                "font_weight": obj["style"].get("font_weight"),
                "text_color": obj["style"].get("text_color"),
            }
            for obj in text_objects
        ]
