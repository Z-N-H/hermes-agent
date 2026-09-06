---
name: json-canvas
description: Use when creating, editing, or validating JSON Canvas (.canvas) files with nodes (text, file, link, group), edges, positions, colors, and connections following the JSON Canvas Spec 1.0. Do NOT use for regular JSON or other canvas formats.
---

# JSON Canvas

## File Structure (`.canvas`)

A canvas file contains two top-level arrays per [JSON Canvas Spec 1.0](https://jsoncanvas.org/spec/1.0/):

```json
{
  "nodes": [],
  "edges": []
}
```

- `nodes` (optional): Array of node objects
- `edges` (optional): Array of edge objects connecting nodes

## Common Workflows

### Create a New Canvas
1. Create `.canvas` file with base structure `{"nodes":[],"edges":[]}`
2. Generate unique 16-character hex IDs for each node (e.g., `"6f0ad84f44ce9c17"`)
3. Add nodes with required fields: `id`, `type`, `x`, `y`, `width`, `height`
4. Add edges referencing valid node IDs via `fromNode` and `toNode`
5. **Validate**: Parse JSON; verify all `fromNode`/`toNode` values exist in nodes array

### Add a Node
1. Read and parse existing `.canvas` file as JSON
2. Generate unique ID (no collision with existing node/edge IDs)
3. Choose position (`x`, `y`) avoiding overlap (leave 50–100px spacing)
4. Append new node object to `nodes` array
5. Optionally add edges connecting new node to existing nodes
6. **Validate**: All IDs unique, all edge references resolve to existing nodes

### Connect Two Nodes
1. Identify source and target node IDs
2. Generate unique edge ID
3. Set `fromNode` and `toNode` to source/target IDs
4. Optionally set `fromSide`/`toSide` (`top`, `right`, `bottom`, `left`) for anchor points
5. Optionally set `label` for descriptive text on the edge
6. Append edge to `edges` array
7. **Validate**: Both `fromNode` and `toNode` reference existing node IDs

### Edit an Existing Canvas
1. Read and parse `.canvas` file as JSON
2. Locate target node or edge by `id`
3. Modify desired attributes (text, position, color, etc.)
4. Write updated JSON back to file
5. **Validate**: Re-check ID uniqueness and edge reference integrity

## Nodes

Array order determines z-index: first node = bottom layer, last node = top layer.

### Generic Node Attributes
| Attribute | Required | Type | Description |
|-----------|----------|------|-------------|
| `id` | Yes | string | Unique 16-char hex identifier |
| `type` | Yes | string | `text`, `file`, `link`, or `group` |
| `x` | Yes | integer | X position in pixels |
| `y` | Yes | integer | Y position in pixels |
| `width` | Yes | integer | Width in pixels |
| `height` | Yes | integer | Height in pixels |
| `color` | No | string | Preset `"1"`–`"6"` or hex (e.g., `"#FF0000"`) |

### Text Nodes
| Attribute | Required | Type | Description |
|-----------|----------|------|-------------|
| `text` | Yes | string | Plain text with Markdown syntax |
```json
{
  "id": "6f0ad84f44ce9c17",
  "type": "text",
  "x": 0,
  "y": 0,
  "width": 400,
  "height": 200,
  "text": "# Hello World\n\nThis is **Markdown** content."
}
```
> **Newline pitfall**: Use `\n` for line breaks in JSON strings. Do **not** use literal `\\n` – Obsidian renders that as the characters `\` and `n`.

### File Nodes
| Attribute | Required | Type | Description |
|-----------|----------|------|-------------|
| `file` | Yes | string | Path to file within the system |
| `subpath` | No | string | Link to heading or block (starts with `#`) |
```json
{
  "id": "a1b2c3d4e5f67890",
  "type": "file",
  "x": 500,
  "y": 0,
  "width": 400,
  "height": 300,
  "file": "Attachments/diagram.png"
}
```

### Link Nodes
| Attribute | Required | Type | Description |
|-----------|----------|------|-------------|
| `url` | Yes | string | External URL |
```json
{
  "id": "c3d4e5f678901234",
  "type": "link",
  "x": 1000,
  "y": 0,
  "width": 400,
  "height": 200,
  "url": "https://obsidian.md"
}
```

### Group Nodes
Visual containers for organizing other nodes. Position child nodes inside the group's bounds.
| Attribute | Required | Type | Description |
|-----------|----------|------|-------------|
| `label` | No | string | Text label for the group |
| `background` | No | string | Path to background image |
| `backgroundStyle` | No | string | `cover`, `ratio`, or `repeat` |
```json
{
  "id": "d4e5f6789012345a",
  "type": "group",
  "x": -50,
  "y": -50,
  "width": 1000,
  "height": 600,
  "label": "Project Overview",
  "color": "4"
}
```

## Edges

Edges connect nodes via `fromNode` and `toNode` IDs.

| Attribute | Required | Type | Default | Description |
|-----------|----------|------|---------|-------------|
| `id` | Yes | string | – | Unique identifier |
| `fromNode` | Yes | string | – | Source node ID |
| `fromSide` | No | string | – | `top`, `right`, `bottom`, or `left` |
| `fromEnd` | No | string | `none` | `none` or `arrow` |
| `toNode` | Yes | string | – | Target node ID |
| `toSide` | No | string | – | `top`, `right`, `bottom`, or `left` |
| `toEnd` | No | string | `arrow` | `none` or `arrow` |
| `color` | No | string | – | Line color |
| `label` | No | string | – | Text label |

```json
{
  "id": "0123456789abcdef",
  "fromNode": "6f0ad84f44ce9c17",
  "fromSide": "right",
  "toNode": "a1b2c3d4e5f67890",
  "toSide": "left",
  "fromEnd": "none",
  "toEnd": "arrow",
  "label": "connects to",
  "color": "2"
}
```

## Complete Example
```json
{
  "nodes": [
    {
      "id": "6f0ad84f44ce9c17",
      "type": "text",
      "x": 0,
      "y": 0,
      "width": 400,
      "height": 200,
      "text": "# Project Overview\n\nThis is the main project node.",
      "color": "1"
    },
    {
      "id": "a1b2c3d4e5f67890",
      "type": "file",
      "x": 500,
      "y": 0,
      "width": 400,
      "height": 300,
      "file": "Attachments/diagram.png"
    },
    {
      "id": "c3d4e5f678901234",
      "type": "link",
      "x": 1000,
      "y": 0,
      "width": 400,
      "height": 200,
      "url": "https://obsidian.md",
      "color": "3"
    }
  ],
  "edges": [
    {
      "id": "0123456789abcdef",
      "fromNode": "6f0ad84f44ce9c17",
      "fromSide": "right",
      "toNode": "a1b2c3d4e5f67890",
      "toSide": "left",
      "label": "see diagram"
    }
  ]
}
```

## References
- [JSON Canvas Spec 1.0](https://jsoncanvas.org/spec/1.0/)