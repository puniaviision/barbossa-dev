#!/usr/bin/env python3
"""
Test script for new API endpoints
Tests the functionality of the newly implemented API modules
"""

import requests
import json
import time
import sys
from pathlib import Path
import subprocess

# Configuration
BASE_URL = "http://localhost:8443"  # Adjust port as needed
API_ENDPOINTS = {
    'advanced_api': '/api/v3',
    'monitoring_api': '/api/monitoring',
    'devtools_api': '/api/devtools'
}

def test_endpoint(url, method='GET', data=None, expected_status=200):
    """Test a single endpoint"""
    try:
        print(f"Testing {method} {url}")
        
        if method == 'GET':
            response = requests.get(url, timeout=10, verify=False)
        elif method == 'POST':
            response = requests.post(url, json=data, timeout=10, verify=False)
        elif method == 'PUT':
            response = requests.put(url, json=data, timeout=10, verify=False)
        elif method == 'DELETE':
            response = requests.delete(url, timeout=10, verify=False)
        else:
            print(f"  ❌ Unsupported method: {method}")
            return False
        
        if response.status_code == expected_status:
            print(f"  ✅ Success: {response.status_code}")
            return True
        else:
            print(f"  ❌ Expected {expected_status}, got {response.status_code}")
            if response.text:
                print(f"     Response: {response.text[:200]}...")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"  ❌ Request failed: {e}")
        return False
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return False

def test_advanced_api():
    """Test advanced API endpoints"""
    print("\n=== Testing Advanced API (v3) ===")
    base_url = f"{BASE_URL}{API_ENDPOINTS['advanced_api']}"
    
    tests = [
        # Documentation and health
        (f"{base_url}/docs", 'GET'),
        (f"{base_url}/health", 'GET'),
        (f"{base_url}/status/summary", 'GET'),
        
        # Analytics (may fail if no data)
        (f"{base_url}/analytics/trends?metric=cpu_percent&hours=1", 'GET', None, [200, 400, 404]),
        (f"{base_url}/analytics/performance-score", 'GET'),
        
        # Backup operations
        (f"{base_url}/backup/list", 'GET'),
        (f"{base_url}/backup/create", 'POST', {
            'backup_type': 'config',
            'compress': True
        }),
        
        # Database operations
        (f"{base_url}/database/info", 'GET'),
        
        # Optimization
        (f"{base_url}/optimization/recommendations", 'GET'),
        
        # Workflow templates
        (f"{base_url}/workflows/templates", 'GET'),
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        url, method = test[0], test[1]
        data = test[2] if len(test) > 2 else None
        expected = test[3] if len(test) > 3 else 200
        
        if isinstance(expected, list):
            # Multiple acceptable status codes
            success = False
            for status in expected:
                if test_endpoint(url, method, data, status):
                    success = True
                    break
            if success:
                passed += 1
        else:
            if test_endpoint(url, method, data, expected):
                passed += 1
    
    print(f"\nAdvanced API Results: {passed}/{total} tests passed")
    return passed == total

def test_monitoring_api():
    """Test monitoring API endpoints"""
    print("\n=== Testing Monitoring API ===")
    base_url = f"{BASE_URL}{API_ENDPOINTS['monitoring_api']}"
    
    tests = [
        # Basic endpoints
        (f"{base_url}/health", 'GET'),
        (f"{base_url}/config", 'GET'),
        (f"{base_url}/dashboard/summary", 'GET'),
        
        # Metrics
        (f"{base_url}/metrics/live", 'GET'),
        (f"{base_url}/metrics/baseline", 'GET'),
        
        # Monitors
        (f"{base_url}/monitors", 'GET'),
        (f"{base_url}/monitors", 'POST', {
            'name': 'Test CPU Monitor',
            'type': 'metric_threshold',
            'config': {
                'metric': 'cpu_percent',
                'threshold': 80,
                'operator': '>',
                'interval': 60
            }
        }),
        
        # Alerts
        (f"{base_url}/alerts", 'GET'),
        
        # Observability
        (f"{base_url}/observability/traces", 'GET'),
        (f"{base_url}/observability/dependencies", 'GET'),
    ]
    
    passed = 0
    total = len(tests)
    
    for url, method, *rest in tests:
        data = rest[0] if rest else None
        expected = rest[1] if len(rest) > 1 else 200
        
        if test_endpoint(url, method, data, expected):
            passed += 1
    
    print(f"\nMonitoring API Results: {passed}/{total} tests passed")
    return passed == total

def test_devtools_api():
    """Test development tools API endpoints"""
    print("\n=== Testing Development Tools API ===")
    base_url = f"{BASE_URL}{API_ENDPOINTS['devtools_api']}"
    
    tests = [
        # Basic endpoints
        (f"{base_url}/health", 'GET'),
        
        # Projects
        (f"{base_url}/projects", 'GET'),
        
        # Build history
        (f"{base_url}/builds", 'GET'),
        
        # Workflow templates
        (f"{base_url}/workflow/templates", 'GET'),
        
        # Project analysis (may fail if no valid projects)
        (f"{base_url}/projects", 'POST', {
            'project_path': str(Path.home() / 'barbossa-engineer' / 'projects' / 'davy-jones-intern')
        }, [200, 403, 404]),
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        url, method = test[0], test[1]
        data = test[2] if len(test) > 2 else None
        expected = test[3] if len(test) > 3 else 200
        
        if isinstance(expected, list):
            # Multiple acceptable status codes
            success = False
            for status in expected:
                if test_endpoint(url, method, data, status):
                    success = True
                    break
            if success:
                passed += 1
        else:
            if test_endpoint(url, method, data, expected):
                passed += 1
    
    print(f"\nDevelopment Tools API Results: {passed}/{total} tests passed")
    return passed == total

def check_server_running():
    """Check if the web portal server is running"""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5, verify=False)
        return response.status_code in [200, 404]  # 404 is fine, means server is running
    except:
        return False

def main():
    """Main test function"""
    print("🧪 Testing New API Endpoints")
    print("=" * 50)
    
    # Check if server is running
    if not check_server_running():
        print(f"❌ Server not running at {BASE_URL}")
        print("Please start the web portal server first:")
        print("cd ~/barbossa-engineer/web_portal && python3 app.py")
        sys.exit(1)
    
    print(f"✅ Server is running at {BASE_URL}")
    
    # Run tests
    results = []
    
    try:
        results.append(test_advanced_api())
        results.append(test_monitoring_api())
        results.append(test_devtools_api())
    except KeyboardInterrupt:
        print("\n\n🛑 Tests interrupted by user")
        sys.exit(1)
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Summary")
    print("=" * 50)
    
    total_passed = sum(results)
    total_tests = len(results)
    
    if total_passed == total_tests:
        print(f"✅ All {total_tests} API modules passed their tests!")
    else:
        print(f"⚠️  {total_passed}/{total_tests} API modules passed their tests")
    
    # Individual results
    api_names = ['Advanced API', 'Monitoring API', 'Development Tools API']
    for i, (name, passed) in enumerate(zip(api_names, results)):
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {name}: {status}")
    
    # Additional recommendations
    print("\n📝 Recommendations:")
    print("  • Check server logs for any error details")
    print("  • Verify all required dependencies are installed")
    print("  • Test endpoints manually with curl or Postman")
    print("  • Review API documentation at /api/v3/docs")
    
    return total_passed == total_tests

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)