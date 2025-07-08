

from typing import Any
from modflow_devtools.dfn import Field


def lark_type(field_type: str) -> str:
    if field_type in ['integer', 'double precision']:
        return 'NUMBER'
    if 'recarray' in field_type:
        return 'recarray'
    return "word"


def lark_field(field: Field) -> dict[str, Any]:
    return {
        'name': field['name'],
        'type': lark_type(field['type']),
        'description': field["description"]
    }