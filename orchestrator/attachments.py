"""
orchestrator/attachments.py
───────────────────────────
Pipeline for attachment classification, inspection, extraction, and normalization.

Features:
  - Explicit categories: image, pdf, text, code, unsupported
  - PDF inspection via PyMuPDF:
      * Selectable text extraction for text PDFs
      * Page rendering to PNG images for scanned/image PDFs
      * Page count & size limiting for security & memory protection
  - Safe sanitization of filenames to prevent directory traversal
  - Request modality & capability deduction
  - Keeps binary data isolated from DB persistence
"""

from __future__ import annotations

import base64
import logging
import os
import re
from typing import List, Optional, Tuple

from orchestrator.schemas import Attachment, AttachmentKind, AttachmentInfo

logger = logging.getLogger(__name__)

# ── Security & Resource Limits ────────────────────────────────────────────────
MAX_ATTACHMENT_SIZE_BYTES = 20 * 1024 * 1024   # 20 MB max file size
MAX_PAGES_TO_PROCESS = 10                       # Process up to 10 pages per PDF
MAX_TEXT_EXTRACTION_CHARS = 100_000             # Truncate text extraction if huge
PDF_RENDER_DPI = 120                            # Crisp rendering for vision models

# ── Known File Types ──────────────────────────────────────────────────────────
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}
IMAGE_MIME_PREFIX = "image/"

PDF_EXTENSIONS = {".pdf"}
PDF_MIMES = {"application/pdf", "application/x-pdf"}

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".tsv", ".log", ".rtf"}
TEXT_MIMES = {"text/plain", "text/markdown", "text/csv", "text/tab-separated-values"}

CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".html", ".htm", ".css",
    ".rs", ".go", ".java", ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp",
    ".sql", ".sh", ".bash", ".ps1", ".yaml", ".yml", ".xml", ".ini", ".toml",
}
CODE_MIMES = {
    "application/json", "application/xml", "application/javascript",
    "text/javascript", "text/x-python", "application/x-python-code",
    "text/css", "text/html", "text/x-c", "text/x-c++", "text/x-java-source",
    "text/x-rust", "text/x-go", "text/x-shellscript", "application/x-sh",
}


def sanitize_filename(filename: Optional[str]) -> str:
    """Sanitize filename to prevent directory traversal or invalid characters."""
    if not filename:
        return "attachment"
    # Take only the base name (strips path components like ../ or C:\)
    base = os.path.basename(filename).strip()
    # Remove control characters and non-printable characters
    base = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", base)
    return base or "attachment"


def categorize_attachment(
    filename: str,
    content_type: Optional[str] = None,
) -> Tuple[AttachmentKind, str]:
    """
    Determine AttachmentKind and normalized MIME type based on content-type and extension.
    Fallback to extension if content-type is generic (e.g. application/octet-stream).
    """
    cleaned_name = sanitize_filename(filename).lower()
    _, ext = os.path.splitext(cleaned_name)
    ct = (content_type or "").lower().strip()

    # 1. Images
    if ct.startswith(IMAGE_MIME_PREFIX) or ext in IMAGE_EXTENSIONS:
        norm_mime = ct if ct.startswith(IMAGE_MIME_PREFIX) else (
            "image/png" if ext == ".png" else
            "image/jpeg" if ext in (".jpg", ".jpeg") else
            "image/webp" if ext == ".webp" else
            "image/gif" if ext == ".gif" else "image/png"
        )
        return AttachmentKind.IMAGE, norm_mime

    # 2. PDF
    if ct in PDF_MIMES or ext in PDF_EXTENSIONS:
        return AttachmentKind.PDF, "application/pdf"

    # 3. Code files
    if ext in CODE_EXTENSIONS or ct in CODE_MIMES:
        norm_mime = ct if ct in CODE_MIMES else (
            "application/json" if ext == ".json" else
            "text/x-python" if ext == ".py" else
            "text/javascript" if ext in (".js", ".jsx") else
            "text/plain"
        )
        return AttachmentKind.CODE, norm_mime

    # 4. Text files
    if ct.startswith("text/") or ext in TEXT_EXTENSIONS:
        norm_mime = ct if ct in TEXT_MIMES else "text/plain"
        return AttachmentKind.TEXT, norm_mime

    # 5. Unsupported
    return AttachmentKind.UNSUPPORTED, ct or "application/octet-stream"


def inspect_and_process_pdf(
    file_bytes: bytes,
    filename: str,
) -> Attachment:
    """
    Inspect PDF document structure:
      - Determine page count
      - Extract selectable text
      - Identify if PDF contains raster images or scanned content
      - If image-based or no/low text: render page(s) to PNG images for vision analysis
      - If selectable text: normalize as document text
    """
    import pymupdf

    try:
        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    except Exception as exc:
        logger.warning("Failed to parse PDF '%s': %s", filename, exc)
        raise ValueError(f"Corrupted or invalid PDF file '{filename}': {exc}")

    total_pages = len(doc)
    pages_to_process = min(total_pages, MAX_PAGES_TO_PROCESS)

    extracted_pages = []
    has_raster_images = False
    total_text_len = 0

    for idx in range(pages_to_process):
        page = doc[idx]
        text = page.get_text().strip()
        if text:
            extracted_pages.append(f"--- Page {idx + 1} ---\n{text}")
            total_text_len += len(text)
        images = page.get_images()
        if images:
            has_raster_images = True

    # Image/Scanned detection:
    # If the document has minimal text (< 50 chars) or has images with low text (< 150 chars),
    # it is considered visual/scanned/poster and requires page rendering.
    is_visual_pdf = (total_text_len < 50) or (has_raster_images and total_text_len < 150)

    rendered_pages = []
    if is_visual_pdf:
        # Render pages to PNG images for multimodal vision models
        for idx in range(pages_to_process):
            page = doc[idx]
            pix = page.get_pixmap(dpi=PDF_RENDER_DPI)
            png_bytes = pix.tobytes("png")
            b64_png = base64.b64encode(png_bytes).decode("ascii")
            rendered_pages.append(b64_png)

    full_extracted_text = "\n\n".join(extracted_pages).strip()
    if len(full_extracted_text) > MAX_TEXT_EXTRACTION_CHARS:
        full_extracted_text = full_extracted_text[:MAX_TEXT_EXTRACTION_CHARS] + "\n...[truncated]"

    b64_raw = base64.b64encode(file_bytes).decode("ascii")

    logger.info(
        "Inspected PDF '%s': pages=%d processed=%d text_len=%d visual=%s rendered_pages=%d",
        filename, total_pages, pages_to_process, total_text_len, is_visual_pdf, len(rendered_pages),
    )

    return Attachment(
        filename=filename,
        content_type="application/pdf",
        data_base64=b64_raw,
        size_bytes=len(file_bytes),
        kind=AttachmentKind.PDF,
        extracted_text=full_extracted_text if full_extracted_text else None,
        rendered_pages=rendered_pages,
        page_count=total_pages,
        has_visual_content=is_visual_pdf,
    )


def process_attachment_bytes(
    filename: str,
    content_type: str,
    file_bytes: bytes,
) -> Attachment:
    """
    Validate, categorize, and process an attachment from raw bytes.
    Raises ValueError with a user-friendly message for unsupported or oversized files.
    """
    clean_name = sanitize_filename(filename)

    if len(file_bytes) > MAX_ATTACHMENT_SIZE_BYTES:
        max_mb = MAX_ATTACHMENT_SIZE_BYTES // (1024 * 1024)
        raise ValueError(
            f"Attachment '{clean_name}' ({len(file_bytes)} bytes) exceeds the maximum allowed size of {max_mb} MB."
        )

    kind, norm_mime = categorize_attachment(clean_name, content_type)

    if kind == AttachmentKind.UNSUPPORTED:
        raise ValueError(
            f"Unsupported file format for '{clean_name}' (type: {content_type or 'unknown'}). "
            "Supported formats: Images (PNG, JPG, WEBP, GIF), PDF, Text (TXT, MD, CSV), and Code files (PY, JS, TS, JSON, etc.)."
        )

    if kind == AttachmentKind.IMAGE:
        b64 = base64.b64encode(file_bytes).decode("ascii")
        return Attachment(
            filename=clean_name,
            content_type=norm_mime,
            data_base64=b64,
            size_bytes=len(file_bytes),
            kind=AttachmentKind.IMAGE,
            has_visual_content=True,
        )

    if kind == AttachmentKind.PDF:
        return inspect_and_process_pdf(file_bytes, clean_name)

    if kind in (AttachmentKind.TEXT, AttachmentKind.CODE):
        b64 = base64.b64encode(file_bytes).decode("ascii")
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1", errors="replace")

        if len(text) > MAX_TEXT_EXTRACTION_CHARS:
            text = text[:MAX_TEXT_EXTRACTION_CHARS] + "\n...[truncated]"

        return Attachment(
            filename=clean_name,
            content_type=norm_mime,
            data_base64=b64,
            size_bytes=len(file_bytes),
            kind=kind,
            extracted_text=text,
            has_visual_content=False,
        )

    # Fallback
    raise ValueError(f"Unable to process attachment '{clean_name}'.")


def normalize_attachment(att: Attachment) -> Attachment:
    """
    Ensure an Attachment instance is fully processed and populated.
    Decodes base64 data if kind is not yet determined or if processing is pending.
    """
    # If already fully categorized and processed, return as is
    if att.kind != AttachmentKind.UNSUPPORTED and (
        att.has_visual_content or att.extracted_text or att.kind == AttachmentKind.IMAGE
    ):
        return att

    clean_name = sanitize_filename(att.filename)
    kind, norm_mime = categorize_attachment(clean_name, att.content_type)

    if kind == AttachmentKind.UNSUPPORTED:
        raise ValueError(
            f"Unsupported file format for '{clean_name}'. "
            "Supported formats: Images (PNG, JPG, WEBP, GIF), PDF, Text (TXT, MD, CSV), and Code files."
        )

    if not att.data_base64:
        raise ValueError(f"Attachment '{clean_name}' contains no data.")

    file_bytes = base64.b64decode(att.data_base64)
    return process_attachment_bytes(clean_name, norm_mime, file_bytes)


def normalize_request(
    query: str,
    attachments: List[Attachment],
) -> Tuple[List[str], List[str]]:
    """
    Deduce normalized input modalities and required capabilities based on query and attachments.

    Rules:
      - Text only: modalities=["text"], capabilities=[]
      - Image: modalities=["text", "image"], capabilities=["vision"]
      - PDF with text: modalities=["text", "document"], capabilities=[]
      - Scanned/image PDF: modalities=["text", "document", "image"], capabilities=["vision"]
      - Code attachment: modalities=["text", "document", "code"], capabilities=["coding"] (or text)
    """
    modalities = ["text"]
    required_caps = []

    for att in attachments:
        if att.kind == AttachmentKind.IMAGE or getattr(att, "content_type", "").startswith("image/"):
            if "image" not in modalities:
                modalities.append("image")
            if "vision" not in required_caps:
                required_caps.append("vision")

        elif att.kind == AttachmentKind.PDF:
            if "document" not in modalities:
                modalities.append("document")
            if att.has_visual_content or att.rendered_pages:
                if "image" not in modalities:
                    modalities.append("image")
                if "vision" not in required_caps:
                    required_caps.append("vision")

        elif att.kind in (AttachmentKind.TEXT, AttachmentKind.CODE):
            if "document" not in modalities:
                modalities.append("document")
            if att.kind == AttachmentKind.CODE and "code" not in modalities:
                modalities.append("code")

    return modalities, required_caps
