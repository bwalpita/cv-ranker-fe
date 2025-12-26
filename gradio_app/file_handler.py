"""
File Upload Handler
Manages CV and JD file uploads with validation
"""

import os
from pathlib import Path
from typing import Tuple, Optional
import mimetypes

# Configuration from environment
MAX_FILE_SIZE_MB = int(os.environ.get("MAX_FILE_SIZE_MB", 10))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS = os.environ.get("ALLOWED_FILE_TYPES", "pdf,docx,txt").split(",")


def validate_file_upload(file_content: bytes, filename: str) -> Tuple[bool, str]:
    """
    Validate uploaded file
    
    Args:
        file_content: File bytes
        filename: Original filename
    
    Returns:
        Tuple of (is_valid, message)
    """
    
    # Check file size
    if len(file_content) > MAX_FILE_SIZE_BYTES:
        return False, f"File too large. Maximum size: {MAX_FILE_SIZE_MB}MB"
    
    # Check file extension
    file_ext = Path(filename).suffix.lower().lstrip(".")
    if file_ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(ALLOWED_EXTENSIONS)
        return False, f"Invalid file type. Allowed types: {allowed}"
    
    # Check if file is empty
    if len(file_content) == 0:
        return False, "File is empty"
    
    return True, "File valid"


def extract_text_from_file(file_content: bytes, filename: str) -> Optional[str]:
    """
    Extract text content from uploaded file
    
    Supports: PDF, DOCX, TXT
    
    Args:
        file_content: File bytes
        filename: Original filename
    
    Returns:
        Extracted text or None if error
    """
    
    try:
        file_ext = Path(filename).suffix.lower()
        
        if file_ext == ".txt":
            return file_content.decode("utf-8", errors="ignore")
        
        elif file_ext == ".pdf":
            try:
                from PyPDF2 import PdfReader
                from io import BytesIO
                
                pdf_file = BytesIO(file_content)
                reader = PdfReader(pdf_file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
                return text
            except Exception as e:
                return f"Error reading PDF: {str(e)}"
        
        elif file_ext == ".docx":
            try:
                from docx import Document
                from io import BytesIO
                
                doc = Document(BytesIO(file_content))
                text = ""
                for paragraph in doc.paragraphs:
                    text += paragraph.text + "\n"
                return text
            except Exception as e:
                return f"Error reading DOCX: {str(e)}"
        
        else:
            return f"Unsupported file type: {file_ext}"
    
    except Exception as e:
        return f"Error extracting text: {str(e)}"


def format_file_info(filename: str, file_size_bytes: int) -> str:
    """Format file information for display"""
    size_mb = file_size_bytes / (1024 * 1024)
    return f"**{filename}** ({size_mb:.2f}MB)"
