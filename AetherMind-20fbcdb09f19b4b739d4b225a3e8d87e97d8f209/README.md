# AetherMind – Layout-Aware Document Intelligence & Reconstruction Framework

AetherMind is a multi-agent document intelligence platform that transforms PowerPoint presentations into reconstruction-grade structured representations.

Unlike traditional OCR systems that focus primarily on text extraction, AetherMind captures visual layouts, spatial relationships, styling metadata, tables, diagrams, connectors, images, reading order, and semantic flows. The platform produces structured JSON blueprints that downstream AI systems can use to analyze, search, summarize, validate, and recreate documents with high visual fidelity.

---

## Core Innovation

AetherMind treats presentations as visual systems rather than text documents.

The platform preserves:

* Visual Structure
* Spatial Relationships
* Semantic Meaning
* Layout Intelligence
* Diagram Topology
* Reconstruction Metadata

This enables AI systems to understand not only what a document says, but how it is visually constructed.

---

# Key Capabilities

## Document Understanding

* Verbatim text extraction with hierarchy preservation
* Reading-order detection and semantic grouping
* Layout classification and visual hierarchy analysis
* Slide-level semantic interpretation using LLM reasoning
* Context-aware content extraction

---

## Layout Intelligence

* Coordinate-aware extraction in EMUs and percentages
* Shape, connector, and proximity relationship mapping
* Header and footer detection
* Visual attention flow reconstruction
* Slide geometry understanding

---

## Table & Diagram Understanding

* Table structure extraction and normalization
* Diagram node and edge detection
* Flowchart topology reconstruction
* Relationship inference across visual elements
* Mermaid.js diagram generation

---

## Image Understanding

* Vision-LLM powered image interpretation
* Embedded text extraction
* Component-level image analysis
* Design pattern understanding
* Reconstruction prompt generation

Supported Providers:

* Gemini
* OpenAI
* Groq
* Ollama
* BLIP Local Models

---

## Reconstruction Intelligence

* Reconstruction-ready JSON blueprints
* Typography and styling preservation
* Color and border extraction
* Coordinate-based rendering instructions
* Layout recreation metadata
* Visual reconstruction prompts

---

## Multi-Agent Framework

AetherMind coordinates specialized AI agents that work together to understand documents.

### Agents

* Text Extraction Agent
* Layout Analysis Agent
* Position Mapping Agent
* Relationship Mapping Agent
* Table Understanding Agent
* Diagram Understanding Agent
* Flowchart Analysis Agent
* Slide Interpretation Agent
* Image Understanding Agent

---

# Architecture

```text
Input Presentation
        │
        ▼
 PPT Extraction Layer
        │
        ▼
 Agent Orchestrator
        │
 ┌──────┼──────┬──────┬──────┬──────┐
 ▼      ▼      ▼      ▼      ▼
Text  Layout  Table Diagram Relations
Agent Agent   Agent Agent   Agent
        │
        ▼
 Context Builder
        │
        ▼
 Structured Document Model
        │
        ▼
 Reconstruction Blueprint
        │
        ▼
 AI-Powered Document Recreation
```

---

# Technology Stack

### Core Processing

* Python 3.9+
* python-pptx
* Pydantic
* Pydantic-AI

### AI & Vision

* Google Gemini
* OpenAI GPT
* Groq LLMs
* Ollama
* BLIP Transformers

### Data Processing

* Pillow
* Requests
* Torch
* Transformers

---

# Installation

```bash
git clone https://github.com/ShikharVeer10/AetherMind.git

cd AetherMind

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

---

# Usage

Run the extraction pipeline:

```bash
python main.py
```

When prompted, provide the target PowerPoint file path.

---

## Programmatic Usage

```python
import asyncio
from services.extraction_service import ExtractionService

async def main():
    service = ExtractionService(
        document_path="presentation.pptx",
        enable_summaries=True,
        enable_image_summaries=True
    )

    document = await service.extract_document()

    output_path = service.export_to_json(document)

    print(output_path)

if __name__ == "__main__":
    asyncio.run(main())
```

---

# Configuration

| Variable               | Description                                         |
| ---------------------- | --------------------------------------------------- |
| ENABLE_SUMMARIES       | Enables slide interpretation and semantic summaries |
| ENABLE_IMAGE_SUMMARIES | Enables image understanding services                |
| GEMINI_API_KEY         | Gemini vision and text models                       |
| OPENAI_API_KEY         | OpenAI fallback models                              |
| GROQ_API_KEY           | Groq inference models                               |
| OLLAMA_HOST            | Local Ollama endpoint                               |
| OLLAMA_VISION_MODEL    | Local vision model                                  |

---

# Project Structure

```text
AetherMind/
│
├── agents/
│   ├── agent_orchestrator.py
│   ├── extraction_agents.py
│   ├── slide_interpretation.py
│   └── image_summarization.py
│
├── extractors/
│   └── ppt_extractor.py
│
├── models/
│   └── document_model.py
│
├── services/
│   ├── context_builder.py
│   ├── diagram_understanding.py
│   ├── flowchart_service.py
│   ├── header_footer_service.py
│   ├── image_reconstruction.py
│   ├── image_understanding.py
│   ├── layout_analysis.py
│   └── slide_reconstruction.py
│
├── output/
│   └── extracted_json/
│
├── main.py
│
└── requirements.txt
```

---

# Extracted Outputs

AetherMind generates reconstruction-grade document intelligence.

---

## 1. Structured JSON Blueprint

Contains:

* Slide dimensions
* Text hierarchy
* Coordinates
* Shape geometry
* Layout metadata
* Table structures
* Connector networks
* Reading order
* Diagram topology
* Relationship mappings
* Styling information
* Reconstruction prompts

---

## 2. Semantic Slide Summary

Provides:

* Conceptual interpretation
* Semantic flow
* Visual design analysis
* Diagram explanations
* Plain-English summaries
* Reconstruction guidance

---

# Why AetherMind?

| Traditional OCR            | AetherMind |
| -------------------------- | ---------- |
| Text Extraction            | ✓          |
| Layout Intelligence        | ✓          |
| Coordinate Mapping         | ✓          |
| Table Understanding        | ✓          |
| Diagram Understanding      | ✓          |
| Relationship Mapping       | ✓          |
| Reading Order Analysis     | ✓          |
| Visual Hierarchy Detection | ✓          |
| Reconstruction Metadata    | ✓          |
| AI Recreation Support      | ✓          |

AetherMind enables AI systems to understand both the content and structure of documents, making high-fidelity document reconstruction possible.

---

# Current Capabilities

* PowerPoint Extraction
* Layout Analysis
* Diagram Understanding
* Flowchart Reasoning
* Relationship Mapping
* Image Understanding
* Reconstruction Blueprint Generation
* Multi-Agent Document Intelligence

---

# Roadmap

### Near-Term

* PDF Extraction
* Advanced Form Understanding
* Improved Table Reconstruction
* Enhanced Diagram Reasoning

### Future

* Multi-Document Reasoning
* Knowledge Graph Generation
* Reconstruction Fidelity Scoring
* Pixel-Level Validation
* Enterprise Document Intelligence Workflows

---

# License

This project is intended for research, experimentation, and enterprise document intelligence workflows.

---

## AetherMind

Transforming documents into reconstruction-ready intelligence through layout awareness, multi-agent reasoning, and semantic understanding.

