#!/usr/bin/env python3
"""
Comprehensive test suite for Enhanced API endpoints
Tests all new v2 API functionality
"""

import json
import os
import sys
import unittest
import tempfile
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))
sys.path.append(str(Path(__file__).parent.parent / 'web_portal'))

try:
    from flask import Flask
    from enhanced_api import enhanced_api, validate_request_data, PROJECT_SCHEMA, TASK_SCHEMA
    from enhanced_api import cache_response, get_cached_response, clear_cache
    FLASK_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Flask or enhanced_api not available: {e}")
    FLASK_AVAILABLE = False


class TestEnhancedAPI(unittest.TestCase):
    """Test Enhanced API endpoints"""
    
    def setUp(self):
        """Set up test environment"""
        if not FLASK_AVAILABLE:
            self.skipTest("Flask or enhanced_api not available")
        
        # Create test Flask app
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True
        self.app.register_blueprint(enhanced_api)
        self.client = self.app.test_client()
        
        # Create temporary database
        self.temp_db_fd, self.temp_db_path = tempfile.mkstemp(suffix='.db')
        
        # Mock the database path in enhanced_api
        self.original_db_path = None
        
        # Set up test database
        self.setup_test_database()
        
        # Clear cache before each test
        clear_cache()
    
    def tearDown(self):
        """Clean up test environment"""
        if hasattr(self, 'temp_db_fd'):
            os.close(self.temp_db_fd)
            os.unlink(self.temp_db_path)
    
    def setup_test_database(self):
        """Set up test database with sample data"""
        with sqlite3.connect(self.temp_db_path) as conn:
            cursor = conn.cursor()
            
            # Create projects table
            cursor.execute('''
                CREATE TABLE projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    repository_url TEXT,
                    status TEXT DEFAULT 'active',
                    priority INTEGER DEFAULT 3,
                    tags TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            
            # Create tasks table
            cursor.execute('''
                CREATE TABLE tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    project_id TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    priority INTEGER DEFAULT 3,
                    assigned_to TEXT,
                    due_date TEXT,
                    tags TEXT DEFAULT '[]',
                    dependencies TEXT DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    FOREIGN KEY (project_id) REFERENCES projects (id)
                )
            ''')
            
            # Insert sample data
            sample_project = {
                'id': 'test-project-1',
                'name': 'Test Project',
                'description': 'A test project',
                'repository_url': 'https://github.com/ADWilkinson/test-repo',
                'status': 'active',
                'priority': 3,
                'tags': '["test", "api"]',
                'metadata': '{}',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            
            cursor.execute('''
                INSERT INTO projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', list(sample_project.values()))
            
            sample_task = {
                'id': 'test-task-1',
                'title': 'Test Task',
                'description': 'A test task',
                'project_id': 'test-project-1',
                'status': 'pending',
                'priority': 3,
                'assigned_to': 'testuser',
                'due_date': (datetime.now() + timedelta(days=7)).isoformat(),
                'tags': '["test"]',
                'dependencies': '[]',
                'metadata': '{}',
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat(),
                'completed_at': ''
            }
            
            cursor.execute('''
                INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', list(sample_task.values()))
            
            conn.commit()
    
    def mock_db_path(self):
        """Mock database path to use test database"""
        # This would need to be implemented to properly mock the database path
        # For now, we'll assume the functions can be patched
        pass
    
    def test_api_status(self):
        """Test API status endpoint"""
        response = self.client.get('/api/v2/status')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertIn('status_info', data)
        self.assertIn('api_version', data['status_info'])
        self.assertEqual(data['status_info']['api_version'], '2.0.0')
    
    def test_api_documentation(self):
        """Test API documentation endpoint"""
        response = self.client.get('/api/v2/docs')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertIn('documentation', data)
        self.assertIn('endpoints', data['documentation'])
        self.assertIn('schemas', data['documentation'])
    
    @patch('enhanced_api.Path.home')
    @patch('enhanced_api.sqlite3.connect')
    def test_get_projects(self, mock_connect, mock_home):
        """Test getting projects"""
        # Mock database path
        mock_home.return_value = Path('/tmp')
        
        # Mock database connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        # Mock query results
        mock_cursor.fetchone.return_value = [1]  # Count query
        mock_cursor.fetchall.return_value = [
            {
                'id': 'test-project-1',
                'name': 'Test Project',
                'description': 'A test project',
                'status': 'active',
                'tags': '["test"]',
                'metadata': '{}'
            }
        ]
        
        # Mock row factory
        mock_conn.row_factory = sqlite3.Row
        
        response = self.client.get('/api/v2/projects')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertIn('projects', data)
        self.assertIn('total', data)
    
    @patch('enhanced_api.Path.home')
    @patch('enhanced_api.sqlite3.connect')
    @patch('enhanced_api.get_security_guard')
    def test_create_project(self, mock_security_guard, mock_connect, mock_home):
        """Test creating a project"""
        # Mock security guard
        mock_guard = MagicMock()
        mock_guard.is_repository_allowed.return_value = True
        mock_security_guard.return_value = mock_guard
        
        # Mock database
        mock_home.return_value = Path('/tmp')
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        project_data = {
            'name': 'New Test Project',
            'description': 'A new test project',
            'repository_url': 'https://github.com/ADWilkinson/new-repo',
            'status': 'active',
            'priority': 4,
            'tags': ['new', 'test']
        }
        
        response = self.client.post('/api/v2/projects', 
                                  data=json.dumps(project_data),
                                  content_type='application/json')
        self.assertEqual(response.status_code, 201)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertIn('project', data)
        self.assertEqual(data['project']['name'], project_data['name'])
    
    def test_create_project_validation(self):
        """Test project creation validation"""
        # Test missing required field
        invalid_data = {
            'description': 'Project without name'
        }
        
        response = self.client.post('/api/v2/projects',
                                  data=json.dumps(invalid_data),
                                  content_type='application/json')
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'Validation failed')
        self.assertIn('errors', data)
    
    @patch('enhanced_api.psutil.cpu_percent')
    @patch('enhanced_api.psutil.virtual_memory')
    @patch('enhanced_api.psutil.disk_partitions')
    @patch('enhanced_api.psutil.net_io_counters')
    @patch('enhanced_api.psutil.pids')
    @patch('enhanced_api.psutil.process_iter')
    @patch('enhanced_api.psutil.boot_time')
    def test_system_metrics(self, mock_boot_time, mock_process_iter, mock_pids,
                           mock_net_io, mock_disk_partitions, mock_virtual_memory,
                           mock_cpu_percent):
        """Test system metrics endpoint"""
        # Mock system data
        mock_cpu_percent.return_value = 25.5
        
        mock_memory = MagicMock()
        mock_memory.total = 8589934592  # 8GB
        mock_memory.available = 4294967296  # 4GB
        mock_memory.used = 4294967296  # 4GB
        mock_memory.percent = 50.0
        mock_virtual_memory.return_value = mock_memory
        
        mock_swap = MagicMock()
        mock_swap.total = 2147483648  # 2GB
        mock_swap.used = 0
        mock_swap.percent = 0.0
        mock_memory.swap_memory = lambda: mock_swap
        
        mock_disk_partitions.return_value = []
        
        mock_net = MagicMock()
        mock_net.bytes_sent = 1000000
        mock_net.bytes_recv = 2000000
        mock_net.packets_sent = 1000
        mock_net.packets_recv = 2000
        mock_net_io.return_value = mock_net
        
        mock_pids.return_value = [1, 2, 3, 4, 5]
        mock_process_iter.return_value = []
        mock_boot_time.return_value = 1640995200  # Some timestamp
        
        response = self.client.get('/api/v2/system/metrics')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertIn('metrics', data)
        self.assertIn('cpu', data['metrics'])
        self.assertIn('memory', data['metrics'])
        self.assertEqual(data['metrics']['cpu']['usage_percent'], 25.5)
    
    @patch('enhanced_api.psutil.cpu_percent')
    @patch('enhanced_api.psutil.virtual_memory')
    @patch('enhanced_api.psutil.disk_partitions')
    def test_system_health(self, mock_disk_partitions, mock_virtual_memory, mock_cpu_percent):
        """Test system health endpoint"""
        # Mock healthy system
        mock_cpu_percent.return_value = 50.0
        
        mock_memory = MagicMock()
        mock_memory.percent = 60.0
        mock_virtual_memory.return_value = mock_memory
        
        mock_disk_partitions.return_value = []
        
        response = self.client.get('/api/v2/system/health')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertIn('health', data)
        self.assertIn('overall_status', data['health'])
        self.assertIn('checks', data['health'])
        self.assertIn('summary', data['health'])
    
    @patch('enhanced_api.psutil.process_iter')
    def test_system_processes(self, mock_process_iter):
        """Test system processes endpoint"""
        # Mock process data
        mock_proc = MagicMock()
        mock_proc.info = {
            'pid': 1234,
            'name': 'test_process',
            'cpu_percent': 15.5,
            'memory_percent': 5.2,
            'status': 'running',
            'create_time': 1640995200,
            'cmdline': ['test_process', '--arg1', '--arg2']
        }
        mock_process_iter.return_value = [mock_proc]
        
        response = self.client.get('/api/v2/system/processes')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertIn('processes', data)
        self.assertIn('total', data)
    
    def test_security_audit(self):
        """Test security audit endpoint"""
        with patch('enhanced_api.get_security_guard') as mock_guard_func:
            mock_guard = MagicMock()
            mock_guard_func.return_value = mock_guard
            
            response = self.client.get('/api/v2/security/audit')
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'success')
            self.assertIn('audit', data)
    
    def test_security_scan(self):
        """Test security scan endpoint"""
        with patch('enhanced_api.get_security_guard') as mock_guard_func:
            mock_guard = MagicMock()
            mock_guard_func.return_value = mock_guard
            
            scan_data = {'type': 'quick'}
            response = self.client.post('/api/v2/security/scan',
                                      data=json.dumps(scan_data),
                                      content_type='application/json')
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'success')
            self.assertIn('scan', data)
    
    def test_cache_functionality(self):
        """Test API caching functionality"""
        # Test cache storage
        test_data = {'test': 'data'}
        cache_response('test_key', test_data, ttl=60)
        
        # Test cache retrieval
        cached_data = get_cached_response('test_key')
        self.assertEqual(cached_data, test_data)
        
        # Test cache expiry
        cache_response('expired_key', test_data, ttl=0)
        import time
        time.sleep(0.1)
        expired_data = get_cached_response('expired_key')
        self.assertIsNone(expired_data)
        
        # Test cache clearing
        clear_cache()
        cleared_data = get_cached_response('test_key')
        self.assertIsNone(cleared_data)
    
    @patch('enhanced_api.Path.home')
    @patch('builtins.open', create=True)
    def test_get_logs(self, mock_open, mock_home):
        """Test getting system logs"""
        mock_home.return_value = Path('/tmp')
        
        # Mock log file content
        mock_log_content = [
            "2024-01-01 12:00:00 INFO Test log message\n",
            "2024-01-01 12:01:00 ERROR Test error message\n"
        ]
        
        mock_file = MagicMock()
        mock_file.__enter__.return_value = mock_file
        mock_file.__exit__.return_value = None
        mock_file.__iter__.return_value = iter(mock_log_content)
        mock_open.return_value = mock_file
        
        # Mock Path.glob
        with patch('enhanced_api.Path.glob') as mock_glob:
            mock_log_file = MagicMock()
            mock_log_file.name = 'barbossa_20240101.log'
            mock_log_file.stat.return_value.st_mtime = 1640995200
            mock_glob.return_value = [mock_log_file]
            
            response = self.client.get('/api/v2/logs')
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'success')
            self.assertIn('logs', data)
            self.assertIn('total', data)
    
    @patch('enhanced_api.Path.home')
    def test_get_log_files(self, mock_home):
        """Test getting log files list"""
        mock_home.return_value = Path('/tmp')
        
        with patch('enhanced_api.Path.exists') as mock_exists, \
             patch('enhanced_api.Path.glob') as mock_glob:
            
            mock_exists.return_value = True
            
            # Mock log file
            mock_log_file = MagicMock()
            mock_log_file.name = 'test.log'
            mock_log_file.stat.return_value.st_size = 1024
            mock_log_file.stat.return_value.st_mtime = 1640995200
            mock_glob.return_value = [mock_log_file]
            
            response = self.client.get('/api/v2/logs/files')
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'success')
            self.assertIn('log_files', data)
    
    @patch('enhanced_api.Path.home')
    def test_clear_logs_dry_run(self, mock_home):
        """Test clearing logs in dry run mode"""
        mock_home.return_value = Path('/tmp')
        
        clear_data = {
            'days_older_than': 30,
            'file_types': ['system'],
            'dry_run': True
        }
        
        with patch('enhanced_api.Path.exists') as mock_exists, \
             patch('enhanced_api.Path.glob') as mock_glob:
            
            mock_exists.return_value = True
            mock_glob.return_value = []  # No files to remove
            
            response = self.client.post('/api/v2/logs/clear',
                                      data=json.dumps(clear_data),
                                      content_type='application/json')
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'success')
            self.assertTrue(data['dry_run'])
            self.assertIn('files_to_remove', data)
    
    @patch('enhanced_api.Path.home')
    @patch('builtins.open', create=True)
    def test_get_configuration(self, mock_open, mock_home):
        """Test getting system configuration"""
        mock_home.return_value = Path('/tmp')
        
        # Mock config file content
        mock_config = {'test_setting': 'test_value'}
        
        mock_file = MagicMock()
        mock_file.__enter__.return_value = mock_file
        mock_file.__exit__.return_value = None
        mock_open.return_value = mock_file
        
        with patch('enhanced_api.json.load') as mock_json_load, \
             patch('enhanced_api.Path.exists') as mock_exists:
            
            mock_exists.return_value = True
            mock_json_load.return_value = mock_config
            
            response = self.client.get('/api/v2/config')
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'success')
            self.assertIn('configuration', data)
    
    @patch('enhanced_api.Path.home')
    @patch('builtins.open', create=True)
    def test_get_notifications(self, mock_open, mock_home):
        """Test getting notifications"""
        mock_home.return_value = Path('/tmp')
        
        # Mock notifications file
        mock_notifications = [
            {
                'id': 'test-notification-1',
                'title': 'Test Notification',
                'message': 'Test message',
                'severity': 'info',
                'read': False,
                'timestamp': '2024-01-01T12:00:00'
            }
        ]
        
        mock_file = MagicMock()
        mock_file.__enter__.return_value = mock_file
        mock_file.__exit__.return_value = None
        mock_open.return_value = mock_file
        
        with patch('enhanced_api.json.load') as mock_json_load, \
             patch('enhanced_api.Path.exists') as mock_exists:
            
            mock_exists.return_value = True
            mock_json_load.return_value = mock_notifications
            
            response = self.client.get('/api/v2/notifications')
            self.assertEqual(response.status_code, 200)
            
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'success')
            self.assertIn('notifications', data)
            self.assertIn('unread_count', data)
    
    @patch('enhanced_api.Path.home')
    @patch('builtins.open', create=True)
    def test_create_notification(self, mock_open, mock_home):
        """Test creating a notification"""
        mock_home.return_value = Path('/tmp')
        
        # Mock file operations
        mock_file = MagicMock()
        mock_file.__enter__.return_value = mock_file
        mock_file.__exit__.return_value = None
        mock_open.return_value = mock_file
        
        with patch('enhanced_api.json.load') as mock_json_load, \
             patch('enhanced_api.json.dump') as mock_json_dump, \
             patch('enhanced_api.Path.exists') as mock_exists, \
             patch('enhanced_api.Path.mkdir') as mock_mkdir:
            
            mock_exists.return_value = True
            mock_json_load.return_value = []
            
            notification_data = {
                'title': 'Test Notification',
                'message': 'Test message',
                'severity': 'info'
            }
            
            response = self.client.post('/api/v2/notifications',
                                      data=json.dumps(notification_data),
                                      content_type='application/json')
            self.assertEqual(response.status_code, 201)
            
            data = json.loads(response.data)
            self.assertEqual(data['status'], 'success')
            self.assertIn('notification', data)
            self.assertEqual(data['notification']['title'], notification_data['title'])
    
    @patch('enhanced_api.subprocess.run')
    @patch('enhanced_api.psutil.process_iter')
    def test_get_services(self, mock_process_iter, mock_subprocess):
        """Test getting services status"""
        # Mock subprocess for systemctl commands
        mock_result = MagicMock()
        mock_result.stdout = 'active'
        mock_result.returncode = 0
        mock_subprocess.return_value = mock_result
        
        # Mock process iterator
        mock_process_iter.return_value = []
        
        response = self.client.get('/api/v2/services')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertIn('system_services', data)
        self.assertIn('barbossa_processes', data)
    
    def test_get_metrics_history(self):
        """Test getting metrics history"""
        response = self.client.get('/api/v2/metrics/history')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertIn('metrics', data)
        self.assertIn('interval', data)
    
    @patch('enhanced_api.Path.home')
    @patch('enhanced_api.sqlite3.connect')
    @patch('enhanced_api.psutil.cpu_percent')
    @patch('enhanced_api.psutil.virtual_memory')
    @patch('enhanced_api.psutil.disk_partitions')
    @patch('enhanced_api.psutil.net_io_counters')
    def test_store_metrics(self, mock_net_io, mock_disk_partitions, 
                          mock_virtual_memory, mock_cpu_percent, 
                          mock_connect, mock_home):
        """Test storing current metrics"""
        mock_home.return_value = Path('/tmp')
        
        # Mock system metrics
        mock_cpu_percent.return_value = 25.5
        
        mock_memory = MagicMock()
        mock_memory.percent = 60.0
        mock_virtual_memory.return_value = mock_memory
        
        mock_disk_partitions.return_value = []
        
        mock_net = MagicMock()
        mock_net._asdict.return_value = {
            'bytes_sent': 1000000,
            'bytes_recv': 2000000
        }
        mock_net_io.return_value = mock_net
        
        # Mock database
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        mock_connect.return_value = mock_conn
        
        response = self.client.post('/api/v2/metrics/store')
        self.assertEqual(response.status_code, 200)
        
        data = json.loads(response.data)
        self.assertEqual(data['status'], 'success')
        self.assertIn('metrics', data)
        self.assertIn('timestamp', data['metrics'])
        self.assertIn('cpu_percent', data['metrics'])


class TestValidation(unittest.TestCase):
    """Test request validation functions"""
    
    def test_project_validation(self):
        """Test project data validation"""
        # Valid project data
        valid_data = {
            'name': 'Test Project',
            'description': 'A test project',
            'status': 'active',
            'priority': 3
        }
        is_valid, errors = validate_request_data(valid_data, PROJECT_SCHEMA)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
        
        # Missing required field
        invalid_data = {
            'description': 'Project without name'
        }
        is_valid, errors = validate_request_data(invalid_data, PROJECT_SCHEMA)
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)
        
        # Invalid choice
        invalid_choice = {
            'name': 'Test Project',
            'status': 'invalid_status'
        }
        is_valid, errors = validate_request_data(invalid_choice, PROJECT_SCHEMA)
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)
        
        # String too long
        too_long = {
            'name': 'x' * 101  # Exceeds max_length of 100
        }
        is_valid, errors = validate_request_data(too_long, PROJECT_SCHEMA)
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)
    
    def test_task_validation(self):
        """Test task data validation"""
        # Valid task data
        valid_data = {
            'title': 'Test Task',
            'description': 'A test task',
            'project_id': 'test-project-1',
            'status': 'pending',
            'priority': 3
        }
        is_valid, errors = validate_request_data(valid_data, TASK_SCHEMA)
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)
        
        # Missing required fields
        invalid_data = {
            'description': 'Task without title or project_id'
        }
        is_valid, errors = validate_request_data(invalid_data, TASK_SCHEMA)
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)
        
        # Invalid priority range
        invalid_priority = {
            'title': 'Test Task',
            'project_id': 'test-project-1',
            'priority': 10  # Exceeds max of 5
        }
        is_valid, errors = validate_request_data(invalid_priority, TASK_SCHEMA)
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)


class TestIntegration(unittest.TestCase):
    """Integration tests for Enhanced API"""
    
    def setUp(self):
        """Set up integration test environment"""
        if not FLASK_AVAILABLE:
            self.skipTest("Flask or enhanced_api not available")
        
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True
        self.app.register_blueprint(enhanced_api)
        self.client = self.app.test_client()
    
    def test_project_task_workflow(self):
        """Test complete project and task workflow"""
        # This test would require a full database setup
        # For now, we'll test the error responses
        
        # Try to get non-existent project
        response = self.client.get('/api/v2/projects/non-existent')
        self.assertEqual(response.status_code, 500)  # Database connection error expected
        
        # Try to create project without data
        response = self.client.post('/api/v2/projects')
        self.assertEqual(response.status_code, 400)
        
        data = json.loads(response.data)
        self.assertEqual(data['error'], 'No data provided')
    
    def test_error_handling(self):
        """Test API error handling"""
        # Test 404 for non-existent endpoints
        response = self.client.get('/api/v2/non-existent')
        self.assertEqual(response.status_code, 404)
        
        # Test invalid JSON
        response = self.client.post('/api/v2/projects',
                                  data='invalid json',
                                  content_type='application/json')
        self.assertEqual(response.status_code, 400)


def run_api_tests():
    """Run all Enhanced API tests"""
    test_suite = unittest.TestSuite()
    
    # Add test classes
    test_classes = [TestEnhancedAPI, TestValidation, TestIntegration]
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        test_suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    return result.wasSuccessful()


if __name__ == '__main__':
    if not FLASK_AVAILABLE:
        print("ERROR: Flask or enhanced_api not available. Cannot run tests.")
        sys.exit(1)
    
    print("Running Enhanced API Test Suite...")
    print("=" * 60)
    
    success = run_api_tests()
    
    print("=" * 60)
    if success:
        print("✅ All tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed!")
        sys.exit(1)