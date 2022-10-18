from pydantic import BaseModel

class AccessToken(BaseModel):
    id : int = None
    user_id : int

    token_hash : str

    ip : str
    user_agent : str
    created : int