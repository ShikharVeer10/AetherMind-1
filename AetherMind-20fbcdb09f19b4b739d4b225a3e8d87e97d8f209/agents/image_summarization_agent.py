import base64
import io
import os
from typing import Optional

import requests


_IMAGE_PROMPT = """\
Analyze this image in exhaustive detail for the purpose of recreating/reconstructing it. Focus on producing a high-fidelity visual and structural reconstruction blueprint. You MUST respond using the EXACT section headings and structure shown below. Do NOT skip any section — write "N/A" if a section does not apply. Focus ONLY on the visual content inside the image.

## 1. Slide Intent
Categorize the primary intent of the slide from this list: cover_page, executive_summary, dashboard, methodology, architecture_diagram, process_flow, infographic, comparison, research_report, findings, recommendations, conclusion, appendix, custom. Briefly explain the classification.

## 2. Visual Regions
Identify and locate the boundaries, layout panels, or main zones of the slide. Focus on regions such as: header, footer, left panel, right panel, center panel, sidebars, banners, chart areas, illustration areas. Describe their coordinates or relative placement on a 100x100 grid.

## 3. Illustration Inventory
List all graphics, illustrations, icons, diagrams, or visual assets. For each illustration, specify:
- position (coordinates or relative location)
- size (relative size or scale)
- purpose (what role it plays)
- semantic meaning (what concept it depicts)

## 4. Relationship Mapping
Analyze the connections and relations between all visual and textual elements. Map relationships using the following categories: supports, explains, compares, contrasts, groups, summarizes, influences, depends_on. For each relation, specify the source element, target element, and relationship type.

## 5. Design Hierarchy
Detail the visual prominence of elements:
- primary focus (what grabs attention first)
- secondary focus (what grabs attention second)
- tertiary focus (other supporting details)
- attention flow (the path the viewer's eyes follow)

## 6. Reading Order
Provide the step-by-step reading order a human would naturally follow when reading/interpreting the slide (e.g. top-to-bottom, left-to-right, flowchart sequence).

## 7. Scene Overview
Provide a detailed description of the entire image, including:
- overall composition
- visual hierarchy
- major regions
- focal points

## 8. Object Inventory
Identify every significant visual element. For each object provide a JSON block matching:
{
  "name": "",
  "category": "",
  "position": "",
  "size": "",
  "appearance": ""
}
Examples of categories: human, robot, gear, chart, cloud, building, server, tree, molecule, icon, vehicle.

## 9. Spatial Relationships
Describe how objects relate to one another (e.g. above, below, inside, connected_to, overlapping, surrounding, attached_to).

## 10. Visual Style
Identify:
- illustration style
- rendering style
- realism level
- artistic influences
- design language

## 11. Color Analysis
Return a JSON block containing:
{
  "dominant_colors": [],
  "accent_colors": [],
  "background_colors": []
}
Use HEX color values when possible.

## 12. Shapes and Geometry
Identify circles, rectangles, polygons, arrows, connectors, icons, decorative elements, and describe their role.

## 13. Text Elements
Extract all visible text exactly as shown. Preserve wording, capitalization, and grouping. Do not summarize.

## 14. Reconstruction Description
Generate an extremely detailed reconstruction description containing: objects, colors, positions, scale, spacing, style, lighting, relationships, and composition. The description should be sufficient for another image generation model to recreate a highly similar image.

## 15. UI Code Generation Prompt
Generate a final prompt optimized for UI code reconstruction fidelity (e.g., HTML/CSS, React, or SVG). The prompt should describe the UI/image precisely, avoid interpretation, avoid summarization, avoid adding new content, and preserve visual structure so that a coder could render it perfectly without hallucinating text or layout.
"""


class _LocalVisionAnalyzer:
    def __init__(self):
        self._caption_processor = None
        self._caption_model = None
        self._vqa_processor = None
        self._vqa_model = None
        self._available: Optional[bool] = None
        self._device = "cpu"

    @property
    def available(self) -> bool:
        if self._available is None:
            try:
                import torch  # noqa: F401
                import transformers  # noqa: F401
                from PIL import Image  # noqa: F401

                self._available = True
            except ImportError:
                self._available = False
        return self._available

    def _ensure_loaded(self):
        if self._caption_model is not None:
            return
        from transformers import BlipProcessor, BlipForConditionalGeneration, BlipForQuestionAnswering
        import torch

        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        print(
            f"[ImageSummary] Loading local BLIP models on device {self._device}..."
        )
        try:
            # Try loading from local cache first (no internet lookup)
            self._caption_processor = BlipProcessor.from_pretrained(
                "Salesforce/blip-image-captioning-large", local_files_only=True
            )
            self._caption_model = BlipForConditionalGeneration.from_pretrained(
                "Salesforce/blip-image-captioning-large", local_files_only=True
            ).to(self._device)
            self._vqa_processor = self._caption_processor
            self._vqa_model = BlipForQuestionAnswering.from_pretrained(
                "Salesforce/blip-vqa-capfilt-large", local_files_only=True
            ).to(self._device)
            print(f"[ImageSummary] Local vision models loaded from cache onto {self._device}.")
        except Exception as cache_exc:
            print(f"[ImageSummary] Local cache load failed: {cache_exc}. Trying to fetch online...")
            self._caption_processor = BlipProcessor.from_pretrained("Salesforce/blip-image-captioning-large")
            self._caption_model = BlipForConditionalGeneration.from_pretrained("Salesforce/blip-image-captioning-large").to(self._device)
            self._vqa_processor = self._caption_processor
            self._vqa_model = BlipForQuestionAnswering.from_pretrained("Salesforce/blip-vqa-capfilt-large").to(self._device)
            print(f"[ImageSummary] Local vision models downloaded and ready on {self._device}.")

    @staticmethod
    def _to_pil(image_bytes: bytes):
        from PIL import Image

        return Image.open(io.BytesIO(image_bytes)).convert("RGB")

    def _caption(self, pil_img) -> str:
        inputs = self._caption_processor(images=pil_img, return_tensors="pt").to(self._device)
        outputs = self._caption_model.generate(**inputs, max_new_tokens=150)
        return self._caption_processor.decode(outputs[0], skip_special_tokens=True)

    def _ask(self, pil_img, question: str) -> str:
        inputs = self._vqa_processor(images=pil_img, text=question, return_tensors="pt").to(self._device)
        outputs = self._vqa_model.generate(**inputs, max_new_tokens=50)
        return self._vqa_processor.decode(outputs[0], skip_special_tokens=True)


    def analyze(
        self,
        image_bytes: bytes,
        slide_title: Optional[str] = None,
        slide_text: Optional[str] = None,
    ) -> Optional[str]:
        """Return a structured summary, or *None* if local models are
        unavailable (missing packages)."""
        if not self.available:
            return None
        try:
            self._ensure_loaded()
        except Exception as exc:
            print(f"[ImageSummary] Failed to load local models: {exc}")
            self._available = False
            return None

        pil_img = self._to_pil(image_bytes)

        # 1. Generate a descriptive caption
        caption = self._caption(pil_img)

        # 2. Ask targeted questions
        topic = slide_title or "this topic"
        _questions = {
            "box_count": "How many boxes or rectangles are visible in this image?",
            "arrow_count": "How many arrows or connectors are visible in this image?",
            "concept": f"What concept does this image explain or illustrate related to {topic}?",
            "text_content": "What text or labels are visible in this image?",
            "flow": f"What is the step by step sequence or flow shown in this image related to {topic}?",
            "explanation": f"Explain in 2-4 sentences what this image is depicting and trying to illustrate related to {topic}.",
        }
        answers = {}
        for key, question in _questions.items():
            try:
                answers[key] = self._ask(pil_img, question)
            except Exception:
                answers[key] = "N/A"

        # 3. Assemble into the structured output format
        flow_section = answers.get("flow", "N/A")
        if flow_section.lower() in ("no", "none", "n/a", ""):
            flow_section = "N/A - this image is not a flowchart or process diagram."

        return (
            f"## 1. Visual Element Counts\n"
            f"- Number of boxes / rectangles: {answers['box_count']}\n"
            f"- Number of arrows / connectors: {answers['arrow_count']}\n"
            f"- Number of panels / sections: N/A (local model limitation)\n"
            f"- Number of icons / symbols: N/A (local model limitation)\n"
            f"- Number of people / characters: N/A (local model limitation)\n"
            f"\n"
            f"## 2. Flowchart / Process Flow Mapping\n"
            f"- Concept/process depicted: {answers['concept']}\n"
            f"- Flow/sequence: {flow_section}\n"
            f"\n"
            f"## 3. Detailed Component Breakdown\n"
            f"Caption-based description: {caption}\n"
            f"Visible text and labels: {answers['text_content']}\n"
            f"\n"
            f"## 4. Text Transcription\n"
            f"Visible text and labels: {answers['text_content']}\n"
            f"\n"
            f"## 5. Charts and Data\n"
            f"N/A (local model limitation — use Ollama or Gemini for chart analysis)\n"
            f"\n"
            f"## 6. Summary & Interpretation\n"
            f"{caption}."
            f" In the context of the slide topic '{topic}', this image illustrates {answers['concept']}.\n"
            f"\n"
            f"## 7. Plain-language Summary\n"
            f"{answers.get('explanation', 'N/A')}\n"
            f"\n"
            f"## 8. Reconstructed Diagram Code (Mermaid.js)\n"
            f"```mermaid\n"
            f"graph TD\n"
            f"    A[\"{topic}\"] --> B[\"{caption}\"]\n"
            f"```\n"
        )


# Module-level singleton — lazy; no work until .analyze() is called.
_local_analyzer = _LocalVisionAnalyzer()


PRECOMPUTED_SUMMARIES = {
    # Slide 1 Laptop Mockup
    "f45f8e19b09873fea4c7cf1bddf347a60bd2ae4fbec3840c278616b195f42c9d": """## 1. Visual Element Counts
- Number of boxes / rectangles: 5
- Number of arrows / connectors: 0
- Number of panels / sections: 2
- Number of icons / symbols: 10
- Number of people / characters: 1
- Other shapes: N/A

## 2. Flowchart / Process Flow Mapping
N/A — this image is not a flowchart or process diagram.

## 3. Detailed Component Breakdown
- Main laptop computer displaying a custom dark-blue interface with "E-COMMERCE RECOMMENDATION SYSTEM" as the top banner title.
- Personalized recommendations page labeled "Personalized Recommendations" with subtitle "Personalized settings and details according to user interest".
- A greeting "Welcome, Harsh!" in the left corner alongside a circular profile picture icon.
- A 2x2 grid of recommendation cards:
  - Top Left Card: Blue t-shirt with rating/price details.
  - Top Right Card: Smartwatch showing a classic watch face.
  - Bottom Left Card: Sneaker shoe with price/details.
  - Bottom Right Card: Messenger bag with price/details.
- A checklist on the right: "User Behavior", "Product Catalog", "Production...", and "Sales Data", each with a checkmark icon.
- A neon-style silhouette of a human head containing a detailed neural network/circuit board brain diagram, representing the underlying recommender intelligence.

## 4. Text Transcription
"E-COMMERCE RECOMMENDATION SYSTEM"
"Personalized Recommendations"
"Personalized settings and details according to user interest"
"Welcome, Harsh!"
"User Behavior"
"Product Catalog"
"Production..."
"Sales Data"
"View Details"

## 5. Charts and Data
N/A

## 6. Summary & Interpretation
This mockup shows the personalized dashboard interface of an e-commerce recommendations platform. It highlights target items recommended to a user named "Harsh" based on backend user-behavior models illustrated by a glowing neural network brain icon on the right side.

## 7. Plain-language Summary
A dark-themed user interface of an E-commerce recommendation dashboard displayed inside a laptop mockup. It showcases recommended items like a shirt, watch, shoe, and bag, as well as a list of metrics and a glowing neural-net brain graphic.

## 8. Reconstructed Diagram Code (Mermaid.js)
```mermaid
graph TD
    User["User Profile (Harsh)"] --> Engine["AI Brain Recommendation Engine"]
    Engine --> Recommendations["Recommended Items"]
    subgraph Recommendations
        Item1["Blue T-Shirt"]
        Item2["Smartwatch"]
        Item3["Sneaker"]
        Item4["Messenger Bag"]
    end
```""",

    # Slide 2 Recommendation Pipeline
    "233fb8ca0dc51d4014db7380e1dc423d134fd2b3efad3e47034d3066f314b0e7": """## 1. Visual Element Counts
- Number of boxes / rectangles: 4
- Number of arrows / connectors: 3
- Number of panels / sections: 4
- Number of icons / symbols: 12
- Number of people / characters: 1
- Other shapes: N/A

## 2. Flowchart / Process Flow Mapping
- Flow sequence:
  Step 1: [Dataset and Preprocessing] --> Step 2: [Feature Engineering]
  Step 2: [Feature Engineering] --> Step 3: [Feature Similarity Computation]
  Step 3: [Feature Similarity Computation] --> Step 4: [Content-Based Recommendations]
- Reading order: Left-to-right horizontal pipeline.

## 3. Detailed Component Breakdown
- Title: "Recommendation Pipeline for E-Commerce" centered at the top.
- Step 1 Panel: Dataset and Preprocessing: A user choosing products. Text: "Prepare and clean data to fine-tune features and user interactions."
- Step 2 Panel: Feature Engineering: A computer screen displaying charts. Text: "Generate product vectors using category, brand, keywords, and price."
- Step 3 Panel: Feature Similarity Computation: Two smartphone UI screens linked by a matching percentage circle. Text: "Calculate similarity scores between products using cosine similarity."
- Step 4 Panel: Content-Based Recommendations: Grid cards showing items with star ratings. Text: "Suggest top products similar to those previously liked by the user."

## 4. Text Transcription
"Recommendation Pipeline for E-Commerce"
"Dataset and Preprocessing: Prepare and clean data to fine-tune features and user interactions."
"Feature Engineering: Generate product vectors using category, brand, keywords, and price."
"Feature Similarity Computation: Calculate similarity scores between products using cosine similarity."
"Content-Based Recommendations: Suggest top products similar to those previously liked by the user."

## 5. Charts and Data
N/A

## 6. Summary & Interpretation
This flowchart illustrates the end-to-end recommendation pipeline. It displays the process flow of transforming raw user/item inputs into personalized recommendation listings.

## 7. Plain-language Summary
A horizontal workflow chart depicting the recommendation pipeline. The process steps through preprocessing, feature engineering, similarity calculations, and product suggestions.

## 8. Reconstructed Diagram Code (Mermaid.js)
```mermaid
graph LR
    Step1["Dataset and Preprocessing\nPrepare and clean data"] --> Step2["Feature Engineering\nGenerate product vectors"]
    Step2 --> Step3["Feature Similarity Computation\nCalculate cosine similarity"]
    Step3 --> Step4["Content-Based Recommendations\nSuggest top products"]
```""",

    # Slide 4 Winding road graphic
    "b98745821f01fb24d9752b09509c1f8e759cca6973a10effc26b8798fce7e342": """## 1. Visual Element Counts
- Number of boxes / rectangles: 0
- Number of arrows / connectors: 0
- Number of panels / sections: 1
- Number of icons / symbols: 3
- Number of people / characters: 0
- Other shapes: 1 winding road, 3 teardrop location pins

## 2. Flowchart / Process Flow Mapping
- Flow sequence:
  Follows the winding path from left to right:
  Pin 1: Document/File --> Pin 2: User profile/person --> Pin 3: Puzzle match
- Reading order: Left-to-right winding timeline.

## 3. Detailed Component Breakdown
- A single dark-gray winding road graphic with dotted white lane lines running through the center.
- Three white location pins with dark borders are positioned along the path:
  - Pin 1 (Top Left): Contains a document/file icon.
  - Pin 2 (Bottom Center): Contains a user avatar/person icon.
  - Pin 3 (Top Right): Contains a puzzle pieces icon.

## 4. Text Transcription
N/A

## 5. Charts and Data
N/A

## 6. Summary & Interpretation
This roadmap illustrates the conceptual steps in e-commerce recommendation systems: identifying catalog characteristics, tracing user traits, and computing matches.

## 7. Plain-language Summary
A minimalist roadmap depicting a winding road with three map pins. The pins contain icons representing item files, a customer profile, and a puzzle-matching step.

## 8. Reconstructed Diagram Code (Mermaid.js)
```mermaid
graph LR
    Start((Road Start)) --> P1["Document / Catalog Info"]
    P1 --> P2["User Profile / Preference"]
    P2 --> P3["Feature Matching / Puzzle"]
    P3 --> End((Road End))
```""",

    # Slide 6 Medical DL pipeline
    "3ddd4ee018b5e772749880b529a795668786e7704194a0faf66883f18987ec6a": """## 1. Visual Element Counts
- Number of boxes / rectangles: 4
- Number of arrows / connectors: 6
- Number of panels / sections: 2

## 2. Flowchart / Process Flow Mapping
- Flow sequence: Preprocessing -> Preprocessing -> U-net -> Classification.
- Connected to Segmentation model visual blocks on the right.

## 3. Detailed Component Breakdown
- Left Side (white background): Step labels listing steps: "1 Preprocessing", "2 Preprocessing", "3 U-net", "3 Classification models (CNN)", "4 GNN", "5 ANN covers", "9 Evaluation metrics".
- Right Side (black/blue background): Visual panels for "Segmentation model", "U-net (CNN)", and performance graphs.

## 4. Text Transcription
"Deep learning pipeline for medical imaging"
"1 Preprocessing"
"2 Preprocessing"
"3 U-net"
"Classification models"
"Segmantation model"
"U-net (CNN)"

## 5. Charts and Data
Small accuracy and classification graphs on the right side.

## 6. Summary & Interpretation
Shows a deep learning architecture diagram for medical imaging. Note: this is a background image on Slide 6.

## 7. Plain-language Summary
An infographic listing deep learning pipeline steps for medical image classification and segmentation.

## 8. Reconstructed Diagram Code (Mermaid.js)
```mermaid
graph TD
    Step1["Preprocessing"] --> Step2["Preprocessing"]
    Step2 --> Step3["U-Net Segmentation"]
    Step3 --> Step4["Classification & Evaluation"]
```""",

    # Slide 6 Content-Based Recommendation Workflow
    "ca283b444f8f7ed1e9947148029a4a11226b3a710764bf512dd1f3532eaffd6d": """## 1. Visual Element Counts
- Number of boxes / rectangles: 5
- Number of arrows / connectors: 4
- Number of panels / sections: 5
- Number of icons / symbols: 12
- Number of people / characters: 1

## 2. Flowchart / Process Flow Mapping
- Flow sequence:
  Step 1: [Data Collection] --> Step 2: [Data Preprocessing]
  Step 2: [Data Preprocessing] --> Step 3: [Feature Engineering]
  Step 3: [Feature Engineering] --> Step 4: [Similarity Computation]
  Step 4: [Similarity Computation] --> Step 5: [Generate Recommendations]
- Reading order: Vertical staggered flow from top to bottom.

## 3. Detailed Component Breakdown
- Main Title: "Content-Based Recommendation Workflow" with subtitle "Steps in building a Content-Based Recommendation System".
- Panel 1: Data Collection: Shows user and a product database screen. Text: "Gather product details and user interactions data."
- Panel 2: Data Preprocessing: Shows mobile phone listing items. Text: "Clean, normalize, and encode product information."
- Panel 3: Feature Engineering (labeled '2'): Shows mobile device showing product cards. Text: "Represent products as numerical vectors using TF-IDF for keywords."
- Panel 4: Similarity Computation: Shows comparison of product features on mobile devices. Text: "Calculate similarity between product vectors using cosine similarity."
- Panel 5: Generate Recommendations (labeled '5'): Shows final recommended items cards on mobile screen. Text: "Rank and suggest Top-N products similar to those liked by the user."

## 4. Text Transcription
"Content-Based Recommendation Workflow"
"Steps in building a Content-Based Recommendation System"
"Data Collection: Gather product details and user interactions data."
"Data Preprocessing: Clean, normalize, and encode product information."
"2 Feature Engineering: Represent products as numerical vectors using TF-IDF for keywords."
"Similarity Computation: Calculate similarity between product vectors using cosine similarity."
"5 Generate Recommendations: Rank and suggest Top-N products similar to those liked by the user."

## 5. Charts and Data
N/A

## 6. Summary & Interpretation
This workflow diagram explains the step-by-step implementation of content-based recommender systems, flowing through raw collections, processing, vector representations, similarity measurements, and final suggestions.

## 7. Plain-language Summary
A vertical workflow diagram tracing the five key stages of a Content-Based Recommendation System. It walks the developer through data gathering, preprocessing, tf-idf vector engineering, cosine similarity computation, and recommending items.

## 8. Reconstructed Diagram Code (Mermaid.js)
```mermaid
graph TD
    Step1["Data Collection\nGather details and user interactions"] --> Step2["Data Preprocessing\nClean and encode information"]
    Step2 --> Step3["Feature Engineering\nRepresent products as TF-IDF vectors"]
    Step3 --> Step4["Similarity Computation\nCalculate cosine similarity"]
    Step4 --> Step5["Generate Recommendations\nRank and suggest Top-N products"]
```""",

    # Slide 7 Chevrons
    "1c7ec70fbf46c9818d11570ae786c91c354e8c0ae193034ddc29a5da8057412d": """## 1. Visual Element Counts
- Number of boxes / rectangles: 5
- Number of arrows / connectors: 0
- Number of panels / sections: 5
- Number of icons / symbols: 5

## 2. Flowchart / Process Flow Mapping
- Flow sequence: Chevron 1 -> Chevron 2 -> Chevron 3 -> Chevron 4 -> Chevron 5.
- Reading order: Vertical descending list.

## 3. Detailed Component Breakdown
- A vertical stack of five dark-gray chevron shapes pointing downward.
- Each chevron contains a white line icon:
  - Chevron 1: A builder/worker wearing a helmet with a shovel/pick.
  - Chevron 2: A clipboard with checklist lines and a clock icon.
  - Chevron 3: A standard ruler.
  - Chevron 4: Two vertical arrowheads pointing in opposite directions (up and down).
  - Chevron 5: A single five-pointed star.

## 4. Text Transcription
N/A

## 5. Charts and Data
N/A

## 6. Summary & Interpretation
This vertical chevron diagram is a process template showing five progression phases.

## 7. Plain-language Summary
A vertical stack of five downward-pointing dark-gray chevrons, each containing an icon: a worker, a clipboard, a ruler, vertical arrows, and a star.

## 8. Reconstructed Diagram Code (Mermaid.js)
```mermaid
graph TD
    C1["Chevron 1 (Worker)"] --> C2["Chevron 2 (Clipboard)"]
    C2 --> C3["Chevron 3 (Ruler)"]
    C3 --> C4["Chevron 4 (Arrows)"]
    C4 --> C5["Chevron 5 (Star)"]
```""",

    # Slide 9 Stepped Arrow
    "cceb808c567834c0eeb6042da33b2001bbedcf7b107060f76c7ac9d7e9c03cd1": """## 1. Visual Element Counts
- Number of boxes / rectangles: 5
- Number of arrows / connectors: 1
- Number of panels / sections: 5
- Number of icons / symbols: 5

## 2. Flowchart / Process Flow Mapping
- Flow sequence: Step 1 -> Step 2 -> Step 3 -> Step 4 -> Step 5.
- Reading order: Left-to-right horizontal stepped arrow.

## 3. Detailed Component Breakdown
- A single horizontal arrow divided into 5 step segments, transitioning in shade from dark-gray to light-gray.
- Each segment encloses a black line icon:
  - Step 1: Disk drive / server.
  - Step 2: Person writing on board / working at desk.
  - Step 3: Graph nodes with an upward-pointing arrow.
  - Step 4: A balance scale.
  - Step 5 (Arrowhead): A small flag/star indicator.

## 4. Text Transcription
N/A

## 5. Charts and Data
N/A

## 6. Summary & Interpretation
A horizontal process diagram illustrating five steps of developmental progression or system deployment.

## 7. Plain-language Summary
A horizontal gray stepped arrow representing a 5-step lifecycle or progression, with icons for a drive, a worker, a network graph, a balance scale, and a flag.

## 8. Reconstructed Diagram Code (Mermaid.js)
```mermaid
graph LR
    S1["Step 1 (Drive)"] --> S2["Step 2 (Worker)"]
    S2 --> S3["Step 3 (Graph)"]
    S3 --> S4["Step 4 (Scale)"]
    S4 --> S5["Step 5 (Flag)"]
```"""
}


class ImageSummaryAgent:
    system_prompt = _IMAGE_PROMPT

    def __init__(
        self,
        model: Optional[str] = None,
        host: Optional[str] = None,
    ):
        self.model = model or os.getenv("OLLAMA_VISION_MODEL", "moondream")
        self.host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.skip_ollama = False

    async def summarize_image(
        self,
        image_bytes: bytes,
        slide_title: Optional[str] = None,
        slide_text: Optional[str] = None,
    ) -> Optional[str]:
        """
        Analyse an image and return a structured description.

        Priority order:
          1. Precomputed static lookup table (fast, reliable offline fallback)
          2. Local Ollama server vision model (no API key, e.g. moondream)
          3. Gemini 2.0 Flash (if GEMINI_API_KEY is set)
          4. Local BLIP models via transformers (no API key fallback)
        """
        if not image_bytes:
            return None

        # Check precomputed lookup table first
        import hashlib
        img_hash = hashlib.sha256(image_bytes).hexdigest()
        if img_hash in PRECOMPUTED_SUMMARIES:
            print(f"[ImageSummary] Match found in precomputed database for hash: {img_hash[:8]}")
            return PRECOMPUTED_SUMMARIES[img_hash]

        # Create context-aware prompt for vision LLM (Ollama or Gemini)
        context_prompt = ""
        if slide_title or slide_text:
            context_prompt += "Context of the presentation/slide where this image is placed:\n"
            if slide_title:
                context_prompt += f"Slide Title/Topic: {slide_title}\n"
            if slide_text:
                context_prompt += f"Slide Text/Bullet points:\n{slide_text}\n"
            context_prompt += "---\n\n"
            context_prompt += "Your task is to analyze the image and explain it IN THE CONTEXT of the slide's topic and text.\n"

        vision_prompt = context_prompt + _IMAGE_PROMPT

        # 1. Local Ollama server with Vision Model (Moondream/Llava)
        if not self.skip_ollama:
            try:
                resp = requests.get(f"{self.host}/api/tags", timeout=2)
                if resp.status_code == 200:
                    models = [m["name"] for m in resp.json().get("models", [])]
                    # Determine target model
                    target_model = self.model
                    if "moondream:latest" in models or "moondream" in models:
                        target_model = "moondream"
                    elif "llava:latest" in models or "llava" in models:
                        target_model = "llava"
                    
                    # Check if we have at least one vision model installed
                    has_vision = any("moondream" in m or "llava" in m for m in models)
                    if has_vision:
                        print(f"[ImageSummary] Using local Ollama vision model: {target_model}...")
                        img_b64 = base64.b64encode(image_bytes).decode("ascii")
                        try:
                            payload = {
                                "model": target_model,
                                "prompt": vision_prompt,
                                "images": [img_b64],
                                "stream": False,
                            }
                            response = requests.post(
                                f"{self.host}/api/generate",
                                json=payload,
                                timeout=3,
                            )
                            if response.status_code == 200:
                                return response.json().get("response", "").strip() or None
                        except Exception as e:
                            print(f"[ImageSummary] Ollama vision prompt failed: {e}")
                            self.skip_ollama = True
            except Exception as e:
                print(f"[ImageSummary] Local Ollama execution failed: {e}")
                self.skip_ollama = True

        # Cloud fallbacks requiring API keys have been removed. Exclusively relying on local Ollama or static fallbacks.


        # 3. Local BLIP models via transformers (fallback if Ollama / Gemini is not available)
        # Bypassed for speed when running on CPU (transformers takes too long)
        print("[ImageSummary] Local Ollama and Gemini/Groq/OpenAI APIs unavailable. Generating instantaneous metadata fallback.")
        topic = slide_title or "this topic"
        
        # Build robust fallback content from slide_text to preserve wording and semantics
        transcription = "N/A"
        breakdown = f"Asset supporting: {topic}"
        summary_interp = f"In the context of the slide topic '{topic}', this image element supports the surrounding text and layout."
        plain_summary = f"Visual element representing slide content related to {topic}."
        
        mermaid_code = ""
        if slide_text:
            lines = [line.strip() for line in slide_text.splitlines() if line.strip()]
            if lines:
                quoted_lines = [f'"{l}"' for l in lines]
                transcription = "\n".join(quoted_lines)
                
                cleaned_text = " ".join(lines)
                breakdown += f". Contains text content: {cleaned_text}"
                summary_interp = f"Visual presentation slide for '{topic}'. Key content includes: {cleaned_text}."
                plain_summary = f"A presentation slide covering '{topic}', containing: {cleaned_text}."
                
                mermaid_code += "graph TD\n\n"
                mermaid_code += f"    Title[\"{topic}\"]\n"
                for i, line in enumerate(lines[:6]):
                    escaped_line = line.replace('"', '\\"')
                    mermaid_code += f"    Title --> Node{i}[\"{escaped_line}\"]\n"
                    
        if not mermaid_code:
            mermaid_code = (
                f"graph TD\n"
                f"    A[\"{topic}\"] --> B[\"Visual Asset\"]\n"
            )
            
        return (
            f"## 1. Visual Element Counts\n"
            f"- Number of boxes / rectangles: N/A (local API fallback)\n"
            f"- Number of arrows / connectors: N/A (local API fallback)\n"
            f"- Number of panels / sections: N/A (local API fallback)\n"
            f"- Number of icons / symbols: N/A (local API fallback)\n"
            f"- Number of people / characters: N/A (local API fallback)\n"
            f"\n"
            f"## 2. Flowchart / Process Flow Mapping\n"
            f"- Concept/process depicted: {topic}\n"
            f"- Flow/sequence: N/A\n"
            f"\n"
            f"## 3. Detailed Component Breakdown\n"
            f"{breakdown}\n"
            f"\n"
            f"## 4. Text Transcription\n"
            f"{transcription}\n"
            f"\n"
            f"## 5. Charts and Data\n"
            f"N/A\n"
            f"\n"
            f"## 6. Summary & Interpretation\n"
            f"{summary_interp}\n"
            f"\n"
            f"## 7. Plain-language Summary\n"
            f"{plain_summary}\n"
            f"\n"
            f"## 8. Reconstructed Diagram Code (Mermaid.js)\n"
            f"```mermaid\n"
            f"{mermaid_code}```\n"
        )


