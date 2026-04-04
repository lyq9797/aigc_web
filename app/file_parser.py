from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

from fastapi import HTTPException, status

# =========================
# Constants
# =========================

SUPPORTED_SUFFIXES = {".txt", ".docx", ".doc"}
SUPPORTED_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


# =========================
# Exception Helper
# =========================

def _raise_bad_request(detail: str) -> None:
    """抛出400错误响应"""
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


# =========================
# Text Decoding
# =========================

def _decode_text_bytes(raw: bytes) -> str:
    """尝试多种编码解码文本，全部失败则报错"""
    for encoding in SUPPORTED_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    _raise_bad_request("TXT 文件编码无法识别，请保存为 UTF-8 或 GBK")


# =========================
# DOCX Parser
# =========================

def _extract_docx_text(raw: bytes) -> str:
    """从docx文件提取文本，优先段落后表格"""
    try:
        from docx import Document
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="缺少 python-docx 库，请安装: pip install python-docx"
        ) from exc

    document = Document(io.BytesIO(raw))

    # 提取段落文本
    paragraphs = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    if paragraphs:
        return "\n".join(paragraphs)

    # 提取表格文本
    table_lines = []
    for table in document.tables:
        for row in table.rows:
            row_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if row_texts:
                table_lines.append("\t".join(row_texts))
    return "\n".join(table_lines)


# =========================
# DOC Parser (Windows only)
# =========================

def _extract_doc_text(raw: bytes) -> str:
    """从.doc文件提取文本（依赖Windows Word组件）"""
    try:
        import pythoncom
        from win32com.client import DispatchEx
    except ImportError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="解析 .doc 文件需要安装 pywin32: pip install pywin32"
        ) from exc

    temp_path = None
    word_app = None

    try:
        # 写入临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=".doc") as tmp:
            tmp.write(raw)
            temp_path = tmp.name

        # 启动Word应用
        pythoncom.CoInitialize()
        word_app = DispatchEx("Word.Application")
        word_app.Visible = False
        word_app.DisplayAlerts = 0

        # 打开并读取文档
        doc = word_app.Documents.Open(temp_path, ReadOnly=1)
        try:
            return doc.Content.Text.strip()
        finally:
            doc.Close(False)

    except HTTPException:
        raise
    except Exception as exc:
        _raise_bad_request(f".doc 文件解析失败: {exc}")
    finally:
        # 清理Word进程
        if word_app:
            try:
                word_app.Quit()
            except Exception:
                pass
        # 清理COM线程
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
        # 删除临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


# =========================
# Public API
# =========================

def extract_text_from_file(filename: str, raw: bytes) -> str:
    """
    从上传文件中提取纯文本

    Args:
        filename: 原始文件名
        raw: 文件二进制内容

    Returns:
        提取的文本内容
    """
    # 文件大小校验
    if len(raw) > MAX_FILE_SIZE:
        _raise_bad_request(f"文件过大，最大支持 {MAX_FILE_SIZE // 1024 // 1024}MB")

    # 文件类型校验
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        _raise_bad_request(f"不支持的文件类型，仅支持 {', '.join(SUPPORTED_SUFFIXES)}")

    # 根据类型调用对应解析器
    if suffix == ".txt":
        return _decode_text_bytes(raw).strip()
    if suffix == ".docx":
        return _extract_docx_text(raw).strip()
    return _extract_doc_text(raw).strip()