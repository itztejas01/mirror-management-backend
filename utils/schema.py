from pydantic import BaseModel


class UserLoginSchema(BaseModel):
    email: str
    password: str


class UserSchema(BaseModel):
    id: str
    email: str
    name: str
    role: str
    created_at: str
    updated_at: str
