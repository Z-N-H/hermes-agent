---
name: creative-tools
description: "Creative visual and media generation: diagrams, ASCII art, infographics, web design, generative art, video, and media workflows."
version: 1.0.0
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [creative, visual, diagrams, ascii, infographics, web-design, generative-art, video, media, comfyui, manim, p5js]
---

# Creative Tools

Generate visual content, diagrams, art, video, and media with AI-powered and code-driven tools.

---

## Diagrams & Architecture

### Architecture Diagrams (dark-themed SVG)

Generate dark-themed SVG architecture/cloud/infra diagrams as standalone HTML files.

**Trigger:** user asks for "architecture diagram," "cloud diagram," "system diagram," "draw the architecture."

**Workflow:**
1. Ask the user for the diagram type (cloud architecture, data flow, network, etc.)
2. Generate a dark-themed SVG diagram using HTML/CSS/SVG
3. Output as a single `.html` file with embedded styles
4. Open in browser or share the HTML directly

See `references/architecture-diagram.md` for full templates and examples.

### Excalidraw (hand-drawn style)

Create hand-drawn Excalidraw JSON diagrams for architecture, flowcharts, and sequence diagrams.

**Trigger:** user asks for "excalidraw," "hand-drawn diagram," "sketch diagram."

**Workflow:**
1. Determine diagram type (arch, flow, sequence)
2. Generate Excalidraw-compatible JSON
3. Save as `.excalidraw` file
4. Open in Excalidraw (web or desktop app)

See `references/excalidraw.md` for JSON structure and generation scripts.

---

## ASCII Art & Video

### ASCII Art

Generate ASCII art using pyfiglet, cowsay, boxes, and image-to-ASCII conversion.

```bash
pyfiglet "Hello World"           # large text art
cowsay "Moo"                      # speech bubble with cow
boxes -d diamond "text"           # bordered text
python3 scripts/image_to_ascii.py img.jpg  # convert image
```

See `references/ascii-art.md` for full command reference and style options.

### ASCII Video

Convert video/audio to colored ASCII MP4/GIF.

```bash
python3 scripts/ascii_video.py input.mp4 output.mp4
```

Supports color palettes, character sets, and frame-rate control.

See `references/ascii-video.md` for codec options and rendering parameters.

---

## Infographics

### Baoyu Infographic (信息图)

Generate infographics in 21 layouts × 21 styles (信息图, 可视化).

**Trigger:** user asks for "infographic," "信息图," "visualization in Chinese style."

**Workflow:**
1. Collect data points and narrative from the user
2. Choose layout and style from the 21×21 matrix
3. Generate HTML/SVG infographic
4. Export as PNG or share HTML

See `references/baoyu-infographic.md` for the layout/style matrix and generation API.

---

## Web Design & HTML Artifacts

### Claude Design (HTML artifacts)

Design one-off HTML artifacts: landing pages, decks, prototypes.

**Trigger:** user asks for "landing page," "deck," "prototype," "HTML artifact."

**Workflow:**
1. Understand the purpose (landing, deck, prototype)
2. Design responsive HTML/CSS/JS in a single file
3. Include interactive elements and animations
4. Save as `.html` and open in browser

See `references/claude-design.md` for design patterns and component library.

### Sketch (throwaway mockups)

Create throwaway HTML mockups: 2-3 design variants to compare.

**Trigger:** user asks for "mockup," "wireframe," "design variant."

**Workflow:**
1. Generate 2-3 HTML variants with different layouts/styles
2. Save as separate `.html` files
3. Open side-by-side for comparison
4. Iterate based on user feedback

See `references/sketch.md` for rapid mockup patterns.

### Pretext (browser demos)

Build creative browser demos with @chenglou/pretext.

**Trigger:** user asks for "browser demo," "interactive demo," "pretext."

**Workflow:**
1. Set up pretext project
2. Build interactive demo with React-like components
3. Bundle and serve

See `references/pretext.md` for setup and component patterns.

### Popular Web Designs (design systems)

Implement 54 real design systems (Stripe, Linear, Vercel, etc.) as HTML/CSS.

**Trigger:** user asks for "design system," "Stripe-style," "Linear-style," "Vercel-style."

**Workflow:**
1. Identify the target design system
2. Generate HTML/CSS matching the system's tokens (colors, typography, spacing)
3. Save as standalone `.html` or component files

See `templates/` for starter files from major design systems.

### Design MD (spec files)

Author and validate Google's DESIGN.md token spec files.

**Trigger:** user asks for "DESIGN.md," "design tokens," "token spec."

**Workflow:**
1. Create DESIGN.md with token definitions
2. Validate against the spec
3. Export to CSS variables, JSON, or other formats

See `templates/design-token-spec.md` for the spec template.

---

## Generative Art & Video

### p5.js

Create generative art, shaders, interactive sketches, 3D, and more with p5.js.

**Trigger:** user asks for "generative art," "p5js," "processing," "creative coding."

**Workflow:**
1. Set up p5.js sketch (HTML + JS)
2. Implement generative algorithm or interactive scene
3. Run in browser or export as video/GIF

See `references/p5js.md` for sketch templates and shader examples.

### Manim Video

Create 3Blue1Brown-style math/algorithm animations with Manim CE.

**Trigger:** user asks for "animation," "math video," "manim," "3b1b style."

**Workflow:**
1. Write Python scene using Manim CE
2. Render with `manim -pql scene.py SceneName`
3. Output as MP4

See `references/manim-video.md` for scene templates and rendering options.

### ComfyUI

Generate images, video, and audio with ComfyUI workflow system.

**Trigger:** user asks for "ComfyUI," "image generation workflow," "stable diffusion workflow."

**Workflow:**
1. Install ComfyUI and required nodes
2. Build or load a workflow JSON
3. Run the workflow to generate media

See `references/comfyui.md` for workflow patterns and node installation.

### TouchDesigner MCP

Control a running TouchDesigner instance via twozero MCP server.

**Trigger:** user asks for "TouchDesigner," "TD," "visual programming," "real-time graphics."

**Workflow:**
1. Start TouchDesigner with MCP server
2. Send commands to control parameters, trigger scenes, or read data
3. Build interactive real-time visuals

See `references/touchdesigner-mcp.md` for MCP setup and command reference.

---

## Text Humanization

### Humanizer

Strip AI-isms and add real voice to text.

**Trigger:** user asks to "humanize," "make this sound natural," "remove AI tone."

**Workflow:**
1. Analyze the text for AI markers ("In conclusion," "It's important to note," etc.)
2. Replace with natural alternatives
3. Add specificity, imperfection, and personal voice
4. Vary sentence length and structure

See `references/humanizer.md` for the full transformation guide and before/after examples.

---

## GIF Search

Search and download GIFs from Tenor via curl + jq.

```bash
# Search Tenor
curl -s "https://g.tenor.com/v1/search?q=hello&key=YOUR_KEY&limit=10" | jq '.results[].media[0].gif.url'

# Download
curl -sL "URL" -o hello.gif
```

See `references/gif-search.md` for API details and batch download scripts.

---

## When to Use What

| Task | Tool |
|------|------|
| Dark-themed architecture diagram | Architecture Diagram (SVG HTML) |
| Hand-drawn sketch diagram | Excalidraw |
| ASCII text art | ASCII Art (pyfiglet, cowsay) |
| ASCII video | ASCII Video |
| Chinese-style infographic | Baoyu Infographic |
| Landing page / deck / prototype | Claude Design |
| Quick mockup comparison | Sketch |
| Browser demo | Pretext |
| Real design system implementation | Popular Web Designs |
| Design token spec | Design MD |
| Generative art / shaders | p5.js |
| Math / algorithm animation | Manim Video |
| Image/video/audio workflow | ComfyUI |
| Real-time visuals | TouchDesigner MCP |
| Humanize AI text | Humanizer |
| Find a GIF | GIF Search |
