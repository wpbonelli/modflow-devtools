"""
MODFLOW 6 definition file tools.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from itertools import groupby
from os import PathLike
from pathlib import Path
from typing import (
    Any,
    Literal,
)

import tomli
from boltons.dictutils import OMD
from boltons.iterutils import remap

import modflow_devtools.dfn.schema.v1 as v1_schema
import modflow_devtools.dfn.schema.v2 as v2_schema
from modflow_devtools.dfn.legacy_parser import (
    field_attr_sort_key,
    is_advanced_package,
    is_multi_package,
    parse_dfn,
    try_parse_bool,
    try_parse_package_reference,
    try_parse_solution_package,
)
from modflow_devtools.dfn.schema.block import Block, Blocks
from modflow_devtools.dfn.schema.field import Field, Fields
from modflow_devtools.dfn.schema.ref import Ref
from modflow_devtools.dfn.schema.sln import Sln
from modflow_devtools.misc import try_literal_eval

Format = Literal["dfn", "toml"]
"""DFN serialization format."""


SchemaVersion = Literal[1, 2]
"""DFN schema version number."""


Dfns = dict[str, "Dfn"]


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
    children: Dfns | None

    @property
    def fields(self) -> Fields:
        """
        Extract a flat dictionary of fields from an input definition.
        Only top-level fields are included, i.e. subfields of records
        or recarrays are not included.
        """
        fields = []
        for block in self.blocks.values():
            for field in block.values():
                fields.append([field["name"], field])
        return OMD(fields)

    def schema(self) -> SchemaVersion:
        """
        Return the schema version of this definition.
        """
        if (field := next(iter(self.fields.values()), None)) is None or isinstance(
            field, v2_schema.FieldV2
        ):
            return 2
        return 1


class SchemaMap(ABC):
    @abstractmethod
    def map(self, dfn: Dfn) -> Dfn: ...


class MapV1To2(SchemaMap):
    @staticmethod
    def map_period_block(dfn: Dfn, block: Block) -> Block:
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

    @staticmethod
    def map_field(dfn: Dfn, field: Field) -> Field:
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

        flat = dfn.fields

        def _map_field(_field) -> Field:
            _field = _field.copy()
            # parse booleans from strings. everything else can
            # stay a string except default values, which we'll
            # try to parse as arbitrary literals below, and at
            # some point types, once we introduce type hinting
            _field = {k: try_parse_bool(v) for k, v in _field.items()}
            _name = _field.pop("name")
            _type = _field.pop("type", None)
            shape = _field.pop("shape", None)
            shape = None if shape == "" else shape
            block = _field.pop("block", None)
            default = _field.pop("default", None)
            default = try_literal_eval(default) if _type != "string" else default
            description = _field.pop("description", "")
            reader = _field.pop("reader", "urword")

            def _item() -> Field:
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
                    return MapV1To2.map_field(
                        dfn, next(iter(flat.getlist(item_names[0])))
                    )

                # implicit simple record (no children)
                if all(t in v1_schema._SCALAR_TYPES for t in item_types):
                    return Field(
                        name=_name,
                        type="record",
                        block=block,
                        children=_fields(),
                        description=description.replace(
                            "is the list of", "is the record of"
                        ),
                        reader=reader,
                        **_field,
                    )

                # implicit complex record (has children)
                fields = {
                    v["name"]: MapV1To2.map_field(dfn, v)
                    for v in flat.values(multi=True)
                    if v["name"] in item_names and v.get("in_record", False)
                }
                first = next(iter(fields.values()))
                single = len(fields) == 1
                item_type = (
                    "keystring" if single and "keystring" in first["type"] else "record"
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
                    **_field,
                )

            def _choices() -> Fields:
                names = _type.split()[1:]
                return {
                    v["name"]: MapV1To2.map_field(dfn, v)
                    for v in flat.values(multi=True)
                    if v["name"] in names and v.get("in_record", False)
                }

            def _fields() -> Fields:
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
                    fields[name] = _map_field(v)
                return fields

            _field = Field(
                name=_name,
                shape=shape,
                block=block,
                description=description,
                default=default,
                reader=reader,
                **_field,
            )

            if _type.startswith("recarray"):
                item = _item()
                _field["children"] = {item["name"]: item}
                _field["type"] = "recarray"

            elif _type.startswith("keystring"):
                _field["children"] = _choices()
                _field["type"] = "keystring"

            elif _type.startswith("record"):
                _field["children"] = _fields()
                _field["type"] = "record"

            # for now, we can tell a var is an array if its type
            # is scalar and it has a shape. once we have proper
            # typing, this can be read off the type itself.
            elif shape is not None and _type not in v1_schema._SCALAR_TYPES:
                raise TypeError(f"Unsupported array type: {_type}")

            else:
                _field["type"] = _type

            return _field

        return dict(sorted(_map_field(field).items(), key=field_attr_sort_key))

    @staticmethod
    def map_blocks(dfn: Dfn) -> Blocks:
        blocks = dfn.blocks
        # map top-level fields. nested # fields mapped recursively
        fields = {
            field["name"]: MapV1To2.map_field(dfn, field)
            for field in dfn.fields.values(multi=True)
            if not field.get("in_record", False)
        }
        # group variables by block
        blocks = {
            block_name: {v["name"]: v for v in block}
            for block_name, block in groupby(fields.values(), lambda v: v["block"])
        }
        # if there's a period block, convert array representations
        if (period_block := blocks.get("period", None)) is not None:
            blocks["period"] = MapV1To2.map_period_block(dfn, period_block)

        # remove unneeded variable attributes
        def remove_attrs(path, key, value):
            if key in ["in_record", "tagged", "preserve_case"]:
                return False
            return True

        return remap(blocks, visit=remove_attrs)

    def map(self, dfn: Dfn) -> Dfn:
        if dfn.schema == 2:
            return dfn
        return Dfn(
            name=self.name,
            advanced=self.advanced,
            multi=self.multi,
            sln=self.sln,
            ref=self.ref,
            blocks=MapV1To2.map_blocks(dfn),
        )


def map(
    dfn: Dfn,
    schema: SchemaVersion = 2,
) -> Dfn:
    """Map a MODFLOW 6 specification to another schema version."""
    if schema == 1:
        raise NotImplementedError("Mapping to v1 schema is not implemented yet.")
    elif schema == 2:
        return MapV1To2().map(dfn)


def load(
    f: str | PathLike,
    schema: SchemaVersion = 2,
    **kwargs,
) -> Dfn:
    """Load a MODFLOW 6 definition file."""
    path = Path(f).expanduser().resolve()
    if path.suffix == ".dfn":
        with path.open() as file:
            flat, meta = parse_dfn(file, **kwargs)
            blocks = {
                block_name: {v["name"]: v for v in block}
                for block_name, block in groupby(flat.values(), lambda v: v["block"])
            }
            dfn = Dfn(
                name=path.stem,
                blocks=blocks,
                advanced=is_advanced_package(meta),
                multi=is_multi_package(meta),
                sln=try_parse_solution_package(meta),
                ref=try_parse_package_reference(meta),
            )
    elif path.suffix == ".toml":
        with path.open("rb") as file:
            dfn = Dfn(**tomli.load(file))
    return dfn.map(schema)


def load_all(
    dfndir: str | PathLike,
    schema: SchemaVersion = 2,
) -> Dfns:
    """Load a MODFLOW 6 specification from definition files in a directory."""
    exclude = ["common", "flopy"]
    dfn_paths = [p for p in dfndir.glob("*.dfn") if p.stem not in exclude]
    toml_paths = [p for p in dfndir.glob("*.toml") if p.stem not in exclude]
    dfns: Dfns = {}
    if dfn_paths:
        if not (common_path := dfndir / "common.dfn").is_file:
            common = None
        else:
            common = load(common_path, schema=1)
        for path in dfn_paths:
            dfn = load(path, schema=1, common=common)
            dfns[path.stem] = dfn
    if toml_paths:
        for path in toml_paths:
            dfn = load(path, schema=schema)
            dfns[path.stem] = dfn
    return dfns


def infer_tree(dfns: Dfns) -> Dfn:
    """
    Infer the MODFLOW 6 input component hierarchy from a flat spec:
    unlinked DFNs, i.e. without `children` populated, only `parent`.

    Returns the root component with children filled.
    There must be exactly one root, i.e. component with no `parent`.

    Assumes all DFNs are of the same schema version.
    """

    def drop_none_or_empty(path, key, value):
        if value is None or value == "" or value == [] or value == {}:
            return False
        return True

    def add_parent(dfn):
        if (dfn_name := dfn["name"]) == "sim-nam":
            dfn = dfn.copy()
            dfn["name"] = "sim"
        elif dfn_name.endswith("-nam"):
            model_type = dfn_name[:-4]  # Remove "-nam"
            dfn = dfn.copy()
            dfn["name"] = model_type
            dfn["parent"] = "sim"
        elif dfn_name.startswith("exg-"):
            dfn = dfn.copy()
            dfn["parent"] = "sim"
        elif dfn_name.startswith("sln-"):
            dfn = dfn.copy()
            dfn["parent"] = "sim"
        elif dfn_name.startswith("utl-"):
            dfn = dfn.copy()
            dfn["parent"] = "sim"
        elif "-" in dfn_name:
            model_type = dfn_name.split("-")[0]
            dfn = dfn.copy()
            dfn["parent"] = model_type

        return remap(dfn, visit=drop_none_or_empty)

    dfns = {name: add_parent(dfn) for name, dfn in dfns.items()}
    if (schema := next(iter(dfns.values()), None)) == 1:
        # TODO implement v1 schema structure inference
        raise NotImplementedError("Structure inference from v1 schema not implemented")
    elif schema == 2:
        if (
            len(roots := [name for name, dfn in dfns.items() if not dfn.get("parent")])
            != 1
        ):
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


def load_tree(
    dfndir: str | PathLike,
    schema: SchemaVersion = 2,
) -> Dfn:
    """
    Load a structured MODFLOW 6 specification from definition files in a directory.

    A single root component definition (the simulation) is returned. This contains
    child (and grandchild) components for the relevant models and packages.
    """
    return infer_tree(load_all(dfndir, schema=schema))
