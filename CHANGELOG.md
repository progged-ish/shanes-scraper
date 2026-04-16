# Changelog

All notable changes to the NWS Synoptic Scraper will be documented in this file.

## [8.0.0] - 2026-04-09

### Added
- Collapsible CONUS Synoptic Summary section with `<details><summary>` wrapper
- Nested `<details open>` for AI Expert Summary (expanded by default)
- Proper keyword pill styling with specific CSS classes (hud-pill front, dryline, trough, ridge, shortwave, low, etc.)
- Enhanced office-level AI summaries with descriptive synoptic narrative paragraphs

### Changed
- Header title from "NWS SYNOPSIS SCRAPER v6" to "SYNOPTIC SCRAPER v8"
- Office-level AI summaries: removed bullet points, switched to flowing descriptive paragraphs
- Version bump: 7.0.0 → 8.0.0

### Fixed
- CONUS summary now properly wraps AI content in collapsible `<details>` blocks
- Nested `<details>` parsing issue resolved
- AI prompts now enforce paragraph-style output over bullet lists
- Keyword office links now have proper pill styling matching discussion keywords

## [7.0.0] - Earlier version history

### Previous versions tracked in v7 backup files
