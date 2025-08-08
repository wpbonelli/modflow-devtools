from typing import Literal

from modflow_devtools.dfn.schema.field import Field

FieldType = Literal[
    "keyword", "integer", "double", "string", "record", "union", "array"
]


class FieldV2(Field):
    type: FieldType
