from pydantic import BaseModel, Field


class BaseSchema(BaseModel):
    class Config:
        anystr_strip_whitespace = True
        orm_mode = True
        extra = "forbid"


class RegisterRequest(BaseSchema):
    username: str = Field(..., min_length=3, max_length=50, description="用户名，3-50 字符")
    password: str = Field(..., min_length=6, max_length=128, description="密码，6-128 字符")


class LoginRequest(BaseSchema):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class AuthResponse(BaseSchema):
    token: str = Field(..., description="JWT 访问令牌")
    username: str = Field(..., description="登录用户名")


class DetectRequest(BaseSchema):
    text: str = Field(..., min_length=1, description="待检测文本")


class HistoryItem(BaseSchema):
    id: int
    input_text: str
    result: dict
    created_at: str
