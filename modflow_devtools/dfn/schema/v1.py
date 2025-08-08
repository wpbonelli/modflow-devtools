from typing import Literal

from modflow_devtools.dfn.schema.field import Field

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
