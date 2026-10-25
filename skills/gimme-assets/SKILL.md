---
name: gimme-assets
description: Find and download official brand or retailer product images from a supplied product list, with exact variant matching, source provenance, and measured print suitability. Use for beauty packshots and other product images intended for magazine or marketing layouts.
---

# Gimme Assets

Turn a product list into an organised local export of verified official product imagery. The default is **maximum print dimensions at 300 ppi**, because placement sizes vary. Report measured suitability, never an unconditional claim that a large file is print ready.

## Inputs and defaults

Accept pasted lists, CSV, spreadsheets, or documents. Retain product names and input order; identify brand, product, shade/variant, size, and SKU where supplied. Use connected/file tools appropriate to the supplied format. Do not require a template.

Default to one front-facing product packshot per product, preferably a clean white or transparent background. Prefer the brand's source when equivalent quality is available. Use a retailer when it supplies a better exact-match image. Save additional angles only when requested or when they resolve a useful ambiguity. Do not substitute another shade, size, gift set, reformulation, or packaging generation silently.

Use a named export destination when given. Otherwise create `exports/product-images-YYYY-MM-DD-HHMMSS/` in the task workspace. Use a fresh directory for each run. The default delivery is **one flat `images/` folder**, without category, brand, or product subfolders. Put category, brand, product, size/concentration, and any alternative label in readable filenames. Proceed with clear products while flagging ambiguous entries; ask only about ambiguity that affects selection.

## Find and verify sources

Browse the live web for every sourcing run. Start with the brand's product page, official press/media library, or publicly accessible official asset library; then established retailers' product pages. Search results and image search are discovery aids: open the originating page and establish provenance before downloading.

Accept only images demonstrably supplied by the brand or retailer. A retailer's customer review gallery, marketplace seller upload, social repost, blog, Pinterest pin, search thumbnail, or influencer photo does not qualify. Prefer direct brand/retailer sites over marketplaces; use a marketplace only if official brand/retailer ownership and the particular image's official provenance are evidenced. Record the evidence, not just a plausible domain.

For each selected image:

- Confirm the requested product, size, shade, and visible packaging against page text and imagery. If the source doesn't establish a requested detail, keep it unresolved.
- Record the source page URL, direct asset URL, source kind (`brand` or `retailer`), and brief evidence linking the asset to the official product gallery or media library. CDN hosting is acceptable when the source page exposes that asset; the CDN hostname alone is not proof.
- Inspect the page's full-size gallery links, responsive `srcset`/`picture`, structured product data, and public media downloads for the largest genuine source. A zoom viewport can still show a small file. Use exposed originals or documented image service controls; speculative URL enlargement can return the same pixels or server-upscaled pixels and proves nothing.
- On Shopify product pages, the public product JSON at the observed product path plus `.json` can expose original gallery URLs, dimensions, and variant-image mappings. Inspect the gallery before choosing: the first image may be small, and the largest may depict only the box, ingredients, or a model. A brand gallery can itself contain licensed/reposted UGC; exclude images labelled UGC or otherwise of uncertain origin.
- Compare the actual downloaded dimensions and appearance. Do not use screenshots, cached thumbnails, or AI-generated/recreated products as substitutes. Do not upscale, retouch, remove watermarks, or remove backgrounds to make a deficient source appear to qualify.

Use available browser/download tools or a direct HTTP download of the verified asset. Respect access controls. If blocked, try another official source; do not bypass a login, challenge, or paywall. After the brand's available sources and at least two plausible retailers have been checked, or earlier if there are no relevant retailers, record the specific gap and move on. Continue the remaining list.

## Assess actual print suitability

Measure the downloaded file, not advertised dimensions, file size, or embedded DPI metadata. Inspect the actual image visually at meaningful magnification before approving it. Check sharp product edges/text, compression, genuine detail, watermarks, wrong packaging, cropping, unwanted overlays, and whether excessive empty canvas inflates the reported size.

At 300 ppi: `maximum print dimension in cm = native pixels / 300 × 2.54`. Calculate width and height together at the original aspect ratio. Never treat those two maxima as independently stretchable. When a product occupies a small part of the canvas, also measure a reviewed subject/crop box and report its dimensions; distinguish full-canvas from usable subject size. Do not infer resolution from byte size. Do not claim that a large pixel count proves a file was never upscaled.

If placement dimensions are provided, assess the final usable crop at that size, accounting for cover-cropping and any supplied bleed. Do not assume a bleed specification. Use the publication's requested PPI when supplied; otherwise use 300. A file below the requirement must have `needs-review` status and a `REVIEW - ` filename prefix, even if it is the best available. When no placement size is given, label the result **size reported**, subject to the stated maximum, rather than guaranteeing suitability for every placement.

Preserve downloaded originals byte for byte, including their colour profiles and transparency. Keep original JPEG and PNG production files unchanged. **Use lossless PNG as the default conversion format instead of TIFF** for compatible RGB/grayscale WebP, TIFF, AVIF, HEIC, and other raster sources. PNG preserves pixels and transparency without another lossy encoding; converting an existing JPEG to PNG adds no quality. Retain native resolution and valid ICC profiles. The helper performs and verifies these PNG conversions automatically for supported single-frame modes. Do not rename extensions, upscale, or claim conversion adds detail. Keep unsupported, animated, multipage, or unusual-colour sources in review. PNG cannot carry CMYK pixels: keep a suitable original CMYK JPEG, or flag a CMYK source requiring a publication-specific decision rather than silently converting colour spaces. Use TIFF only if the user or publication specifically requests it. Do not perform an arbitrary CMYK conversion; use the publication's output profile only when supplied and requested. See [references/print-and-export.md](references/print-and-export.md) for assessment details, export fields, and the helper's input schema.

## Download and organise

Use [scripts/export_images.py](scripts/export_images.py) to download chosen assets, preserve originals, create lossless PNG copies where needed, inspect raster data, calculate print sizes, and generate a flat images folder and index. It requires Python 3.10+ and Pillow, declared in [requirements.txt](requirements.txt). Prefer an available bundled Python runtime containing Pillow; discover it with `load_workspace_dependencies` when available, or use an existing suitable environment. If unavailable, create an isolated environment and install the requirements file for the helper rather than changing system Python.

Prepare a candidate JSON file following the linked schema. Include unresolved products as rows with `status: "not-found"`, `"ambiguous"`, or `"blocked"`, plus a reason and sources checked. Set verification flags only after the relevant review. The helper records the agent's provenance/match/visual assertions; it does not independently browse or verify them. It initially prefixes unreviewed or deficient images with `REVIEW - `. A useful two-pass workflow is to download with `visual_reviewed: false`, inspect the saved originals and any PNG derivatives with an image-viewing tool, update the candidate file, then rerun with a **new** export directory and each candidate's `local_file` pointing to its inspected original in `originals/`. Preserve the original `asset_url`; this avoids redownloading, retains original source provenance, and connects reviewed bytes to the export. Do not approve a visual review of only a search thumbnail.

Example (adapt interpreter and destination to the environment):

```bash
python3 /path/to/gimme-assets/scripts/export_images.py candidates.json --output exports/product-images-2026-10-25-120000
```

The helper creates:

```text
product-images-<timestamp>/
  images/
    001 Perfumes - Brand - Product - 50 ml - Eau de Parfum.png
    002 Perfumes - Rabanne - Invictus Elixir - 100 ml - Parfum Elixir - Alternative B.png
    REVIEW - 003 Candles - Brand - Product - 250 ml.jpg
  originals/
    <readable-source-filenames>.<original-ext>
  image-index.csv
  manifest.json
  summary.txt
```

`selected` status means the official source, exact match, and visual quality have been reviewed, with print dimensions stated. Files with `needs-review` status remain in the same `images/` folder but are clearly prefixed `REVIEW - ` and identified in the index. Do not infer reproduction permission from public availability; record published usage terms or credit requirements when available, otherwise `not-established`. Keep this as a manifest field, not an unnecessary obstacle to authorised downloading. Do not contact brands or retailers without the user's instruction.

Pass `category` when the list is grouped (for example Perfumes and Candles); the helper retains it in filenames and the index. Pass `alternative_label` for explicitly requested alternatives. The helper keeps originals in a separate flat `originals/` folder and records original paths, hashes, source formats and conversions beside production files. The source asset's format can differ from the PNG derivative's measured format; say so explicitly.

The CSV/JSON must account for every input product, including failures, with file paths, source links, dimensions, print sizes, verification status, issues, and reasons. Inspect production files, confirm indexes match files on disk, and reconcile totals against the input list. Review assets must retain their filename prefix and index status so they cannot be mistaken for approved selections. Offer a ZIP when useful or requested; keep the usable folder as well. Link directly to `images/` for convenient bulk handling.

Finish with a link to the export folder and index, selected/review/unresolved counts, and the most useful gaps. State that sizes are measured at 300 ppi (or the requested PPI). Avoid claiming all products were sourced when any are missing or mismatched.
