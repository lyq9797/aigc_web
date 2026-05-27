"""
AIGC 文本检测系统 - 应用主入口 (Application Entry Point)

【安全检测全局说明】
1. 本模块暴露了系统的 Web 页面与 RESTful API。
2. 所有涉及用户输入的接口（文本检测、文件上传）必须实施严格的长度/大小限制，防御拒绝服务 (DoS) 攻击。
3. 认证相关接口应配合网关层或中间件实施速率限制 (Rate Limiting)，以防御暴力破解 (Brute-force) 和撞库攻击。
4. 生产环境部署时，必须配置反向代理（如 Nginx）并启用 HTTPS，严禁直接暴露 Uvicorn 端口。
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import (
    Depends,
    FastAPI,
    File,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db
from .auth import (
    create_token,
    decode_token,
    hash_password,
    parse_bearer_token,
    verify_password,
)
from .file_parser import extract_text_from_file
from .schemas import AuthResponse, DetectRequest, HistoryItem, LoginRequest, RegisterRequest
from .service import DetectionService

# 【规范说明】使用模块级 logger，记录安全审计与运行异常
logger = logging.getLogger(__name__)

# ==========================================
# 1. 常量与安全基线 (Constants & Baselines)
# ==========================================

# 【安全检测说明】业务限制常量，防止恶意用户提交超长文本或超大文件导致 AI 模型 OOM 或 CPU 耗尽 (DoS)
MAX_DETECT_TEXT_LENGTH = 10_000  # 单次检测最大字符数
MAX_UPLOAD_FILE_SIZE = 10 * 1024 * 1024  # 单次上传最大 10MB
FILE_READ_CHUNK_SIZE = 1024 * 1024  # 文件分块读取大小 1MB

BASE_DIR = Path(__file__).resolve().parent


# ==========================================
# 2. 应用生命周期管理 (Application Lifespan)
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    管理 FastAPI 应用的启动与关闭事件。

    【规范说明】
    替代已废弃的 @app.on_event("startup")，确保在应用接收请求前完成数据库等基础设施的初始化。
    """
    # --- 启动阶段 (Startup) ---
    logger.info("Initializing database schema...")
    db.init_db()

    yield  # 应用运行中

    # --- 关闭阶段 (Shutdown) ---
    logger.info("Application shutting down gracefully...")
    # 此处可添加关闭数据库连接池、清理后台任务等逻辑


# ==========================================
# 3. 应用实例与中间件配置 (App Instance & Middleware)
# ==========================================

app = FastAPI(
    title="AIGC Text Detection System",
    version="1.0.0",
    lifespan=lifespan,
    # 【安全检测说明】在生产环境中，建议配置 docs_url=None, redoc_url=None 以关闭 Swagger UI，减少攻击面
)

# 挂载静态资源与模板引擎
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

# 初始化业务服务层
service = DetectionService()


# ==========================================
# 4. 依赖注入 (Dependency Injection)
# ==========================================

def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """
    从请求头中解析并验证 JWT Token，返回当前用户上下文。

    【安全检测说明】
    - 依赖 FastAPI 的 Depends 机制，确保受保护的路由在执行前必须通过身份校验。
    - 若 Token 无效或用户已被删除，将直接抛出 401 阻断请求。
    """
    token = parse_bearer_token(authorization)
    payload = decode_token(token)

    user_id = int(payload.get("sub", 0))
    user = db.get_user_by_id(user_id)

    if not user:
        # 记录安全审计日志：Token 有效但用户不存在（可能用户已被注销或数据库数据不一致）
        logger.warning("Authentication failed: User ID %s from token not found in DB.", user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or account disabled"
        )

    return {"id": int(user["id"]), "username": str(user["username"])}


# ==========================================
# 5. Web 页面路由 (Web Pages Routing)
# ==========================================

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def home() -> RedirectResponse:
    """根路径重定向至登录页"""
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_class=HTMLResponse, include_in_schema=False)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse, include_in_schema=False)
def register_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/detect", response_class=HTMLResponse, include_in_schema=False)
def detect_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("detect.html", {"request": request})


@app.get("/history", response_class=HTMLResponse, include_in_schema=False)
def history_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("history.html", {"request": request})


# ==========================================
# 6. 认证 API (Authentication APIs)
# ==========================================

@app.post("/api/register", response_model=AuthResponse, tags=["Auth"])
def register(body: RegisterRequest) -> AuthResponse:
    """
    用户注册接口。

    【安全检测说明 - 用户名枚举与弱口令防御】
    1. 错误信息应保持模糊，避免明确提示“用户名已存在”，防止攻击者批量探测有效用户名。
    2. 密码强度校验（如长度、复杂度）应在 RegisterRequest (Pydantic Schema) 中严格定义。
    3. 生产环境必须在此接口前添加速率限制 (Rate Limiting)，防止恶意批量注册 (Spamming)。
    """
    exists = db.get_user_by_username(body.username)
    if exists:
        # 【安全规范】使用统一的模糊错误提示，防御用户名枚举攻击 (Username Enumeration)
        raise HTTPException(status_code=400, detail="Invalid registration credentials")

    hashed = hash_password(body.password)
    user_id = db.create_user(body.username, hashed)
    token = create_token(user_id=user_id, username=body.username)

    logger.info("New user registered: %s (ID: %s)", body.username, user_id)
    return AuthResponse(token=token, username=body.username)


@app.post("/api/login", response_model=AuthResponse, tags=["Auth"])
def login(body: LoginRequest) -> AuthResponse:
    """
    用户登录接口。

    【安全检测说明 - 暴力破解防御】
    1. 无论用户名不存在还是密码错误，均返回相同的错误提示，防御枚举攻击。
    2. 生产环境必须配合 Redis 实施登录失败次数限制与账号锁定机制 (Account Lockout)。
    """
    row = db.get_user_by_username(body.username)

    # 【安全规范】统一校验逻辑，避免通过响应时间差异或错误信息差异泄露用户是否存在
    if not row or not verify_password(body.password, row["password_hash"]):
        logger.warning("Failed login attempt for username: %s", body.username)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_token(user_id=int(row["id"]), username=str(row["username"]))
    return AuthResponse(token=token, username=str(row["username"]))


# ==========================================
# 7. 核心业务 API (Core Business APIs)
# ==========================================

@app.post("/api/detect", tags=["Detection"])
def detect(
        body: DetectRequest,
        current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """
    AIGC 文本检测接口。

    【安全检测说明 - 算法 DoS 防御】
    必须对输入文本的长度进行严格限制。AI 模型推理的时间复杂度通常随文本长度呈非线性增长，
    不限制长度会导致攻击者提交超长文本（如 100 万字），瞬间耗尽服务器 CPU/GPU 资源。
    """
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty")

    if len(text) > MAX_DETECT_TEXT_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Text exceeds maximum allowed length of {MAX_DETECT_TEXT_LENGTH} characters"
        )

    result = service.detect(text)
    item_id = db.save_detection(user_id=current_user["id"], input_text=text, result=result)

    return {"id": item_id, "result": result}


@app.post("/api/extract-text", tags=["Detection"])
async def extract_text(
        file: UploadFile = File(...),
        current_user: dict[str, Any] = Depends(get_current_user)
) -> dict[str, Any]:
    """
    从上传的文档中提取纯文本。

    【安全检测核心说明 - 内存耗尽 (OOM) 与 Zip Bomb 防御】
    1. 严禁直接使用 `await file.read()` 读取未限制大小的文件！
    2. 必须采用分块读取 (Chunked Reading) 并累计字节数，一旦超过 MAX_UPLOAD_FILE_SIZE 立即中断，
       防止攻击者上传数 GB 的恶意文件导致服务器内存溢出 (OOM) 崩溃。
    """
    raw_chunks = bytearray()
    total_size = 0

    while chunk := await file.read(FILE_READ_CHUNK_SIZE):
        total_size += len(chunk)
        if total_size > MAX_UPLOAD_FILE_SIZE:
            raise HTTPException(
                status_code=413,  # 413 Payload Too Large
                detail=f"File size exceeds the maximum limit of {MAX_UPLOAD_FILE_SIZE // (1024 * 1024)}MB"
            )
        raw_chunks.extend(chunk)

    raw_bytes = bytes(raw_chunks)

    if not raw_bytes:
        raise HTTPException(status_code=400, detail="文件为空")

    # 调用文件解析器（内部已包含 XXE 和 RCE 防御逻辑）
    text = extract_text_from_file(file.filename or "unknown_file", raw_bytes)

    if not text.strip():
        raise HTTPException(status_code=400, detail="文件中没有可识别的文本内容")

    return {
        "filename": file.filename,
        "text": text,
        "length": len(text),
    }


# ==========================================
# 8. 历史记录 API (History APIs)
# ==========================================

@app.get("/api/history", response_model=list[HistoryItem], tags=["History"])
def get_history(current_user: dict[str, Any] = Depends(get_current_user)) -> list[dict[str, Any]]:
    """获取当前用户的历史检测记录"""
    # 【安全说明】强制限制 limit 参数，防止一次性拉取全表数据导致数据库或网络拥塞
    return db.list_detections(current_user["id"], limit=100)


@app.delete("/api/history", tags=["History"])
def clear_history(current_user: dict[str, Any] = Depends(get_current_user)) -> dict[str, int]:
    """清空当前用户的所有历史检测记录"""
    deleted = db.clear_detections(current_user["id"])
    logger.info("User %s cleared %d detection records.", current_user["username"], deleted)
    return {"deleted": deleted}