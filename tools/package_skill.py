#!/usr/bin/env python3
"""Build the installable skill ZIP without local caches or generated exports."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    root = Path(__file__).resolve().parents[1]
    skill = root / "skills" / "gimme-assets"
    output = root / "dist" / "gimme-assets.zip"
    excluded = {".venv", "__pycache__", ".git", "exports", "work"}
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for path in sorted(skill.rglob("*")):
            relative = path.relative_to(skill)
            if (not path.is_file() or path.is_symlink()
                    or any(part in excluded or part.startswith(".") for part in relative.parts)
                    or path.suffix in {".pyc", ".pyo"}):
                continue
            archive.write(path, Path("gimme-assets") / relative)
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert "gimme-assets/SKILL.md" in archive.namelist()
        assert "gimme-assets/scripts/export_images.py" in archive.namelist()
    print(output)


if __name__ == "__main__":
    main()
