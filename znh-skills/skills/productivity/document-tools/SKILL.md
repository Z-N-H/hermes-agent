---
name: document-tools
description: "Document processing: PDF editing, text extraction/OCR, and PowerPoint creation/editing."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [pdf, documents, ocr, powerpoint, pptx, editing, extraction]
---

# Document Tools

Process PDFs, scanned documents, and presentations. Covers editing, extraction, OCR, and slide deck creation.

---

## PDF Editing (`nano-pdf`)

Edit PDFs using natural-language instructions.

```bash
uv pip install nano-pdf
nano-pdf edit document.pdf "fix the typo on page 3: 'teh' -> 'the'"
nano-pdf edit document.pdf "update the title on page 1 to 'Q2 Report'"
nano-pdf edit document.pdf "remove the footer from all pages"
```

**When to use:** Quick text/typo fixes in PDFs without recreating the source document.

---

## PDF & Document Extraction / OCR

Extract text from PDFs and scanned documents.

### If URL is available

Always try `web_extract` first — handles PDF-to-markdown via Firecrawl:

```python
web_extract(urls=["https://arxiv.org/pdf/2402.03300"])
```

### Local extraction

**Simple PDFs (text-based):**
```python
import pymupdf

doc = pymupdf.open("document.pdf")
for page in doc:
    print(page.get_text())
```

**Scanned PDFs / images (OCR):**
```bash
pip install marker-pdf
marker_single document.pdf --output_dir ./output/
```

**Structured extraction (tables, headers):**
```python
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict

converter = PdfConverter(create_model_dict())
doc = converter("document.pdf")
print(doc.markdown)
```

**When to use:** Extracting text from research papers, scanned reports, or image-based PDFs.

---

## PowerPoint (`python-pptx` / `pptxgenjs`)

Create, read, and edit .pptx presentations.

### Read content

```bash
python -m markitdown presentation.pptx
```

### Create from scratch

```python
from pptx import Presentation

prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout

# Add title
title = slide.shapes.add_textbox(Inches(1), Inches(0.5), Inches(8), Inches(1))
title.text_frame.text = "Q2 Results"

# Add bullet points
content = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(4))
tf = content.text_frame
tf.text = "Revenue: $1.2M"
p = tf.add_paragraph()
p.text = "Growth: +23%"
p.level = 1

prs.save("presentation.pptx")
```

### Edit existing deck

```python
from pptx import Presentation

prs = Presentation("existing.pptx")

# Update slide 3 title
slide = prs.slides[2]
slide.shapes.title.text = "Updated Title"

prs.save("updated.pptx")
```

### Speaker notes

```python
notes_slide = slide.notes_slide
text_frame = notes_slide.notes_text_frame
text_frame.text = "Speaker notes here"
```

**When to use:** Creating pitch decks, updating presentations, extracting content from .pptx files.

---

## When to Use What

| Task | Tool |
|------|------|
| Fix typo in PDF | `nano-pdf` |
| Extract text from PDF | `web_extract` (URL) or `pymupdf`/`marker-pdf` (local) |
| OCR a scanned document | `marker-pdf` |
| Create a presentation | `python-pptx` or `pptxgenjs` |
| Read a .pptx file | `markitdown` |
| Edit existing slides | `python-pptx` |

## Related Skills

- `google-workspace` — For Google Docs/Sheets/Slides integration.
- `ocr-and-documents` → absorbed into this skill.
