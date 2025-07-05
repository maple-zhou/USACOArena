#!/usr/bin/env python3
"""
Quick test script for CompeteMAS server API endpoints.
This script provides a fast way to verify server functionality.
"""

import requests
import json
import sys

# Configuration
API_BASE = "http://localhost:5000"
TIMEOUT = 10

def test_endpoint(method, endpoint, data=None, params=None, expected_status=200):
    """Test a single endpoint"""
    url = f"{API_BASE}{endpoint}"
    headers = {"Content-Type": "application/json"}
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, params=params, timeout=TIMEOUT)
        elif method.upper() == "POST":
            response = requests.post(url, json=data, headers=headers, timeout=TIMEOUT)
        else:
            print(f"❌ Unsupported method: {method}")
            return False
        
        success = response.status_code == expected_status
        status = "✅" if success else "❌"
        print(f"{status} {method} {endpoint} - {response.status_code}")
        
        if not success and response.content:
            try:
                error_data = response.json()
                print(f"   Error: {error_data.get('message', 'Unknown error')}")
            except:
                print(f"   Error: {response.text[:100]}...")
        
        return success
        
    except Exception as e:
        print(f"❌ {method} {endpoint} - Exception: {str(e)}")
        return False

def main():
    """Run quick tests"""
    print("🚀 Quick Server Test")
    print("=" * 40)
    
    # Check server connection
    print("Testing server connection...")
    if not test_endpoint("GET", "/api/system/oj-status"):
        print("❌ Server not responding. Make sure it's running on", API_BASE)
        sys.exit(1)
    
    print("\nTesting basic endpoints...")
    
    # System endpoints
    test_endpoint("GET", "/api/system/oj-status")
    
    # Problem library endpoints
    test_endpoint("GET", "/api/problem-library")
    test_endpoint("GET", "/api/problem-library", params={"level": "bronze"})
    
    # Similar problems - first get a valid problem ID
    library_response = requests.get(f"{API_BASE}/api/problem-library", timeout=TIMEOUT)
    if library_response.status_code == 200:
        library_data = library_response.json()
        if library_data.get("status") == "success" and library_data.get("data"):
            problems = library_data["data"]
            if problems:
                valid_problem_id = problems[0]["id"]
                test_endpoint("GET", "/api/problems/similar", params={
                    "problem_id": valid_problem_id,
                    "num_problems": 2
                })
            else:
                print("❌ No problems available in library")
        else:
            print("❌ Failed to get problem library")
    else:
        print("❌ Failed to get problem library")
    
    # Textbook search
    test_endpoint("GET", "/api/textbook/search", params={"query": "algorithm", "max_results": 3})
    
    # Competition endpoints
    test_endpoint("GET", "/api/competitions/list")
    test_endpoint("GET", "/api/competitions/list", params={"active_only": "true"})
    
    print("\n✅ Quick test completed!")
    print("For comprehensive testing, run: python test_server_comprehensive.py")

if __name__ == "__main__":
    main() 