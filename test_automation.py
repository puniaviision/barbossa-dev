#!/usr/bin/env python3
"""
Test Suite for Barbossa Workflow Automation System
Comprehensive tests to verify all automation components work correctly
"""

import asyncio
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import sys

# Add current directory to path for imports
sys.path.append(str(Path(__file__).parent))

# Import workflow components
try:
    from workflow_automation import (
        WorkflowEngine, Workflow, WorkflowTask, TaskExecutor,
        WorkflowStatus, TaskStatus, TriggerType
    )
    from workflow_monitor import WorkflowMonitor, MetricsCollector, AlertManager
    AUTOMATION_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import automation components: {e}")
    AUTOMATION_AVAILABLE = False


class TestWorkflowEngine(unittest.TestCase):
    """Test cases for WorkflowEngine"""
    
    def setUp(self):
        """Set up test environment"""
        if not AUTOMATION_AVAILABLE:
            self.skipTest("Automation components not available")
        
        # Create temporary directory for tests
        self.test_dir = Path(tempfile.mkdtemp())
        self.workflow_engine = WorkflowEngine(self.test_dir)
    
    def tearDown(self):
        """Clean up test environment"""
        if hasattr(self, 'test_dir'):
            import shutil
            shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_workflow_creation(self):
        """Test workflow creation from configuration"""
        config = {
            'name': 'Test Workflow',
            'description': 'A test workflow',
            'tasks': [
                {
                    'id': 'task1',
                    'name': 'Test Task 1',
                    'type': 'shell_command',
                    'command': 'echo "Hello World"'
                },
                {
                    'id': 'task2',
                    'name': 'Test Task 2',
                    'type': 'shell_command',
                    'command': 'echo "Task 2"',
                    'dependencies': ['task1']
                }
            ]
        }
        
        workflow = self.workflow_engine.create_workflow_from_config(config)
        
        self.assertIsInstance(workflow, Workflow)
        self.assertEqual(workflow.name, 'Test Workflow')
        self.assertEqual(len(workflow.tasks), 2)
        self.assertEqual(workflow.execution_order, ['task1', 'task2'])
    
    def test_workflow_execution_order(self):
        """Test workflow task execution order calculation"""
        config = {
            'name': 'Dependency Test',
            'description': 'Test task dependencies',
            'tasks': [
                {
                    'id': 'task_c',
                    'name': 'Task C',
                    'type': 'shell_command',
                    'command': 'echo "C"',
                    'dependencies': ['task_a', 'task_b']
                },
                {
                    'id': 'task_a',
                    'name': 'Task A',
                    'type': 'shell_command',
                    'command': 'echo "A"'
                },
                {
                    'id': 'task_b',
                    'name': 'Task B',
                    'type': 'shell_command',
                    'command': 'echo "B"',
                    'dependencies': ['task_a']
                }
            ]
        }
        
        workflow = self.workflow_engine.create_workflow_from_config(config)
        
        # Expected order: task_a, task_b, task_c
        self.assertEqual(workflow.execution_order, ['task_a', 'task_b', 'task_c'])
    
    def test_circular_dependency_detection(self):
        """Test detection of circular dependencies"""
        config = {
            'name': 'Circular Test',
            'description': 'Test circular dependency detection',
            'tasks': [
                {
                    'id': 'task_a',
                    'name': 'Task A',
                    'type': 'shell_command',
                    'command': 'echo "A"',
                    'dependencies': ['task_b']
                },
                {
                    'id': 'task_b',
                    'name': 'Task B',
                    'type': 'shell_command',
                    'command': 'echo "B"',
                    'dependencies': ['task_a']
                }
            ]
        }
        
        with self.assertRaises(ValueError):
            self.workflow_engine.create_workflow_from_config(config)


class TestTaskExecutor(unittest.TestCase):
    """Test cases for TaskExecutor"""
    
    def setUp(self):
        """Set up test environment"""
        if not AUTOMATION_AVAILABLE:
            self.skipTest("Automation components not available")
        
        self.test_dir = Path(tempfile.mkdtemp())
        self.workflow_engine = WorkflowEngine(self.test_dir)
        self.task_executor = TaskExecutor(self.workflow_engine)
    
    def tearDown(self):
        """Clean up test environment"""
        if hasattr(self, 'test_dir'):
            import shutil
            shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_shell_command_task(self):
        """Test shell command task execution"""
        # Create a simple workflow with shell command
        workflow = Workflow(
            workflow_id='test_workflow',
            name='Test Shell Command',
            description='Test shell command execution',
            config={
                'tasks': [
                    {
                        'id': 'test_task',
                        'name': 'Echo Test',
                        'type': 'shell_command',
                        'command': 'echo "Hello Test"'
                    }
                ]
            }
        )
        
        # Create task
        task = WorkflowTask(
            task_id='test_task',
            name='Echo Test',
            task_type='shell_command',
            config={'command': 'echo "Hello Test"'}
        )
        
        # Execute task
        async def run_test():
            result = await self.task_executor.execute_task(workflow, task)
            return result
        
        result = asyncio.run(run_test())
        
        self.assertTrue(result)
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertIn('Hello Test', task.outputs.get('stdout', ''))
    
    def test_file_operation_task(self):
        """Test file operation task execution"""
        test_file = self.test_dir / 'test_file.txt'
        test_file.write_text('Test content')
        
        workflow = Workflow(
            workflow_id='test_workflow',
            name='Test File Operation',
            description='Test file operation execution',
            config={}
        )
        
        task = WorkflowTask(
            task_id='copy_task',
            name='Copy File',
            task_type='file_operation',
            config={
                'operation': 'copy',
                'source': str(test_file),
                'destination': str(self.test_dir / 'copied_file.txt')
            }
        )
        
        async def run_test():
            result = await self.task_executor.execute_task(workflow, task)
            return result
        
        result = asyncio.run(run_test())
        
        self.assertTrue(result)
        self.assertEqual(task.status, TaskStatus.COMPLETED)
        self.assertTrue((self.test_dir / 'copied_file.txt').exists())
    
    def test_task_timeout(self):
        """Test task timeout functionality"""
        workflow = Workflow(
            workflow_id='test_workflow',
            name='Test Timeout',
            description='Test task timeout',
            config={}
        )
        
        task = WorkflowTask(
            task_id='timeout_task',
            name='Timeout Test',
            task_type='shell_command',
            config={
                'command': 'sleep 10',  # Long running command
                'timeout': 1  # 1 second timeout
            }
        )
        
        async def run_test():
            result = await self.task_executor.execute_task(workflow, task)
            return result
        
        result = asyncio.run(run_test())
        
        self.assertFalse(result)
        self.assertEqual(task.status, TaskStatus.FAILED)
        self.assertIn('timed out', task.error_message)


class TestWorkflowMonitor(unittest.TestCase):
    """Test cases for WorkflowMonitor"""
    
    def setUp(self):
        """Set up test environment"""
        if not AUTOMATION_AVAILABLE:
            self.skipTest("Automation components not available")
        
        self.test_dir = Path(tempfile.mkdtemp())
        self.monitor = WorkflowMonitor(self.test_dir)
    
    def tearDown(self):
        """Clean up test environment"""
        if hasattr(self, 'test_dir'):
            import shutil
            shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_metrics_collection(self):
        """Test metrics collection"""
        # Record some test metrics
        self.monitor.metrics_collector.record_workflow_execution(
            'test_workflow', 'Test Workflow', 'completed', 120.5, 3
        )
        
        # Get metrics
        metrics = self.monitor.metrics_collector.get_workflow_metrics()
        
        self.assertIn('test_workflow', metrics)
        workflow_metrics = metrics['test_workflow']
        self.assertIn('execution_duration', workflow_metrics)
        self.assertIn('success', workflow_metrics)
    
    def test_alert_rules(self):
        """Test alert rule evaluation"""
        alert_config = {
            'alert_rules': {
                'test_alert': {
                    'condition': {
                        'metric_path': 'failure_rate',
                        'operator': '>',
                        'threshold': 50
                    },
                    'severity': 'warning',
                    'message': 'Test alert triggered'
                }
            },
            'notification_channels': {
                'log': {'type': 'log'}
            }
        }
        
        alert_manager = AlertManager(alert_config)
        
        # Test metrics that should trigger alert
        metrics = {'failure_rate': 75}
        alerts = alert_manager.check_alerts(metrics)
        
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['rule_name'], 'test_alert')
        
        # Test metrics that should not trigger alert
        metrics = {'failure_rate': 25}
        alerts = alert_manager.check_alerts(metrics)
        
        self.assertEqual(len(alerts), 0)


class TestWorkflowTemplates(unittest.TestCase):
    """Test cases for workflow templates"""
    
    def setUp(self):
        """Set up test environment"""
        if not AUTOMATION_AVAILABLE:
            self.skipTest("Automation components not available")
        
        self.test_dir = Path(tempfile.mkdtemp())
        self.templates_dir = self.test_dir / 'workflow_templates'
        self.templates_dir.mkdir()
        self.workflow_engine = WorkflowEngine(self.test_dir)
    
    def tearDown(self):
        """Clean up test environment"""
        if hasattr(self, 'test_dir'):
            import shutil
            shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_template_creation(self):
        """Test workflow creation from template"""
        # Create a test template
        template_config = {
            'name': 'Test Template',
            'description': 'A test template',
            'variables': {
                'project_name': 'default_project',
                'environment': 'development'
            },
            'tasks': [
                {
                    'id': 'setup',
                    'name': 'Setup ${project_name}',
                    'type': 'shell_command',
                    'command': 'echo "Setting up ${project_name} in ${environment}"'
                }
            ]
        }
        
        # Save template
        template_file = self.templates_dir / 'test_template.yaml'
        import yaml
        with open(template_file, 'w') as f:
            yaml.dump(template_config, f)
        
        # Create workflow from template
        variables = {
            'project_name': 'my_project',
            'environment': 'production'
        }
        
        workflow = self.workflow_engine.create_workflow_from_template('test_template', variables)
        
        self.assertEqual(workflow.name, 'Test Template')
        self.assertEqual(len(workflow.tasks), 1)
        
        # Check variable substitution
        task = list(workflow.tasks.values())[0]
        self.assertEqual(task.name, 'Setup my_project')
        self.assertIn('my_project in production', task.config['command'])


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete automation system"""
    
    def setUp(self):
        """Set up test environment"""
        if not AUTOMATION_AVAILABLE:
            self.skipTest("Automation components not available")
        
        self.test_dir = Path(tempfile.mkdtemp())
        self.workflow_engine = WorkflowEngine(self.test_dir)
        self.monitor = WorkflowMonitor(self.test_dir)
    
    def tearDown(self):
        """Clean up test environment"""
        if hasattr(self, 'test_dir'):
            import shutil
            shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_complete_workflow_execution(self):
        """Test complete workflow execution with monitoring"""
        # Create a test workflow
        config = {
            'name': 'Integration Test Workflow',
            'description': 'Test complete workflow execution',
            'tasks': [
                {
                    'id': 'prepare',
                    'name': 'Prepare Environment',
                    'type': 'shell_command',
                    'command': f'mkdir -p {self.test_dir}/test_output'
                },
                {
                    'id': 'create_file',
                    'name': 'Create Test File',
                    'type': 'shell_command',
                    'command': f'echo "Integration test output" > {self.test_dir}/test_output/result.txt',
                    'dependencies': ['prepare']
                },
                {
                    'id': 'verify',
                    'name': 'Verify Output',
                    'type': 'shell_command',
                    'command': f'cat {self.test_dir}/test_output/result.txt',
                    'dependencies': ['create_file']
                }
            ]
        }
        
        workflow = self.workflow_engine.create_workflow_from_config(config)
        
        # Start monitoring
        self.monitor.start_monitoring(self.workflow_engine)
        
        # Execute workflow
        async def run_test():
            result = await self.workflow_engine.execute_workflow(workflow, TriggerType.MANUAL)
            return result
        
        result = asyncio.run(run_test())
        
        # Verify results
        self.assertTrue(result)
        self.assertEqual(workflow.status, WorkflowStatus.COMPLETED)
        
        # Check all tasks completed
        for task in workflow.tasks.values():
            self.assertEqual(task.status, TaskStatus.COMPLETED)
        
        # Verify output file was created
        result_file = self.test_dir / 'test_output' / 'result.txt'
        self.assertTrue(result_file.exists())
        self.assertIn('Integration test output', result_file.read_text())
        
        # Stop monitoring
        self.monitor.stop_monitoring()


class TestDatabaseOperations(unittest.TestCase):
    """Test database operations for workflow automation"""
    
    def setUp(self):
        """Set up test environment"""
        if not AUTOMATION_AVAILABLE:
            self.skipTest("Automation components not available")
        
        self.test_dir = Path(tempfile.mkdtemp())
        self.db_path = self.test_dir / 'test_workflows.db'
    
    def tearDown(self):
        """Clean up test environment"""
        if hasattr(self, 'test_dir'):
            import shutil
            shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_workflow_storage(self):
        """Test workflow storage and retrieval from database"""
        workflow_engine = WorkflowEngine(self.test_dir)
        
        # Create and store a workflow
        config = {
            'name': 'DB Test Workflow',
            'description': 'Test database storage',
            'tasks': [
                {
                    'id': 'test_task',
                    'name': 'Test Task',
                    'type': 'shell_command',
                    'command': 'echo "test"'
                }
            ]
        }
        
        workflow = workflow_engine.create_workflow_from_config(config)
        
        # Retrieve workflows from database
        workflows = workflow_engine.list_workflows()
        
        self.assertEqual(len(workflows), 1)
        self.assertEqual(workflows[0]['name'], 'DB Test Workflow')
    
    def test_metrics_storage(self):
        """Test metrics storage and retrieval"""
        metrics_collector = MetricsCollector(self.db_path)
        
        # Record some metrics
        metrics_collector.record_workflow_execution(
            'test_workflow', 'Test Workflow', 'completed', 45.2, 2
        )
        metrics_collector.record_workflow_execution(
            'test_workflow', 'Test Workflow', 'failed', 12.1, 2
        )
        
        # Retrieve metrics
        metrics = metrics_collector.get_workflow_metrics('test_workflow')
        
        self.assertIn('test_workflow', metrics)
        workflow_metrics = metrics['test_workflow']
        self.assertIn('execution_duration', workflow_metrics)
        self.assertIn('success', workflow_metrics)


def run_tests():
    """Run all automation tests"""
    print("Barbossa Workflow Automation - Test Suite")
    print("=" * 50)
    
    if not AUTOMATION_AVAILABLE:
        print("ERROR: Automation components not available for testing")
        return False
    
    # Create test suite
    test_classes = [
        TestWorkflowEngine,
        TestTaskExecutor,
        TestWorkflowMonitor,
        TestWorkflowTemplates,
        TestIntegration,
        TestDatabaseOperations
    ]
    
    suite = unittest.TestSuite()
    
    for test_class in test_classes:
        tests = unittest.TestLoader().loadTestsFromTestCase(test_class)
        suite.addTests(tests)
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Print summary
    print("\n" + "=" * 50)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print(f"Skipped: {len(result.skipped) if hasattr(result, 'skipped') else 0}")
    
    if result.failures:
        print("\nFailures:")
        for test, traceback in result.failures:
            print(f"- {test}: {traceback}")
    
    if result.errors:
        print("\nErrors:")
        for test, traceback in result.errors:
            print(f"- {test}: {traceback}")
    
    success = len(result.failures) == 0 and len(result.errors) == 0
    print(f"\nOverall result: {'PASS' if success else 'FAIL'}")
    
    return success


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)