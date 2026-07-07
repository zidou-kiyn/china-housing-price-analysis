from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    is_active: bool

    model_config = {"from_attributes": True}


class UserAdminOut(UserOut):
    created_at: datetime


class UserListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[UserAdminOut]


class RoleUpdateRequest(BaseModel):
    role: str = Field(pattern="^(user|admin)$")
