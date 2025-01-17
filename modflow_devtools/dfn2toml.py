"""Convert DFNs to TOML."""

import argparse
from os import PathLike
from pathlib import Path

import tomli_w as tomli

from modflow_devtools.dfn import Dfn
from modflow_devtools.misc import filter_recursive


def convert(indir: PathLike, outdir: PathLike):
    indir = Path(indir).expanduser().absolute()
    outdir = Path(outdir).expanduser().absolute()
    outdir.mkdir(exist_ok=True, parents=True)
    for dfn in Dfn.load_all(indir).values():
        with Path.open(outdir / f"{dfn['name']}.toml", "wb") as f:
            tomli.dump(
                filter_recursive(
                    dfn,
                    lambda v: v is not None
                    and not (isinstance(v, dict) and not any(v)),
                ),
                f,
            )


if __name__ == "__main__":
    """Convert DFN files to TOML."""

    parser = argparse.ArgumentParser(description="Convert DFN files to TOML.")
    parser.add_argument(
        "--indir",
        "-i",
        type=str,
        help="Directory containing DFN files.",
    )
    parser.add_argument(
        "--outdir",
        "-o",
        help="Output directory.",
    )
    args = parser.parse_args()
    convert(args.indir, args.outdir)
