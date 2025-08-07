"""
MODFLOW 6 definition file tools.
"""

from dataclasses import dataclass
from ast import literal_eval
from collections.abc import Mapping
from itertools import groupby
from os import PathLike
from pathlib import Path
from typing import (
    Any,
)
from warnings import warn

import tomli
from boltons.dictutils import OMD
from boltons.iterutils import remap

from modflow_devtools.misc import try_literal_eval


# TODO finish reimpl


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

    @staticmethod  # type: ignore[misc]
    def _load_v1_flat(f, common: dict | None = None) -> tuple[Mapping, list[str]]:
        field = {}
        flat = []
        meta = []
        common = common or {}

        for line in f:
            # remove whitespace/etc from the line
            line = line.strip()

            # record context name and flopy metadata
            # attributes, skip all other comment lines
            if line.startswith("#"):
                _, sep, tail = line.partition("flopy")
                if sep == "flopy":
                    if (
                        "multi-package" in tail
                        or "solution_package" in tail
                        or "subpackage" in tail
                        or "parent" in tail
                    ):
                        meta.append(tail.strip())
                _, sep, tail = line.partition("package-type")
                if sep == "package-type":
                    meta.append(f"package-type {tail.strip()}")
                continue

            # if we hit a newline and the parameter dict
            # is nonempty, we've reached the end of its
            # block of attributes
            if not any(line):
                if any(field):
                    flat.append((field["name"], field))
                    field = {}
                continue

            # split the attribute's key and value and
            # store it in the parameter dictionary
            key, _, value = line.partition(" ")
            if key == "default_value":
                key = "default"
            field[key] = value

            # make substitutions from common variable definitions,
            # remove backslashes, TODO: generate/insert citations.
            descr = field.get("description", None)
            if descr:
                descr = descr.replace("\\", "").replace("``", "'").replace("''", "'")
                _, replace, tail = descr.strip().partition("REPLACE")
                if replace:
                    key, _, subs = tail.strip().partition(" ")
                    subs = literal_eval(subs)
                    cmmn = common.get(key, None)
                    if cmmn is None:
                        warn(
                            "Can't substitute description text, "
                            f"common variable not found: {key}"
                        )
                    else:
                        descr = cmmn.get("description", "")
                        if any(subs):
                            descr = descr.replace("\\", "").replace(
                                "{#1}", subs["{#1}"]
                            )
                field["description"] = descr

        # add the final parameter
        if any(field):
            flat.append((field["name"], field))

        # the point of the OMD is to losslessly handle duplicate variable names
        return OMD(flat), meta

    @classmethod  # type: ignore[misc]
    def _load_v1(cls, f, name, **kwargs) -> "Dfn":
        """
        Temporary load routine for the v1 DFN format.
        """

        flat, meta = Dfn._load_v1_flat(f, **kwargs)

        def _convert_period_block(block: Block) -> Block:
            """
            Convert a period block recarray to individual arrays, one per column.

            Extracts recarray fields and creates separate array variables. Gives
            each an appropriate grid- or tdis-aligned shape as opposed to sparse
            list shape in terms of maxbound as previously.
            """

            fields = list(block.values())
            if fields[0]["type"] == "recarray":
                assert len(fields) == 1
                recarray_name = fields[0]["name"]
                item = next(iter(fields[0]["children"].values()))
                columns = item["children"]
            else:
                recarray_name = None
                columns = block
            block.pop(recarray_name, None)
            cellid = columns.pop("cellid", None)
            for col_name, column in columns.items():
                col_copy = column.copy()
                old_dims = col_copy.get("shape")
                if old_dims:
                    old_dims = old_dims[1:-1].split(",")
                new_dims = ["nper"]
                if cellid:
                    new_dims.append("nnodes")
                if old_dims:
                    new_dims.extend([dim for dim in old_dims if dim != "maxbound"])
                col_copy["shape"] = f"({', '.join(new_dims)})"
                block[col_name] = col_copy

            return block

        def _convert_field(var: dict[str, Any]) -> Field:
            """
            Convert an input field specification from its representation
            in a v1 format definition file to the v2 (structured) format.

            Notes
            -----
            If the field does not have a `default` attribute, it will
            default to `False` if it is a keyword, otherwise to `None`.

            A filepath field whose name functions as a foreign key
            for a separate context will be given a reference to it.
            """

            def _load(field) -> Field:
                field = field.copy()

                # parse booleans from strings. everything else can
                # stay a string except default values, which we'll
                # try to parse as arbitrary literals below, and at
                # some point types, once we introduce type hinting
                field = {k: try_parse_bool(v) for k, v in field.items()}

                _name = field.pop("name")
                _type = field.pop("type", None)
                shape = field.pop("shape", None)
                shape = None if shape == "" else shape
                block = field.pop("block", None)
                default = field.pop("default", None)
                default = try_literal_eval(default) if _type != "string" else default
                description = field.pop("description", "")
                reader = field.pop("reader", "urword")

                def _item() -> Field:
                    """Load list item."""

                    item_names = _type.split()[1:]
                    item_types = [
                        v["type"]
                        for v in flat.values(multi=True)
                        if v["name"] in item_names and v.get("in_record", False)
                    ]
                    n_item_names = len(item_names)
                    if n_item_names < 1:
                        raise ValueError(f"Missing list definition: {_type}")

                    # explicit record
                    if n_item_names == 1 and (
                        item_types[0].startswith("record")
                        or item_types[0].startswith("keystring")
                    ):
                        return _convert_field(next(iter(flat.getlist(item_names[0]))))

                    # implicit simple record (no children)
                    if all(t in _SCALAR_TYPES for t in item_types):
                        return Field(
                            name=_name,
                            type="record",
                            block=block,
                            children=_fields(),
                            description=description.replace(
                                "is the list of", "is the record of"
                            ),
                            reader=reader,
                            **field,
                        )

                    # implicit complex record (has children)
                    fields = {
                        v["name"]: _convert_field(v)
                        for v in flat.values(multi=True)
                        if v["name"] in item_names and v.get("in_record", False)
                    }
                    first = next(iter(fields.values()))
                    single = len(fields) == 1
                    item_type = (
                        "keystring"
                        if single and "keystring" in first["type"]
                        else "record"
                    )
                    return Field(
                        name=first["name"] if single else _name,
                        type=item_type,
                        block=block,
                        children=first["children"] if single else fields,
                        description=description.replace(
                            "is the list of", f"is the {item_type} of"
                        ),
                        reader=reader,
                        **field,
                    )

                def _choices() -> Fields:
                    """Load keystring (union) choices."""
                    names = _type.split()[1:]
                    return {
                        v["name"]: _convert_field(v)
                        for v in flat.values(multi=True)
                        if v["name"] in names and v.get("in_record", False)
                    }

                def _fields() -> Fields:
                    """Load record fields."""
                    names = _type.split()[1:]
                    fields = {}
                    for name in names:
                        v = flat.get(name, None)
                        if (
                            not v
                            or not v.get("in_record", False)
                            or v["type"].startswith("record")
                        ):
                            continue
                        fields[name] = _convert_field(v)
                    return fields

                var_ = Field(
                    name=_name,
                    shape=shape,
                    block=block,
                    description=description,
                    default=default,
                    reader=reader,
                    **field,
                )

                if _type.startswith("recarray"):
                    item = _item()
                    var_["children"] = {item["name"]: item}
                    var_["type"] = "recarray"

                elif _type.startswith("keystring"):
                    var_["children"] = _choices()
                    var_["type"] = "keystring"

                elif _type.startswith("record"):
                    var_["children"] = _fields()
                    var_["type"] = "record"

                # for now, we can tell a var is an array if its type
                # is scalar and it has a shape. once we have proper
                # typing, this can be read off the type itself.
                elif shape is not None and _type not in _SCALAR_TYPES:
                    raise TypeError(f"Unsupported array type: {_type}")

                else:
                    var_["type"] = _type

                return var_

            return dict(sorted(_load(var).items(), key=field_attr_sort_key))

        # load top-level fields. any nested
        # fields will be loaded recursively
        fields = {
            field["name"]: _convert_field(field)
            for field in flat.values(multi=True)
            if not field.get("in_record", False)
        }

        # group variables by block
        blocks = {
            block_name: {v["name"]: v for v in block}
            for block_name, block in groupby(fields.values(), lambda v: v["block"])
        }

        # if there's a period block, extract distinct arrays from
        # the recarray-style definition
        if (period_block := blocks.get("period", None)) is not None:
            blocks["period"] = _convert_period_block(period_block)

        # remove unneeded variable attributes
        def remove_attrs(path, key, value):
            if key in ["in_record", "tagged", "preserve_case"]:
                return False
            return True

        blocks = remap(blocks, visit=remove_attrs)

        def _advanced() -> bool | None:
            return any("package-type advanced" in m for m in meta)

        def _multi() -> bool:
            return any("multi-package" in m for m in meta)

        def _sln() -> Sln | None:
            sln = next(
                iter(
                    m
                    for m in meta
                    if isinstance(m, str) and m.startswith("solution_package")
                ),
                None,
            )
            if sln:
                abbr, pattern = sln.split()[1:]
                return Sln(abbr=abbr, pattern=pattern)
            return None

        def _sub() -> Ref | None:
            def _parent():
                line = next(
                    iter(
                        m for m in meta if isinstance(m, str) and m.startswith("parent")
                    ),
                    None,
                )
                if not line:
                    return None
                split = line.split()
                return split[1]

            def _rest():
                line = next(
                    iter(
                        m for m in meta if isinstance(m, str) and m.startswith("subpac")
                    ),
                    None,
                )
                if not line:
                    return None
                _, key, abbr, param, val = line.split()
                matches = [v for v in fields.values() if v["name"] == val]
                if not any(matches):
                    descr = None
                else:
                    if len(matches) > 1:
                        warn(f"Multiple matches for referenced variable {val}")
                    match = matches[0]
                    descr = match["description"]

                return {
                    "key": key,
                    "val": val,
                    "abbr": abbr,
                    "param": param,
                    "description": descr,
                }

            parent = _parent()
            rest = _rest()
            if parent and rest:
                return Ref(parent=parent, **rest)
            return None

        return cls(
            name=name,
            advanced=_advanced(),
            multi=_multi(),
            sln=_sln(),
            ref=_sub(),
            **blocks,
        )

    @classmethod  # type: ignore[misc]
    def load(
        cls,
        f,
        name: str | None = None,
        version: SchemaVersion = 1,
        **kwargs,
    ) -> "Dfn":
        """
        Load a component definition from a definition file.
        """

        if version == 1:
            return cls._load_v1(f, name, **kwargs)
        elif version == 2:
            return cls._load_v2(f, name)
        else:
            raise ValueError(f"Unsupported version, expected one of {version.__args__}")

    @staticmethod  # type: ignore[misc]
    def _load_all_v1(dfndir: PathLike) -> Dfns:
        paths: list[Path] = [
            p for p in dfndir.glob("*.dfn") if p.stem not in ["common", "flopy"]
        ]

        # load common variables
        common_path: Path | None = dfndir / "common.dfn"
        if not common_path.is_file:
            common = None
        else:
            with common_path.open() as f:
                common, _ = Dfn._load_v1_flat(f)

        # load definitions
        dfns: Dfns = {}
        for path in paths:
            with path.open() as f:
                dfn = Dfn.load(f, name=path.stem, common=common)
                dfns[path.stem] = dfn

        return dfns

    @staticmethod  # type: ignore[misc]
    def _load_all_v2(dfndir: PathLike) -> Dfns:
        paths: list[Path] = [
            p for p in dfndir.glob("*.toml") if p.stem not in ["common", "flopy"]
        ]
        dfns: Dfns = {}
        for path in paths:
            with path.open(mode="rb") as f:
                dfn = Dfn.load(f, name=path.stem, version=2)
                dfns[path.stem] = dfn

        return dfns

    @staticmethod  # type: ignore[misc]
    def load_all(dfndir: PathLike, version: SchemaVersion = 1) -> Dfns:
        """Load all component definitions from the given directory."""
        if version == 1:
            return Dfn._load_all_v1(dfndir)
        elif version == 2:
            return Dfn._load_all_v2(dfndir)
        else:
            raise ValueError(f"Unsupported version, expected one of {version.__args__}")
