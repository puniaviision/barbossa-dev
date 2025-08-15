#!/usr/bin/env python3
"""
Comprehensive Test Suite for Enhanced API v2 Endpoints
Tests all new API endpoints for functionality, error handling, and performance
"""

import json
import time
import uuid
import requests
import sqlite3
from pathlib import Path
from datetime import datetime
import tempfile
import shutil
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EnhancedAPITester:
    def __init__(self, base_url='http://localhost:8443', username='admin', password='admin'):
        self.base_url = base_url
        self.auth = (username, password)
        self.session = requests.Session()
        self.session.auth = self.auth
        self.session.verify = False  # For self-signed certificates
        
        # Disable SSL warnings for testing
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Test data storage
        self.test_project_id = None
        self.test_task_id = None
        self.test_backup_id = None
        self.test_webhook_id = None
        self.test_alert_id = None
        
        # Test results
        self.results = {
            'passed': 0,
            'failed': 0,
            'errors': [],
            'test_details': []
        }

    def log_test(self, test_name, status, details=None, error=None):
        """Log test result"""
        self.results['test_details'].append({
            'test': test_name,
            'status': status,
            'details': details,
            'error': error,
            'timestamp': datetime.now().isoformat()
        })
        
        if status == 'PASS':
            self.results['passed'] += 1
            logger.info(f"✓ {test_name}")
        else:
            self.results['failed'] += 1
            logger.error(f"✗ {test_name}: {error}")
            self.results['errors'].append(f"{test_name}: {error}")

    def make_request(self, method, endpoint, **kwargs):
        """Make HTTP request with error handling"""
        url = f"{self.base_url}/api/v2{endpoint}"
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
            return response
        except Exception as e:
            raise Exception(f"Request failed: {e}")

    def test_projects_crud(self):
        """Test project CRUD operations"""
        # Create project
        project_data = {
            "name": "Test Project API",
            "description": "Test project for API validation",
            "status": "active",
            "priority": 3,
            "tags": ["test", "api"]
        }
        
        response = self.make_request('POST', '/projects', json=project_data)
        if response.status_code == 201:
            data = response.json()
            self.test_project_id = data['project']['id']
            self.log_test('Create Project', 'PASS', f"Created project {self.test_project_id}")
        else:
            self.log_test('Create Project', 'FAIL', error=f"Status {response.status_code}: {response.text}")
            return

        # Get project
        response = self.make_request('GET', f'/projects/{self.test_project_id}')
        if response.status_code == 200:
            self.log_test('Get Project', 'PASS')
        else:
            self.log_test('Get Project', 'FAIL', error=f"Status {response.status_code}")

        # Update project
        update_data = {"description": "Updated description"}
        response = self.make_request('PUT', f'/projects/{self.test_project_id}', json=update_data)
        if response.status_code == 200:
            self.log_test('Update Project', 'PASS')
        else:
            self.log_test('Update Project', 'FAIL', error=f"Status {response.status_code}")

        # List projects
        response = self.make_request('GET', '/projects?limit=10')
        if response.status_code == 200:
            data = response.json()
            if 'projects' in data:
                self.log_test('List Projects', 'PASS', f"Found {len(data['projects'])} projects")
            else:
                self.log_test('List Projects', 'FAIL', error="No projects in response")
        else:
            self.log_test('List Projects', 'FAIL', error=f"Status {response.status_code}")

    def test_tasks_crud(self):
        """Test task CRUD operations"""
        if not self.test_project_id:
            self.log_test('Task CRUD', 'SKIP', error="No project ID available")
            return

        # Create task
        task_data = {
            "title": "Test Task API",
            "description": "Test task for API validation",
            "project_id": self.test_project_id,
            "status": "pending",
            "priority": 2,
            "tags": ["test"]
        }
        
        response = self.make_request('POST', '/tasks', json=task_data)
        if response.status_code == 201:
            data = response.json()
            self.test_task_id = data['task']['id']
            self.log_test('Create Task', 'PASS', f"Created task {self.test_task_id}")
        else:
            self.log_test('Create Task', 'FAIL', error=f"Status {response.status_code}: {response.text}")
            return

        # Get task
        response = self.make_request('GET', f'/tasks/{self.test_task_id}')
        if response.status_code == 200:
            self.log_test('Get Task', 'PASS')
        else:
            self.log_test('Get Task', 'FAIL', error=f"Status {response.status_code}")

        # Update task
        update_data = {"status": "in_progress"}
        response = self.make_request('PUT', f'/tasks/{self.test_task_id}', json=update_data)
        if response.status_code == 200:
            self.log_test('Update Task', 'PASS')
        else:
            self.log_test('Update Task', 'FAIL', error=f"Status {response.status_code}")

    def test_system_endpoints(self):
        """Test system monitoring endpoints"""
        # Test metrics
        response = self.make_request('GET', '/system/metrics')
        if response.status_code == 200:
            data = response.json()
            if 'metrics' in data:
                self.log_test('System Metrics', 'PASS', f"Retrieved metrics with {len(data['metrics'])} categories")
            else:
                self.log_test('System Metrics', 'FAIL', error="No metrics in response")
        else:
            self.log_test('System Metrics', 'FAIL', error=f"Status {response.status_code}")

        # Test health
        response = self.make_request('GET', '/system/health')
        if response.status_code == 200:
            data = response.json()
            if 'health' in data:
                self.log_test('System Health', 'PASS', f"Health status: {data['health']['overall_status']}")
            else:
                self.log_test('System Health', 'FAIL', error="No health data in response")
        else:
            self.log_test('System Health', 'FAIL', error=f"Status {response.status_code}")

        # Test processes
        response = self.make_request('GET', '/system/processes?limit=5')
        if response.status_code == 200:
            data = response.json()
            if 'processes' in data:
                self.log_test('System Processes', 'PASS', f"Found {len(data['processes'])} processes")
            else:
                self.log_test('System Processes', 'FAIL', error="No processes in response")
        else:
            self.log_test('System Processes', 'FAIL', error=f"Status {response.status_code}")

    def test_backup_endpoints(self):
        """Test backup and restore endpoints"""
        # Create backup
        backup_data = {
            "type": "config",
            "include_logs": False,
            "compression": "gzip"
        }
        
        response = self.make_request('POST', '/backup/create', json=backup_data)
        if response.status_code == 201:
            data = response.json()
            self.test_backup_id = data['backup']['id']
            self.log_test('Create Backup', 'PASS', f"Created backup {self.test_backup_id}")
        else:
            self.log_test('Create Backup', 'FAIL', error=f"Status {response.status_code}: {response.text}")
            return

        # List backups
        response = self.make_request('GET', '/backup/list')
        if response.status_code == 200:
            data = response.json()
            if 'backups' in data:
                self.log_test('List Backups', 'PASS', f"Found {len(data['backups'])} backups")
            else:
                self.log_test('List Backups', 'FAIL', error="No backups in response")
        else:
            self.log_test('List Backups', 'FAIL', error=f"Status {response.status_code}")

    def test_monitoring_endpoints(self):
        """Test real-time monitoring endpoints"""
        # Test real-time monitoring
        response = self.make_request('GET', '/monitoring/realtime')
        if response.status_code == 200:
            data = response.json()
            if 'metrics' in data:
                self.log_test('Real-time Monitoring', 'PASS', "Retrieved real-time metrics")
            else:
                self.log_test('Real-time Monitoring', 'FAIL', error="No metrics in response")
        else:
            self.log_test('Real-time Monitoring', 'FAIL', error=f"Status {response.status_code}")

        # Test alerts
        response = self.make_request('GET', '/monitoring/alerts')
        if response.status_code == 200:
            data = response.json()
            if 'alerts' in data:
                self.log_test('Get Alerts', 'PASS', f"Found {len(data['alerts'])} alerts")
            else:
                self.log_test('Get Alerts', 'FAIL', error="No alerts in response")
        else:
            self.log_test('Get Alerts', 'FAIL', error=f"Status {response.status_code}")

        # Create alert
        alert_data = {
            "name": "Test CPU Alert",
            "metric": "cpu",
            "threshold": 80,
            "severity": "high"
        }
        
        response = self.make_request('POST', '/monitoring/alerts', json=alert_data)
        if response.status_code == 201:
            data = response.json()
            self.test_alert_id = data['alert']['id']
            self.log_test('Create Alert', 'PASS', f"Created alert {self.test_alert_id}")
        else:
            self.log_test('Create Alert', 'FAIL', error=f"Status {response.status_code}: {response.text}")

    def test_search_endpoints(self):
        """Test search functionality"""
        # Test search
        response = self.make_request('GET', '/search?q=test&category=all&limit=10')
        if response.status_code == 200:
            data = response.json()
            if 'results' in data:
                total = data['total_results']
                self.log_test('Advanced Search', 'PASS', f"Found {total} results")
            else:
                self.log_test('Advanced Search', 'FAIL', error="No results in response")
        else:
            self.log_test('Advanced Search', 'FAIL', error=f"Status {response.status_code}")

    def test_analytics_endpoints(self):
        """Test analytics endpoints"""
        # Test analytics summary
        response = self.make_request('GET', '/analytics/summary?period=7d')
        if response.status_code == 200:
            data = response.json()
            if 'analytics' in data:
                self.log_test('Analytics Summary', 'PASS', "Retrieved analytics data")
            else:
                self.log_test('Analytics Summary', 'FAIL', error="No analytics in response")
        else:
            self.log_test('Analytics Summary', 'FAIL', error=f"Status {response.status_code}")

    def test_database_endpoints(self):
        """Test database management endpoints"""
        # Test database stats
        response = self.make_request('GET', '/database/stats')
        if response.status_code == 200:
            data = response.json()
            if 'database_stats' in data:
                self.log_test('Database Stats', 'PASS', f"Found {len(data['database_stats']['databases'])} databases")
            else:
                self.log_test('Database Stats', 'FAIL', error="No database stats in response")
        else:
            self.log_test('Database Stats', 'FAIL', error=f"Status {response.status_code}")

        # Test database optimization (dry run)
        optimize_data = {
            "database": "all",
            "operations": ["analyze"]
        }
        
        response = self.make_request('POST', '/database/optimize', json=optimize_data)
        if response.status_code == 200:
            data = response.json()
            if 'optimization_results' in data:
                self.log_test('Database Optimize', 'PASS', f"Optimized {len(data['optimization_results'])} databases")
            else:
                self.log_test('Database Optimize', 'FAIL', error="No optimization results in response")
        else:
            self.log_test('Database Optimize', 'FAIL', error=f"Status {response.status_code}")

    def test_integration_endpoints(self):
        """Test integration endpoints"""
        # Test webhook integration
        webhook_data = {
            "name": "Test Webhook",
            "url": "https://httpbin.org/post",
            "events": ["test.event"],
            "enabled": True
        }
        
        response = self.make_request('POST', '/integration/webhooks', json=webhook_data)
        if response.status_code == 201:
            data = response.json()
            self.test_webhook_id = data['webhook']['id']
            self.log_test('Create Webhook', 'PASS', f"Created webhook {self.test_webhook_id}")
        else:
            self.log_test('Create Webhook', 'FAIL', error=f"Status {response.status_code}: {response.text}")

        # Test get webhooks
        response = self.make_request('GET', '/integration/webhooks')
        if response.status_code == 200:
            data = response.json()
            if 'webhooks' in data:
                self.log_test('Get Webhooks', 'PASS', f"Found {len(data['webhooks'])} webhooks")
            else:
                self.log_test('Get Webhooks', 'FAIL', error="No webhooks in response")
        else:
            self.log_test('Get Webhooks', 'FAIL', error=f"Status {response.status_code}")

        # Test integration test
        test_data = {
            "type": "webhook",
            "url": "https://httpbin.org/post",
            "timeout": 10
        }
        
        response = self.make_request('POST', '/integration/test', json=test_data)
        if response.status_code == 200:
            data = response.json()
            if 'test_result' in data:
                success = data['test_result'].get('success', False)
                self.log_test('Test Integration', 'PASS' if success else 'FAIL', 
                             f"Test {'passed' if success else 'failed'}")
            else:
                self.log_test('Test Integration', 'FAIL', error="No test result in response")
        else:
            self.log_test('Test Integration', 'FAIL', error=f"Status {response.status_code}")

    def test_performance_endpoints(self):
        """Test performance monitoring endpoints"""
        # Test performance profile
        response = self.make_request('GET', '/performance/profile')
        if response.status_code == 200:
            data = response.json()
            if 'performance_profile' in data:
                self.log_test('Performance Profile', 'PASS', "Retrieved performance profile")
            else:
                self.log_test('Performance Profile', 'FAIL', error="No performance profile in response")
        else:
            self.log_test('Performance Profile', 'FAIL', error=f"Status {response.status_code}")

        # Test benchmark (quick)
        benchmark_data = {
            "type": "quick",
            "duration": 5,
            "tests": ["cpu", "memory"]
        }
        
        response = self.make_request('POST', '/performance/benchmark', json=benchmark_data)
        if response.status_code == 200:
            data = response.json()
            if 'benchmark_results' in data:
                test_count = len(data['benchmark_results']['tests'])
                self.log_test('Performance Benchmark', 'PASS', f"Completed {test_count} benchmark tests")
            else:
                self.log_test('Performance Benchmark', 'FAIL', error="No benchmark results in response")
        else:
            self.log_test('Performance Benchmark', 'FAIL', error=f"Status {response.status_code}")

        # Test performance recommendations
        response = self.make_request('GET', '/performance/recommendations')
        if response.status_code == 200:
            data = response.json()
            if 'recommendations' in data:
                rec_count = len(data['recommendations'])
                self.log_test('Performance Recommendations', 'PASS', f"Generated {rec_count} recommendations")
            else:
                self.log_test('Performance Recommendations', 'FAIL', error="No recommendations in response")
        else:
            self.log_test('Performance Recommendations', 'FAIL', error=f"Status {response.status_code}")

    def test_logs_endpoints(self):
        """Test log management endpoints"""
        # Test get logs
        response = self.make_request('GET', '/logs?type=all&limit=10')
        if response.status_code == 200:
            data = response.json()
            if 'logs' in data:
                self.log_test('Get Logs', 'PASS', f"Retrieved {len(data['logs'])} log entries")
            else:
                self.log_test('Get Logs', 'FAIL', error="No logs in response")
        else:
            self.log_test('Get Logs', 'FAIL', error=f"Status {response.status_code}")

        # Test get log files
        response = self.make_request('GET', '/logs/files')
        if response.status_code == 200:
            data = response.json()
            if 'log_files' in data:
                self.log_test('Get Log Files', 'PASS', f"Found {len(data['log_files'])} log files")
            else:
                self.log_test('Get Log Files', 'FAIL', error="No log files in response")
        else:
            self.log_test('Get Log Files', 'FAIL', error=f"Status {response.status_code}")

    def test_config_endpoints(self):
        """Test configuration management endpoints"""
        # Test get configuration
        response = self.make_request('GET', '/config')
        if response.status_code == 200:
            data = response.json()
            if 'configuration' in data:
                self.log_test('Get Configuration', 'PASS', f"Retrieved {len(data['configuration'])} config sections")
            else:
                self.log_test('Get Configuration', 'FAIL', error="No configuration in response")
        else:
            self.log_test('Get Configuration', 'FAIL', error=f"Status {response.status_code}")

    def test_notifications_endpoints(self):
        """Test notification endpoints"""
        # Create notification
        notification_data = {
            "title": "Test API Notification",
            "message": "This is a test notification from the API test suite",
            "severity": "info",
            "category": "test"
        }
        
        response = self.make_request('POST', '/notifications', json=notification_data)
        if response.status_code == 201:
            data = response.json()
            notification_id = data['notification']['id']
            self.log_test('Create Notification', 'PASS', f"Created notification {notification_id}")
            
            # Test get notifications
            response = self.make_request('GET', '/notifications?limit=10')
            if response.status_code == 200:
                data = response.json()
                if 'notifications' in data:
                    self.log_test('Get Notifications', 'PASS', f"Found {len(data['notifications'])} notifications")
                else:
                    self.log_test('Get Notifications', 'FAIL', error="No notifications in response")
            else:
                self.log_test('Get Notifications', 'FAIL', error=f"Status {response.status_code}")
        else:
            self.log_test('Create Notification', 'FAIL', error=f"Status {response.status_code}: {response.text}")

    def test_services_endpoints(self):
        """Test service management endpoints"""
        # Test get services
        response = self.make_request('GET', '/services')
        if response.status_code == 200:
            data = response.json()
            if 'system_services' in data:
                service_count = len(data['system_services'])
                process_count = len(data.get('barbossa_processes', []))
                self.log_test('Get Services', 'PASS', f"Found {service_count} services, {process_count} processes")
            else:
                self.log_test('Get Services', 'FAIL', error="No services in response")
        else:
            self.log_test('Get Services', 'FAIL', error=f"Status {response.status_code}")

    def test_metrics_endpoints(self):
        """Test metrics history endpoints"""
        # Test store metrics
        response = self.make_request('POST', '/metrics/store')
        if response.status_code == 200:
            data = response.json()
            if 'metrics' in data:
                self.log_test('Store Metrics', 'PASS', "Stored current metrics")
            else:
                self.log_test('Store Metrics', 'FAIL', error="No metrics in response")
        else:
            self.log_test('Store Metrics', 'FAIL', error=f"Status {response.status_code}")

        # Test get metrics history
        response = self.make_request('GET', '/metrics/history?type=cpu&interval=hour')
        if response.status_code == 200:
            data = response.json()
            if 'metrics' in data:
                self.log_test('Get Metrics History', 'PASS', "Retrieved metrics history")
            else:
                self.log_test('Get Metrics History', 'FAIL', error="No metrics in response")
        else:
            self.log_test('Get Metrics History', 'FAIL', error=f"Status {response.status_code}")

    def test_api_documentation(self):
        """Test API documentation endpoints"""
        # Test documentation
        response = self.make_request('GET', '/docs')
        if response.status_code == 200:
            data = response.json()
            if 'documentation' in data:
                endpoint_count = sum(len(endpoints) for endpoints in data['documentation']['endpoints'].values())
                self.log_test('API Documentation', 'PASS', f"Retrieved docs for {endpoint_count} endpoints")
            else:
                self.log_test('API Documentation', 'FAIL', error="No documentation in response")
        else:
            self.log_test('API Documentation', 'FAIL', error=f"Status {response.status_code}")

        # Test API status
        response = self.make_request('GET', '/status')
        if response.status_code == 200:
            data = response.json()
            if 'status_info' in data:
                api_status = data['status_info']['status']
                self.log_test('API Status', 'PASS', f"API status: {api_status}")
            else:
                self.log_test('API Status', 'FAIL', error="No status info in response")
        else:
            self.log_test('API Status', 'FAIL', error=f"Status {response.status_code}")

    def cleanup_test_data(self):
        """Clean up test data"""
        cleanup_operations = []
        
        # Delete test task
        if self.test_task_id:
            try:
                response = self.make_request('DELETE', f'/tasks/{self.test_task_id}')
                if response.status_code == 200:
                    cleanup_operations.append(f"Deleted task {self.test_task_id}")
            except:
                pass

        # Delete test project
        if self.test_project_id:
            try:
                response = self.make_request('DELETE', f'/projects/{self.test_project_id}?cascade=true')
                if response.status_code == 200:
                    cleanup_operations.append(f"Deleted project {self.test_project_id}")
            except:
                pass

        # Delete test backup
        if self.test_backup_id:
            try:
                response = self.make_request('DELETE', f'/backup/{self.test_backup_id}/delete')
                if response.status_code == 200:
                    cleanup_operations.append(f"Deleted backup {self.test_backup_id}")
            except:
                pass

        if cleanup_operations:
            self.log_test('Cleanup', 'PASS', f"Completed {len(cleanup_operations)} cleanup operations")
        else:
            self.log_test('Cleanup', 'SKIP', "No cleanup needed")

    def run_all_tests(self):
        """Run all API tests"""
        logger.info("Starting Enhanced API v2 Test Suite")
        start_time = time.time()

        # Test categories
        test_methods = [
            ('Projects CRUD', self.test_projects_crud),
            ('Tasks CRUD', self.test_tasks_crud),
            ('System Endpoints', self.test_system_endpoints),
            ('Backup Endpoints', self.test_backup_endpoints),
            ('Monitoring Endpoints', self.test_monitoring_endpoints),
            ('Search Endpoints', self.test_search_endpoints),
            ('Analytics Endpoints', self.test_analytics_endpoints),
            ('Database Endpoints', self.test_database_endpoints),
            ('Integration Endpoints', self.test_integration_endpoints),
            ('Performance Endpoints', self.test_performance_endpoints),
            ('Logs Endpoints', self.test_logs_endpoints),
            ('Config Endpoints', self.test_config_endpoints),
            ('Notifications Endpoints', self.test_notifications_endpoints),
            ('Services Endpoints', self.test_services_endpoints),
            ('Metrics Endpoints', self.test_metrics_endpoints),
            ('Documentation Endpoints', self.test_api_documentation)
        ]

        for category_name, test_method in test_methods:
            try:
                logger.info(f"Testing {category_name}...")
                test_method()
            except Exception as e:
                self.log_test(f"{category_name} (Category)", 'FAIL', error=str(e))

        # Cleanup
        self.cleanup_test_data()

        # Generate summary
        total_time = time.time() - start_time
        total_tests = self.results['passed'] + self.results['failed']
        success_rate = (self.results['passed'] / total_tests * 100) if total_tests > 0 else 0

        logger.info(f"\n{'='*60}")
        logger.info(f"Enhanced API v2 Test Results")
        logger.info(f"{'='*60}")
        logger.info(f"Total Tests: {total_tests}")
        logger.info(f"Passed: {self.results['passed']}")
        logger.info(f"Failed: {self.results['failed']}")
        logger.info(f"Success Rate: {success_rate:.1f}%")
        logger.info(f"Total Time: {total_time:.2f} seconds")

        if self.results['errors']:
            logger.info(f"\nErrors:")
            for error in self.results['errors']:
                logger.info(f"  - {error}")

        return self.results

    def save_results(self, filename=None):
        """Save test results to file"""
        if not filename:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"enhanced_api_test_results_{timestamp}.json"
        
        test_dir = Path.home() / 'barbossa-engineer' / 'web_portal'
        filepath = test_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        logger.info(f"Test results saved to {filepath}")
        return filepath


def main():
    """Main test execution"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Test Enhanced API v2 Endpoints')
    parser.add_argument('--url', default='https://localhost:8443', help='Base URL for API')
    parser.add_argument('--username', default='admin', help='Username for authentication')
    parser.add_argument('--password', default='admin', help='Password for authentication')
    parser.add_argument('--save', action='store_true', help='Save results to file')
    
    args = parser.parse_args()
    
    tester = EnhancedAPITester(
        base_url=args.url,
        username=args.username,
        password=args.password
    )
    
    try:
        results = tester.run_all_tests()
        
        if args.save:
            tester.save_results()
        
        # Exit with error code if tests failed
        if results['failed'] > 0:
            exit(1)
        else:
            exit(0)
            
    except KeyboardInterrupt:
        logger.info("Tests interrupted by user")
        exit(1)
    except Exception as e:
        logger.error(f"Test execution failed: {e}")
        exit(1)


if __name__ == '__main__':
    main()