#!/usr/bin/env python3
"""
Comprehensive test script for CompeteMAS server API endpoints.
This script tests all functions in server.py systematically.
"""

import requests
import json
import time
import sys
from typing import Dict, List, Any, Optional

# Configuration
API_BASE = "http://localhost:5000"
TIMEOUT = 30

# Test data
TEST_COMPETITION = {
    "title": "Test Competition 2025",
    "description": "A comprehensive test competition",
    "problem_ids": ["1524_platinum_forklift_certified"],
    "max_tokens_per_participant": 10000,
    "rules": {
        "scoring": {"bronze": 100, "silver": 200, "gold": 500},
        "penalties": {"AC": 0, "WA": 10, "RE": 10, "CE": 5, "TLE": 10, "MLE": 10},
        "hint_tokens": {"level_1": 500, "level_2": 1000, "level_3": 1500},
        "submission_tokens": {"AC": 100, "WA": 100, "RE": 100, "CE": 100, "TLE": 100, "MLE": 100},
        "lambda": 100
    }
}

TEST_PARTICIPANT = {
    "name": "TestParticipant",
    "api_base_url": "http://100.76.8.43:10086/",
    "api_key": "sk-EFhZxTqkXfedmKP_yxB8-XIisFkXQ7JGL6sunBI3XBfQfinP3oBgl5wzqDw",
    "limit_tokens": 5000,
    "lambda_value": 100
}

TEST_SUBMISSION = {
    "code": """
#include <iostream>
using namespace std;

int main() {
    int n;
    cin >> n;
    cout << n * 2 << endl;
    return 0;
}
""",
    "language": "cpp"
}

class ServerTester:
    def __init__(self, api_base: str = API_BASE):
        self.api_base = api_base
        self.competition_id = None
        self.participant_id = None
        self.problem_id = None
        self.submission_id = None
        self.test_results = []
        
    def log_test(self, test_name: str, success: bool, message: str = "", data: Any = None):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if message:
            print(f"   {message}")
        if data and not success:
            print(f"   Data: {data}")
        print()
        
        self.test_results.append({
            "test": test_name,
            "success": success,
            "message": message,
            "data": data
        })
    
    def make_request(self, method: str, endpoint: str, data: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict:
        """Make HTTP request and return response"""
        url = f"{self.api_base}{endpoint}"
        headers = {"Content-Type": "application/json"}
        
        try:
            if method.upper() == "GET":
                response = requests.get(url, params=params, timeout=TIMEOUT)
            elif method.upper() == "POST":
                response = requests.post(url, json=data, headers=headers, timeout=TIMEOUT)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            return {
                "status_code": response.status_code,
                "data": response.json() if response.content else None,
                "success": response.status_code < 400
            }
        except Exception as e:
            return {
                "status_code": 0,
                "data": {"error": str(e)},
                "success": False
            }
    
    def test_oj_status(self):
        """Test OJ status endpoint"""
        print("=== Testing OJ Status ===")
        
        result = self.make_request("GET", "/api/system/oj-status")
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        self.log_test(
            "OJ Status Check",
            success,
            f"Status: {result['status_code']}, Connected: {result['data'].get('data', {}).get('connected', 'Unknown') if result['data'] else 'Unknown'}"
        )
    
    def test_problem_library(self):
        """Test problem library endpoints"""
        print("=== Testing Problem Library ===")
        
        # Test list problem library
        result = self.make_request("GET", "/api/problem-library")
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        problems = result["data"].get("data", []) if result["data"] else []
        self.log_test(
            "List Problem Library",
            success,
            f"Found {len(problems)} problems"
        )
        
        # Test with level filter
        if problems:
            result = self.make_request("GET", "/api/problem-library", params={"level": "bronze"})
            success = result["success"] and result["data"] and result["data"].get("status") == "success"
            
            filtered_problems = result["data"].get("data", []) if result["data"] else []
            self.log_test(
                "List Problem Library (Bronze Level)",
                success,
                f"Found {len(filtered_problems)} bronze problems"
            )
        
    
    def test_similar_problems(self):
        """Test similar problems endpoint"""
        print("=== Testing Similar Problems ===")
        
        # Test with valid problem ID
        result = self.make_request("GET", "/api/problems/similar", params={
            "problem_id": "1524_platinum_forklift_certified",
            "num_problems": 2
        })
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        similar_problems = result["data"].get("data", []) if result["data"] else []
        self.log_test(
            "Get Similar Problems",
            success,
            f"Found {len(similar_problems)} similar problems"
        )
        
        # Test with invalid problem ID
        result = self.make_request("GET", "/api/problems/similar", params={
            "problem_id": "invalid_problem",
            "num_problems": 2
        })
        success = not result["success"]  # Should fail
        self.log_test(
            "Get Similar Problems (Invalid ID)",
            success,
            "Correctly rejected invalid problem ID"
        )
        # print(result)
    
    def test_textbook_search(self):
        """Test textbook search endpoint"""
        print("=== Testing Textbook Search ===")
        
        # Test with valid query
        result = self.make_request("GET", "/api/textbook/search", params={
            "query": "algorithm",
            "max_results": 1
        })
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        search_results = result["data"].get("data", []) if result["data"] else []
        self.log_test(
            "Textbook Search",
            success,
            f"Found {len(search_results)} results"
        )
        
        # Test with empty query
        result = self.make_request("GET", "/api/textbook/search", params={
            "query": "",
            "max_results": 1
        })
        success = not result["success"]  # Should fail
        self.log_test(
            "Textbook Search (Empty Query)",
            success,
            "Correctly rejected empty query"
        )
        # print(result)
    
    def test_competition_creation(self):
        """Test competition creation"""
        print("=== Testing Competition Creation ===")
        
        result = self.make_request("POST", "/api/competitions/create", TEST_COMPETITION)
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        print(result)
        if success:
            self.competition_id = result["data"]["data"]["competition"]["id"]
            self.log_test(
                "Create Competition",
                success,
                f"Created competition: {self.competition_id}"
            )
        else:
            self.log_test(
                "Create Competition",
                success,
                "Failed to create competition"
            )
    
    def test_competition_operations(self):
        """Test competition get and list operations"""
        print("=== Testing Competition Operations ===")
        
        if not self.competition_id:
            self.log_test("Get Competition", False, "No competition ID available")
            return
        
        # Test get competition
        result = self.make_request("GET", f"/api/competitions/get/{self.competition_id}")
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        self.log_test(
            "Get Competition",
            success,
            f"Retrieved competition: {self.competition_id}"
        )
        
        # Test get competition with details
        result = self.make_request("GET", f"/api/competitions/get/{self.competition_id}", 
                                 params={"include_details": "true"})
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        details = result["data"].get("data", {}) if result["data"] else {}
        self.log_test(
            "Get Competition (with details)",
            success,
            f"Problems: {len(details.get('problems', []))}, Participants: {len(details.get('participants', []))}"
        )
        print(result)
        
        # Test list competitions
        result = self.make_request("GET", "/api/competitions/list")
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        competitions = result["data"].get("data", []) if result["data"] else []
        self.log_test(
            "List Competitions",
            success,
            f"Found {len(competitions)} competitions"
        )
        
        # Test list active competitions
        result = self.make_request("GET", "/api/competitions/list", params={"active_only": "true"})
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        active_competitions = result["data"].get("data", []) if result["data"] else []
        self.log_test(
            "List Active Competitions",
            success,
            f"Found {len(active_competitions)} active competitions"
        )
    
    def test_participant_creation(self):
        """Test participant creation"""
        print("=== Testing Participant Creation ===")
        
        if not self.competition_id:
            self.log_test("Create Participant", False, "No competition ID available")
            return
        
        result = self.make_request("POST", f"/api/participants/create/{self.competition_id}", TEST_PARTICIPANT)
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        if success:
            self.participant_id = result["data"]["data"]["id"]
            self.log_test(
                "Create Participant",
                success,
                f"Created participant: {self.participant_id}"
            )
        else:
            self.log_test(
                "Create Participant",
                success,
                "Failed to create participant"
            )
    
    def test_participant_operations(self):
        """Test participant operations"""
        print("=== Testing Participant Operations ===")
        
        if not self.competition_id or not self.participant_id:
            self.log_test("Get Participant", False, "No competition or participant ID available")
            return
        
        # Test get participant
        result = self.make_request("GET", f"/api/participants/get/{self.competition_id}/{self.participant_id}")
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        self.log_test(
            "Get Participant",
            success,
            f"Retrieved participant: {self.participant_id}"
        )
        
        # Test get participant with submissions
        result = self.make_request("GET", f"/api/participants/get/{self.competition_id}/{self.participant_id}",
                                 params={"include_submissions": "true"})
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        participant_data = result["data"].get("data", {}) if result["data"] else {}
        self.log_test(
            "Get Participant (with submissions)",
            success,
            f"Submissions: {len(participant_data.get('submissions', []))}"
        )
        
        # Test list participants
        result = self.make_request("GET", f"/api/participants/list/{self.competition_id}")
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        participants = result["data"].get("data", []) if result["data"] else []
        self.log_test(
            "List Participants",
            success,
            f"Found {len(participants)} participants"
        )
    
    def test_problem_operations(self):
        """Test problem operations"""
        print("=== Testing Problem Operations ===")
        
        if not self.competition_id:
            self.log_test("Get Problem", False, "No competition ID available")
            return
        
        # Test list problems
        result = self.make_request("GET", f"/api/problems/list/{self.competition_id}")
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        problems = result["data"].get("data", []) if result["data"] else []
        self.log_test(
            "List Problems",
            success,
            f"Found {len(problems)} problems"
        )
        
        if problems:
            self.problem_id = problems[0]["id"]
            
            # Test get problem
            result = self.make_request("GET", f"/api/problems/get/{self.competition_id}/{self.problem_id}")
            success = result["success"] and result["data"] and result["data"].get("status") == "success"
            
            self.log_test(
                "Get Problem",
                success,
                f"Retrieved problem: {self.problem_id}"
            )
        else:
            self.log_test("Get Problem", False, "No problems available")
    
    def test_submission_creation(self):
        """Test submission creation"""
        print("=== Testing Submission Creation ===")
        
        if not self.competition_id or not self.participant_id or not self.problem_id:
            self.log_test("Create Submission", False, "Missing competition, participant, or problem ID")
            return
        
        result = self.make_request("POST", f"/api/submissions/create/{self.competition_id}/{self.participant_id}/{self.problem_id}", 
                                 TEST_SUBMISSION)
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        if success:
            self.submission_id = result["data"]["data"]["submission_id"]
            self.log_test(
                "Create Submission",
                success,
                f"Created submission: {self.submission_id}"
            )
        else:
            self.log_test(
                "Create Submission",
                success,
                "Failed to create submission"
            )
    
    def test_submission_operations(self):
        """Test submission operations"""
        print("=== Testing Submission Operations ===")
        
        if not self.competition_id:
            self.log_test("List Submissions", False, "No competition ID available")
            return
        
        # Test list submissions
        result = self.make_request("GET", f"/api/submissions/list/{self.competition_id}")
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        submissions = result["data"].get("data", []) if result["data"] else []
        self.log_test(
            "List Submissions",
            success,
            f"Found {len(submissions)} submissions"
        )
        
        # Test list submissions with filters
        if self.participant_id:
            result = self.make_request("GET", f"/api/submissions/list/{self.competition_id}",
                                     params={"participant_id": self.participant_id})
            success = result["success"] and result["data"] and result["data"].get("status") == "success"
            
            filtered_submissions = result["data"].get("data", []) if result["data"] else []
            self.log_test(
                "List Submissions (by participant)",
                success,
                f"Found {len(filtered_submissions)} submissions for participant"
            )
        
        if self.problem_id:
            result = self.make_request("GET", f"/api/submissions/list/{self.competition_id}",
                                     params={"problem_id": self.problem_id})
            success = result["success"] and result["data"] and result["data"].get("status") == "success"
            
            filtered_submissions = result["data"].get("data", []) if result["data"] else []
            self.log_test(
                "List Submissions (by problem)",
                success,
                f"Found {len(filtered_submissions)} submissions for problem"
            )
        
        # Test get submission
        if self.submission_id:
            result = self.make_request("GET", f"/api/submissions/get/{self.submission_id}")
            success = result["success"] and result["data"] and result["data"].get("status") == "success"
            
            self.log_test(
                "Get Submission",
                success,
                f"Retrieved submission: {self.submission_id}"
            )
            
            # Test get submission with code
            result = self.make_request("GET", f"/api/submissions/get/{self.submission_id}",
                                     params={"include_code": "true"})
            success = result["success"] and result["data"] and result["data"].get("status") == "success"
            
            self.log_test(
                "Get Submission (with code)",
                success,
                "Retrieved submission with code"
            )
    
    def test_rankings(self):
        """Test rankings endpoint"""
        print("=== Testing Rankings ===")
        
        if not self.competition_id:
            self.log_test("Get Rankings", False, "No competition ID available")
            return
        
        result = self.make_request("GET", f"/api/rankings/get/{self.competition_id}")
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        rankings = result["data"].get("data", []) if result["data"] else []
        self.log_test(
            "Get Rankings",
            success,
            f"Found {len(rankings)} ranked participants"
        )
    
    def test_hint_system(self):
        """Test hint system"""
        print("=== Testing Hint System ===")
        
        if not self.competition_id or not self.participant_id or not self.problem_id:
            self.log_test("Get Hint", False, "Missing competition, participant, or problem ID")
            return
        
        # Test level 1 hint
        result = self.make_request("POST", f"/api/hints/get/{self.competition_id}/{self.participant_id}/{self.problem_id}",
                                 {"hint_level": 1})
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        if success:
            hint_data = result["data"]["data"]
            self.log_test(
                "Get Hint (Level 1)",
                success,
                f"Token cost: {hint_data.get('tokens_cost')}, Remaining: {hint_data.get('remaining_tokens')}"
            )
        else:
            self.log_test(
                "Get Hint (Level 1)",
                success,
                "Failed to get hint"
            )
        
        # Test invalid hint level
        result = self.make_request("POST", f"/api/hints/get/{self.competition_id}/{self.participant_id}/{self.problem_id}",
                                 {"hint_level": 4})
        success = not result["success"]  # Should fail
        self.log_test(
            "Get Hint (Invalid Level)",
            success,
            "Correctly rejected invalid hint level"
        )
    
    def test_agent_system(self):
        """Test agent system"""
        print("=== Testing Agent System ===")
        
        if not self.competition_id or not self.participant_id:
            self.log_test("Agent Request", False, "Missing competition or participant ID")
            return
        
        # Test agent request
        agent_request = {
            "json": {
                "model": "sf-deepseek-v3",
                "messages": [{"role": "user", "content": "Hello, this is a test message."}],
                "limit_tokens": 50
            },
            "timeout": 10.0
        }
        
        result = self.make_request("POST", f"/api/agent/call/{self.competition_id}/{self.participant_id}", agent_request)
        success = result["success"] and result["data"]
        print(result)
        
        self.log_test(
            "Agent Request",
            success,
            "Agent request processed"
        )
        
        # Test streaming agent request
        stream_request = {
            "json": {
                "model": "sf-deepseek-v3",
                "messages": [{"role": "user", "content": "Hello, this is a streaming test."}],
                "limit_tokens": 50,
                "stream": True
            },
            "timeout": 10.0
        }
        
        result = self.make_request("POST", f"/api/stream_agent/call/{self.competition_id}/{self.participant_id}", stream_request)
        success = result["success"] and result["data"]
        print(result)
        
        self.log_test(
            "Streaming Agent Request",
            success,
            "Streaming agent request processed"
        )
        
    
    def test_participant_termination(self):
        """Test participant termination"""
        print("=== Testing Participant Termination ===")
        
        if not self.competition_id or not self.participant_id:
            self.log_test("Terminate Participant", False, "Missing competition or participant ID")
            return
        
        # Test participant status
        result = self.make_request("GET", f"/api/participants/status/{self.competition_id}/{self.participant_id}")
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        # print(result)

        status_data = result["data"].get("data", {}) if result["data"] else {}
        self.log_test(
            "Get Participant Status",
            success,
            f"Running: {status_data.get('is_running', 'Unknown')}, Tokens: {status_data.get('remaining_tokens', 'Unknown')}"
        )
        
        # Test terminate participant
        result = self.make_request("POST", f"/api/participants/terminate/{self.competition_id}/{self.participant_id}",
                                 {"reason": "test_termination"})
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        print(result)
        self.log_test(
            "Terminate Participant",
            success,
            "Participant terminated for testing"
        )
        
        # Test list terminated participants
        result = self.make_request("GET", f"/api/participants/terminated/{self.competition_id}")
        success = result["success"] and result["data"] and result["data"].get("status") == "success"
        
        terminated_participants = result["data"].get("data", []) if result["data"] else []
        self.log_test(
            "List Terminated Participants",
            success,
            f"Found {len(terminated_participants)} terminated participants"
        )
    
    def run_all_tests(self):
        """Run all tests in sequence"""
        print("🚀 Starting Comprehensive Server Tests")
        print("=" * 60)
        
        # System tests
        self.test_oj_status()
        
        # Problem library tests
        self.test_problem_library()
        self.test_similar_problems()
        self.test_textbook_search()
        
        # Competition tests
        self.test_competition_creation()
        self.test_competition_operations()
        
        # Participant tests
        self.test_participant_creation()
        self.test_participant_operations()
        
        # Problem tests
        self.test_problem_operations()
        
        # Submission tests
        self.test_submission_creation()
        self.test_submission_operations()
        
        # Ranking tests
        self.test_rankings()
        
        # Hint tests
        self.test_hint_system()
        
        # Agent tests
        self.test_agent_system()
        
        # Termination tests
        self.test_participant_termination()
        
        # Print summary
        self.print_summary()
    
    def print_summary(self):
        """Print test summary"""
        print("=" * 60)
        print("📊 TEST SUMMARY")
        print("=" * 60)
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result["success"])
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"✅ Passed: {passed_tests}")
        print(f"❌ Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        if failed_tests > 0:
            print("\n❌ Failed Tests:")
            for result in self.test_results:
                if not result["success"]:
                    print(f"  - {result['test']}: {result['message']}")
        
        print("\n🎯 Test IDs Created:")
        if self.competition_id:
            print(f"  Competition: {self.competition_id}")
        if self.participant_id:
            print(f"  Participant: {self.participant_id}")
        if self.problem_id:
            print(f"  Problem: {self.problem_id}")
        if self.submission_id:
            print(f"  Submission: {self.submission_id}")

def main():
    """Main function"""
    print("🔧 CompeteMAS Server Comprehensive Test Suite")
    print("=" * 60)
    
    # Check if server is running
    try:
        response = requests.get(f"{API_BASE}/api/system/oj-status", timeout=5)
        if response.status_code != 200:
            print(f"❌ Server not responding properly. Status: {response.status_code}")
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"❌ Cannot connect to server at {API_BASE}")
        print(f"   Error: {e}")
        print(f"   Make sure the server is running on {API_BASE}")
        sys.exit(1)
    
    print(f"✅ Server is running at {API_BASE}")
    print()
    
    # Run tests
    tester = ServerTester()
    tester.run_all_tests()

if __name__ == "__main__":
    main() 