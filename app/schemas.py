from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


# =========================
# Base Schema
# =========================

class BaseSchema(BaseModel):
    """基础Schema，定义通用配置"""

    class Config:
        anystr_strip_whitespace = True  # 自动去除字符串首尾空白
        orm_mode = True  # 支持ORM对象转换
        extra = "forbid"  # 禁止额外字段
        json_encoders = {
            datetime: lambda v: v.isoformat()  # datetime自动转ISO格式
        }


# =========================
# Request Schemas
# =========================

class RegisterRequest(BaseSchema):
    """注册请求"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名，3-50 字符")
    password: str = Field(..., min_length=6, max_length=128, description="密码，6-128 字符")
    email: Optional[str] = Field(None, max_length=100, description="邮箱（可选）")


class LoginRequest(BaseSchema):
    """登录请求"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    remember_me: bool = Field(False, description="记住我")


class DetectRequest(BaseSchema):
    """检测请求"""
    text: str = Field(..., min_length=1, max_length=10000, description="待检测文本，最长10000字符")
    model_type: Optional[str] = Field("default", description="模型类型：default/fast/accurate")


class BatchDetectRequest(BaseSchema):
    """批量检测请求"""
    texts: List[str] = Field(..., min_items=1, max_items=50, description="待检测文本列表，最多50条")


# =========================
# Response Schemas
# =========================

class AuthResponse(BaseSchema):
    """认证响应"""
    token: str = Field(..., description="JWT 访问令牌")
    username: str = Field(..., description="登录用户名")
    expires_in: int = Field(..., description="Token过期时间（秒）")


class WordResult(BaseSchema):
    """单词级检测结果"""
    token: str = Field(..., description="单词内容")
    label: str = Field(..., description="标签：AIGT/HWT")
    label_id: int = Field(..., description="标签ID：1=AIGT, 0=HWT")
    position: int = Field(..., description="单词在文本中的位置")


class SentenceResult(BaseSchema):
    """句子级检测结果"""
    index: int = Field(..., description="句子序号")
    text: str = Field(..., description="句子内容")
    label: str = Field(..., description="标签：AIGT/HWT")
    confidence: float = Field(..., ge=0, le=1, description="置信度 0-1")


class DetectSummary(BaseSchema):
    """检测摘要"""
    word_model: str = Field(..., description="词模型类型")
    sentence_model: str = Field(..., description="句模型类型")
    switch_word_index: int = Field(..., description="切换词位置")
    switch_sentence_index: int = Field(..., description="切换句位置")
    fallback_used: bool = Field(..., description="是否使用降级模型")
    processing_time_ms: Optional[float] = Field(None, description="处理耗时（毫秒）")


class DetectResponse(BaseSchema):
    """检测响应"""
    id: int = Field(..., description="记录ID")
    result: dict = Field(..., description="检测结果")
    summary: Optional[DetectSummary] = Field(None, description="检测摘要")


class HistoryItem(BaseSchema):
    """历史记录项"""
    id: int
    input_text: str
    result: dict
    created_at: str
    text_length: Optional[int] = Field(None, description="文本长度")
    word_count: Optional[int] = Field(None, description="单词数量")


class HistoryListResponse(BaseSchema):
    """历史记录列表响应"""
    total: int = Field(..., description="总记录数")
    items: List[HistoryItem] = Field(..., description="历史记录列表")
    page: int = Field(1, description="当前页码")
    page_size: int = Field(50, description="每页数量")


class ExtractTextResponse(BaseSchema):
    """文本提取响应"""
    filename: str = Field(..., description="原始文件名")
    text: str = Field(..., description="提取的文本内容")
    length: int = Field(..., description="文本长度")
    word_count: int = Field(..., description="单词数量")


class ClearHistoryResponse(BaseSchema):
    """清空历史响应"""
    deleted: int = Field(..., description="删除的记录数")
    message: str = Field("success", description="操作结果")


class PaginationParams(BaseSchema):
    """分页参数"""
    page: int = Field(1, ge=1, description="页码，从1开始")
    page_size: int = Field(20, ge=1, le=100, description="每页数量")


# =========================
# Error Schemas
# =========================

class ErrorResponse(BaseSchema):
    """错误响应"""
    detail: str = Field(..., description="错误详情")
    code: Optional[str] = Field(None, description="错误码")
    timestamp: datetime = Field(default_factory=datetime.now, description="错误发生时间")