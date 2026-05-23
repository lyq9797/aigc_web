from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    token: str
    username: str


class DetectRequest(BaseModel):
    text: str = Field(min_length=1)


class HistoryItem(BaseModel):
    id: int
    input_text: str
    result: dict
    created_at: str
