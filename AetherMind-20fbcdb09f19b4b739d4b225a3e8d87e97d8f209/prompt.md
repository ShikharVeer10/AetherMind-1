You are an expert Presentation Designer. I have uploaded extraction files representing a slide document (_reconstruction.json, _slide_blueprint.json, _summary.txt, and _full.json). **YOUR OBJECTIVE:** I want you to use your image generation tool (DALL-E 3) to visually recreate this slide as an image. **INSTRUCTIONS BEFORE GENERATING:** 1. **Read the Files:** Briefly analyze _reconstruction.json and _slide_blueprint.json to understand the visual layout (e.g., is it a two-column layout, a flowchart, or a single-column findings panel?). Look for the color_palette, background_color, and design_tokens. 2. **Find the Prompts:** Look inside the JSON/Summary for any pre-written image_generation_prompt or reconstruction_instructions. 3. **Handle Text Carefully:** DALL-E cannot render massive amounts of paragraph text without misspelling words. Therefore, only include the **Main Slide Title** and the **Primary Subheadings** in the image generation prompt. Represent body paragraphs as visually styled placeholder blocks or abstract text lines. 4. **Construct the DALL-E Prompt:** Combine the layout structure, the color palette, the specific shapes/charts mentioned, and the main headings into one highly descriptive, diffusion-optimized prompt. **ACTION:** Please generate the image now using the visual context you extracted. Ensure the aspect ratio is set to widescreen (16:9) if possible, and make the design look like a premium, professional corporate presentation slide.
## STRICT CONTENT PRESERVATION

Every first-level semantic section extracted from the JSON MUST appear in the regenerated slide.

Do not merge sections.

Do not omit any category.

Do not summarize categories.

If the source slide contains N top-level cards, panels, columns, or sections, the regenerated slide MUST contain exactly N corresponding sections.

Preserve:
- number of sections
- visual grouping
- hierarchy
- ordering
- relative placement

Only rewrite the wording inside each section.

Never remove an entire card because of space constraints.

If necessary, shorten individual bullet text while preserving its semantic meaning rather than deleting a section.
Before generating the slide:

1. Count the number of semantic groups/cards in the extracted JSON.
2. Verify that the regenerated layout contains the same number.
3. If the counts differ, regenerate internally until they match.

Original Slide
        ↓
Extraction
        ↓
Semantic JSON
        ↓
Count semantic cards
        ↓
Generate Prompt
        ↓
Generate Image
        ↓
Validate:
    JSON cards = Image cards?
        ↓
No → Regenerate
Yes → Return