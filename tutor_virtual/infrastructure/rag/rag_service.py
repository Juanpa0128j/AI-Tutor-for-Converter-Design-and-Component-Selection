"""RAG Service - Coordinates document processing and retrieval."""

import os
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import uuid4

from langchain_core.documents import Document

from .document_processor import UnstructuredDocumentProcessor, SUPPORTED_EXTENSIONS
from .vector_store import PineconeVectorStoreManager

logger = logging.getLogger(__name__)

# Default storage path for uploaded documents
DEFAULT_DOCUMENTS_PATH = Path(__file__).parent.parent.parent / "data" / "documents"


class RAGService:
    """
    Coordinates document processing and RAG retrieval.
    
    Handles the full lifecycle of documents:
    - Upload and store files
    - Process with Unstructured API
    - Index in Pinecone vector store
    - Retrieve relevant context for queries
    """
    
    def __init__(self, documents_path: Optional[str] = None):
        """
        Initialize the RAG service.
        
        Args:
            documents_path: Path to store uploaded documents. Defaults to data/documents.
        """
        self.documents_path = Path(documents_path) if documents_path else DEFAULT_DOCUMENTS_PATH
        self.documents_path.mkdir(parents=True, exist_ok=True)
        
        # Metadata file to track indexed documents
        self.metadata_file = self.documents_path / ".rag_metadata.json"
        
        # Get timeout from env
        timeout = int(os.getenv("UNSTRUCTURED_TIMEOUT", "60"))
        self.document_processor = UnstructuredDocumentProcessor(timeout=timeout)
        self.vector_store_manager = PineconeVectorStoreManager()
        
        # Load existing metadata
        self._metadata = self._load_metadata()
    
    def _load_metadata(self) -> Dict[str, Any]:
        """Load metadata from disk."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load metadata: {e}")
        return {"documents": {}}
    
    def _save_metadata(self):
        """Save metadata to disk."""
        try:
            with open(self.metadata_file, "w") as f:
                json.dump(self._metadata, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")
    
    def get_supported_extensions(self) -> List[str]:
        """Get list of supported file extensions."""
        return self.document_processor.get_supported_extensions()
    
    def process_and_index_file(self, file_path: str, original_filename: Optional[str] = None, strategy: str = "fast") -> Dict[str, Any]:
        """
        Process a file and index it in the vector store.
        
        Args:
            file_path: Path to the file to process.
            original_filename: Original filename (useful when file was uploaded with temp name).
            strategy: Partitioning strategy ("fast", "hi_res", "auto", "ocr_only").
            
        Returns:
            Dict with processing results including doc_id, chunk_count, etc.
        """
        path = Path(file_path)
        original_filename = original_filename or path.name
        
        logger.info(f"Processing and indexing file: {original_filename} with strategy={strategy}")
        
        # Generate unique document ID
        doc_id = str(uuid4())
        
        try:
            # Process file with Unstructured
            documents = self.document_processor.process_file(file_path, strategy=strategy)
            
            if not documents:
                raise ValueError("No content extracted from file")
            
            # Add document ID and metadata to all chunks
            chunk_ids = []
            for i, doc in enumerate(documents):
                chunk_id = f"{doc_id}_{i}"
                chunk_ids.append(chunk_id)
                doc.metadata["doc_id"] = doc_id
                doc.metadata["chunk_index"] = i
                doc.metadata["original_filename"] = original_filename
            
            # Index in vector store
            self.vector_store_manager.add_documents(documents, ids=chunk_ids)
            
            # Store file locally
            stored_path = self.documents_path / f"{doc_id}_{original_filename}"
            if not path.samefile(stored_path) if stored_path.exists() else True:
                import shutil
                shutil.copy2(file_path, stored_path)
            
            # Update metadata
            self._metadata["documents"][doc_id] = {
                "filename": original_filename,
                "stored_path": str(stored_path),
                "chunk_count": len(documents),
                "chunk_ids": chunk_ids,
                "indexed_at": datetime.now().isoformat(),
            }
            self._save_metadata()
            
            logger.info(f"Successfully indexed {len(documents)} chunks for {original_filename}")
            
            return {
                "doc_id": doc_id,
                "filename": original_filename,
                "chunk_count": len(documents),
                "status": "success",
            }
            
        except Exception as e:
            logger.error(f"Failed to process file {original_filename}: {e}")
            return {
                "doc_id": None,
                "filename": original_filename,
                "chunk_count": 0,
                "status": "error",
                "error": str(e),
            }
    
    def retrieve_context(self, query: str, k: int = 5) -> List[Document]:
        """
        Retrieve relevant context for a query.
        
        Args:
            query: The search query.
            k: Number of results to return.
            
        Returns:
            List of relevant Document objects.
        """
        try:
            return self.vector_store_manager.similarity_search(query, k=k)
        except Exception as e:
            logger.error(f"Error retrieving context: {e}")
            return []
    
    def retrieve_context_formatted(self, query: str, k: int = 5) -> str:
        """
        Retrieve and format context for LLM consumption.
        
        Args:
            query: The search query.
            k: Number of results to return.
            
        Returns:
            Formatted string with relevant context.
        """
        documents = self.retrieve_context(query, k=k)
        
        if not documents:
            return "No relevant documents found in the knowledge base."
        
        formatted_parts = ["## Relevant Context from Uploaded Documents\n"]
        
        for i, doc in enumerate(documents, 1):
            filename = doc.metadata.get("original_filename", "Unknown")
            page = doc.metadata.get("page_number", "N/A")
            content = doc.page_content.strip()
            formatted_parts.append(f"### Source {i}: {filename} (Page {page})\n{content}\n")
        
        return "\n".join(formatted_parts)
    
    def get_indexed_documents(self) -> List[Dict[str, Any]]:
        """
        Get list of all indexed documents.
        
        Returns:
            List of document metadata dictionaries.
        """
        # Reload metadata to ensure we have the latest updates from worker
        self._metadata = self._load_metadata()
        
        return [
            {
                "doc_id": doc_id,
                **info,
            }
            for doc_id, info in self._metadata.get("documents", {}).items()
        ]
    
    def delete_document(self, doc_id: str) -> bool:
        """
        Delete a document from the index and storage.
        
        Args:
            doc_id: The document ID to delete.
            
        Returns:
            True if successful, False otherwise.
        """
        if doc_id not in self._metadata.get("documents", {}):
            logger.warning(f"Document not found: {doc_id}")
            return False
        
        try:
            doc_info = self._metadata["documents"][doc_id]
            
            # Delete from vector store
            chunk_ids = doc_info.get("chunk_ids", [])
            if chunk_ids:
                self.vector_store_manager.delete_documents(chunk_ids)
            
            # Delete stored file
            stored_path = Path(doc_info.get("stored_path", ""))
            if stored_path.exists():
                stored_path.unlink()
            
            # Remove from metadata
            del self._metadata["documents"][doc_id]
            self._save_metadata()
            
            logger.info(f"Successfully deleted document: {doc_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting document {doc_id}: {e}")
            return False


# Singleton instance for use across the application
_rag_service: Optional[RAGService] = None


def get_rag_service() -> RAGService:
    """Get the singleton RAG service instance."""
    global _rag_service
    if _rag_service is None:
        _rag_service = RAGService()
    return _rag_service
