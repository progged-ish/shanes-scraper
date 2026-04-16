# Shane's NWS Scraper V9 — Development Log
_Started: 2026-04-13_

## Context
V8 was a broken reconstruction that lost all prompt tuning from the weekend. The per-office prompt ("Summarize this in 3-4 bullet points") produces forecast summaries, NOT synoptic feature extractions. V9 is a full rewrite of the prompting architecture.

## Key Design Decision: Feed FULL AFD, Not Extracted Sections
- AFDs do NOT have a consistent "SYNOPTIC" section across offices
- Three formats exist: .SYNOPSIS (Western, short), .DISCUSSION (full synoptic), .NEAR TERM/.SHORT TERM (SPC region)
- Extracting sections misses synoptic info scattered in other sections
- **V9 feeds the entire AFD text** (truncated to 16K chars for LM Studio context)
- v8's `extract_synoptic_discussion()` function is NO LONGER USED for per-office AI calls

## Per-Office Prompt (V9.1 — FINALIZED 2026-04-13)

### Architecture: Split System + User Prompt
Rules in the user message (right before AFD text) suppress leakage far better than system-only. The model attends more to instructions adjacent to the input data.

### System Prompt
```
You are a synoptic analyst scanning NWS Area Forecast Discussions for operational weather intelligence.

Extract ONLY synoptic-scale features the forecaster identifies. Report:
- Positioning and evolution of troughs, ridges, fronts, drylines, surface lows, shortwaves, and jet streaks
- Interactions between features (e.g., shortwave ejecting out of base of longwave trough)
- Mesoscale features tied to synoptic forcing: dryline position and mixing evolution, outflow boundaries, low-level jets, convective initiation timing relative to synoptic lift, model uncertainty on these features
- Anything the forecaster notes that models may struggle with (e.g., dryline position, phasing, amplification doubts)

Format: 2-4 short statements. Each statement names the feature first, then its position or behavior. No bullets, no markdown.
```

### User Prefix (prepended before AFD text)
```
Extract synoptic features from this AFD. STRICT RULES:
- If the AFD mentions a Watch, Warning, Advisory, or Red Flag — do NOT repeat it. Name the synoptic driver instead.
- No impact language ("severe storms possible", "hard freeze likely", "critical fire weather"). Only the feature causing it.
- No precipitation totals, snow totals, RH values, or fire weather indices.
- No public-facing phrasing.

If the AFD says "Red Flag Warning due to low RH and gusty winds" you write: "Dry southwesterly flow with low mixing heights."

EXAMPLE of good output (format only, do not copy or paraphrase this content):
Longwave trough anchored over the eastern Pacific with shortwaves rotating through the base. Amplifying ridge over the Intermountain West nudging the trough axis eastward by midweek. Model spread on timing of the next shortwave ejection.

AFD TEXT:
```

### V9.1 Iteration History

**V9.0** (single system prompt, no examples, original from first session):
- PQR: Good, borderline mesoscale on CAPE line
- SLC: Strong output
- OUN: Leaked "severe storms possible" + "Red Flag Warning" (lines 4-5)
- LWX: Clean
- RIW: Leaked "hard freeze" (line 4)
- ~20% impact leakage rate

**V9.1-1** (added mesoscale carve-out + few-shot GOOD/BAD examples in system prompt):
- OUN: Still leaked Red Flag/Watch + "severe storms"
- FFC: Hallucinated dryline/GFS-NAM from example (FFC AFD has no dryline)
- BOU: Hallucinated dryline/GFS-NAM from example (BOU AFD has no dryline)
- GJT: Clean
- MHX: Clean
- Problem: Few-shot example too geographically specific → model copies content, not format

**V9.1-2** (generic Pacific example, added "do not copy content" warning):
- OUN: Still leaked Red Flag + "severe storms"
- FFC: Clean
- BOU: Clean (minor "critical fire weather" tail)
- GJT: Clean
- MHX: Clean
- Example hallucination fixed, but OUN impact leakage persists from system-only rules

**V9.1-3** (SPLIT prompt — rules moved to user message prefix): ← FINAL
- OUN: 1 minor leak ("severe storms possible") — acceptable, "severe" is a convective classification
- FFC: CLEAN — ridge + model uncertainty
- BOU: CLEAN — trough/jet/moisture/surface low
- GJT: CLEAN — split-flow, PWAT, QPF uncertainty
- MHX: CLEAN — ridge/front + outflow boundaries
- Product/impact leakage (Warning/Watch/Red Flag/hard freeze): effectively zero

### Key Findings from Prompt Iteration
1. **Split system/user prompt** matters more than prompt length — rules adjacent to input data suppress leakage
2. **Few-shot examples must be geographically generic** — specific dryline/GFS-NAM example gets hallucinated into non-Plains offices
3. **"Do not copy or paraphrase this content"** is necessary alongside examples for 7b models
4. **Mesoscale carve-out** works well — dryline, outflow boundaries, LLJ, convective initiation timing are correctly preserved as synoptically-forced features
5. **"severe" leakage** is acceptable — it's a storm classification, not a product name. Hard line: no Watch/Warning/Advisory/Red Flag product names
6. **temperature=0.3** works well; lower temps don't meaningfully reduce the remaining leakage but do reduce variety

---

## Regional + CONUS Prompts (CARRIED FROM V8 — STILL GOOD)

### Regional Rollup Prompt
```
You are a Duty Synoptician writing a regional weather brief for the forecast desk.

You will receive multiple office-level synoptic summaries from a single NWS region. Each office covers part of a larger weather pattern.

MERGE AND DE-DUPLICATE: Recognize that adjacent offices are describing the SAME weather features from different vantage points. Merge overlapping reports into unified descriptions of regional-scale systems.

OUTPUT: 2-3 sentences describing the dominant synoptic pattern across this region. Active voice. No bullets, no lists, no markdown, no filler. Start directly with the pattern.

AVOID TEMPLATE PHRASING: Do not repeat boilerplate like "undercuts the retreating ridge" or "steepening lapse rates and enhancing deep-layer shear." Each region has distinct dynamics — describe them specifically.
```

### CONUS Bulletin Prompt
```
You are the Lead National Synoptician preparing the continental CONUS weather bulletin.

You will receive 4 regional synoptic narratives (Western, Central, Southern, Eastern). Each is already filtered to pure synoptic mechanics.

SYNTHESIZE: Merge overlapping features across regions into continental-scale systems. A front described by both Southern and Eastern regions is ONE front. A trough spanning Central and Western regions is ONE trough.

STRUCTURE: 2-3 paragraphs. Open with the dominant longwave pattern and its evolution, then detail the key shortwave/surface reflections and their interactions, close with what's coming next.

TONE: Professional internal forecast desk brief. Discuss advection, cyclogenesis, jet dynamics. No public-facing language.

NO: bullets, lists, markdown, introductory phrases, or concluding phrases. Output ONLY the bulletin text.

AVOID TEMPLATE PHRASING: Do not reuse formulaic phrases like "undercuts the retreating ridge" or "steepening lapse rates and enhancing deep-layer shear." Write each paragraph with fresh, specific language about the actual pattern.
```

**Status: Regional and CONUS prompts are close to finalized. No changes needed pending v9 code integration.**

---

## Architecture (V9 — Fully Implemented)

### Dual-Model Hybrid
- **Per-office**: qwen2.5-7b-instruct via LM Studio (parallel, 8 workers, 138 offices)
- **Regional + CONUS**: gemini-2.5-flash via Gemini API (5 calls, rate-limited at 12.2s interval)
- Fallback: If Gemini unavailable, regional/CONUS falls through to LM Studio

### Code Changes Completed
1. ✅ **Remove `extract_synoptic_discussion()` from per-office AI call path** — feed full AFD
2. ✅ **Update `get_fast_model_summary()`** to use V9.1 split prompt, pass full AFD text
3. ✅ **Keep `extract_synoptic_discussion()`** only for keyword extraction (untouched in process_office)
4. ✅ **Tighten prompt** to reduce impact/hazard language leakage (split system/user architecture)
5. ✅ **Remove AK/CAN offices** from `all_offices_synoptic` dict (138 offices, down from ~147)
6. ✅ **`process_office()`** already passes `discussion` not `synoptic_text` — no change needed
7. ✅ **HTML/UI modernization** — v9 template, collapsed keyword/discussion sections, 15px font
8. ✅ **JSON export enriched** — raw AFD text, ai_elapsed, synoptic_summary, regional_narratives
9. ✅ **Template updated** — v9 template with collapsible sections, larger font, v9 branding

### Files
- Script: `/home/progged-ish/projects/shanes-scraper/shanes_nws_scraper_v9.py` (V9.1 prompt, AK/CAN removed, full AFD feed)
- Template: `/home/progged-ish/projects/shanes-scraper/html_templates/modern_dark_template_v9.html` (15px, collapsible, v9 branding)
- Venv: `/home/progged-ish/projects/shanes-scraper/venv/`
- Data dir: `/home/progged-ish/projects/shanes-scraper/data/`
- Config: `/home/progged-ish/projects/shanes-scraper/config/smtp_config.json`

### HTML/UI Changes (V9)
- ✅ Keyword count section removed from sidebar, keyword office links retained
- ✅ Keyword pills: subdued outline style (unchanged from v8, already good)
- ✅ AI summary expanded by default, keyword features and full discussion collapsed (click to expand)
- ✅ Font size bumped from 14px to 15px base
- ✅ Template versioned as v9 (title, topbar, footer)
+- ✅ Details toggle buttons styled with .collapsible-header CSS + toggle arrows
+- ✅ Sidebar keyword office links now color-coded outline pills matching hud-pill palette (kw-link-*, kw-label-*, kw-section-*)
+  - Python: `canonicalize_keyword()` applied to sidebar keyword groups → class names like `kw-link-front`, `kw-label-trough`, `kw-section-dryline`
+  - CSS: 3 new class families added to template — `.kw-label-*` (label text color), `.kw-section-*` (left border tint), `.kw-link-*` (link pill color + border at 0.4 alpha)
+  - Colors match hud-pill palette exactly: front=red, trough=orange, dryline=yellow, ridge=green, shortwave=amber, jet-streak=cyan, low=blue, upper-low=violet, record=rose
