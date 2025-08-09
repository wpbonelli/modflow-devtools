from collections.abc import Mapping
from typing import Any, TypedDict

Fields = Mapping[str, "Field"]


class Field(TypedDict):
    name: str
    block: str
    default: Any | None
    description: str | None
    children: Fields | None
    optional: bool | None
    shape: str | None
    type: str
