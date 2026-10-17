import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Bootstrap(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    tenant_name: str = Field(min_length=1, max_length=200)


class Refresh(BaseModel):
    refresh_token: str = Field(min_length=32, max_length=128)


class Tokens(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    status: str


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    status: str
