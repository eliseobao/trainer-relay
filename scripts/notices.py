"""Collect licenses for shipped runtime distributions and the build bootloader."""

import importlib.metadata as metadata
import sys
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOTS = ("bleak", "pyusb", "pyinstaller", "pyinstaller-hooks-contrib")


def collect():
    pending, seen, sections = list(ROOTS), set(), []
    while pending:
        name = canonicalize_name(pending.pop())
        if name in seen:
            continue
        seen.add(name)
        dist = metadata.distribution(name)
        for entry in dist.requires or []:
            requirement = Requirement(entry)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
        licenses = []
        for entry in dist.files or []:
            path = str(entry).lower()
            if (
                ".dist-info/" in path
                and any(word in Path(path).name for word in ("license", "copying", "notice"))
            ) or (name == "pyinstaller" and Path(path).name in ("copying.txt", "license.txt")):
                file = dist.locate_file(entry)
                if file.is_file():
                    licenses.append(
                        f"--- {entry} ---\n{file.read_text(encoding='utf-8', errors='replace')}"
                    )
        license_field = (
            dist.metadata.get("License-Expression") or dist.metadata.get("License") or ""
        )
        if not licenses and len(license_field) < 100:
            raise RuntimeError(f"No full license text found for {dist.metadata['Name']}")
        sections.append(
            f"{dist.metadata['Name']} {dist.version}\n{license_field}\n" + "\n".join(licenses)
        )
    base = Path(sys.base_prefix)
    python_license = base / "LICENSE.txt"
    if not python_license.exists():
        raise RuntimeError("Python LICENSE.txt missing")
    sections.append(
        "Python runtime\n" + python_license.read_text(encoding="utf-8", errors="replace")
    )
    for component in ("tcl8.6", "tk8.6"):
        file = base / "tcl" / component / "license.terms"
        if not file.exists():
            file = base / "tcl" / component / "license"
        if not file.exists() and component == "tcl8.6":
            file = Path(__file__).resolve().parents[1] / "assets" / "licenses" / "Tcl.txt"
        if not file.exists():
            raise RuntimeError(f"{component} license missing")
        sections.append(component + "\n" + file.read_text(encoding="utf-8", errors="replace"))
    return (
        "TrainerRelay — bundled third-party licenses\n\n"
        + "\n\n"
        + ("\n\n" + "=" * 78 + "\n\n").join(sections)
    )


if __name__ == "__main__":
    Path(sys.argv[1]).write_text(collect(), encoding="utf-8")
