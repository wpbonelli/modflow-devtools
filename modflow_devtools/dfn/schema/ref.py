from typing import TypedDict


class Ref(TypedDict):
    """
    A foreign-key-like reference between a file input variable
    in a referring input component and another input component
    referenced by it.
    """

    key: str  # name of file path field in referring component
    tgt: str  # name of target component
