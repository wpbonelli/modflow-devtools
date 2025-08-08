from typing import TypedDict


class Sln(TypedDict):
    """
    MODFLOW 6 solution package metadata. Describes which kinds
    of models this solution applies to.
    """

    models: list[str]  # list of model types this solution applies to
