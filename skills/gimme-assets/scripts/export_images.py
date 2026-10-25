#!/usr/bin/env python3
"""Download reviewed product-image candidates and report native print sizes.

Requires Pillow. Does not search the web or certify provenance/visual quality.
"""

import argparse
import csv
import hashlib
import json
import math
import re
import shutil
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


def slug(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value).lower()).strip("-")[:75] or "unspecified"


def asset_name(row, index):
    """Readable, portable names; the numeric prefix prevents collisions."""
    parts = [row.get("category"), row["brand"], row["product"], row.get("size"), row.get("variant")]
    if row.get("alternative_label"):
        parts.append(row["alternative_label"].split(" — ")[0])
    if row.get("view") and row["view"] != "front":
        parts.append(row["view"])
    clean = []
    for part in parts:
        if not part:
            continue
        part = unicodedata.normalize("NFKD", str(part)).encode("ascii", "ignore").decode()
        part = re.sub(r'[\\/:*?"<>|]+', "-", part)
        clean.append(re.sub(r"\s+", " ", part).strip(" .-"))
    return f"{index:03d} " + " - ".join(clean)[:195].rstrip(" .-")


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
        if row.get("source_kind") not in {"brand", "retailer"}:
            raise ValueError(f"Row {index}: source_kind must be brand or retailer.")
        for key in ("source_page_url", "asset_url"):
            if not web_url(row.get(key, "")):
                raise ValueError(f"Row {index}: {key} requires an HTTP(S) URL without credentials.")
        if not isinstance(row.get("source_evidence"), str) or not row["source_evidence"].strip():
            raise ValueError(f"Row {index}: source_evidence is required.")
        for key in ("source_verified", "match_verified", "visual_reviewed"):
            if key in row and not isinstance(row[key], bool):
                raise ValueError(f"Row {index}: {key} must be boolean.")
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
        "User-Agent": "GimmeAssets/0.1", "Accept": "image/*,*/*;q=0.5"})
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
    for key in ("source_verified", "match_verified", "visual_reviewed"):
        if row.get(key) is not True:
            issues.append(f"{key} incomplete")
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
        "crop_box_px": crop, "measurement_basis": "reviewed-crop" if "crop_box_px" in row else "full-canvas",
        "usable_width_px": usable_width, "usable_height_px": usable_height, "ppi": ppi,
        "full_max_width_cm": round(width * 2.54 / ppi, 3),
        "full_max_height_cm": round(height * 2.54 / ppi, 3),
        "max_width_cm": round(usable_width * 2.54 / ppi, 3),
        "max_height_cm": round(usable_height * 2.54 / ppi, 3),
        "effective_ppi_at_target": round(target_ppi, 2) if target_ppi is not None else None,
        "print_status": print_status, "review_reasons": issues,
        "status": "needs-review" if issues else "selected",
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


def export(rows, output, ppi):
    output.mkdir(parents=True, exist_ok=False)
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
                name = asset_name(row, index)
                original_path = output / "originals" / (name + EXTENSIONS.get(source_info["format"], ".img"))
                original_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(downloaded, original_path)
                record.update(original_file=original_path.relative_to(output).as_posix(),
                              original_sha256=source_info["sha256"], source_format=source_info["format"])
                production, conversion = layout_image(downloaded, Path(temporary) / "layout.png", source_info, ppi)
                record.update(inspect(production, row, ppi), conversion=conversion)
                prefix = "REVIEW - " if record["status"] == "needs-review" else ""
                filename = prefix + name + EXTENSIONS.get(record["format"], ".img")
                destination = output / "images" / filename
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(production, destination)
                record["file"] = destination.relative_to(output).as_posix()
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
            continue
        for record in group:
            record["review_reasons"].append("Identical bytes used for different requested products or variants")
            if record["status"] == "selected":
                previous = output / record["file"]
                destination = previous.with_name("REVIEW - " + previous.name)
                previous.rename(destination)
                record.update(status="needs-review", file=destination.relative_to(output).as_posix())
    counts = dict(Counter(record["status"] for record in records))
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "ppi": ppi,
                "counts": counts, "records": records}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    columns = ["id", "input_id", "input_product", "category", "brand", "product", "variant", "size", "sku", "view", "alternative_group", "alternative_label", "status",
               "file", "original_file", "original_sha256", "source_format", "conversion", "format", "width_px", "height_px", "usable_width_px", "usable_height_px",
               "measurement_basis", "ppi", "max_width_cm", "max_height_cm", "full_max_width_cm",
               "full_max_height_cm", "target_width_cm", "target_height_cm", "effective_ppi_at_target",
               "print_status", "source_kind", "source_page_url", "asset_url", "download_url",
               "source_evidence", "source_verified", "match_verified", "match_notes", "visual_reviewed",
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
               f"Native print dimensions reported at {ppi:g} ppi; preserve aspect ratio.\n"
               "Selected means source/match/visual review passed, subject to measured size.\n"
               "All production images share images/; REVIEW filenames identify assets needing review.\n"
               "Compatible non-JPEG/PNG sources have lossless PNG production copies at native resolution.\n"
               "Reproduction permission is recorded separately from image suitability.\n" +
               "".join(f"{key}: {value}\n" for key, value in sorted(counts.items())))
    (output / "summary.txt").write_text(summary, encoding="utf-8")
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidates", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="New destination directory; must not exist")
    parser.add_argument("--ppi", type=float, default=300)
    args = parser.parse_args()
    try:
        if not math.isfinite(args.ppi) or args.ppi <= 0:
            raise ValueError("PPI must be positive and finite.")
        rows = json.loads(args.candidates.read_text(encoding="utf-8-sig"))
        validate(rows)
        counts = export(rows, args.output.expanduser().resolve(), args.ppi)
    except (ValueError, OSError) as error:
        parser.exit(2, f"Export error: {error}\n")
    print(json.dumps({"output": str(args.output.expanduser().resolve()), "counts": counts}, indent=2))


if __name__ == "__main__":
    main()
