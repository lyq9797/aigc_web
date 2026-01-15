from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db
from .auth import create_token, decode_token, hash_password, parse_bearer_token, verify_password
from .file_parser import extract_text_from_file
from .schemas import AuthResponse, DetectRequest, HistoryItem, LoginRequest, RegisterRequest
from .service import DetectionService

app = FastAPI(title="AIGC Text Detection System", version="1.0.0")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

service = DetectionService()


@app.on_event("startup")
def startup_event() -> None:
    db.init_db()


def get_current_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    token = parse_bearer_token(authorization)
    payload = decode_token(token)
    user = db.get_user_by_id(int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return {"id": int(user["id"]), "username": str(user["username"])}


@app.get("/", response_class=HTMLResponse)
def home() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})


@app.get("/detect", response_class=HTMLResponse)
def detect_page(request: Request):
    return templates.TemplateResponse("detect.html", {"request": request})


@app.get("/history", response_class=HTMLResponse)
def history_page(request: Request):
    return templates.TemplateResponse("history.html", {"request": request})


@app.post("/api/register", response_model=AuthResponse)
def register(body: RegisterRequest):
    exists = db.get_user_by_username(body.username)
    if exists:
        raise HTTPException(status_code=400, detail="Username already exists")

    hashed = hash_password(body.password)
    user_id = db.create_user(body.username, hashed)
    token = create_token(user_id=user_id, username=body.username)
    return AuthResponse(token=token, username=body.username)


@app.post("/api/login", response_model=AuthResponse)
def login(body: LoginRequest):
    row = db.get_user_by_username(body.username)
    if not row or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_token(user_id=int(row["id"]), username=str(row["username"]))
    return AuthResponse(token=token, username=str(row["username"]))


@app.post("/api/detect")
def detect(body: DetectRequest, current_user: dict[str, Any] = Depends(get_current_user)):
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Text is empty")

    result = service.detect(text)
    item_id = db.save_detection(user_id=current_user["id"], input_text=text, result=result)
    return {"id": item_id, "result": result}


@app.post("/api/extract-text")
async def extract_text(file: UploadFile = File(...), current_user: dict[str, Any] = Depends(get_current_user)):
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


@app.get("/api/history", response_model=list[HistoryItem])
def history(current_user: dict[str, Any] = Depends(get_current_user)):
    return db.list_detections(current_user["id"], limit=100)


@app.delete("/api/history")
def clear_history(current_user: dict[str, Any] = Depends(get_current_user)):
    deleted = db.clear_detections(current_user["id"])
    return {"deleted": deleted}
