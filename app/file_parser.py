from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException, status

SUPPORTED_SUFFIXES = {".txt", ".docx", ".doc"}
SUPPORTED_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk")


def _raise_bad_request(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def _decode_text_bytes(raw: bytes) -> str:
    for encoding in SUPPORTED_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    _raise_bad_request("TXT 文件编码无法识别，请保存为 UTF-8 或 GBK")


def _extract_docx_text(raw: bytes) -> str:
    try:
        from docx import Document
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="缺少 docx 解析库") from exc

    document = Document(io.BytesIO(raw))
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    if paragraphs:
        return "\n".join(paragraphs)

    table_lines: list[str] = []
    for table in document.tables:
        for row in table.rows:
            row_texts = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if row_texts:
                table_lines.append("\t".join(row_texts))
    return "\n".join(table_lines)


def _extract_doc_text(raw: bytes) -> str:
    try:
        import pythoncom
        from win32com.client import DispatchEx
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="当前环境缺少 Word 组件，无法解析 .doc 文件，请先安装 Microsoft Word 或将文件另存为 .docx",
        ) from exc

    temp_path = None
    word_app = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".doc") as temp_file:
            temp_file.write(raw)
            temp_path = temp_file.name

        pythoncom.CoInitialize()
        word_app = DispatchEx("Word.Application")
        word_app.Visible = False
        word_app.DisplayAlerts = 0
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
        if word_app is not None:
            try:
                word_app.Quit()
            except Exception:
                pass
        if pythoncom is not None:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass


def extract_text_from_file(filename: str, raw: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        _raise_bad_request("仅支持 .txt、.docx、.doc 文件")

    if suffix == ".txt":
        return _decode_text_bytes(raw).strip()
    if suffix == ".docx":
        return _extract_docx_text(raw).strip()
    return _extract_doc_text(raw).strip()
