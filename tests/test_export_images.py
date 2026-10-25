"""Observable export guarantees, using synthetic local sources only."""

import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image, ImageCms

SCRIPT = Path(__file__).resolve().parents[1] / "skills/gimme-assets/scripts/export_images.py"
SPEC = importlib.util.spec_from_file_location("gimme_assets_export", SCRIPT)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="gimme-assets-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        Image.new("RGB", (300, 450), "#6e819a").save(self.root / "photo.jpg", quality=95, dpi=(72, 72))

    def candidate(self, identifier, source="photo.jpg", **extra):
        row = {
            "id": identifier, "input_product": identifier, "category": "Perfumes",
            "brand": "Example Brand", "product": identifier, "size": "50 ml",
            "source_kind": "brand", "source_page_url": "https://brand.example/product",
            "asset_url": "https://brand.example/image", "source_evidence": "Synthetic test fixture",
            "source_verified": True, "match_verified": True, "visual_reviewed": True,
            "local_file": str(self.root / source),
        }
        row.update(extra)
        return row

    def run_export(self, rows, **options):
        exporter.validate(rows)
        output = self.root / "export"
        exporter.export(rows, output, 300, **options)
        manifest = json.loads((output / "manifest.json").read_text())
        return output, manifest["records"]

    def test_original_jpeg_bytes_and_native_print_size(self):
        output, rows = self.run_export([self.candidate("serum")])
        row = rows[0]
        self.assertEqual(row["status"], "selected")
        self.assertEqual((row["max_width_cm"], row["max_height_cm"]), (2.54, 3.81))
        self.assertEqual((output / row["file"]).read_bytes(), (self.root / "photo.jpg").read_bytes())
        self.assertEqual((output / row["original_file"]).read_bytes(), (self.root / "photo.jpg").read_bytes())

    def test_png_conversion_preserves_alpha_pixels_and_icc(self):
        source = self.root / "transparent.webp"
        Image.new("RGBA", (120, 180), (40, 80, 120, 70)).save(source, lossless=True, icc_profile=self.profile)
        output, rows = self.run_export([self.candidate("transparent", source.name)])
        row = rows[0]
        self.assertEqual(row["status"], "selected")
        self.assertEqual(row["format"], "PNG")
        with Image.open(source) as original, Image.open(output / row["file"]) as converted:
            self.assertEqual(converted.size, original.size)
            self.assertEqual(converted.tobytes(), original.tobytes())
            self.assertEqual(converted.info["icc_profile"], self.profile)
            self.assertEqual(converted.getpixel((0, 0))[3], 70)
        self.assertEqual(row["original_sha256"], hashlib.sha256(source.read_bytes()).hexdigest())

    def test_rgb_tiff_becomes_png_without_resizing(self):
        source = self.root / "source.tif"
        Image.new("RGB", (200, 300), "purple").save(source, icc_profile=self.profile)
        output, rows = self.run_export([self.candidate("tiff", source.name)])
        self.assertEqual(rows[0]["format"], "PNG")
        with Image.open(source) as original, Image.open(output / rows[0]["file"]) as converted:
            self.assertEqual(converted.tobytes(), original.tobytes())
            self.assertEqual(converted.info["icc_profile"], original.info["icc_profile"])

    def test_palette_transparency_survives_conversion(self):
        source = self.root / "palette.gif"
        image = Image.new("P", (80, 80), 0)
        image.putpalette([20, 30, 40, 240, 220, 200] + [0] * 762)
        image.putpixel((20, 20), 1)
        image.save(source, transparency=0)
        output, rows = self.run_export([self.candidate("palette", source.name)])
        self.assertEqual(rows[0]["format"], "PNG")
        with Image.open(source) as original, Image.open(output / rows[0]["file"]) as converted:
            self.assertEqual(converted.convert("RGBA").tobytes(), original.convert("RGBA").tobytes())

    def test_cmyk_source_is_held_without_silent_colour_conversion(self):
        source = self.root / "cmyk.tif"
        Image.new("CMYK", (100, 100), (0, 120, 70, 20)).save(source)
        output, rows = self.run_export([self.candidate("cmyk", source.name)])
        row = rows[0]
        self.assertEqual(row["status"], "needs-review")
        self.assertEqual(Path(row["file"]).name, "Example Brand_cmyk_001.tif")
        self.assertEqual(row["mode"], "CMYK")
        self.assertEqual((output / row["file"]).read_bytes(), source.read_bytes())

    def test_multipage_source_is_not_silently_reduced_to_one_page(self):
        source = self.root / "pages.tif"
        Image.new("RGB", (100, 100), "red").save(
            source, save_all=True, append_images=[Image.new("RGB", (100, 100), "blue")])
        output, rows = self.run_export([self.candidate("pages", source.name)])
        self.assertEqual(rows[0]["status"], "needs-review")
        self.assertEqual(rows[0]["frames"], 2)
        self.assertEqual((output / rows[0]["file"]).read_bytes(), source.read_bytes())

    def test_flat_default_names_preserve_spaces_and_accents(self):
        output, rows = self.run_export([self.candidate(
            "elixir", brand="Béauty Brand", product="Elixir Intense", alternative_label="Alternative B — Elixir")])
        row = rows[0]
        filename = Path(row["file"])
        self.assertEqual(filename.parts[0], "images")
        self.assertEqual(len(filename.parts), 2)
        self.assertEqual(filename.name, "Béauty Brand_Elixir Intense_001.jpg")
        self.assertEqual(row["alternative_label"], "Alternative B — Elixir")
        self.assertEqual(len(Path(row["original_file"]).parts), 2)
        self.assertFalse(any(path.is_dir() for path in (output / "images").iterdir()))

    def test_reviewed_crop_does_not_overstate_subject_size(self):
        _, rows = self.run_export([self.candidate("crop", crop_box_px=[50, 100, 250, 400])])
        row = rows[0]
        self.assertEqual((row["usable_width_px"], row["usable_height_px"]), (200, 300))
        self.assertAlmostEqual(row["max_width_cm"], 1.693, places=3)
        self.assertEqual(row["full_max_width_cm"], 2.54)

    def test_insufficient_target_resolution_requires_review(self):
        _, rows = self.run_export([self.candidate("small", target_width_cm=20, target_height_cm=30)])
        self.assertEqual(rows[0]["status"], "needs-review")
        self.assertEqual(rows[0]["print_status"], "below-target")
        self.assertEqual(Path(rows[0]["file"]).name, "Example Brand_small_001.jpg")

    def test_duplicate_bytes_for_different_products_are_both_flagged(self):
        _, rows = self.run_export([self.candidate("one"), self.candidate("two")])
        self.assertTrue(all(row["status"] == "needs-review" for row in rows))
        self.assertEqual([Path(row["file"]).name for row in rows],
                         ["Example Brand_one_001.jpg", "Example Brand_two_002.jpg"])
        self.assertEqual(len({row["file"] for row in rows}), 2)

    def test_incomplete_review_is_not_approved(self):
        _, rows = self.run_export([self.candidate("unreviewed", visual_reviewed=False)])
        self.assertEqual(rows[0]["status"], "needs-review")

    def test_failures_remain_in_the_inventory(self):
        (self.root / "not-an-image.html").write_text("<html>Access denied</html>")
        output, rows = self.run_export([
            self.candidate("broken", "not-an-image.html"),
            {"id": "missing", "brand": "Example", "product": "Missing",
             "status": "not-found", "reason": "No exact match"},
        ])
        self.assertEqual([row["status"] for row in rows], ["download-failed", "not-found"])
        with (output / "image-index.csv").open(encoding="utf-8-sig") as stream:
            self.assertEqual(len(list(csv.DictReader(stream))), 2)

    def test_spreadsheet_formula_strings_are_escaped_in_csv_only(self):
        output, rows = self.run_export([self.candidate("formula", input_product="=1+1")])
        self.assertEqual(rows[0]["input_product"], "=1+1")
        with (output / "image-index.csv").open(encoding="utf-8-sig") as stream:
            self.assertEqual(next(csv.DictReader(stream))["input_product"], "'=1+1")

    def test_existing_export_is_not_overwritten(self):
        rows = [self.candidate("existing")]
        output, _ = self.run_export(rows)
        sentinel = output / "keep.txt"
        sentinel.write_text("Keep this file")
        with self.assertRaises(FileExistsError):
            exporter.export(rows, output, 300)
        self.assertEqual(sentinel.read_text(), "Keep this file")

    def test_duplicate_ids_are_rejected_before_creating_output(self):
        candidates = self.root / "input.json"
        candidates.write_text(json.dumps([self.candidate("same"), self.candidate("same")]))
        output = self.root / "must-not-exist"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(candidates), "--output", str(output)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.exists())

    def test_custom_format_and_existing_destination_via_cli(self):
        destination = self.root / "Layout assets"
        destination.mkdir()
        (destination / "keep.txt").write_text("Unrelated file")
        candidates = self.root / "input.json"
        candidates.write_text(json.dumps([self.candidate(
            "elixir", brand="Beauty Brand", product="Elixir Intense", alternative_label="Alternative B")]))
        output = self.root / "Reports"
        pattern = "{index:03d} - {brand} - {product} - {size} - {alternative_label}"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(candidates), "--output", str(output),
             "--destination", str(destination), "--filename-format", pattern], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        image = destination / "001 - Beauty Brand - Elixir Intense - 50 ml - Alternative B.jpg"
        self.assertEqual(image.read_bytes(), (self.root / "photo.jpg").read_bytes())
        self.assertEqual((destination / "keep.txt").read_text(), "Unrelated file")
        self.assertFalse(any(path.is_dir() for path in destination.iterdir()))
        self.assertFalse((output / "images").exists())
        manifest = json.loads((output / "manifest.json").read_text())
        self.assertEqual(manifest["filename_format"], pattern)
        self.assertEqual(manifest["destination"], str(destination))
        self.assertEqual((output / manifest["records"][0]["file"]).resolve(), image)

    def test_destination_only_uses_separate_default_report_folder(self):
        candidates = self.root / "input.json"
        candidates.write_text(json.dumps([self.candidate("serum")]))
        destination = self.root / "My assets"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), str(candidates), "--destination", str(destination)],
            capture_output=True, text=True, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)
        self.assertTrue((destination / "Example Brand_serum_001.jpg").is_file())
        self.assertEqual(Path(response["output"]).parent, self.root / "exports")
        self.assertTrue((Path(response["output"]) / "manifest.json").is_file())

    def test_collision_in_existing_destination_is_rejected_without_writes(self):
        destination = self.root / "Assets"
        destination.mkdir()
        existing = destination / "EXAMPLE BRAND_SERUM_001.JPG"
        existing.write_bytes(b"Keep original")
        output = self.root / "export"
        with self.assertRaisesRegex(ValueError, "collision"):
            exporter.export([self.candidate("serum")], output, 300, destination=destination)
        self.assertEqual(existing.read_bytes(), b"Keep original")
        self.assertFalse(output.exists())
        self.assertEqual(list(destination.iterdir()), [existing])

    def test_custom_format_collision_is_rejected_before_export(self):
        output = self.root / "export"
        with self.assertRaisesRegex(ValueError, "collision"):
            exporter.export([self.candidate("one"), self.candidate("two")], output, 300,
                            filename_format="{brand}")
        self.assertFalse(output.exists())

    def test_invalid_format_cannot_escape_destination_or_read_other_fields(self):
        for pattern in ("../{product}", "folder/{product}", r"folder\{product}",
                        "{brand.__class__}", "{source_page_url}", "{brand!r}", "{index:999999d}",
                        "{product", "{brand:{product}}", " ", "CON"):
            with self.subTest(pattern=pattern):
                output = self.root / "export"
                with self.assertRaises(ValueError):
                    exporter.export([self.candidate("serum")], output, 300, filename_format=pattern)
                self.assertFalse(output.exists())

    def test_filename_values_cannot_create_subfolders(self):
        output, rows = self.run_export([self.candidate("serum", brand="Beauty/Brand", product="A:B\\C")])
        self.assertEqual(rows[0]["file"], "images/Beauty-Brand_A-B-C_001.jpg")
        self.assertTrue((output / rows[0]["file"]).is_file())

    def test_copy_refuses_overwrite_even_after_preflight(self):
        destination = self.root / "existing.jpg"
        destination.write_bytes(b"Keep original")
        with self.assertRaises(FileExistsError):
            exporter.copy_exclusive(self.root / "photo.jpg", destination)
        self.assertEqual(destination.read_bytes(), b"Keep original")

    def test_destination_on_another_drive_records_an_absolute_path(self):
        destination = self.root / "Other drive"
        with patch.object(exporter.os.path, "relpath", side_effect=ValueError("Different drives")):
            _, rows = self.run_export([self.candidate("serum")], destination=destination)
        self.assertEqual(rows[0]["status"], "selected")
        self.assertEqual(Path(rows[0]["file"]), destination / "Example Brand_serum_001.jpg")
        self.assertTrue(Path(rows[0]["file"]).is_file())


if __name__ == "__main__":
    unittest.main()
