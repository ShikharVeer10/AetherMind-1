from typing import Optional
from openai import AsyncOpenAI
class ImageInterpretationAgent:
    def __init__(self):
        self.client = AsyncOpenAI()
    async def interpret_image(self,image_bytes: bytes,slide_title: Optional[str] = None) -> str:
        prompt = self._build_prompt(slide_title=slide_title)
        response = await self.client.responses.create(
            model="gpt-4.1",
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": prompt
                        },
                        {
                            "type": "input_image",
                            "image_data": image_bytes
                        }
                    ]
                }
            ]
        )
        return response.output_text
    def _build_prompt(self,slide_title: Optional[str]) -> str:
        return """\
You are an expert visual analysis and image reconstruction system.

Analyze the provided image and produce a structured description optimized for faithful image reconstruction.

Do NOT describe slides, presentations, documents, or surrounding context.

Focus ONLY on the visual content inside the image.

Your objective is to extract enough information so that another AI image generation model can recreate a visually similar image even if the original image becomes unavailable.

Analyze the image and extract:

## 1. Scene Overview
Provide a detailed description of the entire image, including:
- overall composition
- visual hierarchy
- major regions
- focal points

## 2. Object Inventory
Identify every significant visual element. For each object provide a JSON block matching:
{
  "name": "",
  "category": "",
  "position": "",
  "size": "",
  "appearance": ""
}
Examples of categories: human, robot, gear, chart, cloud, building, server, tree, molecule, icon, vehicle.

## 3. Spatial Relationships
Describe how objects relate to one another (e.g. above, below, inside, connected_to, overlapping, surrounding, attached_to).

## 4. Visual Style
Identify:
- illustration style
- rendering style
- realism level
- artistic influences
- design language
Examples: photorealistic, corporate infographic, flat design, vector art, futuristic, 3D render, technical diagram, medical illustration, scientific visualization.

## 5. Color Analysis
Return a JSON block containing:
{
  "dominant_colors": [],
  "accent_colors": [],
  "background_colors": []
}
Use HEX color values when possible.

## 6. Shapes and Geometry
Identify:
- circles
- rectangles
- polygons
- arrows
- connectors
- icons
- decorative elements
Describe their placement and role.

## 7. Text Elements
Extract all visible text exactly as shown. Preserve wording, capitalization, and grouping. Do not summarize.

## 8. Visual Structure
Describe columns, rows, clusters, panels, sections, layers, and their arrangement.

## 9. Reconstruction Description
Generate an extremely detailed reconstruction description containing: objects, colors, positions, scale, spacing, style, lighting, relationships, and composition. The description should be sufficient for another image generation model to recreate a highly similar image.

## 10. Reconstruction Prompt
Generate a final image-generation prompt optimized for reconstruction fidelity. The prompt should describe the image precisely, avoid interpretation, avoid summarization, avoid adding new content, and preserve visual structure.

Critical Requirement:
Do not explain the image.
Do not summarize the image.
Do not infer business meaning.
Do not infer slide context.
Only describe what is visually present and necessary for reconstruction.
"""