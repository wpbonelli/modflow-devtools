"""Convert DFNs to TOML."""

import argparse
from os import PathLike
from pathlib import Path

import tomli_w as tomli

from modflow_devtools.dfn import load_all

# mypy: ignore-errors


def convert(indir: PathLike, outdir: PathLike):
    indir = Path(indir).expanduser().absolute()
    outdir = Path(outdir).expanduser().absolute()
    outdir.mkdir(exist_ok=True, parents=True)
    dfns = load_all(indir, schema=2)
    for dfn in dfns:
        dfn_name = dfn["name"]
        filename = f"{dfn_name}.toml"
        with Path.open(outdir / filename, "wb") as f:
            tomli.dump(dfn, f)


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
