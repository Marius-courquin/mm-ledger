from pydantic import BaseModel, Field

class PasswordRequest(BaseModel):
    password: str = Field(..., min_length=1, repr=False)

class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, repr=False)
    new_password: str = Field(..., min_length=1, repr=False)

class VaultStatusResponse(BaseModel):
    state: str

class VaultActionResponse(BaseModel):
    status: str
