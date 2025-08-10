from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

Fields = Mapping[str, "Field"]


@dataclass
class Field:
    name: str
    block: str
    default: Any | None
    description: str | None
    children: Fields | None
    optional: bool | None
    shape: str | None
    type: str
