from ast import literal_eval
from os import PathLike
from typing import Any
from warnings import warn

from boltons.dictutils import OMD

from modflow_devtools.dfn.schema.field import Field
from modflow_devtools.dfn.schema.ref import Ref
from modflow_devtools.dfn.schema.sln import Sln


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
    if k == "reader":
        return 4
    if k == "optional":
        return 5
    if k == "longname":
        return 6
    if k == "description":
        return 7
    return 8


def try_parse_bool(value: Any) -> Any:
    """
    Try to parse a boolean from a string as represented
    in a DFN file, otherwise return the value unaltered.
    """
    if isinstance(value, str):
        value = value.lower()
        if value in ["true", "false"]:
            return value == "true"
    return value


def try_parse_solution_package(meta: list[str]) -> Sln | None:
    sln = next(
        iter(
            m for m in meta if isinstance(m, str) and m.startswith("solution_package")
        ),
        None,
    )
    if sln:
        abbr, pattern = sln.split()[1:]
        return Sln(abbr=abbr, pattern=pattern)
    return None


def try_parse_package_reference(meta: list[str], fields: list[Field]) -> Ref | None:
    def _parent():
        line = next(
            iter(m for m in meta if isinstance(m, str) and m.startswith("parent")),
            None,
        )
        if not line:
            return None
        split = line.split()
        return split[1]

    def _rest():
        line = next(
            iter(m for m in meta if isinstance(m, str) and m.startswith("subpac")),
            None,
        )
        if not line:
            return None
        _, key, abbr, param, tgt = line.split()
        matches = [v for v in fields.values() if v["name"] == tgt]
        if not any(matches):
            descr = None
        else:
            if len(matches) > 1:
                warn(f"Multiple matches for referenced variable {tgt}")
            match = matches[0]
            descr = match["description"]

        return {
            "key": key,
            "tgt": tgt,
            "abbr": abbr,
            "param": param,
            "description": descr,
        }

    parent = _parent()
    rest = _rest()
    if parent and rest:
        return Ref(parent=parent, **rest)
    return None


def is_advanced_package(meta: list[str]) -> bool | None:
    return any("package-type advanced" in m for m in meta)


def is_multi_package(meta: list[str]) -> bool | None:
    return any("multi-package" in m for m in meta)


def parse_dfn(
    f: str | PathLike,
    common: dict | None = None,
) -> tuple[OMD, list[str]]:
    field = {}
    flat = []
    meta = []
    common = common or {}

    for line in f:
        # remove whitespace/etc from the line
        line = line.strip()

        # record context name and flopy metadata
        # attributes, skip all other comment lines
        if line.startswith("#"):
            _, sep, tail = line.partition("flopy")
            if sep == "flopy":
                if (
                    "multi-package" in tail
                    or "solution_package" in tail
                    or "subpackage" in tail
                    or "parent" in tail
                ):
                    meta.append(tail.strip())
            _, sep, tail = line.partition("package-type")
            if sep == "package-type":
                meta.append(f"package-type {tail.strip()}")
            continue

        # if we hit a newline and the parameter dict
        # is nonempty, we've reached the end of its
        # block of attributes
        if not any(line):
            if any(field):
                flat.append((field["name"], field))
                field = {}
            continue

        # split the attribute's key and value and
        # store it in the parameter dictionary
        key, _, value = line.partition(" ")
        if key == "default_value":
            key = "default"
        field[key] = value

        # make substitutions from common variable definitions,
        # remove backslashes, TODO: generate/insert citations.
        descr = field.get("description", None)
        if descr:
            descr = descr.replace("\\", "").replace("``", "'").replace("''", "'")
            _, replace, tail = descr.strip().partition("REPLACE")
            if replace:
                key, _, subs = tail.strip().partition(" ")
                subs = literal_eval(subs)
                cmmn = common.get(key, None)
                if cmmn is None:
                    warn(
                        "Can't substitute description text, "
                        f"common variable not found: {key}"
                    )
                else:
                    descr = cmmn.get("description", "")
                    if any(subs):
                        descr = descr.replace("\\", "").replace("{#1}", subs["{#1}"])
            field["description"] = descr

    # add the final parameter
    if any(field):
        flat.append((field["name"], field))

    # the point of the OMD is to losslessly handle duplicate variable names
    return OMD(flat), meta
