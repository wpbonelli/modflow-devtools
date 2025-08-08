import modflow_devtools.dfn.schema.v1 as v1
from modflow_devtools.dfn.legacy_parser import field_attr_sort_key, try_parse_bool
from modflow_devtools.dfn.schema.block import Block
from modflow_devtools.dfn.schema.field import Field, Fields
from modflow_devtools.misc import try_literal_eval


class V1ToV2:
    def __init__(self, dfn: "Dfn"):
        self.dfn = dfn

    def map_period_block(self, block: Block) -> Block:
        """
        Convert a period block recarray to individual arrays, one per column.

        Extracts recarray fields and creates separate array variables. Gives
        each an appropriate grid- or tdis-aligned shape as opposed to sparse
        list shape in terms of maxbound as previously.
        """

        fields = list(block.values())
        if fields[0]["type"] == "recarray":
            assert len(fields) == 1
            recarray_name = fields[0]["name"]
            item = next(iter(fields[0]["children"].values()))
            columns = item["children"]
        else:
            recarray_name = None
            columns = block
        block.pop(recarray_name, None)
        cellid = columns.pop("cellid", None)
        for col_name, column in columns.items():
            col_copy = column.copy()
            old_dims = col_copy.get("shape")
            if old_dims:
                old_dims = old_dims[1:-1].split(",")
            new_dims = ["nper"]
            if cellid:
                new_dims.append("nnodes")
            if old_dims:
                new_dims.extend([dim for dim in old_dims if dim != "maxbound"])
            col_copy["shape"] = f"({', '.join(new_dims)})"
            block[col_name] = col_copy

        return block

    def map_field(self, field: Field) -> Field:
        """
        Convert an input field specification from its representation
        in a v1 format definition file to the v2 (structured) format.

        Notes
        -----
        If the field does not have a `default` attribute, it will
        default to `False` if it is a keyword, otherwise to `None`.

        A filepath field whose name functions as a foreign key
        for a separate context will be given a reference to it.
        """

        flat = self.dfn.fields

        def _map(_field) -> Field:
            _field = _field.copy()

            # parse booleans from strings. everything else can
            # stay a string except default values, which we'll
            # try to parse as arbitrary literals below, and at
            # some point types, once we introduce type hinting
            _field = {k: try_parse_bool(v) for k, v in _field.items()}

            _name = _field.pop("name")
            _type = _field.pop("type", None)
            shape = _field.pop("shape", None)
            shape = None if shape == "" else shape
            block = _field.pop("block", None)
            default = _field.pop("default", None)
            default = try_literal_eval(default) if _type != "string" else default
            description = _field.pop("description", "")
            reader = _field.pop("reader", "urword")

            def _item() -> Field:
                """Load list item."""

                item_names = _type.split()[1:]
                item_types = [
                    v["type"]
                    for v in flat.values(multi=True)
                    if v["name"] in item_names and v.get("in_record", False)
                ]
                n_item_names = len(item_names)
                if n_item_names < 1:
                    raise ValueError(f"Missing list definition: {_type}")

                # explicit record
                if n_item_names == 1 and (
                    item_types[0].startswith("record")
                    or item_types[0].startswith("keystring")
                ):
                    return self.map_field(next(iter(flat.getlist(item_names[0]))))

                # implicit simple record (no children)
                if all(t in v1._SCALAR_TYPES for t in item_types):
                    return Field(
                        name=_name,
                        type="record",
                        block=block,
                        children=_fields(),
                        description=description.replace(
                            "is the list of", "is the record of"
                        ),
                        reader=reader,
                        **_field,
                    )

                # implicit complex record (has children)
                fields = {
                    v["name"]: self.map_field(v)
                    for v in flat.values(multi=True)
                    if v["name"] in item_names and v.get("in_record", False)
                }
                first = next(iter(fields.values()))
                single = len(fields) == 1
                item_type = (
                    "keystring" if single and "keystring" in first["type"] else "record"
                )
                return Field(
                    name=first["name"] if single else _name,
                    type=item_type,
                    block=block,
                    children=first["children"] if single else fields,
                    description=description.replace(
                        "is the list of", f"is the {item_type} of"
                    ),
                    reader=reader,
                    **_field,
                )

            def _choices() -> Fields:
                """Load keystring (union) choices."""
                names = _type.split()[1:]
                return {
                    v["name"]: self._map(v)
                    for v in flat.values(multi=True)
                    if v["name"] in names and v.get("in_record", False)
                }

            def _fields() -> Fields:
                """Load record fields."""
                names = _type.split()[1:]
                fields = {}
                for name in names:
                    v = flat.get(name, None)
                    if (
                        not v
                        or not v.get("in_record", False)
                        or v["type"].startswith("record")
                    ):
                        continue
                    fields[name] = _map(v)
                return fields

            _field = Field(
                name=_name,
                shape=shape,
                block=block,
                description=description,
                default=default,
                reader=reader,
                **_field,
            )

            if _type.startswith("recarray"):
                item = _item()
                _field["children"] = {item["name"]: item}
                _field["type"] = "recarray"

            elif _type.startswith("keystring"):
                _field["children"] = _choices()
                _field["type"] = "keystring"

            elif _type.startswith("record"):
                _field["children"] = _fields()
                _field["type"] = "record"

            # for now, we can tell a var is an array if its type
            # is scalar and it has a shape. once we have proper
            # typing, this can be read off the type itself.
            elif shape is not None and _type not in v1._SCALAR_TYPES:
                raise TypeError(f"Unsupported array type: {_type}")

            else:
                _field["type"] = _type

            return _field

        return dict(sorted(_map(field).items(), key=field_attr_sort_key))
