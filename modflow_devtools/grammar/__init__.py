from os import PathLike
from pathlib import Path
import jinja2

from modflow_devtools.dfn import Dfn


def _get_template_env():
    loader = jinja2.PackageLoader("modflow_devtools", "grammar/")
    env = jinja2.Environment(
        loader=loader,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    return env


def make_grammar(dfn: Dfn, outdir: PathLike):
    """Generate a Lark grammar file for a single component."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    env = _get_template_env()
    template = env.get_template("component.lark.j2")
    target_path = outdir / f"{dfn['name']}.lark"
    with open(target_path, 'w') as f:
        f.write(template.render(dfn=dfn))


def make_all(dfns: dict[str, Dfn], outdir: PathLike):
    """Generate grammars for all components."""
    outdir = Path(outdir).expanduser().resolve().absolute()
    outdir.mkdir(parents=True, exist_ok=True)
    for dfn in dfns:
        make_grammar(dfn, outdir)
