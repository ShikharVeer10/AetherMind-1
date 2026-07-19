import json
import os
from typing import Any, Dict, List, Optional

import requests

from services.semantic_slide_extraction_service import SemanticSlideExtractionService


class SemanticSlideExtractionAgent:
    system_prompt = (
        "You are a presentation intelligence agent. Return only valid JSON. "
        "Your job is not OCR, captioning, summarization, template matching, or redesign. "
        "For each supplied object, preserve its structural role and provide semantic metadata plus rewritten_text. "
        "The extracted JSON is the source of truth for layout, spatial arrangement, visual hierarchy, "
        "object positions, colors, typography hierarchy, icons, illustrations, charts, spacing, grouping, "
        "and visual emphasis. Do not change or reinterpret visual properties. "
        "Do not copy source text verbatim into rewritten_text. Avoid copying more than 3-5 consecutive "
        "words unless the text is a universal label such as Email, Phone, Video Call, Instant Messaging, "
        "or Face-to-Face. Preserve 95-100% semantic similarity while keeping lexical similarity below 50%. "
        "Use professional business language, keep approximately the same length, and do not add, remove, "
        "summarize, simplify, or expand facts. Only wording changes."
    )

    def __init__(self, presentation_metadata: Optional[Dict[str, Any]] = None):
        self.presentation_metadata = presentation_metadata or {}
        self.service = SemanticSlideExtractionService()
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.model = os.getenv("SEMANTIC_SLIDE_MODEL", "llama3.2")
        self.skip_ollama = os.getenv("SKIP_OLLAMA", "false").lower() == "true"

    def run(self, slide_model, raw_slide=None) -> Dict[str, Any]:
        extraction = self.service.build_slide_extraction(
            slide_model,
            presentation_metadata=self.presentation_metadata,
        )
        semantic_analysis = self._run_semantic_analysis(extraction)
        extraction = self.service.apply_semantic_analysis(extraction, semantic_analysis)
        for obj in extraction.get("objects", []):
            obj.pop("_source_text", None)
        extraction["agent"] = {
            "name": "SemanticSlideExtractionAgent",
            "mode": "layout_preserving_semantic_rewrite",
            "llm_model": None if self.skip_ollama else self.model,
            "uses_original_image_for_generation": False,
            "raw_slide_available": raw_slide is not None,
        }
        return extraction

    def _run_semantic_analysis(self, extraction_payload: Dict[str, Any]) -> Dict[str, Any]:
        text_objects = self._text_objects_for_llm(extraction_payload)
        if not text_objects:
            return {"objects": []}
        if self.skip_ollama:
            return self._rule_based_semantic_fallback(extraction_payload)

        try:
            payload = {
                "model": self.model,
                "prompt": self._build_prompt(extraction_payload, text_objects),
                "system": self.system_prompt,
                "stream": False,
                "format": "json",
            }
            response = requests.post(f"{self.ollama_host}/api/generate", json=payload, timeout=45)
            if response.status_code == 200:
                data = response.json().get("response", "{}")
                parsed = json.loads(data)
                if isinstance(parsed, dict) and isinstance(parsed.get("objects"), list):
                    return parsed
        except Exception as exc:
            print(f"    [SemanticSlideExtractionAgent] LLM failed: {exc}")

        return self._rule_based_semantic_fallback(extraction_payload)

    def _build_prompt(self, extraction_payload: Dict[str, Any], text_objects: List[Dict[str, Any]]) -> str:
        compact_context = {
            "slide_number": extraction_payload.get("slide_number"),
            "layout_type": extraction_payload.get("layout_type"),
            "reading_order": extraction_payload.get("reading_order", []),
            "visual_groups": extraction_payload.get("visual_groups", []),
            "layout_relationships": extraction_payload.get("layout_relationships", []),
            "objects": text_objects,
        }
        return (
            "Analyze these already-extracted slide objects. Return JSON with this exact top-level shape:\n"
            '{"objects":[{"id":"...","semantic_role":"...","communication_goal":"...",'
            '"intent":"...","importance_level":"high|medium|low","audience":"...",'
            '"tone":"...","keywords":[],"entities":[],"relationships":[],"dependencies":[],'
            '"learning_objective":"...","topic":"...","subcategory":"...","domain":"...",'
            '"semantic_summary":"...","rewritten_text":"..."}]}\n\n'
            "Rules:\n"
            "1. Use each id exactly as supplied.\n"
            "2. rewritten_text must preserve the exact meaning, facts, advice, cautions, and relationships between ideas.\n"
            "3. Rewrite naturally in professional business language; change wording and sentence structure.\n"
            "4. Avoid copying more than 3-5 consecutive words from source_text unless it is a universal label: Email, Phone, Video Call, Instant Messaging, Face-to-Face.\n"
            "5. Keep approximately the same length and do not summarize, omit, expand, merge, split, simplify technical meaning, or invent content.\n"
            "6. Target semantic similarity: 95-100%; target lexical similarity: below 50%.\n"
            "7. Do not mention layout changes; layout and styling are fixed by the object JSON.\n"
            "8. Return no source/original text fields.\n\n"
            "Examples:\n"
            "Best for: Urgent matters, nuanced conversations -> Recommended when immediate discussion and contextual understanding are required.\n"
            "Avoid for: Detailed instructions - follow up in writing -> Not suitable for lengthy procedural guidance; provide written documentation afterward.\n"
            "How urgent is the message? -> What level of urgency does this communication require?\n\n"
            f"Input JSON:\n{json.dumps(compact_context, ensure_ascii=True)}"
        )

    def _text_objects_for_llm(self, extraction_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        text_objects = []
        for obj in extraction_payload.get("objects", []):
            if not obj.get("source", {}).get("has_text"):
                continue
            # The source text is sent only to the rewrite model; it is not retained
            # as a semantic JSON field in the final extraction payload.
            text_objects.append({
                "id": obj["id"],
                "source_text": self._source_text_lookup(obj, extraction_payload),
                "current_role": obj.get("semantic", {}).get("semantic_role"),
                "bbox": obj.get("bbox"),
                "style": obj.get("style"),
                "layout": obj.get("layout"),
                "parent": obj.get("parent"),
                "children": obj.get("children", []),
            })
        return text_objects

    @staticmethod
    def _source_text_lookup(obj: Dict[str, Any], extraction_payload: Dict[str, Any]) -> str:
        # build_slide_extraction keeps this private field only during the agent
        # call. run() removes it before returning the final semantic payload.
        return obj.get("_source_text") or obj.get("semantic", {}).get("rewritten_text") or ""

    def _rule_based_semantic_fallback(self, extraction_payload: Dict[str, Any]) -> Dict[str, Any]:
        objects = []
        for obj in extraction_payload.get("objects", []):
            if not obj.get("source", {}).get("has_text"):
                continue
            semantic = obj.get("semantic", {})
            role = semantic.get("semantic_role", "body")
            fallback_text = semantic.get("rewritten_text", "")
            objects.append({
                "id": obj["id"],
                "semantic_role": role,
                "communication_goal": semantic.get("communication_goal", ""),
                "intent": semantic.get("intent", ""),
                "importance_level": semantic.get("importance_level", "medium"),
                "audience": semantic.get("audience", "presentation audience"),
                "tone": semantic.get("tone", "professional"),
                "keywords": semantic.get("keywords", []),
                "entities": semantic.get("entities", []),
                "relationships": semantic.get("relationships", []),
                "dependencies": semantic.get("dependencies", []),
                "learning_objective": semantic.get("learning_objective", ""),
                "topic": semantic.get("topic", "inferred_from_slide_context"),
                "subcategory": semantic.get("subcategory", role),
                "domain": semantic.get("domain", "general"),
                "semantic_summary": semantic.get("semantic_summary", ""),
                "rewritten_text": fallback_text,
            })
        return {"objects": objects}
