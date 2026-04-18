import re
from langchain_pymupdf4llm import PyMuPDF4LLMLoader
from langchain_community.document_loaders import UnstructuredWordDocumentLoader, TextLoader
from utils.constants import SECTION_KEYWORDS

def load_document(file_path: str, file_extension: str) -> str:
    """Load text content from a file with a fast-pass/slow-fallback strategy."""
    import gc
    import fitz
    from utils.constants import SECTION_KEYWORDS
    
    try:
        if file_extension in ["pdf", "epub", "mobi"]:
            # --- PASS 1: Fast Direct Extraction ---
            try:
                doc = fitz.open(file_path)
                fast_text = ""
                for page in doc:
                    fast_text += page.get_text()
                doc.close()
                
                # Validate Fast Pass: Check for keywords and length
                content_lower = fast_text.lower()
                matched = sum(1 for kw in SECTION_KEYWORDS if kw in content_lower)
                
                # If we have basic resume indicators, trust the fast pass
                if matched >= 3 and len(fast_text.strip()) > 300:
                    return fast_text
            except Exception:
                pass # Fallback to Pass 2

            # --- PASS 2: AI Layout Extraction (PyMuPDF4LLM) ---
            loader = PyMuPDF4LLMLoader(file_path)
            docs = loader.load()
            if not docs:
                return ""
            return "\n\n".join(doc.page_content for doc in docs)

        elif file_extension == "txt":
            loader = TextLoader(file_path, encoding="utf-8")
            docs = loader.load()
            return "\n\n".join(doc.page_content for doc in docs)
        elif file_extension in ["docx"]:
            loader = UnstructuredWordDocumentLoader(file_path, mode="single")
            docs = loader.load()
            return "\n\n".join(doc.page_content for doc in docs)
        else:
            raise ValueError(f"Unsupported file extension: {file_extension}")

    finally:
        gc.collect()

def load_document_standard(file_path: str, file_extension: str) -> str:
    """Standard (last resort) local extraction using bare libraries."""
    import gc
    try:
        if file_extension in ["pdf"]:
            import fitz
            doc = fitz.open(file_path)
            text = ""
            for page in doc:
                text += page.get_text()
            doc.close()
            return text
        elif file_extension in ["docx"]:
            import docx
            doc = docx.Document(file_path)
            return "\n".join([p.text for p in doc.paragraphs])
        return ""
    finally:
        gc.collect()

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
