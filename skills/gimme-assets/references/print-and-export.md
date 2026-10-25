# Print measurements and export contract

## Print checks

- Use native pixel dimensions after interpreting EXIF orientation. Embedded 72/96/300 DPI labels are not an acceptance test. A 1200 × 1800 px file supports about 10.16 × 15.24 cm at 300 ppi; a 3000 × 3000 px file supports 25.4 × 25.4 cm. Neither proves optical sharpness.
- Inspect blank padding and transparent margins. For packshots, report a manually reviewed product/crop bounding box when the canvas is materially larger than the useful subject. Crop coordinates use the orientation-corrected image. State whether shadows and desired margins are included. Keep the original unmodified.
- `crop_box_px: [left, top, right, bottom]` defines the useful rectangle. Coordinates are in orientation-corrected pixels, right/bottom exclusive. The helper uses this rectangle for usable maximum size, while also reporting full-canvas dimensions. No box means full-canvas measurements, not automatically subject measurements.
- With a target width W and height H in cm, `cover_ppi = min(usable_width_px / (W / 2.54), usable_height_px / (H / 2.54))` checks resolution if filling that rectangle, without stretching. Aspect mismatch entails cropping. Visually check that the crop retains the product; numerical resolution alone cannot approve composition. A contained packshot can occupy a smaller proportion of the layout slot; use its actual placed dimensions if known.
- The user's default conversion format is lossless PNG, at the native pixel dimensions. Keep original JPEG/PNG files unchanged; converting JPEG to PNG adds no detail. Retain source bytes separately. The helper verifies the PNG's orientation-corrected dimensions, decoded pixels, palette colours/transparency and embedded ICC bytes against the source. Untagged images stay untagged unless a justified profile assignment is separately requested and documented. PNG cannot store CMYK pixels: preserve a suitable CMYK JPEG or flag unusual colour modes for a publication-specific decision. Do not silently discard a CMYK profile or flatten transparency for JPEG. Use TIFF only when explicitly requested. [Adobe's format guidance](https://experienceleague.adobe.com/en/docs/dynamic-media-classic/using/master-files/best-practices-optimizing-quality-images) explains PNG's lossless compression and alpha support, and JPEG's lossy encoding.
- Do not turn a resolution check into a blanket prepress guarantee: final crop, layout scale, colour/output profile, and any reproduction terms still depend on the publication.

Primary reference: [Adobe: Image size, resolution, and resampling](https://helpx.adobe.com/photoshop/desktop/crop-resize-transform/resize-adjust-resolution/image-size-resolution-and-resampling.html). Adobe explains the pixel/size/PPI relationship and that upsampling does not recover missing detail. [Adobe: Colour-managing imported images](https://helpx.adobe.com/ie/photoshop/using/color-managing-imported-images.html) describes embedded profiles and CMYK handling.

## Candidate input

The helper reads a JSON array. One row per input product is the default; use additional uniquely identified rows for requested alternative views. Use literal booleans for verification flags. Required for downloadable rows: `id`, `brand`, `product`, `source_kind`, `source_page_url`, `asset_url`, and `source_evidence`. The helper can put unverified candidates in review; valid provenance fields are still required.

```json
[
  {
    "id": "001",
    "input_product": "Brand Example Serum 30 ml",
    "brand": "Brand Example",
    "product": "Serum",
    "variant": "",
    "size": "30 ml",
    "sku": "",
    "view": "front",
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

- `category`: group supplied by the user, retained as an index column and available in custom filenames; it does not create a subfolder.
- `alternative_label`: clear label for an explicitly requested alternative; retained in the index and available in custom filenames. Its complete value is used when included in a template.
- `local_file`: absolute path of an original saved by a browser, or an original from the first review pass. Source page and asset URL remain required. The helper copies it byte for byte.
- `crop_box_px`: manually reviewed useful/subject rectangle, as described above.
- `target_width_cm` and `target_height_cm`: supply both for a target size check. The helper defaults to 300 ppi, adjustable with `--ppi`. The same PPI applies to every row in a run.
- `quality_issues`: array of observed concerns; any entry keeps the asset in review. Use specific observations such as `packaging text is blurred`, `retailer overlay`, `source appears enlarged`, or `profile requires colour review`.
- `notes`: useful free text such as packaging-generation evidence or crop rationale.

The script preserves unrecognised input fields in manifest records, allowing product-specific editorial metadata. `status` may be absent/`candidate` for downloadable rows, or `not-found`, `ambiguous`, or `blocked` with a reason for unresolved rows. Duplicate IDs are rejected before downloads.

## Filenames and destination

The default filename stem is `{brand}_{product}_{index:03d}`. The helper appends the extension for the actual production format, for example `Jo Malone London_Sea Salt & Bergamot_001.png`. Spaces and accents inside names are preserved; the underscores separate brand, product and input index. Numbering follows the one-based input row, including unresolved rows, and uses at least three digits. Review status never adds a filename prefix or suffix.

Use `--filename-format` for a custom stem. Supported fields:

| Field | Value |
| --- | --- |
| `{brand}`, `{product}` | Brand and product name |
| `{index:03d}` | Input row number, zero-padded to three digits |
| `{id}` | Unique candidate ID |
| `{category}`, `{variant}`, `{size}`, `{sku}`, `{view}`, `{alternative_label}` | Optional candidate metadata; empty when absent |

For example, `--filename-format "{index:03d} - {brand} - {product} - {size}"` produces `001 - Jo Malone London - Sea Salt & Bergamot - 100 ml.png`. Leave off the file extension. Optional empty fields leave their surrounding separators in place. Only the index supports numeric formatting (`d`, or widths 1–9 such as `03d`). Arbitrary field access, conversions, nested formatting, path separators and invalid filename characters in template literals are rejected. Invalid characters inside candidate values are replaced with hyphens, while whitespace is collapsed to a single space. Filename stems must fit within 240 UTF-8 bytes; overly long or reserved names are rejected rather than silently truncated.

`--destination "/path/to/Layout assets"` saves every production image **directly** into that folder, without an additional `images/` level. The folder can already exist and contain unrelated files. Originals and reports go into the fresh folder specified by `--output`, or a timestamped `exports/product-images-<timestamp>/` folder in the working directory when omitted. Without `--destination`, images go into `<output>/images/`. The originals folder cannot also be used as the image destination.

The report folder must be new. Before creating it or downloading, the helper checks the pattern and rendered stems for collisions within the run and against the image destination, ignoring case and normalising Unicode. Existing entries with the same stem are rejected even if the extension differs. Include `{index:03d}` to distinguish repeated product rows. Files are also opened exclusively at write time, so an existing file is never replaced. On collision, use another destination or change the requested format; do not silently change the format or delete the user's files.

The manifest records `filename_format` and the absolute image `destination`. Record-level `file` and `original_file` paths are relative to the report root; image paths can start with `../` when the destination is outside that root. Resolve them against the report folder, not the current working directory. When Windows images are on a different drive, `file` is an absolute path instead.

## Output interpretation

- `selected` + `size-reported`: verified and visually reviewed; no target size supplied. Use within the reported usable maximum at the stated PPI.
- `selected` + `meets-target`: those same checks passed, with sufficient measured pixels for the requested rectangle. Final composition must also have been reviewed.
- `needs-review`: verification incomplete, quality issue present, unsupported production format/mode, animated source, or insufficient pixels for the specified target. Production files stay in the same flat image folder with the same naming pattern; consult the status and reasons in the index.
- `not-found`, `ambiguous`, `blocked`, `download-failed`: unresolved; reason retained. Do not count these as downloaded images.

All production files are directly inside the chosen destination (or `<output>/images/`), with no product, brand or category subdirectories. All source originals are directly inside `<output>/originals/`, byte for byte, using the same filename stems with their original extensions. The default name contains brand, product and input index; a custom format can include additional metadata. Filenames do not indicate approval status.

`image-index.csv` is a human-readable inventory with spreadsheet-safe cells. `manifest.json` retains nested metadata, full input fields, final download URL, actual format, byte size, SHA-256, ICC presence, image mode, full and usable dimensions, PPI and size calculations, and review reasons. The helper automatically populates `original_file`, `original_sha256`, `source_format`, and `conversion`; these refer to the actual input original and generated production file. A hash detects identical files; identical bytes for different requested variants require investigation, even when both source pages appear plausible. The helper flags cross-product duplicates for review in the reports and leaves filenames unchanged. `summary.txt` reports the image destination, naming format, row totals and counts by status. Alternative views count as asset rows; the agent must also reconcile unique input products when summarising.
