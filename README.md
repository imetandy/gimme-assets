# gimme-assets

A Codex skill that finds official product images and downloads a clean, clearly named folder for editorial and marketing work. Built for beauty products, perfume and candles; usable for other products too.

**[Download the skill ZIP](https://github.com/imetandy/gimme-assets/releases/latest/download/gimme-assets.zip)** · **[Open the skill](skills/gimme-assets/SKILL.md)**

## Install

### Ask Codex to install it

Paste this into Codex:

```text
$skill-installer install https://github.com/imetandy/gimme-assets/tree/main/skills/gimme-assets
```

### Or install the ZIP

1. [Download gimme-assets.zip](https://github.com/imetandy/gimme-assets/releases/latest/download/gimme-assets.zip) and unzip it.
2. Move the complete `gimme-assets` folder into your personal skills directory:
   - **macOS / Linux:** `~/.agents/skills/`
   - **Windows:** `%USERPROFILE%\.agents\skills\`
3. Start a new Codex turn. If the skill does not appear, restart Codex.

The installed folder should contain `gimme-assets/SKILL.md`, alongside its `scripts`, `references`, `agents` and dependency file. Keep the whole folder together. See the [official OpenAI skills guidance](https://learn.chatgpt.com/docs/build-skills) for skill discovery and installation locations.

## Use

Paste a product list into Codex, or provide a CSV, spreadsheet or document. For example:

```text
Use $gimme-assets to find official product images for:

Perfumes
- Diptyque L’Eau Papier
- Tom Ford Black Orchid

Candles
- Loewe Tomato Leaves candle

Report the maximum print dimensions at 300 ppi and save the export
to my project’s exports folder.
```

Add sizes, concentrations, shades or SKUs when they matter. You can also specify a final placement size, such as “the bottle will print 8 cm tall”, and ask Codex to assess it. If you want two similarly named products, say “include both as labelled alternatives”.

## What it does

- Searches brand websites and retailer product pages, and records where each image came from.
- Checks the product and its variant, then inspects the downloaded image rather than relying on a search thumbnail.
- Excludes customer uploads, influencer images, UGC-labelled galleries and other unverified sources.
- Preserves source files. Keeps original JPEGs and PNGs unchanged, and makes lossless PNG copies of compatible WebP, TIFF and other raster sources.
- Measures both the full canvas and the useful product area, so empty margins do not exaggerate the print size.
- Reports maximum print dimensions at **300 ppi** by default. It does not upscale small images.
- Puts all production images in **one flat folder**, with readable category, brand, product, size and alternative labels in the filenames.

Sources that need attention stay in the same folder with a clear `REVIEW - ` prefix and an explanation in the index. Missing or ambiguous products are recorded too.

## Your export

```text
product-images-<timestamp>/
  images/
    001 Perfumes - Brand - Product - 50 ml - Eau de Parfum.png
    002 Candles - Brand - Product - 190 g.jpg
    REVIEW - 003 Candles - Brand - Product - 250 ml.jpg
  originals/
    <unchanged source files>
  image-index.csv
  manifest.json
  summary.txt
```

The files directly inside `images/` are the ones to collect for your layout. `originals/` retains the downloaded sources. The CSV is the image inventory; the JSON includes detailed provenance, hashes, measurements, conversion records and review reasons. Codex can also add a simpler print-size guide, browsing sheets or a ZIP.

## Print quality and image use

Print suitability depends on the image's actual pixels and the size at which you place it. A “300 dpi” label alone proves nothing. For example, 1200 pixels support about 10.16 cm at 300 ppi along that dimension. Width and height must be used together at the existing aspect ratio.

PNG conversion preserves the decoded pixels and transparency; it adds no detail. Existing JPEGs are kept without another lossy save. Unusual colour modes, animated or multipage files, and deficient images need review. The skill does not silently flatten transparency or apply a generic CMYK conversion.

Being on a brand or retailer website does not itself grant reproduction permission. Published usage terms and credit requirements are recorded when available. The software licence below covers this skill and its code; it does not license any product images you download.

## Requirements

Use an agent with live web browsing, local file access and image viewing. The included helper needs **Python 3.10+ and Pillow**. Codex should use its existing compatible runtime when available, or create an isolated environment with the skill's `requirements.txt`.

The agent performs searching, source verification and visual review. The helper downloads the chosen candidates, converts compatible files, measures their print dimensions and writes the export. Running the helper alone does not search the web or independently certify the product match.

## Update

Download the latest skill ZIP and replace your installed `gimme-assets` folder, keeping a copy of any local customisations first. Alternatively, ask Codex to update the installed skill from this repository. The installer may ask you to remove an existing installation before installing again.

## Development

From a repository checkout, create an isolated environment and run the checks:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r skills/gimme-assets/requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tools/package_skill.py
```

The package command writes `dist/gimme-assets.zip`, containing the complete installable skill folder. Tests use synthetic local images and make no network requests. Actual editorial exports and downloaded brand images are excluded from this repository.

## Licence

[MIT](LICENSE).
