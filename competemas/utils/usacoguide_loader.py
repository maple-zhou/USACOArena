# competemas/utils/usacoguide_loader.py
import json
import os
from typing import Dict, List, Optional, Any

class USACOGuideLoader:
    """Load and provide USACO guide content"""
    
    def __init__(self, data_path: Optional[str] = None):
        if data_path is None:
            # Try to find the path relative to the current file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            possible_paths = [
                os.path.join(current_dir, "..", "..", "dataset", "datasets", "USACO_guide.json"),
                "dataset/datasets/USACO_guide.json"  # Fallback to the original path
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    self.data_path = path
                    break
            else:
                self.data_path = "dataset/datasets/USACO_guide.json"  # Use as default if nothing found
        else:
            self.data_path = data_path
            
        self.guide_data = {}
        self._load_guide()
    
    def _load_guide(self):
        """Load the guide content"""
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    self.guide_data = json.load(f)
            except Exception as e:
                print(f"Error loading guide: {e}")
                self.guide_data = {}
        else:
            print(f"Guide file not found: {self.data_path}")
            self.guide_data = {}
    
    def is_loaded(self) -> bool:
        """Check if guide is loaded"""
        return len(self.guide_data) > 0
    
    def get_all_data(self) -> Dict[str, Any]:
        """Get all guide content"""
        return self.guide_data
    
    def get_first_level_keys(self) -> List[str]:
        """Get all first level keys"""
        return list(self.guide_data.keys())
    
    def get_second_level_keys(self, first_level_key: str) -> List[str]:
        """Get all second level keys for a given first level key"""
        if first_level_key in self.guide_data:
            value = self.guide_data[first_level_key]
            if isinstance(value, dict):
                return list(value.keys())
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                return list(value[0].keys())
        return []
    
    def search_second_level_key(self, problem_difficulty: str, hint_knowledge: str) -> Optional[Dict[str, Any]]:
        """
        重要方法：在指定的problem_difficulty中搜索hint_knowledge二级键的内容
        
        Args:
            problem_difficulty: 要搜索的一级键
            hint_knowledge: 要搜索的二级键名
            
        Returns:
            如果找到，返回包含该键值对的字典；否则返回None
        """
        if not self.is_loaded():
            return None
        
        if problem_difficulty not in self.guide_data:
            return None
            
        first_level_value = self.guide_data[problem_difficulty]
        
        # 如果一级键的值是字典
        if isinstance(first_level_value, dict):
            # 检查二级键中是否存在搜索的键
            if hint_knowledge in first_level_value:
                return {
                    problem_difficulty: {
                        hint_knowledge: first_level_value[hint_knowledge]
                    }
                }
        
        # 如果一级键的值是列表，且列表元素是字典
        elif isinstance(first_level_value, list) and first_level_value:
            for i, item in enumerate(first_level_value):
                if isinstance(item, dict) and hint_knowledge in item:
                    return {
                        f"{problem_difficulty}[{i}]": {
                            hint_knowledge: item[hint_knowledge]
                        }
                    }
        
        return None
    
    def search_second_level_key_similar(self, problem_difficulty: str, hint_knowledge: str, max_results: int = 1) -> List[Dict[str, Any]]:
        """
        使用BM25算法在指定的problem_difficulty中查找与hint_knowledge相似的二级键
        
        Args:
            problem_difficulty: 要搜索的一级键
            hint_knowledge: 要搜索的二级键名
            max_results: 最大返回结果数
            
        Returns:
            返回相似度排序的结果列表，每个结果包含键名、值和相似度分数
        """
        if not self.is_loaded():
            return []
        
        if problem_difficulty not in self.guide_data:
            return []
        
        try:
            from rank_bm25 import BM25Okapi
            
            
            # 收集所有二级键名用于相似度搜索
            all_second_level_keys = []
            key_info = []  # 存储键的详细信息
            
            first_level_value = self.guide_data[problem_difficulty]
            
            # 如果一级键的值是字典
            if isinstance(first_level_value, dict):
                for second_level_key in first_level_value.keys():
                    all_second_level_keys.append(second_level_key)
                    key_info.append({
                        "first_level": problem_difficulty,
                        "second_level": second_level_key,
                        "value": first_level_value[second_level_key],
                        "type": "dict"
                    })
            
            # 如果一级键的值是列表，且列表元素是字典
            elif isinstance(first_level_value, list) and first_level_value:
                for i, item in enumerate(first_level_value):
                    if isinstance(item, dict):
                        for second_level_key in item.keys():
                            all_second_level_keys.append(second_level_key)
                            key_info.append({
                                "first_level": f"{problem_difficulty}[{i}]",
                                "second_level": second_level_key,
                                "value": item[second_level_key],
                                "type": "list"
                            })
            
            if not all_second_level_keys:
                return []
            
            # tokenized_corpus = [key.split() for key in all_second_level_keys]
            # 创建BM25语料库
            # 每个元素拼接上三级键concept的value
            tokenized_corpus = []
            for idx, key in enumerate(all_second_level_keys):
                concept_value = ""
                info = key_info[idx]
                value = info["value"]
                # value 可能是dict，尝试取concept字段
                if isinstance(value, dict) and "concept" in value:
                    concept_value = str(value["concept"])
                    explanation_value = str(value["explanation"])[:100]
                    # print("000000",concept_value)
                    # print("111111",explanation_value)
                # 拼接二级键和concept
                combined = f"{key} {concept_value} {explanation_value}".strip()
                # print(combined)
                tokenized_corpus.append(combined.split())
            
            bm25 = BM25Okapi(tokenized_corpus)
            
            # 搜索
            tokenized_query = hint_knowledge.split()
            
            scores = bm25.get_scores(tokenized_query)

            # print(scores)
            
            # 获取最相似的结果
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:max_results]
            
            results = []
            for idx in top_indices:
                info = key_info[idx]
                # print(info,type(info),"\n")
                # print("content",info["value"]["example_problems"],"\n")
                # print("title",info["second_level"],"\n")
                # print("relevance_score",float(scores[idx]))    
                # info["value"].keys()[0]
                results.append({
                    "content": info["value"]["example_problems"],
                    "title": info["second_level"],
                    "relevance_score": float(scores[idx])
                })
            
            # print(results)
            return results
            
        except ImportError:
            # print("BM25 library not available, falling back to simple search")
            return self._simple_search_second_level_key(hint_knowledge, problem_difficulty, max_results)
        except Exception as e:
            # print(f"Error in BM25 search: {e}")
            return self._simple_search_second_level_key(hint_knowledge, problem_difficulty, max_results)
    
    def _simple_search_second_level_key(self, search_key: str, problem_difficulty: str, max_results: int = 3) -> List[Dict[str, Any]]:
        """
        简单的字符串匹配搜索（BM25不可用时的备用方案）
        """
        if not self.is_loaded():
            return []
        
        if problem_difficulty not in self.guide_data:
            return []
        
        results = []
        search_key_lower = search_key.lower()
        
        first_level_value = self.guide_data[problem_difficulty]
        
        # 如果一级键的值是字典
        if isinstance(first_level_value, dict):
            for second_level_key, value in first_level_value.items():
                if search_key_lower in second_level_key.lower():
                    results.append({
                        "first_level_key": problem_difficulty,
                        "second_level_key": second_level_key,
                        "value": value,
                        "similarity_score": second_level_key.lower().count(search_key_lower),
                        "type": "dict"
                    })
        
        # 如果一级键的值是列表，且列表元素是字典
        elif isinstance(first_level_value, list) and first_level_value:
            for i, item in enumerate(first_level_value):
                if isinstance(item, dict):
                    for second_level_key, value in item.items():
                        if search_key_lower in second_level_key.lower():
                            results.append({
                                "first_level_key": f"{problem_difficulty}[{i}]",
                                "second_level_key": second_level_key,
                                "value": value,
                                "similarity_score": second_level_key.lower().count(search_key_lower),
                                "type": "list"
                            })
        
        # 按相似度排序并限制结果数量
        results.sort(key=lambda x: x['similarity_score'], reverse=True)
        return results[:max_results]
    
    def get_section_by_key(self, section_key: str) -> Optional[Dict[str, Any]]:
        """Get a specific section by its first level key"""
        return self.guide_data.get(section_key)
    
    def search_content(self, query: str) -> List[Dict[str, Any]]:
        """Search guide content for specific topics"""
        if not self.is_loaded():
            return []
        
        query_lower = query.lower()
        results = []
        
        # Search through all guide sections
        for section_name, section_data in self.guide_data.items():
            if isinstance(section_data, dict):
                for key, value in section_data.items():
                    if isinstance(value, str) and query_lower in value.lower():
                        results.append({
                            "section": section_name,
                            "key": key,
                            "content": value,
                            "relevance": value.lower().count(query_lower)
                        })
                    elif isinstance(value, list):
                        for i, item in enumerate(value):
                            if isinstance(item, str) and query_lower in item.lower():
                                results.append({
                                    "section": section_name,
                                    "key": f"{key}[{i}]",
                                    "content": item,
                                    "relevance": item.lower().count(query_lower)
                                })
            elif isinstance(section_data, list):
                for i, item in enumerate(section_data):
                    if isinstance(item, dict):
                        for key, value in item.items():
                            if isinstance(value, str) and query_lower in value.lower():
                                results.append({
                                    "section": f"{section_name}[{i}]",
                                    "key": key,
                                    "content": value,
                                    "relevance": value.lower().count(query_lower)
                                })
        
        # Sort by relevance
        results.sort(key=lambda x: x['relevance'], reverse=True)
        return results
    
    def format_guide_for_hint(self) -> Dict[str, Any]:
        """Format guide data for hint display - returns all content from guide.json"""
        if not self.is_loaded():
            return {"error": "Guide data not loaded"}
        
        # 直接返回原始指南数据，保持JSON文件的原始结构
        return self.guide_data
