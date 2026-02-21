import re
from langchain_pymupdf4llm import PyMuPDF4LLMLoader
from langchain_community.document_loaders import UnstructuredWordDocumentLoader, TextLoader
from utils.constants import SECTION_KEYWORDS

def load_document(file_path: str, file_extension: str) -> str:
    """Load text content from a file based on its extension."""
    if file_extension in ["pdf", "epub", "mobi"]:
        loader = PyMuPDF4LLMLoader(file_path)
    elif file_extension == "txt":
        loader = TextLoader(file_path, encoding="utf-8")
    elif file_extension in ["docx"]:
        loader = UnstructuredWordDocumentLoader(file_path, mode="single")
    else:
        raise ValueError(f"Unsupported file extension: {file_extension}")

    docs = loader.load()
    if not docs:
        return ""
    return "\n\n".join(doc.page_content for doc in docs)

def validate_extraction(content: str) -> bool:
    """Validate if the extracted content looks like a resume."""
    if not content or len(content.strip()) < 100:
        return False

    content_lower = content.lower()
    matched = sum(1 for kw in SECTION_KEYWORDS if kw in content_lower)
    if matched < 2:
        return False

    garbled_count = len(re.findall(r'[^\x00-\x7F\u00C0-\u024F\u0600-\u06FF]', content))
    garbled_ratio = garbled_count / len(content) if content else 0
    if garbled_ratio > 0.3:
        return False

    return True
