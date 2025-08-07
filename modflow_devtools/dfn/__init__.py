"""
MODFLOW 6 definition file tools.
"""

from dataclasses import dataclass
import shutil
import tempfile
from ast import literal_eval
from collections.abc import Mapping
from itertools import groupby
from os import PathLike
from pathlib import Path
from typing import (
    Any,
    Literal,
    Optional,
    TypedDict,
)
from warnings import warn

import tomli
from boltons.dictutils import OMD
from boltons.iterutils import remap

from modflow_devtools.download import download_and_unzip
from modflow_devtools.misc import try_literal_eval


from dataclasses import dataclass
from typing import Literal
from warnings import warn

from modflow_devtools.dfn.field import Field, Fields, Block, Blocks


FormatOption = Literal["dfn", "toml"]
"""DFN serialization format."""


SchemaVersion = Literal[1, 2]
"""DFN schema version number."""


class Ref(TypedDict):
    """
    A foreign-key-like reference between a file input variable
    in a referring input component and another input component
    referenced by it.
    """

    key: str # name of file path field in referring component
    tgt: str # name of target component


class Sln(TypedDict):
    """
    MODFLOW 6 solution package metadata. Describes which kinds
    of models this solution applies to.
    """

    models: list[str]  # list of model types this solution applies to


@dataclass
class Dfn:
    """
    MODFLOW 6 input component definition.
    """

    name: str
    advanced: bool
    multi: bool
    parent: str | None
    ref: Ref | None
    sln: Sln | None
    blocks: Blocks
    children: "Dfns" | None


    @property
    def fields(self) -> Fields:
        """
        Extract a flat dictionary of fields from an input definition.
        Only top-level fields are included, i.e. subfields of records
        or recarrays are not included.
        """
        fields = {}
        for block in self.blocks.values():
            for field in block.values():
                if field["name"] in fields:
                    warn(f"Duplicate field name {field['name']} in {self['name']}")
                fields[field["name"]] = field
        return fields

    @property
    def schema_version(self) -> SchemaVersion:
        """The schema version used by the DFN."""
        # TODO
        pass

    def to_v2(self) -> "Dfn":
        """Convert the DFN from version 1 to version 2 schema."""
        # TODO
        pass

    def to_v1(self) -> "Dfn":
        """Convert the DFN from version 2 to version 1 schema."""
        # TODO
        pass


Dfns = dict[str, Dfn]


def load_dfn(
    f: str | PathLike,
    name: str | None = None,
    **kwargs,
) -> Dfn:
    # TODO
    pass


def load_toml(
    f: str | PathLike,
    name: str | None = None,
) -> Dfn:
    """
    Load a MODFLOW 6 definition file in TOML format.
    """
    with open(f, "rb") as file:
        data = tomli.load(file)
    
    if name is None:
        name = data.get("name", Path(f).stem)
    elif name != (given_name := data.get("name", None)):
        raise ValueError(f"Name mismatch: {name} != {given_name}")

    return Dfn(name=name, **data)


def load(
    f,
    name: str | None = None,
    format: FormatOption = "dfn",
    schema: SchemaVersion = 2,
    **kwargs,
) -> Dfn:
    """Load a MODFLOW 6 definition file."""
    if format == "dfn":
        dfn = load_dfn(f, name, **kwargs)
    elif format == "toml":
        dfn = load_toml(f, name)
    if schema == 2 and dfn.schema_version == 1:
        dfn = dfn.to_v2()
    elif schema == 1 and dfn.schema_version == 2:
        dfn = dfn.to_v1()
    return dfn


def load_all(
    dfndir: PathLike,
    format: FormatOption = "dfn",
    schema: SchemaVersion = 2,
    **kwargs,
) -> Dfn:
    """Load a MODFLOW 6 specification from definition files in a directory."""
    # TODO
    pass


def infer_tree(dfns: Dfns) -> Dfn:
    """
    Infer the MODFLOW 6 input component hierarchy from a flat dict of
    unlinked DFNs, i.e. without `children` populated, only `parent`.
    
    Returns the root component with children filled.
    There must be exactly one root, i.e. component with no `parent`.
    """

    if len(roots := [name for name, dfn in dfns.items() if not dfn.get("parent")]) != 1:
        raise ValueError(
            f"Expected one root component, found {len(roots)}: {roots}"
        )
    
    def add_children(node_name: str) -> dict[str, Any]:
        node = dict(dfns[node_name])
        children = [
            name for name, dfn in dfns.items() if dfn.get("parent") == node_name
        ]
        for child in children:
            node[child] = add_children(child)
        return node

    return {(root_name := roots[0]): add_children(root_name)}



def fetch_dfns(
    owner: str, repo: str, ref: str, outdir: str | PathLike, verbose: bool = False
):
    """Fetch definition files from the MODFLOW 6 repository."""
    url = f"https://github.com/{owner}/{repo}/archive/{ref}.zip"
    if verbose:
        print(f"Downloading MODFLOW 6 repository archive from {url}")
    with tempfile.TemporaryDirectory() as tmp:
        dl_path = download_and_unzip(url, Path(tmp), verbose=verbose)
        contents = list(dl_path.glob("modflow6-*"))
        proj_path = next(iter(contents), None)
        if not proj_path:
            raise ValueError(f"Missing proj dir in {dl_path}, found {contents}")
        if verbose:
            print("Copying dfns from download dir to output dir")
        shutil.copytree(
            proj_path / "doc" / "mf6io" / "mf6ivar" / "dfn", outdir, dirs_exist_ok=True
        )

get_dfns = fetch_dfns # alias for backward compatibility