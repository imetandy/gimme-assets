# Print measurements and export contract

## Print checks

- The default acceptance gate is **width ≥2500 px and height ≥2500 px**, in any aspect ratio. Only when no qualifying primary images can be found for the exact product after the documented source search may images with **both dimensions ≥1900 px** be selected. `resolution_tier` is `primary`, `fallback` or `below-minimum`; the tier does not alone establish selection. A fallback needs `primary_search_exhausted: true`, `fallback_reason` and `sources_checked`. Known digital overlays and size-policy failures are rejected and omitted from the production folder. See [image-selection.md](image-selection.md) for visual examples and search rules.
- Use native pixel dimensions after interpreting EXIF orientation. Embedded 72/96/300 DPI labels are not an acceptance test. A 1200 × 1800 px file supports about 10.16 × 15.24 cm at 300 ppi; a 3000 × 3000 px file supports 25.4 × 25.4 cm. Neither proves optical sharpness.
- Inspect blank padding and transparent margins. For packshots, report a manually reviewed product/crop bounding box when the canvas is materially larger than the useful subject. Crop coordinates use the orientation-corrected image. State whether shadows and desired margins are included. Keep the original unmodified.
- `crop_box_px: [left, top, right, bottom]` defines the useful rectangle. Coordinates are in orientation-corrected pixels, right/bottom exclusive. The helper uses this rectangle for usable maximum size, while also reporting full-canvas dimensions. No box means full-canvas measurements, not automatically subject measurements.
- With a target width W and height H in cm, `cover_ppi = min(usable_width_px / (W / 2.54), usable_height_px / (H / 2.54))` checks resolution if filling that rectangle, without stretching. Aspect mismatch entails cropping. Visually check that the crop retains the product; numerical resolution alone cannot approve composition. A contained packshot can occupy a smaller proportion of the layout slot; use its actual placed dimensions if known.
- The user's default conversion format is lossless PNG, at the native pixel dimensions. Keep original JPEG/PNG files unchanged; converting JPEG to PNG adds no detail. Retain source bytes separately. The helper verifies the PNG's orientation-corrected dimensions, decoded pixels, palette colours/transparency and embedded ICC bytes against the source. Untagged images stay untagged unless a justified profile assignment is separately requested and documented. PNG cannot store CMYK pixels: preserve a suitable CMYK JPEG or flag unusual colour modes for a publication-specific decision. Do not silently discard a CMYK profile or flatten transparency for JPEG. Use TIFF only when explicitly requested. [Adobe's format guidance](https://experienceleague.adobe.com/en/docs/dynamic-media-classic/using/master-files/best-practices-optimizing-quality-images) explains PNG's lossless compression and alpha support, and JPEG's lossy encoding.
- Do not turn a resolution check into a blanket prepress guarantee: final crop, layout scale, colour/output profile, and any reproduction terms still depend on the publication.

Primary reference: [Adobe: Image size, resolution, and resampling](https://helpx.adobe.com/photoshop/desktop/crop-resize-transform/resize-adjust-resolution/image-size-resolution-and-resampling.html). Adobe explains the pixel/size/PPI relationship and that upsampling does not recover missing detail. [Adobe: Colour-managing imported images](https://helpx.adobe.com/ie/photoshop/using/color-managing-imported-images.html) describes embedded profiles and CMYK handling.

## Candidate input

The helper reads a JSON array with **one row per candidate image**. Every image has a unique `id`; all images of the exact product share an `input_id`. Repeat brand/product/variant/size consistently across its rows. Use multiple rows covering both `image_type: "product"` and `"lifestyle"`. Unresolved products still need an inventory row. Use literal booleans for verification flags. Required for downloadable rows: `id`, `brand`, `product`, `image_type`, `source_kind`, `source_page_url`, `asset_url`, and `source_evidence`. Unverified candidates can be put in temporary review exports; valid provenance fields are still required.

```json
[
  {
    "id": "001",
    "input_id": "serum-30ml",
    "input_product": "Brand Example Serum 30 ml",
    "brand": "Brand Example",
    "product": "Serum",
    "variant": "",
    "size": "30 ml",
    "sku": "",
    "view": "front",
    "image_type": "product",
    "source_kind": "brand",
    "source_page_url": "https://brand.example/products/serum",
    "asset_url": "https://cdn.brand.example/serum-original.jpg",
    "source_evidence": "Direct image linked from the brand's main product gallery; page specifies 30 ml.",
    "source_verified": true,
    "match_verified": true,
    "match_notes": "Product name and 30 ml packaging match the request.",
    "visual_reviewed": false,
    "quality_issues": [],
    "usage_terms": "not-established",
    "usage_terms_url": "",
    "credit": "",
    "sources_checked": ["https://brand.example/products/serum"]
  },
  {
    "id": "002",
    "input_product": "Brand Example Lipstick shade 02",
    "brand": "Brand Example",
    "product": "Lipstick",
    "variant": "02",
    "status": "not-found",
    "reason": "Only shade 01 was available from the sources checked.",
    "sources_checked": ["https://brand.example/products/lipstick"]
  }
]
```

Other optional fields:

- `input_id`: shared identity of the requested exact product across all its images, including unresolved rows. The helper groups coverage and fallback decisions by this ID plus brand/product/variant/size/SKU. Use a different ID for distinct requested products and alternatives.
- `image_type`: required on downloadable rows; `product` or `lifestyle`. Use `view` to describe front, angled, open, detail, still-life, model or in-use compositions. Both types can be included in the same flat destination.
- `overlay_free`: set `true` only after inspecting the actual image and confirming it contains no digitally added text or graphics. `false` rejects it; absent keeps it in review. Text printed on the physical product or in photographed background styling is allowed. This is an agent assertion, not machine detection.
- `primary_search_exhausted`: boolean, paired with a nonempty `fallback_reason` and `sources_checked` URL array to document that no qualifying 2500 px-on-both-sides image can be found for the product. These fields are needed to accept any image with a side between 1900 and 2499 px. They do not override the absolute floor or overlay rule. Do not set the flag before completing the source search.
- `category`: group supplied by the user, retained as an index column and available in custom filenames; it does not create a subfolder.
- `alternative_label`: clear label for an explicitly requested alternative; retained in the index and available in custom filenames. Its complete value is used when included in a template.
- `local_file`: absolute path of an original saved by a browser, or an original from the first review pass. Source page and asset URL remain required. The helper copies it byte for byte.
- `crop_box_px`: manually reviewed useful/subject rectangle, as described above.
- `target_width_cm` and `target_height_cm`: supply both for a target size check. The helper defaults to 300 ppi, adjustable with `--ppi`. The same PPI applies to every row in a run.
- `quality_issues`: array of observed concerns; any entry prevents selection. Use specific observations such as `packaging text is blurred`, `source appears enlarged`, or `profile requires colour review`. For an observed digital overlay also set `overlay_free: false` so it is excluded from production, not merely marked for review.
- `notes`: useful free text such as packaging-generation evidence or crop rationale.

The script preserves unrecognised input fields in manifest records, allowing product-specific editorial metadata. `status` may be absent/`candidate` for downloadable rows, or `not-found`, `ambiguous`, or `blocked` with a reason for unresolved rows. Duplicate image IDs are rejected before downloads. To approve the sample's first row after visual review, set both `visual_reviewed: true` and `overlay_free: true`; no fallback metadata is needed when both dimensions are at least 2500 px.

## Filenames and destination

The default filename stem is `{brand}_{product}_{index:03d}`. The helper appends the extension for the actual production format, for example `Jo Malone London_Sea Salt & Bergamot_001.png`. Spaces and accents inside names are preserved; the underscores separate brand, product and candidate-image index. Numbering follows the one-based row across the export, including unresolved or rejected rows, and uses at least three digits. Multiple images of a product therefore get different numbers without changing the default pattern. Review status never adds a filename prefix or suffix.

Use `--filename-format` for a custom stem. Supported fields:

| Field | Value |
| --- | --- |
| `{brand}`, `{product}` | Brand and product name |
| `{index:03d}` | Input row number, zero-padded to three digits |
| `{id}` | Unique candidate ID |
| `{image_type}` | `product` or `lifestyle` |
| `{category}`, `{variant}`, `{size}`, `{sku}`, `{view}`, `{alternative_label}` | Optional candidate metadata; empty when absent |

For example, `--filename-format "{index:03d} - {brand} - {product} - {size}"` produces `001 - Jo Malone London - Sea Salt & Bergamot - 100 ml.png`. Leave off the file extension. Optional empty fields leave their surrounding separators in place. Only the index supports numeric formatting (`d`, or widths 1–9 such as `03d`). Arbitrary field access, conversions, nested formatting, path separators and invalid filename characters in template literals are rejected. Invalid characters inside candidate values are replaced with hyphens, while whitespace is collapsed to a single space. Filename stems must fit within 240 UTF-8 bytes; overly long or reserved names are rejected rather than silently truncated.

`--destination "/path/to/Layout assets"` saves every production image **directly** into that folder, without an additional `images/` level. The folder can already exist and contain unrelated files. Originals and reports go into the fresh folder specified by `--output`, or a timestamped `exports/product-images-<timestamp>/` folder in the working directory when omitted. Without `--destination`, images go into `<output>/images/`. The originals folder cannot also be used as the image destination.

The report folder must be new. Before creating it or downloading, the helper checks the pattern and rendered stems for collisions within the run and against the image destination, ignoring case and normalising Unicode. Existing entries with the same stem are rejected even if the extension differs. Include `{index:03d}` to distinguish repeated product rows. Files are also opened exclusively at write time, so an existing file is never replaced. On collision, use another destination or change the requested format; do not silently change the format or delete the user's files.

The manifest records `filename_format` and the absolute image `destination`. Record-level `file` and `original_file` paths are relative to the report root; image paths can start with `../` when the destination is outside that root. Resolve them against the report folder, not the current working directory. When Windows images are on a different drive, `file` is an absolute path instead.

## Output interpretation

- `selected` + `size-reported`: verified, visually reviewed, overlay-free and meets the pixel policy; no target size supplied. Use within the reported usable maximum at the stated PPI. Check `resolution_tier` and fallback metadata to distinguish primary and fallback images.
- `selected` + `meets-target`: those same checks passed, with sufficient measured pixels for the requested rectangle. Final composition must also have been reviewed.
- `needs-review`: verification incomplete, quality issue present, unsupported production format/mode, animated source, or insufficient pixels for the specified target. Production files stay in the same flat image folder with the same naming pattern; consult the status and reasons in the index.
- `rejected`: below the absolute pixel floor, undocumented/disallowed fallback, known digital overlay, or an identical copy of another image of the same product. Original files remain in `originals/` with measurements and `rejection_reasons`, but there is no production `file`. A fallback is also removed from delivery if another row selects a primary-resolution image of the exact product, regardless of which row appeared first. Temporary review exports can hold unverified files; final delivery should use only the reviewed selection.
- `not-found`, `ambiguous`, `blocked`, `download-failed`: unresolved; reason retained. Do not count these as downloaded images.

All production files are directly inside the chosen destination (or `<output>/images/`), with no product, brand or category subdirectories. All source originals are directly inside `<output>/originals/`, byte for byte, using the same filename stems with their original extensions. The default name contains brand, product and input index; a custom format can include additional metadata. Filenames do not indicate approval status.

`image-index.csv` is a human-readable inventory with spreadsheet-safe cells. `manifest.json` retains nested metadata, full input fields, final download URL, actual format, byte size, SHA-256, ICC presence, image mode, full and usable dimensions, PPI and size calculations, resolution tier, fallback evidence and review/rejection reasons. `pixel_policy` records the primary and fallback minima. `product_summary` reports selected product/lifestyle/fallback counts per exact product, flags missing types and fewer than two selected images, and does not count rejected duplicates. It describes minimum coverage, not whether the default two-of-each search goal was fully achieved; the agent should report that shortfall too.

The helper populates `original_file`, `original_sha256`, `source_format` and `conversion` for actual downloaded originals and generated production files. Identical bytes used for different requested variants are flagged for review; same-product byte duplicates are excluded from delivery. Visual comparison is still needed to catch equivalent photographs saved with different encoding. `summary.txt` includes per-product coverage, image destination, naming format, row totals and status counts. Asset rows and unique input products must be reconciled separately.
