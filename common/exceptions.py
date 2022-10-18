from __future__ import annotations

class InvalidArgument(Exception):
    def __init__(self, error, code):
        """
        Couldn't get an argument from the user input
        """
        super().__init__(error, code)

class InvalidData(Exception):
    def __init__(self, error, code):
        """
        The given data is not valid
        """
        super().__init__(error, code)