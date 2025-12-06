"""Pinecone Vector Store Management using LangChain."""

import os
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Dict, Any

from langchain_core.documents import Document

logger = logging.getLogger(__name__)


class PineconeVectorStoreManager:
    """Manages Pinecone vector store for RAG retrieval."""
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        index_name: Optional[str] = None,
        cloud: Optional[str] = None,
        region: Optional[str] = None,
    ):
        """
        Initialize the Pinecone vector store manager.
        
        Args:
            api_key: Pinecone API key. Defaults to PINECONE_API_KEY env var.
            index_name: Name of the Pinecone index. Defaults to PINECONE_INDEX_NAME env var.
            cloud: Cloud provider. Defaults to PINECONE_CLOUD env var or 'aws'.
            region: Region. Defaults to PINECONE_REGION env var or 'us-east-1'.
        """
        self.api_key = api_key or os.getenv("PINECONE_API_KEY")
        self.index_name = index_name or os.getenv("PINECONE_INDEX_NAME", "tutor-rag-index")
        self.cloud = cloud or os.getenv("PINECONE_CLOUD", "aws")
        self.region = region or os.getenv("PINECONE_REGION", "us-east-1")
        
        self._pc = None
        self._embeddings = None
        self._vector_store = None
        self._initialized = False
    
    def _lazy_init(self):
        """Lazy initialization of Pinecone client and vector store."""
        if self._initialized:
            return
        
        if not self.api_key:
            raise RuntimeError("PINECONE_API_KEY is required.")
        
        google_api_key = os.getenv("GOOGLE_API_KEY")
        if not google_api_key:
            raise RuntimeError("GOOGLE_API_KEY is required for embeddings.")
        
        try:
            from pinecone import Pinecone, ServerlessSpec
            from langchain_pinecone import PineconeVectorStore
            from langchain_google_genai import GoogleGenerativeAIEmbeddings
            
            logger.info(f"Initializing Pinecone client for index: {self.index_name}")
            
            # Initialize Pinecone client
            self._pc = Pinecone(api_key=self.api_key)
            
            # Create index if not exists (dimension=768 for Google text-embedding-004)
            if not self._pc.has_index(self.index_name):
                logger.info(f"Creating Pinecone index: {self.index_name}")
                self._pc.create_index(
                    name=self.index_name,
                    dimension=768,  # text-embedding-004 dimension
                    metric="cosine",
                    spec=ServerlessSpec(cloud=self.cloud, region=self.region),
                )
            
            # Initialize embeddings using Google Generative AI
            self._embeddings = GoogleGenerativeAIEmbeddings(
                model="models/text-embedding-004",
                google_api_key=google_api_key,
            )
            
            # Initialize vector store
            self._vector_store = PineconeVectorStore(
                index=self._pc.Index(self.index_name),
                embedding=self._embeddings,
            )
            
            self._initialized = True
            logger.info("Pinecone vector store initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Pinecone: {e}")
            raise
    
    @property
    def vector_store(self):
        """Get the underlying PineconeVectorStore instance."""
        self._lazy_init()
        return self._vector_store
    
    def add_documents(self, documents: List[Document], ids: Optional[List[str]] = None) -> List[str]:
        """
        Add documents to the vector store using parallel batch processing.
        
        Args:
            documents: List of LangChain Document objects.
            ids: Optional list of IDs for the documents.
            
        Returns:
            List of IDs for the added documents.
        """
        self._lazy_init()
        logger.info(f"Adding {len(documents)} documents to vector store")
        
        batch_size = 100
        max_workers = 5
        max_retries = 3
        
        # Prepare batches
        batches = []
        for i in range(0, len(documents), batch_size):
            batch_docs = documents[i:i + batch_size]
            batch_ids = ids[i:i + batch_size] if ids else None
            batches.append((batch_docs, batch_ids))
            
        all_ids = []
        
        def _process_batch(batch_data):
            b_docs, b_ids = batch_data
            for attempt in range(max_retries):
                try:
                    return self._vector_store.add_documents(documents=b_docs, ids=b_ids)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    time.sleep(2 ** attempt)  # Exponential backoff
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_batch = {executor.submit(_process_batch, batch): batch for batch in batches}
            
            for future in as_completed(future_to_batch):
                try:
                    result_ids = future.result()
                    if result_ids:
                        all_ids.extend(result_ids)
                except Exception as e:
                    logger.error(f"Batch upsert failed after retries: {e}")
                    
        return all_ids
    
    def similarity_search(self, query: str, k: int = 5, filter: Optional[Dict[str, Any]] = None) -> List[Document]:
        """
        Perform similarity search.
        
        Args:
            query: Search query.
            k: Number of results to return.
            filter: Optional metadata filter.
            
        Returns:
            List of similar documents.
        """
        self._lazy_init()
        return self._vector_store.similarity_search(query, k=k, filter=filter)
    
    def similarity_search_with_score(self, query: str, k: int = 5) -> List[tuple]:
        """
        Perform similarity search with relevance scores.
        
        Args:
            query: Search query.
            k: Number of results to return.
            
        Returns:
            List of (document, score) tuples.
        """
        self._lazy_init()
        return self._vector_store.similarity_search_with_score(query, k=k)
    
    def delete_documents(self, ids: List[str]) -> None:
        """
        Delete documents from the vector store.
        
        Args:
            ids: List of document IDs to delete.
        """
        self._lazy_init()
        logger.info(f"Deleting {len(ids)} documents from vector store")
        self._vector_store.delete(ids=ids)
    
    def as_retriever(self, **kwargs):
        """
        Get a retriever interface for the vector store.
        
        Args:
            **kwargs: Arguments passed to as_retriever (e.g., search_type, search_kwargs).
            
        Returns:
            A LangChain retriever.
        """
        self._lazy_init()
        return self._vector_store.as_retriever(**kwargs)
