---
name: research-toolkit
description: "External research tools — arXiv, blog feeds, prediction markets, maps, and feature auditing."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [research, arxiv, blogs, polymarket, maps, audit]
---

# Research Toolkit

## Overview

This umbrella covers external data sources and research utilities: academic paper
search (arXiv), blog/RSS monitoring (blogwatcher), prediction market data
(Polymarket), geospatial queries (maps), and local tool feature auditing.

## 1. arXiv

Search and download academic papers.

```bash
# Search by keyword
arxiv search "transformer architecture"

# Search by author
arxiv search --author "Geoffrey Hinton"

# Search by category
arxiv search --category cs.LG

# Download a paper by ID
arxiv download 2304.12345
```

**Tips:**
- Use `web_extract` on arXiv PDF URLs to get markdown content for summarization.
- The `search_arxiv.py` script in `references/arxiv/scripts/` provides a programmatic
  interface for bulk searches.

See `references/arxiv/search_arxiv.py` for the Python search script.

## 2. Blogwatcher

Monitor blogs and RSS/Atom feeds via `blogwatcher-cli`.

```bash
# Add a feed
blogwatcher add https://karpathy.github.io/feed.xml

# Check for new posts
blogwatcher check

# List tracked feeds
blogwatcher list
```

Use this to stay current on research blogs, project updates, and release notes.

## 3. Polymarket

Query prediction market data for event probabilities and trading history.

```bash
# List active markets
polymarket markets --active

# Get market details
polymarket market --id <market_id>

# Get orderbook
polymarket orderbook --id <market_id>
```

**Python API:** See `references/polymarket/polymarket.py` for programmatic access.

## 4. Maps (OpenStreetMap / OSRM)

Geocoding, points of interest, routes, and timezone queries.

```bash
# Geocode an address
maps geocode "1600 Amphitheatre Parkway, Mountain View, CA"

# Get route
maps route "origin" "destination"

# Find POIs
maps poi --type restaurant --near "San Francisco"
```

**Python client:** See `references/maps/maps_client.py` for the Python API wrapper.

## 5. Tool Feature Audit

Audit a locally-installed open-source tool to determine which features are
available, which require paid tiers, and how the architecture splits.

**Process:**
1. Check installed version (`pip list`, `python3 -c "import pkg; print(pkg.__version__)"`)
2. Check PyPI for latest (`pip index versions <pkg>`)
3. Check what's actually running (`ss -tlnp`, `ps aux`, `curl localhost:port`)
4. Examine wrapper/integration code
5. Research official docs for "Pricing", "Architecture", and feature pages
6. Report as a table: Feature | Local? | Free? | Notes

**Agno-specific reference:** The SDK is fully open source. The AgentOS runtime is
open source. The Control Plane web UI (`os.agno.com`) is hosted-only in the free
tier; self-hosting requires Enterprise.

See `references/tool-feature-audit/agno-architecture.md` for the full Agno
architecture breakdown.
