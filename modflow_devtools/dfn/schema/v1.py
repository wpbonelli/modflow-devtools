from dataclasses import dataclass
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


@dataclass
class FieldV1(Field):
    valid: tuple[str, ...] | None = None
    tagged: bool | None = None
    in_record: bool | None = None
    layered: bool | None = None
    reader: Reader = "urword"
    longname: str | None = None
    preserve_case: bool | None = None
    numeric_index: bool | None = None
    deprecated: bool = False
    removed: bool = False
    mf6internal: str | None = None
