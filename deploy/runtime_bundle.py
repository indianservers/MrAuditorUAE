"""Build a scan-visible runtime library bundle from the matching Debian builder."""

import json
import shutil
import subprocess
from pathlib import Path

PACKAGES = (
    "libatomic1",
    "libbz2-1.0",
    "libexpat1",
    "libffi8",
    "libgcc-s1",
    "libgomp1",
    "liblzma5",
    "libsqlite3-0",
    "libssl3t64",
    "libstdc++6",
    "libzstd1",
    "zlib1g",
)
OPTIONAL_EXTENSIONS = ("_curses", "_curses_panel", "readline", "_uuid")


def main():
    root = Path("/runtime-libs")
    python = Path("/runtime-python/usr/local")
    shutil.copytree("/usr/local", python, symlinks=True)
    removed = []
    for extension in (python / "lib/python3.12/lib-dynload").glob("*.so"):
        if extension.name.split(".", 1)[0] in OPTIONAL_EXTENSIONS:
            removed.append(extension.name)
            extension.unlink()
    packages = []
    for package in PACKAGES:
        status = subprocess.check_output(["dpkg-query", "--status", package], text=True)
        files = subprocess.check_output(
            ["dpkg-query", "--listfiles", package], text=True
        ).splitlines()
        copied = []
        for name in files:
            source = Path(name)
            if ".so" not in source.name or not source.is_file():
                continue
            resolved = source.resolve(strict=True)
            for item in dict.fromkeys((resolved, source)):
                target = root / item.relative_to("/")
                target.parent.mkdir(parents=True, exist_ok=True)
                if item.is_symlink():
                    target.symlink_to(item.readlink())
                else:
                    shutil.copy2(item, target)
                copied.append(str(item))
        if not copied:
            raise ValueError(f"No runtime shared libraries for {package}")
        # Preserve package/version/source metadata for the image vulnerability scanner.
        metadata = root / "var/lib/dpkg/status.d" / ("auditos-" + package)
        metadata.parent.mkdir(parents=True, exist_ok=True)
        metadata.write_text(status, encoding="utf-8")
        copyright = Path("/usr/share/doc") / package / "copyright"
        if copyright.is_file():
            target = root / "usr/share/auditos/licenses" / package / "copyright"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(copyright, target)
        packages.append({"package": package, "libraries": sorted(set(copied))})
    manifest = root / "usr/share/auditos/runtime-bundle.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "python": "3.12",
                "distribution": "debian13",
                "packages": packages,
                "optional_extensions_omitted": removed,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
