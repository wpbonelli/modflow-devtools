from typing import Any, TypedDict

Fields = dict[str, "Field"]
Block = Fields
Blocks = dict[str, Block]


class Field(TypedDict):
    name: str
    block: str
    default: Any | None
    description: str | None
    children: "Fields" | None
    optional: bool | None
    shape: str | None
    type: str