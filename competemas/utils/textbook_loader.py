# competition_system/textbook_loader.py
import json
import os
from typing import Dict, List, Optional, Any

from scripts.competitors import logger

class TextbookLoader:
    """Load and search textbook content"""
    
    def __init__(self, data_path: Optional[str] = None):
        if data_path is None:
            # Try to find the path relative to the current file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            possible_paths = [
                os.path.join(current_dir, "..", "..", "dataset", "corpuses", "cpbook_v2.json"),
                "dataset/corpuses/cpbook_v2.json"  # Fallback to the original path
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    self.data_path = path
                    break
            else:
                self.data_path = "dataset/corpuses/cpbook_v2.json"  # Use as default if nothing found
        else:
            self.data_path = data_path
            
        self.textbook_data = []
        self._load_textbook()
    
    def _load_textbook(self):
        """Load the textbook content"""
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    self.textbook_data = json.load(f)
            except Exception as e:
                logger.error(f"Error loading textbook: {e}")
                self.textbook_data = []
        else:
            logger.error(f"Textbook file not found: {self.data_path}")
            self.textbook_data = []
    
    def search_content(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Search textbook content using BM25"""
        if not self.textbook_data:
            return []
        
        try:
            from rank_bm25 import BM25Okapi
            
            # Create corpus for BM25
            corpus = [article.get('full_article', '') for article in self.textbook_data]
            tokenized_corpus = [doc.split() for doc in corpus]
            bm25 = BM25Okapi(tokenized_corpus)
            
            # Search
            tokenized_query = query.split()
            scores = bm25.get_scores(tokenized_query)
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:max_results]
            
            results = []
            for idx in top_indices:
                article = self.textbook_data[idx]
                results.append({
                    "title": article.get('title', ''),
                    "content": article.get('full_article', ''),
                    "relevance_score": float(scores[idx]),
                    "article_id": idx
                })
            
            return results
            
        except ImportError:
            logger.error("BM25 library not available, falling back to simple search")
            return self._simple_search_content(query, max_results)
        except Exception as e:
            logger.error(f"Error in BM25 search: {e}")
            return self._simple_search_content(query, max_results)
    
    def search_title(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Search textbook titles using BM25"""
        if not self.textbook_data:
            return []
        
        try:
            from rank_bm25 import BM25Okapi
            
            # Create corpus for BM25 using titles only
            corpus = [article.get('title', '') for article in self.textbook_data]
            tokenized_corpus = [doc.split() for doc in corpus]
            bm25 = BM25Okapi(tokenized_corpus)
            
            # Search
            tokenized_query = query.split()
            scores = bm25.get_scores(tokenized_query)
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:max_results]
            
            results = []
            for idx in top_indices:
                article = self.textbook_data[idx]
                results.append({
                    "title": article.get('title', ''),
                    "content": article.get('full_article', ''),
                    "relevance_score": float(scores[idx]),
                    "article_id": idx
                })
            
            return results
            
        except ImportError:
            logger.error("BM25 library not available, falling back to simple search")
            return self._simple_search_title(query, max_results)
        except Exception as e:
            logger.error(f"Error in BM25 search: {e}")
            return self._simple_search_title(query, max_results)
    
    def search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Search textbook content using BM25 (alias for search_content for backward compatibility)"""
        return self.search_content(query, max_results)
    
    def _simple_search_content(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Simple text-based search for content as fallback"""
        if not self.textbook_data:
            return []
        
        query_lower = query.lower()
        results = []
        
        for idx, article in enumerate(self.textbook_data):
            title = article.get('title', '').lower()
            content = article.get('full_article', '').lower()
            
            # Simple relevance scoring
            title_matches = title.count(query_lower)
            content_matches = content.count(query_lower)
            relevance_score = title_matches * 2 + content_matches
            
            if relevance_score > 0:
                results.append({
                    "title": article.get('title', ''),
                    "content": article.get('full_article', ''),
                    "relevance_score": relevance_score,
                    "article_id": idx
                })
        
        # Sort by relevance score and limit results
        results.sort(key=lambda x: x['relevance_score'], reverse=True)
        return results[:max_results]
    
    def _simple_search_title(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Simple text-based search for titles as fallback"""
        if not self.textbook_data:
            return []
        
        query_lower = query.lower()
        results = []
        
        for idx, article in enumerate(self.textbook_data):
            title = article.get('title', '').lower()
            
            # Simple relevance scoring for titles only
            title_matches = title.count(query_lower)
            relevance_score = title_matches
            
            if relevance_score > 0:
                results.append({
                    "title": article.get('title', ''),
                    "content": article.get('full_article', ''),
                    "relevance_score": relevance_score,
                    "article_id": idx
                })
        
        # Sort by relevance score and limit results
        results.sort(key=lambda x: x['relevance_score'], reverse=True)
        return results[:max_results]
    
    def _simple_search(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Simple text-based search as fallback (alias for backward compatibility)"""
        return self._simple_search_content(query, max_results)
    
    def get_article(self, article_id: int) -> Optional[Dict[str, Any]]:
        """Get a specific article by ID"""
        if 0 <= article_id < len(self.textbook_data):
            article = self.textbook_data[article_id]
            return {
                "title": article.get('title', ''),
                "content": article.get('full_article', ''),
                "article_id": article_id
            }
        return None
    
    def get_total_articles(self) -> int:
        """Get total number of articles"""
        return len(self.textbook_data)
    
    def is_loaded(self) -> bool:
        """Check if textbook is loaded"""
        return len(self.textbook_data) > 0 