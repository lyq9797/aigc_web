from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.exceptions import RequestValidationError

from . import db
from .auth import create_token, decode_token, hash_password, parse_bearer_token, verify_password
from .file_parser import extract_text_from_file
from .schemas import AuthResponse, DetectRequest, HistoryItem, LoginRequest, RegisterRequest
from .service import DetectionService

# =========================
# Application Initialization
# =========================

app = FastAPI(title="AIGC Text Detection System", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

service = DetectionService()


# =========================
# Template Helper
# =========================

def render_page(template_name: str, request: Request) -> HTMLResponse:
    """渲染HTML模板"""
    return templates.TemplateResponse(template_name, {"request": request})


# =========================
# Lifecycle Events
# =========================

@app.on_event("startup")
def startup_event() -> None:
    """应用启动时初始化数据库"""
    db.init_db()


# =========================
# Exception Handlers
# =========================

@app.exception_handler(HTTPException)
def http_exception_handler(request, exc: HTTPException):
    """HTTP异常处理器"""
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
def validation_exception_handler(request, exc: RequestValidationError):
    """请求参数校验异常处理器"""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()}
    )


# =========================
# Dependencies
# =========================

def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """获取当前登录用户信息"""
    token = parse_bearer_token(authorization)
    payload = decode_token(token)
    user = db.get_user_by_id(int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return {"id": int(user["id"]), "username": str(user["username"])}


def get_service() -> DetectionService:
    """获取检测服务实例"""
    return service


# =========================
# Page Routes (HTML)
# =========================

@app.get("/", response_class=HTMLResponse)
def home() -> RedirectResponse:
    """首页重定向到登录页"""
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    """登录页面"""
    return render_page("login.html", request)


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request) -> HTMLResponse:
    """注册页面"""
    return render_page("register.html", request)


@app.get("/detect", response_class=HTMLResponse)
def detect_page(request: Request) -> HTMLResponse:
    """检测页面"""
    return render_page("detect.html", request)


@app.get("/history", response_class=HTMLResponse)
def history_page(request: Request) -> HTMLResponse:
    """历史记录页面"""
    return render_page("history.html", request)


# =========================
# API Routes - Auth
# =========================

@app.post("/api/register", response_model=AuthResponse)
def register(body: RegisterRequest):
    """用户注册"""
    if db.get_user_by_username(body.username):
        raise HTTPException(status_code=400, detail="Username already exists")

    hashed = hash_password(body.password)
    user_id = db.create_user(body.username, hashed)
    return AuthResponse(
        token=create_token(user_id=user_id, username=body.username),
        username=body.username
    )


@app.post("/api/login", response_model=AuthResponse)
def login(body: LoginRequest):
    """用户登录"""
    row = db.get_user_by_username(body.username)
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return AuthResponse(
        token=create_token(user_id=int(row["id"]), username=str(row["username"])),
        username=str(row["username"])
    )


# =========================
# API Routes - Detection
# =========================

@app.post("/api/detect")
def detect(
        body: DetectRequest,
        current_user: dict[str, Any] = Depends(get_current_user),
        service_obj: DetectionService = Depends(get_service)
):
    """执行文本检测"""
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty")

    result = service_obj.detect(text)
    item_id = db.save_detection(
        user_id=current_user["id"],
        input_text=text,
        result=result
    )
    return {"id": item_id, "result": result}


@app.post("/api/extract-text")
async def extract_text(
        file: UploadFile = File(...),
        current_user: dict[str, Any] = Depends(get_current_user)
):
    """从上传文件中提取文本"""
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="文件为空")

    text = extract_text_from_file(file.filename or "", raw)
    if not text.strip():
        raise HTTPException(status_code=400, detail="文件中没有可识别的文本内容")

    return {
        "filename": file.filename,
        "text": text,
        "length": len(text),
    }


# =========================
# API Routes - History
# =========================

@app.get("/api/history", response_model=list[HistoryItem])
def history(current_user: dict[str, Any] = Depends(get_current_user)):
    """获取检测历史记录"""
    return db.list_detections(current_user["id"], limit=100)


@app.delete("/api/history")
def clear_history(current_user: dict[str, Any] = Depends(get_current_user)):
    """清空检测历史记录"""
    deleted = db.clear_detections(current_user["id"])
    return {"deleted": deleted}