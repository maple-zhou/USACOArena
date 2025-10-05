# competition_system/strategy_loader.py
import json
import os
from typing import Dict, List, Optional, Any

class StrategyLoader:
    """Load and provide competitive programming strategy content"""
    
    def __init__(self, data_path: Optional[str] = None):
        if data_path is None:
            # Try to find the path relative to the current file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            possible_paths = [
                os.path.join(current_dir, "..", "..", "dataset", "corpuses", "USACO_strategy.json"),
                "dataset/corpuses/USACO_strategy.json"  # Fallback to the original path
            ]
            
            for path in possible_paths:
                if os.path.exists(path):
                    self.data_path = path
                    break
            else:
                self.data_path = "dataset/corpuses/USACO_strategy.json"  # Use as default if nothing found
        else:
            self.data_path = data_path
            
        self.strategy_data = {}
        self._load_strategy()
    
    def _load_strategy(self):
        """Load the strategy content"""
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    self.strategy_data = json.load(f)
            except Exception as e:
                self.strategy_data = {}
        else:
            self.strategy_data = {}
    
    def get_core_philosophy(self) -> Dict[str, Any]:
        """Get core competitive programming philosophy"""
        return self.strategy_data.get('core_philosophy', {})
    
    def get_debugging_checklist(self) -> Dict[str, Any]:
        """Get debugging and error-checking checklist"""
        return self.strategy_data.get('debugging_checklist', {})
    
    def get_contest_strategy(self) -> Dict[str, Any]:
        """Get contest strategy guidelines"""
        return self.strategy_data.get('contest_strategy', {})
    
    def get_all_strategies(self) -> Dict[str, Any]:
        """Get all strategy content"""
        return self.strategy_data
    
    def get_strategy_by_category(self, category: str) -> Dict[str, Any]:
        """Get strategy content by category"""
        return self.strategy_data.get(category, {})
    
    def get_debugging_tips(self) -> List[str]:
        """Get list of debugging tips"""
        checklist = self.get_debugging_checklist()
        return checklist.get('general_troubleshooting', [])
    
    def get_error_specific_guidance(self) -> Dict[str, str]:
        """Get error-specific guidance"""
        checklist = self.get_debugging_checklist()
        return checklist.get('error_specific_guidance', {})
    
    def get_contest_tips(self) -> List[str]:
        """Get list of contest strategy tips"""
        strategy = self.get_contest_strategy()
        return strategy.get('general_approach_and_timing', [])
    
    def get_implementation_tactics(self) -> Dict[str, str]:
        """Get implementation tactics"""
        strategy = self.get_contest_strategy()
        return strategy.get('implementation_tactics', {})
    
    def is_loaded(self) -> bool:
        """Check if strategy is loaded"""
        return len(self.strategy_data) > 0
    
    def format_strategy_for_hint(self) -> Dict[str, Any]:
        """Format strategy data for hint display - returns all content from strategy.json"""
        if not self.is_loaded():
            return {"error": "Strategy data not loaded"}
        
        return self.strategy_data
    
    def get_random_tip(self, category: str = "debugging") -> Optional[str]:
        """Get a random tip from a specific category"""
        import random
        
        if category == "debugging":
            tips = self.get_debugging_tips()
        elif category == "contest":
            tips = self.get_contest_tips()
        else:
            return None
        
        if tips:
            return random.choice(tips)
        return None
    
    def search_strategy(self, query: str) -> List[Dict[str, Any]]:
        """Search strategy content for specific topics"""
        if not self.is_loaded():
            return []
        
        query_lower = query.lower()
        results = []
        
        # Search through all strategy sections
        for section_name, section_data in self.strategy_data.items():
            if isinstance(section_data, dict):
                for key, value in section_data.items():
                    if isinstance(value, str) and query_lower in value.lower():
                        results.append({
                            "section": section_name,
                            "topic": key,
                            "content": value,
                            "relevance": value.lower().count(query_lower)
                        })
                    elif isinstance(value, list):
                        for i, item in enumerate(value):
                            if isinstance(item, str) and query_lower in item.lower():
                                results.append({
                                    "section": section_name,
                                    "topic": f"{key}[{i}]",
                                    "content": item,
                                    "relevance": item.lower().count(query_lower)
                                })
        
        # Sort by relevance
        results.sort(key=lambda x: x['relevance'], reverse=True)
        return results
