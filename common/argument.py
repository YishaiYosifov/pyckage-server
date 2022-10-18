from pydantic import BaseModel
from typing import Any

ITER_STRUCTURE_REPLACES = {
    "',": "':",
    "((": "(",
    "))": ")",
    "),)": ")",
    "), (": ", ",
    "<class ": "",
    ">": ""
}

class Argument(BaseModel):
    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

        if self.iter_structure is not None:
            self.iter_structure_str = str(self.iter_structure)
            for text, replace in ITER_STRUCTURE_REPLACES.items(): self.iter_structure_str = self.iter_structure_str.replace(text, replace)

    type : Any
    required : bool = True

    max_length : int = None
    min_length : int = None

    iter_structure : list | dict = None
    iter_structure_str : str = None