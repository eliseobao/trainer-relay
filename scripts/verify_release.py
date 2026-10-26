"""Check the actual download, including links in its offline documentation."""

import posixpath
import re
import sys
from zipfile import ZipFile


def verify(path):
    with ZipFile(path) as archive:
        names = {name.replace("\\", "/"): name for name in archive.namelist()}
        if len({name.casefold() for name in names}) != len(archive.namelist()):
            raise ValueError("Duplicate paths in release ZIP")
        for name in names:
            if name.startswith("/") or ".." in name.split("/"):
                raise ValueError(f"Invalid archive path: {name}")
        required = {
            "TrainerRelay.exe",
            "README.md",
            "LICENSE",
            "CONTRIBUTING.md",
            "CHANGELOG.md",
            "THIRD_PARTY_NOTICES.txt",
            "assets/app.png",
            "docs/guide.md",
            "docs/development.md",
            "docs/interface.png",
        }
        if missing := required - names.keys():
            raise ValueError(f"Release files missing: {sorted(missing)}")
        if bad := archive.testzip():
            raise ValueError(f"Corrupt ZIP entry: {bad}")
        for name, original in names.items():
            if name.endswith(".md"):
                text = archive.read(original).decode("utf-8")
                for link in re.findall(r"\]\(([^)]+)\)", text):
                    if "://" in link or link.startswith(("#", "mailto:")):
                        continue
                    target = posixpath.normpath(
                        posixpath.join(posixpath.dirname(name), link.split("#")[0])
                    )
                    if target not in names:
                        raise ValueError(f"Broken offline link: {name} → {link}")
    print("Release ZIP and offline documentation verified")


if __name__ == "__main__":
    verify(sys.argv[1])
