import fitz  # PyMuPDF
import docx
from pathlib import Path

ALLOWED_EXTENSIONS = {".pdf", ".docx"}

def extract_from_pdf(file_path: str) -> str:
    text_parts = []
    with fitz.open(file_path) as doc:
        for page in doc:
            text_parts.append(page.get_text())
    return "\n".join(text_parts)

def extract_from_docx(file_path: str) -> str:
    doc = docx.Document(file_path)
    return "\n".join([p.text for p in doc.paragraphs])

def extract_text(file_path: str) -> str:
    ext = Path(file_path).suffix.lower()

    try:
        if ext == ".pdf":
            text = extract_from_pdf(file_path)
        elif ext == ".docx":
            text = extract_from_docx(file_path)
        else:
            raise ValueError(f"Unsupported file type: {ext}. Allowed: {ALLOWED_EXTENSIONS}")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(
            f"Could not read {ext} file. The file may be damaged or invalid."
        ) from exc

    text = text.strip()
    if len(text) < 20:
        raise ValueError("Could not extract enough text from file. It may be a scanned document.")

    return text
