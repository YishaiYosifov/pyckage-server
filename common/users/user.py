from pydantic import BaseModel

class User(BaseModel):
    id : int
    username : str
    hash : str
    salt : bytes

class UserBy:
    USERNAME = "username"
    ID = "id"