from typing import Any, Literal

from modflow_devtools.dfn.field import Field


_SCALAR_TYPES = ("keyword", "integer", "double precision", "string")


FieldType = Literal[
    "keyword",
    "integer",
    "double precision",
    "string",
    "record",
    "recarray",
    "keystring",
]


Reader = Literal[
    "urword",
    "u1ddbl",
    "u2ddbl",
    "readarray",
]


class FieldV1(Field):
    valid: tuple[str, ...] | None
    tagged: bool | None
    in_record: bool | None
    layered: bool | None
    reader: Reader | None
    longname: str | None
    preserve_case: bool | None
    numeric_index: bool | None
    deprecated: bool | None
    removed: bool | None
    mf6internal: str | None


def block_sort_key(item) -> int:
    k, _ = item
    if k == "options":
        return 0
    elif k == "dimensions":
        return 1
    elif k == "griddata":
        return 2
    elif k == "packagedata":
        return 3
    elif "period" in k:
        return 4
    else:
        return 5


def field_attr_sort_key(item) -> int:
    """
    Sort key for input field attributes. The order is:
    -1. block
    0. name
    1. type
    2. shape
    3. default
    4. reader
    5. optional
    6. longname
    7. description
    """

    k, _ = item
    if k == "block":
        return -1
    if k == "name":
        return 0
    if k == "type":
        return 1
    if k == "shape":
        return 2
    if k == "default":
        return 3
    if k == "reader":
        return 4
    if k == "optional":
        return 5
    if k == "longname":
        return 6
    if k == "description":
        return 7
    return 8


def try_parse_bool(value: Any) -> Any:
    """
    Try to parse a boolean from a string as represented
    in a DFN file, otherwise return the value unaltered.
    """
    if isinstance(value, str):
        value = value.lower()
        if value in ["true", "false"]:
            return value == "true"
    return value
