# Product and lifestyle image selection

## Image types and variety

`product` means an image whose main purpose is showing the item clearly: an isolated bottle or jar, a transparent cutout, a neutral-background packshot, an open lid, packaging, a useful angle or product detail. A shadow, coloured backdrop, printed label or physical box does not turn it into an infographic.

`lifestyle` covers styled product still lifes, props and ingredients, creative arrangements, real settings, official campaign/model photographs and in-use scenes that establish the exact requested product. It need not contain a person. Examples include a cream jar styled with an ice-cream cone and sprinkles, or sculptural arrangements of hand-cream packaging. These are visual directions, not products to substitute for the user's list.

Aim for two distinct pictures of each type unless a count is supplied. Search for meaningful changes in view, composition, styling or context. The same image re-encoded, resized, mirrored, cropped differently or copied from another retailer is not another distinct picture. Track `image_type` and `view` in the inventory, keeping the default filenames and flat destination unchanged. If only one type or fewer pictures can be found, deliver the qualifying set and state the shortfall.

## Size gate before acceptance

| Native width × height | Outcome |
| --- | --- |
| 2500 × 2500, 2500 × 4000, 4000 × 2500 | Primary size passes; still requires source, match and visual checks |
| 4000 × 2499 or 1900 × 1900 | Fallback only, after the product's primary search is exhausted and documented |
| 5000 × 1899 | Reject: one side is below the absolute floor |

Use full raster dimensions after interpreting orientation. Also report a reviewed useful crop so blank padding does not exaggerate subject print size. Do not resize, add padding, stretch, or ask a CDN to invent pixels. Large dimensions do not prove genuine detail or clean imagery.

Fallback is per exact product, not a batch-wide lowering of the standard. Search the brand's original gallery and public official media, then plausible retailers, before recording `primary_search_exhausted: true`. Record what was checked and why no qualifying primary image exists in `fallback_reason` and `sources_checked`. A missing lifestyle image or an unmet picture count alone does not permit fallback if qualifying primary images of that product exist. The helper enforces this when a primary image for the same product is selected in the export; the agent must also account for qualifying primary images discovered but not downloaded.

## Digital overlays versus photographed text

Reject an otherwise good photograph if it contains any digitally added promotional or explanatory layer. Check all corners, edges, whitespace, and small footnotes as well as the product itself.

- Award medallions, “New”, “Best Seller”, “Organic”, discount or retailer badges: reject.
- A separate brand logo, stamped logo or watermark floating over the photograph: reject.
- Claims such as “90% agreed”, benefit bullets, ingredients callouts, arrows, icons, diagrams and certification panels: reject.
- “Old / New” comparisons, before/after graphics and split-panel advertising layouts: reject.
- A model/in-use or styled image with extra captions or graphic panels: reject, even when the photograph portion is attractive.
- Brand names, ingredients, certification marks and instructions printed or embossed on the physical product or its packaging: allowed.
- Text visibly part of a photographed prop, sign, surface or physical background styling: allowed.

An award badge placed over a product photo still fails; do not assume it is printed on the packaging merely because it overlaps it. If the distinction is unclear, keep it unresolved and seek a clean official alternative. Set `overlay_free: false` for a known digital overlay, leave it unset while unreviewed, and set it to `true` only after inspecting the actual file. The helper records this assertion; it does not automatically detect overlays.

Do not remove badges, erase text, crop away a graphic panel, remove backgrounds or recreate an image to make it eligible. Find the clean original or omit the asset.

User-supplied example folders are visual references, not evidence that a future image comes from an official brand or retailer, nor an exception to the size rules. Review accessible examples when available and use this written guide when they are unavailable. Do not bundle the user's example images or private folder links into a publicly shared skill without explicit instructions to publish them.
