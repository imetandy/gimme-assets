#!/usr/bin/env python3
"""Download reviewed product-image candidates and report native print sizes.

Requires Pillow. Does not search the web or certify provenance/visual quality.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import re
import shutil
import string
import sys
import tempfile
import unicodedata
import warnings
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("Pillow is required. Use a Python environment with Pillow installed.")

LIMIT = 100 * 1024 * 1024
UNRESOLVED = {"not-found", "ambiguous", "blocked"}
EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "TIFF": ".tif",
              "WEBP": ".webp", "AVIF": ".avif", "GIF": ".gif",
              "BMP": ".bmp", "HEIF": ".heic", "JPEG2000": ".jp2"}
DEFAULT_FILENAME_FORMAT = "{brand}_{product}_{index:03d}"
PRIMARY_MIN_PX = 2500
FALLBACK_MIN_PX = 1900
NAME_FIELDS = {"brand", "product", "category", "variant", "size", "sku", "view", "id", "alternative_label", "image_type"}


def validate_filename_format(pattern):
    if not isinstance(pattern, str) or not pattern.strip():
        raise ValueError("Filename format must be a nonempty string.")
    for literal, field, spec, conversion in string.Formatter().parse(pattern):
        if re.search(r'[\\/:*?"<>|\x00-\x1f\x7f]', literal):
            raise ValueError("Filename format must describe one filename, without paths or invalid characters.")
        if field is None:
            continue
        if field not in NAME_FIELDS | {"index"} or conversion:
            raise ValueError(f"Unsupported filename field: {field!r}.")
        if spec and (field != "index" or (spec != "d" and not re.fullmatch(r"0?[1-9]d", spec))):
            raise ValueError("Only index supports formatting, for example {index:03d}.")


def asset_name(row, index, pattern=DEFAULT_FILENAME_FORMAT):
    """Preserve spaces and accents inside names; underscores separate default fields."""
    values = {}
    for field in NAME_FIELDS:
        value = unicodedata.normalize("NFC", str(row.get(field) or ""))
        value = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]+', "-", value)
        values[field] = re.sub(r"\s+", " ", value).strip(" .")
    name = pattern.format(index=index, **values).strip(" .")
    if not name or len(name.encode("utf-8")) > 240:
        raise ValueError("Rendered filename must contain 1–240 UTF-8 bytes before its extension; shorten the format or names.")
    if re.fullmatch(r"(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])", name.split(".")[0]):
        raise ValueError(f"Reserved filename: {name!r}.")
    return name


def name_key(value):
    return unicodedata.normalize("NFC", value).casefold()


def copy_exclusive(source, destination):
    """Never replace an existing file, including one created after preflight."""
    with destination.open("xb") as output, source.open("rb") as original:
        shutil.copyfileobj(original, output)


def number(value):
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def web_url(value):
    parsed = urlparse(str(value))
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname) and not parsed.username and not parsed.password


def validate(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("Input must be a nonempty JSON array.")
    ids = set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"Row {index}: expected an object.")
        for key in ("id", "brand", "product"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f"Row {index}: {key} must be a nonempty string.")
        if "category" in row and not isinstance(row["category"], str):
            raise ValueError(f"Row {index}: category must be a string.")
        if row["id"] in ids:
            raise ValueError(f"Duplicate ID: {row['id']}")
        ids.add(row["id"])
        status = row.get("status", "candidate")
        if status in UNRESOLVED:
            if not row.get("reason"):
                raise ValueError(f"Row {index}: unresolved rows require a reason.")
            continue
        if status != "candidate":
            raise ValueError(f"Row {index}: unsupported input status {status!r}.")
        if row.get("image_type") not in {"product", "lifestyle"}:
            raise ValueError(f"Row {index}: image_type must be product or lifestyle.")
        if row.get("source_kind") not in {"brand", "retailer"}:
            raise ValueError(f"Row {index}: source_kind must be brand or retailer.")
        for key in ("source_page_url", "asset_url"):
            if not web_url(row.get(key, "")):
                raise ValueError(f"Row {index}: {key} requires an HTTP(S) URL without credentials.")
        if not isinstance(row.get("source_evidence"), str) or not row["source_evidence"].strip():
            raise ValueError(f"Row {index}: source_evidence is required.")
        for key in ("source_verified", "match_verified", "visual_reviewed", "overlay_free", "primary_search_exhausted"):
            if key in row and not isinstance(row[key], bool):
                raise ValueError(f"Row {index}: {key} must be boolean.")
        if "fallback_reason" in row and not isinstance(row["fallback_reason"], str):
            raise ValueError(f"Row {index}: fallback_reason must be a string.")
        checked = row.get("sources_checked", [])
        if not isinstance(checked, list) or not all(isinstance(url, str) and web_url(url) for url in checked):
            raise ValueError(f"Row {index}: sources_checked must be an array of HTTP(S) URLs.")
        issues = row.get("quality_issues", [])
        if not isinstance(issues, list) or not all(isinstance(item, str) and item.strip() for item in issues):
            raise ValueError(f"Row {index}: quality_issues must be an array of nonempty strings.")
        target = [row.get("target_width_cm"), row.get("target_height_cm")]
        if any(value is not None for value in target) and not all(number(value) and value > 0 for value in target):
            raise ValueError(f"Row {index}: supply two positive finite target dimensions.")


def fetch(row, destination):
    if row.get("local_file"):
        source = Path(row["local_file"]).expanduser().resolve()
        if source.stat().st_size > LIMIT:
            raise ValueError("Local image exceeds 100 MiB.")
        shutil.copyfile(source, destination)
        return {"download_url": row["asset_url"], "transfer": "local-copy"}
    request = Request(row["asset_url"], headers={
        "User-Agent": "GimmeAssets/0.3", "Accept": "image/*,*/*;q=0.5"})
    with urlopen(request, timeout=30) as response, destination.open("wb") as output:
        if not web_url(response.url):
            raise ValueError("Download redirected outside HTTP(S).")
        total = 0
        while chunk := response.read(1024 * 1024):
            total += len(chunk)
            if total > LIMIT:
                raise ValueError("Image exceeds 100 MiB.")
            output.write(chunk)
        return {"download_url": response.url, "content_type": response.headers.get_content_type(),
                "transfer": "http-download"}


def inspect(path, row, ppi):
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        with Image.open(path) as original:
            original.verify()
        with Image.open(path) as original:
            fmt, mode = original.format, original.mode
            frames = getattr(original, "n_frames", 1)
            has_icc = bool(original.info.get("icc_profile"))
            has_alpha = "A" in original.getbands() or "transparency" in original.info
            oriented = ImageOps.exif_transpose(original)
            oriented.load()
            width, height = oriented.size
    crop = row.get("crop_box_px", [0, 0, width, height])
    if not isinstance(crop, list) or len(crop) != 4 or not all(isinstance(v, int) and not isinstance(v, bool) for v in crop):
        raise ValueError("crop_box_px must contain four integer coordinates.")
    left, top, right, bottom = crop
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError("crop_box_px is outside the orientation-corrected image.")
    usable_width, usable_height = right - left, bottom - top
    issues = list(row.get("quality_issues", []))
    for key in ("source_verified", "match_verified", "visual_reviewed", "overlay_free"):
        if row.get(key) is not True:
            issues.append(f"{key} incomplete")
    rejected = []
    if min(width, height) >= PRIMARY_MIN_PX:
        resolution_tier = "primary"
    elif min(width, height) >= FALLBACK_MIN_PX:
        resolution_tier = "fallback"
        if not (row.get("primary_search_exhausted") is True
                and isinstance(row.get("fallback_reason"), str) and row["fallback_reason"].strip()
                and row.get("sources_checked")):
            rejected.append("1900 px fallback requires an exhausted 2500 px product search, a reason and sources checked")
    else:
        resolution_tier = "below-minimum"
        rejected.append("Both width and height must be at least 1900 px; preferred minimum is 2500 px on both sides")
    if row.get("overlay_free") is False:
        rejected.append("Digitally added text, badge, logo, watermark or other graphic overlay")
    if fmt not in {"JPEG", "PNG"}:
        issues.append(f"Production compatibility review needed: {fmt}")
    if frames != 1:
        issues.append("Animated or multipage image requires review")
    if mode not in {"RGB", "RGBA", "CMYK", "L", "LA", "P"}:
        issues.append(f"Colour mode requires review: {mode}")
    target_ppi, print_status = None, "size-reported"
    if row.get("target_width_cm") is not None:
        target_ppi = min(usable_width * 2.54 / row["target_width_cm"],
                         usable_height * 2.54 / row["target_height_cm"])
        print_status = "meets-target" if target_ppi >= ppi else "below-target"
        if target_ppi < ppi:
            issues.append(f"Insufficient native pixels for target at {ppi:g} ppi")
    return {
        "format": fmt, "mode": mode, "icc_present": has_icc, "transparency": has_alpha,
        "frames": frames, "width_px": width, "height_px": height,
        "resolution_tier": resolution_tier, "rejection_reasons": rejected,
        "crop_box_px": crop, "measurement_basis": "reviewed-crop" if "crop_box_px" in row else "full-canvas",
        "usable_width_px": usable_width, "usable_height_px": usable_height, "ppi": ppi,
        "full_max_width_cm": round(width * 2.54 / ppi, 3),
        "full_max_height_cm": round(height * 2.54 / ppi, 3),
        "max_width_cm": round(usable_width * 2.54 / ppi, 3),
        "max_height_cm": round(usable_height * 2.54 / ppi, 3),
        "effective_ppi_at_target": round(target_ppi, 2) if target_ppi is not None else None,
        "print_status": print_status, "review_reasons": issues,
        "status": "rejected" if rejected else "needs-review" if issues else "selected",
        "reason": "; ".join(rejected),
        "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def layout_image(source, destination, source_info, ppi):
    """Use lossless PNG for compatible non-JPEG/PNG single-frame sources."""
    if source_info["format"] in {"JPEG", "PNG"}:
        return source, "None; byte-for-byte original copy"
    if source_info["frames"] != 1 or source_info["mode"] not in {"RGB", "RGBA", "L", "LA", "P"}:
        return source, "None; source requires format/colour review before conversion"
    with Image.open(source) as original:
        oriented = ImageOps.exif_transpose(original)
        options = {"dpi": (ppi, ppi), "compress_level": 6}
        profile = original.info.get("icc_profile")
        if profile:
            options["icc_profile"] = profile
        if oriented.mode == "P" and "transparency" in oriented.info:
            options["transparency"] = oriented.info["transparency"]
        oriented.save(destination, format="PNG", **options)
        with Image.open(destination) as check:
            check.load()
            if (check.size != oriented.size or check.mode != oriented.mode
                    or check.tobytes() != oriented.tobytes()
                    or check.convert("RGBA").tobytes() != oriented.convert("RGBA").tobytes()
                    or check.info.get("icc_profile") != profile):
                raise ValueError("PNG conversion did not preserve source pixels, mode, transparency or ICC profile.")
    return destination, (f"{source_info['format']} decoded to lossless PNG; no resizing, retouching or colour "
                         f"conversion; transparency and source profile retained when present; PPI metadata set to {ppi:g}.")


def product_key(row):
    return tuple(str(row.get(key) or "") for key in ("input_id", "brand", "product", "variant", "size", "sku"))


def reject_production(record, output, reason):
    if record.get("file"):
        (output / record.pop("file")).unlink()
    record.setdefault("rejection_reasons", []).append(reason)
    record.update(status="rejected", reason="; ".join(record["rejection_reasons"]))


def product_coverage(records):
    groups = defaultdict(list)
    for record in records:
        groups[product_key(record)].append(record)
    result = []
    for group in groups.values():
        selected = [row for row in group if row["status"] == "selected" and row.get("file")]
        types = Counter(row["image_type"] for row in selected)
        gaps = [f"No selected {kind} images" for kind in ("product", "lifestyle") if not types[kind]]
        if len(selected) < 2:
            gaps.append("Fewer than two selected images")
        result.append({**{key: group[0].get(key, "") for key in ("input_id", "brand", "product", "variant", "size", "sku")},
                       "selected_images": len(selected), "product_images": types["product"],
                       "lifestyle_images": types["lifestyle"],
                       "fallback_images": sum(row.get("resolution_tier") == "fallback" for row in selected),
                       "coverage_gaps": gaps})
    return result


def export(rows, output, ppi, filename_format=DEFAULT_FILENAME_FORMAT, destination=None):
    output = output.expanduser().resolve()
    images = destination.expanduser().resolve() if destination is not None else output / "images"
    if output.exists():
        raise FileExistsError(f"Report folder already exists: {output}")
    validate_filename_format(filename_format)
    if images == output / "originals" or output / "originals" in images.parents:
        raise ValueError("Image destination must be separate from the originals folder.")
    if images.exists() and not images.is_dir():
        raise ValueError("Image destination must be a folder.")
    existing = {name_key(path.stem) for path in images.iterdir()} if images.exists() else set()
    names, used = {}, set()
    for index, row in enumerate(rows, 1):
        if row.get("status") in UNRESOLVED:
            continue
        name = asset_name(row, index, filename_format)
        key = name_key(name)
        if key in used or key in existing:
            raise ValueError(f"Filename collision: {name!r}. Include {{index:03d}}, change the format, or choose another destination.")
        names[index] = name
        used.add(key)
    output.mkdir(parents=True, exist_ok=False)
    images.mkdir(parents=True, exist_ok=True)
    records = []
    for index, row in enumerate(rows, 1):
        record = dict(row)
        record.pop("file", None)
        record["retrieved_at"] = datetime.now(timezone.utc).isoformat()
        record.setdefault("usage_terms", "not-established")
        if row.get("status") in UNRESOLVED:
            records.append(record)
            continue
        with tempfile.TemporaryDirectory(prefix="product-image-") as temporary:
            downloaded = Path(temporary) / "asset"
            try:
                record.update(fetch(row, downloaded))
                source_info = inspect(downloaded, row, ppi)
                name = names[index]
                original_path = output / "originals" / (name + EXTENSIONS.get(source_info["format"], ".img"))
                original_path.parent.mkdir(parents=True, exist_ok=True)
                copy_exclusive(downloaded, original_path)
                record.update(original_file=original_path.relative_to(output).as_posix(),
                              original_sha256=source_info["sha256"], source_format=source_info["format"])
                if source_info["status"] == "rejected":
                    record.update(source_info, conversion="None; rejected before production export")
                    records.append(record)
                    continue
                production, conversion = layout_image(downloaded, Path(temporary) / "layout.png", source_info, ppi)
                record.update(inspect(production, row, ppi), conversion=conversion)
                filename = name + EXTENSIONS.get(record["format"], ".img")
                image_path = images / filename
                copy_exclusive(production, image_path)
                try:
                    record["file"] = Path(os.path.relpath(image_path, output)).as_posix()
                except ValueError:  # Windows destinations can be on a different drive.
                    record["file"] = image_path.as_posix()
            except Exception as error:
                record.update(status="download-failed", reason=f"{type(error).__name__}: {error}")
            records.append(record)
    hashes = defaultdict(list)
    for record in records:
        if record.get("file"):
            hashes[record["sha256"]].append(record)
    for group in hashes.values():
        identities = {(r["brand"], r["product"], r.get("variant", ""), r.get("size", ""), r.get("sku", "")) for r in group}
        if len(identities) < 2:
            keep = sorted(group, key=lambda row: row["status"] != "selected")[0]
            for record in group:
                if record is not keep:
                    reject_production(record, output, "Duplicate image for the same product; not an additional distinct picture")
            continue
        for record in group:
            record["review_reasons"].append("Identical bytes used for different requested products or variants")
            record["status"] = "needs-review"
    primary_products = {product_key(row) for row in records
                        if row["status"] == "selected" and row.get("resolution_tier") == "primary"}
    for record in records:
        if (record.get("file") and record.get("resolution_tier") == "fallback"
                and product_key(record) in primary_products):
            reject_production(record, output, "A qualifying 2500 px image is available for this product; fallback is not needed")
    coverage = product_coverage(records)
    counts = dict(Counter(record["status"] for record in records))
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "ppi": ppi,
                "filename_format": filename_format, "destination": str(images),
                "pixel_policy": {"primary_min_width_px": PRIMARY_MIN_PX, "primary_min_height_px": PRIMARY_MIN_PX,
                                 "fallback_min_width_px": FALLBACK_MIN_PX, "fallback_min_height_px": FALLBACK_MIN_PX},
                "product_summary": coverage,
                "counts": counts, "records": records}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    columns = ["id", "input_id", "input_product", "category", "brand", "product", "variant", "size", "sku", "image_type", "view", "alternative_group", "alternative_label", "status",
               "file", "original_file", "original_sha256", "source_format", "conversion", "format", "width_px", "height_px", "usable_width_px", "usable_height_px",
               "measurement_basis", "ppi", "max_width_cm", "max_height_cm", "full_max_width_cm",
               "full_max_height_cm", "target_width_cm", "target_height_cm", "effective_ppi_at_target",
               "print_status", "source_kind", "source_page_url", "asset_url", "download_url",
               "source_evidence", "source_verified", "match_verified", "match_notes", "visual_reviewed",
               "overlay_free", "resolution_tier", "primary_search_exhausted", "fallback_reason", "rejection_reasons",
               "review_reasons", "reason", "usage_terms", "usage_terms_url", "credit", "icc_present",
               "mode", "transparency", "bytes", "sha256", "retrieved_at", "sources_checked", "crop_notes", "notes"]
    with (output / "image-index.csv").open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for record in records:
            cells = {}
            for key in columns:
                value = record.get(key, "")
                if isinstance(value, (dict, list)):
                    value = json.dumps(value, ensure_ascii=False)
                if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
                    value = "'" + value
                cells[key] = value
            writer.writerow(cells)
    summary = (f"Product image export\nAsset/product rows: {len(records)}\n"
               f"Primary minimum: {PRIMARY_MIN_PX} px on BOTH sides; fallback: {FALLBACK_MIN_PX} px on BOTH sides only after the product search is exhausted.\n"
               f"Native print dimensions reported at {ppi:g} ppi; preserve aspect ratio.\n"
               "Selected means source/match/visual review passed, subject to measured size.\n"
               f"Production image folder: {images}\n"
               f"Filename format: {filename_format}\n"
               "Review status and reasons are in image-index.csv and manifest.json; filenames carry no review labels.\n"
               "Compatible non-JPEG/PNG sources have lossless PNG production copies at native resolution.\n"
               "Known overlays and pixel-policy failures are excluded from the production folder; originals remain for audit.\n"
               "Reproduction permission is recorded separately from image suitability.\n" +
               "".join(f"{key}: {value}\n" for key, value in sorted(counts.items())) +
               "\nPer-product coverage (selected images only):\n" +
               "".join(f"{row['brand']} / {row['product']}: {row['product_images']} product, {row['lifestyle_images']} lifestyle, "
                       f"{row['fallback_images']} fallback; {'; '.join(row['coverage_gaps']) or 'both types covered'}\n"
                       for row in coverage))
    (output / "summary.txt").write_text(summary, encoding="utf-8")
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("--output", type=Path, help="New report/originals folder; defaults to exports/product-images-<timestamp>")
    parser.add_argument("--destination", type=Path, help="Save production images directly here; existing folders are allowed without replacing files")
    parser.add_argument("--filename-format", default=DEFAULT_FILENAME_FORMAT,
                        help="Filename stem template, e.g. {brand}_{product}_{index:03d}; extension is automatic")
    parser.add_argument("--ppi", type=float, default=300)
    args = parser.parse_args()
    try:
        if not math.isfinite(args.ppi) or args.ppi <= 0:
            raise ValueError("PPI must be positive and finite.")
        rows = json.loads(args.candidates.read_text(encoding="utf-8-sig"))
        validate(rows)
        output = (args.output or Path("exports") / datetime.now().strftime("product-images-%Y-%m-%d-%H%M%S-%f")).expanduser().resolve()
        destination = args.destination.expanduser().resolve() if args.destination else output / "images"
        counts = export(rows, output, args.ppi, args.filename_format, destination)
    except (ValueError, OSError) as error:
        parser.exit(2, f"Export error: {error}\n")
    print(json.dumps({"output": str(output), "destination": str(destination), "counts": counts}, indent=2))


if __name__ == "__main__":
    main()
