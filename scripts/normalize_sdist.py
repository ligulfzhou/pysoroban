#!/usr/bin/env python3
"""Rewrite an sdist so two builds of the same tree share a SHA-256.

``python -m build`` already honors ``SOURCE_DATE_EPOCH`` for the wheel.
The sdist gzip header and tar member timestamps still follow the clock, so
this pass sets both to that epoch and drops owner names.
"""

from __future__ import annotations

import argparse
import gzip
import io
import os
import tarfile
from pathlib import Path


def normalize(path: Path, epoch: int) -> None:
    with tarfile.open(path, "r:gz") as source:
        members = list(source.getmembers())
        files = {}
        for member in members:
            if member.isfile():
                extracted = source.extractfile(member)
                files[member.name] = b"" if extracted is None else extracted.read()
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.GNU_FORMAT) as archive:
        for member in sorted(members, key=lambda item: item.name):
            info = tarfile.TarInfo(member.name)
            info.mtime = epoch
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.type = member.type
            if member.isdir():
                info.mode = 0o755
                archive.addfile(info)
            elif member.isfile():
                payload = files[member.name]
                info.mode = 0o644
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
            else:
                raise SystemExit("unsupported tar member {}".format(member.name))
    with path.open("wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=epoch) as compressed:
        compressed.write(buffer.getvalue())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdists", nargs="+", type=Path)
    parser.add_argument("--epoch", type=int, default=int(os.environ["SOURCE_DATE_EPOCH"]))
    args = parser.parse_args(argv)
    for path in args.sdists:
        normalize(path, args.epoch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
