"""Convert DFNs to TOML."""

import argparse
from os import PathLike
from pathlib import Path

from modflow_devtools.dfn import Dfn
from modflow_devtools.grammar import make_all


_GRAMMARS_DIR = Path(__file__).parent / "grammars" / "generated"


def generate(dfndir: PathLike, outdir: PathLike):
    """Generate lark grammars from DFNs."""
    dfndir = Path(dfndir).expanduser().absolute()
    outdir = Path(outdir).expanduser().absolute()
    outdir.mkdir(exist_ok=True, parents=True)
    
    dfns = Dfn.load_all(dfndir).values()
    make_all(dfns, outdir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate lark grammars from DFNs.")
    parser.add_argument(
        "--dfndir",
        "-d",
        type=str,
        help="Directory containing DFN files.",
    )
    parser.add_argument(
        "--outdir",
        "-o",
        help="Output directory.",
        default=_GRAMMARS_DIR,
    )
    args = parser.parse_args()
    make_all(args.dfndir, args.outdir)
