# competition_system/problem_loader.py
import json
import os
from typing import Dict, List, Optional
from models import Problem, TestCase, Level, generate_id

class USACOProblemLoader:
    """Load problems from the USACO problem library"""
    
    def __init__(self, data_path: str = None):
        if data_path is None:
            # Try to find the path relative to the current file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            possible_paths = [
                os.path.join(current_dir, "..", "data", "datasets", "usaco_v3"),
                "data/datasets/usaco_v3"  # Fallback to the original path
            ]
            
            for path in possible_paths:
                if os.path.exists(path) and os.path.isdir(path):
                    self.data_path = path
                    break
            else:
                self.data_path = "data/datasets/usaco_v3"  # Use as default if nothing found
        else:
            self.data_path = data_path
            
        self.problems_dict = {}
        self._load_problem_dict()
    
    def _load_problem_dict(self):
        """Load the USACO problem dictionary"""
        problem_dict_path = os.path.join(self.data_path, '..', "usaco_v2_dict.json")
        if os.path.exists(problem_dict_path):
            try:
                with open(problem_dict_path, 'r') as f:
                    self.problems_dict = json.load(f)
            except Exception as e:
                print(f"Error loading problem dictionary: {e}")
    
    def get_problem_ids(self, level: Optional[str] = None) -> List[str]:
        """Get a list of problem IDs for the specified difficulty level"""
        if not level:
            return list(self.problems_dict.keys())
        
        return [pid for pid, p in self.problems_dict.items() 
                if p.get('problem_level', '').lower() == level.lower()]
    
    def load_problem(self, problem_id: str) -> Optional[Problem]:
        """Load a problem from the USACO problem library"""
        if problem_id not in self.problems_dict:
            return None
        
        problem_data = self.problems_dict[problem_id]
        
        # Create test cases
        test_cases = []
        sample_cases = []
        
        # Load sample test cases
        if 'samples' in problem_data:
            for i, sample in enumerate(problem_data['samples']):
                case = TestCase(
                    id=generate_id(),
                    input_data=sample.get('input', ''),
                    expected_output=sample.get('output', '')
                )
                sample_cases.append(case)
                # test_cases.append(case)  # Samples are also included as test cases
        
        # Load all test cases - be careful with directory access
        test_dir = os.path.join(self.data_path, "tests", problem_id)
        if os.path.exists(test_dir) and os.path.isdir(test_dir):
            try:
                # Support two formats: .in/.out and I./O.
                input_files = []
                for f in os.listdir(test_dir):
                    if f.endswith('.in') or f.startswith('I.'):
                        input_files.append(f)
                input_files.sort()
                
                for input_file in input_files:
                    if input_file.endswith('.in'):
                        output_file = input_file.replace('.in', '.out')
                    else:
                        output_file = 'O.' + input_file[2:]
                        
                    if os.path.exists(os.path.join(test_dir, output_file)):
                        try:
                            with open(os.path.join(test_dir, input_file), 'r') as f_in:
                                input_data = f_in.read()
                            with open(os.path.join(test_dir, output_file), 'r') as f_out:
                                output_data = f_out.read()
                            
                            case = TestCase(
                                id=generate_id(),
                                input_data=input_data,
                                expected_output=output_data
                            )
                            test_cases.append(case)
                        except Exception as e:
                            print(f"Error reading test case {input_file}: {e}")
            except FileNotFoundError:
                # Just skip loading additional test cases if directory doesn't exist
                pass
        
        # Determine difficulty level
        level_str = problem_data.get('problem_level', 'bronze').lower()
        if level_str == 'bronze':
            level = Level.BRONZE
        elif level_str == 'silver':
            level = Level.SILVER
        elif level_str == 'gold':
            level = Level.GOLD
        elif level_str == 'platinum':
            level = Level.PLATINUM
        else:
            level = Level.BRONZE
        
        # Ensure we have at least one test case
        if not test_cases and sample_cases:
            test_cases = sample_cases.copy()  # Use samples as test cases if no other test cases
        
        # Create Problem object
        problem = Problem(
            id=problem_id,
            title=problem_data.get('name', ''),
            description=problem_data.get('description', ''),
            level=level,
            test_cases=test_cases,
            sample_cases=sample_cases,
            time_limit_ms=problem_data.get('runtime_limit', 1)*1000,
            memory_limit_mb=problem_data.get('memory_limit', 256)
        )
        
        return problem
    
    def import_problems_to_competition(self, competition, problem_ids: List[str]) -> int:
        """Import multiple problems to a competition"""
        count = 0
        for pid in problem_ids:
            problem = self.load_problem(pid)
            if problem:
                competition.problems.append(problem)
                count += 1
        return count