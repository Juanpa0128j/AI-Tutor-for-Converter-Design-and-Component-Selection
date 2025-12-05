"""Document Processing using Unstructured API directly."""

import os
import logging
from pathlib import Path
from typing import List, Optional

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# Supported file extensions for Unstructured
SUPPORTED_EXTENSIONS = {
    # Documents
    ".pdf", ".docx", ".doc", ".txt", ".md", ".rst", ".rtf",
    # Spreadsheets
    ".xlsx", ".xls", ".csv",
    # Presentations
    ".pptx", ".ppt",
    # Web
    ".html", ".htm", ".xml",
    # Other
    ".epub", ".odt",
}


class UnstructuredDocumentProcessor:
    """Processes documents using Unstructured API for RAG ingestion."""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize the document processor.
        
        Args:
            api_key: Unstructured API key. If not provided, reads from UNSTRUCTURED_API_KEY env var.
        """
        self.api_key = api_key or os.getenv("UNSTRUCTURED_API_KEY")
        if not self.api_key:
            logger.warning("UNSTRUCTURED_API_KEY not set. Document processing will fail.")
    
    def is_supported(self, file_path: str) -> bool:
        """Check if file extension is supported."""
        ext = Path(file_path).suffix.lower()
        return ext in SUPPORTED_EXTENSIONS
    
    def get_supported_extensions(self) -> List[str]:
        """Return list of supported file extensions."""
        return sorted(list(SUPPORTED_EXTENSIONS))
    
    def process_file(self, file_path: str) -> List[Document]:
        """
        Process a file using Unstructured API and return LangChain documents.
        
        Uses the unstructured-client SDK directly for compatibility with
        the latest langchain-core versions.
        
        Args:
            file_path: Path to the file to process.
            
        Returns:
            List of LangChain Document objects with chunked content.
            
        Raises:
            ValueError: If file extension is not supported.
            RuntimeError: If API key is not configured.
        """
        if not self.api_key:
            raise RuntimeError("UNSTRUCTURED_API_KEY is required for document processing.")
        
        if not self.is_supported(file_path):
            ext = Path(file_path).suffix
            raise ValueError(f"Unsupported file extension: {ext}. Supported: {SUPPORTED_EXTENSIONS}")
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        logger.info(f"Processing file: {file_path}")
        
        try:
            from unstructured_client import UnstructuredClient
            from unstructured_client.models import operations, shared
            
            # Initialize client
            client = UnstructuredClient(api_key_auth=self.api_key)
            
            # Read file
            with open(file_path, "rb") as f:
                file_content = f.read()
            
            filename = Path(file_path).name
            
            # Call Unstructured API
            # Note: newer unstructured-client uses string values, not enums
            req = operations.PartitionRequest(
                partition_parameters=shared.PartitionParameters(
                    files=shared.Files(
                        content=file_content,
                        file_name=filename,
                    ),
                    strategy="auto",
                    chunking_strategy="basic",
                    max_characters=1000,
                ),
            )
            
            res = client.general.partition(request=req)
            
            if res.elements is None:
                logger.warning(f"No elements returned from Unstructured API for {file_path}")
                return []
            
            # Convert to LangChain Documents
            documents = []
            for element in res.elements:
                # Get text content
                text = element.get("text", "")
                if not text or not text.strip():
                    continue
                
                # Get metadata
                metadata = {
                    "source": file_path,
                    "filename": filename,
                    "original_filename": filename,
                    "element_type": element.get("type", "Unknown"),
                }
                
                # Add element metadata if available
                element_metadata = element.get("metadata", {})
                if element_metadata:
                    if "page_number" in element_metadata:
                        metadata["page_number"] = element_metadata["page_number"]
                    if "languages" in element_metadata:
                        metadata["languages"] = element_metadata["languages"]
                
                doc = Document(page_content=text, metadata=metadata)
                documents.append(doc)
            
            logger.info(f"Processed {len(documents)} chunks from {file_path}")
            return documents
            
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            raise
