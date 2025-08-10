from dataclasses import dataclass
from typing import Literal

from modflow_devtools.dfn.schema.field import Field

FieldType = Literal[
    "keyword", "integer", "double", "string", "array", "record", "union"
]


@dataclass
class FieldV2(Field):
    type: FieldType
