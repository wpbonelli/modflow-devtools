


from typing import Literal

from modflow_devtools.dfn.field import Field, Fields, Block


Fields = dict[str, "Field"]
Block = Fields
Blocks = dict[str, Block]


FieldType = Literal[
    "keyword",
    "integer",
    "double",
    "string",
    "record",
    "union",
    "array"
]


class FieldV2(Field):
    type: FieldType


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
    if k == "optional":
        return 4
    if k == "description":
        return 5
    return 6