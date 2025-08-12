#!/usr/bin/env python3
"""
Barbossa Workflow Automation Engine
Advanced automation system for orchestrating complex tasks and workflows
"""

import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Union
import functools
import subprocess
# External dependencies removed for basic functionality
# import schedule
# import yaml

from security_guard import security_guard, SecurityViolationError


class WorkflowStatus(Enum):
    """Workflow execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class TaskStatus(Enum):
    """Individual task status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class TriggerType(Enum):
    """Workflow trigger types"""
    MANUAL = "manual"
    SCHEDULE = "schedule"
    EVENT = "event"
    CONDITION = "condition"
    WEBHOOK = "webhook"


class WorkflowTask:
    """Individual task within a workflow"""
    
    def __init__(self, task_id: str, name: str, task_type: str, config: Dict[str, Any]):
        self.task_id = task_id
        self.name = name
        self.task_type = task_type
        self.config = config
        self.status = TaskStatus.PENDING
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error_message: Optional[str] = None
        self.retry_count = 0
        self.max_retries = config.get('max_retries', 3)
        self.timeout = config.get('timeout', 300)  # 5 minutes default
        self.dependencies = config.get('dependencies', [])
        self.outputs = {}
        self.logs = []
    
    def add_log(self, level: str, message: str):
        """Add log entry to task"""
        self.logs.append({
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'message': message
        })
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary"""
        return {
            'task_id': self.task_id,
            'name': self.name,
            'task_type': self.task_type,
            'status': self.status.value,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'error_message': self.error_message,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'dependencies': self.dependencies,
            'outputs': self.outputs,
            'config': self.config,
            'logs': self.logs[-10:]  # Last 10 log entries
        }


class Workflow:
    """Workflow definition and execution state"""
    
    def __init__(self, workflow_id: str, name: str, description: str, config: Dict[str, Any]):
        self.workflow_id = workflow_id
        self.name = name
        self.description = description
        self.config = config
        self.status = WorkflowStatus.PENDING
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.tasks: Dict[str, WorkflowTask] = {}
        self.execution_order: List[str] = []
        self.current_task: Optional[str] = None
        self.error_message: Optional[str] = None
        self.trigger_type = TriggerType(config.get('trigger_type', 'manual'))
        self.schedule_config = config.get('schedule', {})
        self.retry_policy = config.get('retry_policy', {})
        self.notifications = config.get('notifications', {})
        self.variables = config.get('variables', {})
        self.logs = []
        
        # Build tasks from config
        self._build_tasks()
    
    def _build_tasks(self):
        """Build tasks from workflow configuration"""
        tasks_config = self.config.get('tasks', [])
        
        for task_config in tasks_config:
            task_id = task_config['id']
            task = WorkflowTask(
                task_id=task_id,
                name=task_config['name'],
                task_type=task_config['type'],
                config=task_config
            )
            self.tasks[task_id] = task
        
        # Calculate execution order based on dependencies
        self._calculate_execution_order()
    
    def _calculate_execution_order(self):
        """Calculate task execution order using topological sort"""
        # Build dependency graph
        graph = {task_id: set(task.dependencies) for task_id, task in self.tasks.items()}
        in_degree = {task_id: len(deps) for task_id, deps in graph.items()}
        
        # Topological sort
        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        execution_order = []
        
        while queue:
            task_id = queue.pop(0)
            execution_order.append(task_id)
            
            # Update dependencies
            for other_task_id, deps in graph.items():
                if task_id in deps:
                    deps.remove(task_id)
                    in_degree[other_task_id] -= 1
                    if in_degree[other_task_id] == 0:
                        queue.append(other_task_id)
        
        # Check for circular dependencies
        if len(execution_order) != len(self.tasks):
            raise ValueError("Circular dependency detected in workflow tasks")
        
        self.execution_order = execution_order
    
    def add_log(self, level: str, message: str):
        """Add log entry to workflow"""
        self.logs.append({
            'timestamp': datetime.now().isoformat(),
            'level': level,
            'message': message
        })
    
    def get_task_by_id(self, task_id: str) -> Optional[WorkflowTask]:
        """Get task by ID"""
        return self.tasks.get(task_id)
    
    def get_ready_tasks(self) -> List[WorkflowTask]:
        """Get tasks ready for execution (dependencies completed)"""
        ready_tasks = []
        
        for task_id in self.execution_order:
            task = self.tasks[task_id]
            
            if task.status != TaskStatus.PENDING:
                continue
            
            # Check if all dependencies are completed
            dependencies_completed = all(
                self.tasks[dep_id].status == TaskStatus.COMPLETED
                for dep_id in task.dependencies
                if dep_id in self.tasks
            )
            
            if dependencies_completed:
                ready_tasks.append(task)
        
        return ready_tasks
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert workflow to dictionary"""
        return {
            'workflow_id': self.workflow_id,
            'name': self.name,
            'description': self.description,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'current_task': self.current_task,
            'error_message': self.error_message,
            'trigger_type': self.trigger_type.value,
            'tasks': {task_id: task.to_dict() for task_id, task in self.tasks.items()},
            'execution_order': self.execution_order,
            'variables': self.variables,
            'logs': self.logs[-20:]  # Last 20 log entries
        }


class TaskExecutor:
    """Executes individual workflow tasks"""
    
    def __init__(self, workflow_engine):
        self.workflow_engine = workflow_engine
        self.logger = logging.getLogger(__name__)
        
        # Task type handlers
        self.task_handlers = {
            'shell_command': self._execute_shell_command,
            'python_script': self._execute_python_script,
            'file_operation': self._execute_file_operation,
            'service_management': self._execute_service_management,
            'git_operation': self._execute_git_operation,
            'api_call': self._execute_api_call,
            'database_operation': self._execute_database_operation,
            'notification': self._execute_notification,
            'conditional': self._execute_conditional,
            'parallel_group': self._execute_parallel_group,
            'wait': self._execute_wait,
            'health_check': self._execute_health_check,
            'backup_operation': self._execute_backup_operation,
            'log_analysis': self._execute_log_analysis
        }
    
    async def execute_task(self, workflow: Workflow, task: WorkflowTask) -> bool:
        """Execute a single task"""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        task.add_log('INFO', f"Starting task execution: {task.name}")
        
        try:
            # Get task handler
            handler = self.task_handlers.get(task.task_type)
            if not handler:
                raise ValueError(f"Unknown task type: {task.task_type}")
            
            # Execute with timeout
            result = await asyncio.wait_for(
                handler(workflow, task),
                timeout=task.timeout
            )
            
            if result:
                task.status = TaskStatus.COMPLETED
                task.completed_at = datetime.now()
                task.add_log('INFO', f"Task completed successfully: {task.name}")
                return True
            else:
                raise Exception("Task handler returned False")
        
        except asyncio.TimeoutError:
            task.status = TaskStatus.FAILED
            task.error_message = f"Task timed out after {task.timeout} seconds"
            task.add_log('ERROR', task.error_message)
            return False
        
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.add_log('ERROR', f"Task failed: {e}")
            
            # Handle retries
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                task.status = TaskStatus.RETRYING
                task.add_log('INFO', f"Retrying task (attempt {task.retry_count}/{task.max_retries})")
                # Reset for retry
                await asyncio.sleep(2 ** task.retry_count)  # Exponential backoff
                return await self.execute_task(workflow, task)
            
            return False
    
    async def _execute_shell_command(self, workflow: Workflow, task: WorkflowTask) -> bool:
        """Execute shell command task"""
        command = task.config.get('command')
        if not command:
            raise ValueError("Shell command task requires 'command' parameter")
        
        # Variable substitution
        command = self._substitute_variables(command, workflow.variables, task.outputs)
        
        task.add_log('INFO', f"Executing command: {command}")
        
        # Security check for repository operations
        if any(keyword in command.lower() for keyword in ['git', 'clone', 'pull', 'push']):
            if 'zkp2p' in command.lower():
                raise SecurityViolationError("ZKP2P repository access blocked by security guard")
        
        # Execute command
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=task.config.get('working_directory', '/home/dappnode/barbossa-engineer')
        )
        
        stdout, stderr = await process.communicate()
        
        task.outputs['exit_code'] = process.returncode
        task.outputs['stdout'] = stdout.decode() if stdout else ''
        task.outputs['stderr'] = stderr.decode() if stderr else ''
        
        if process.returncode == 0:
            task.add_log('INFO', f"Command executed successfully")
            return True
        else:
            task.add_log('ERROR', f"Command failed with exit code {process.returncode}: {task.outputs['stderr']}")
            return False
    
    async def _execute_python_script(self, workflow: Workflow, task: WorkflowTask) -> bool:
        """Execute Python script task"""
        script_content = task.config.get('script')
        script_file = task.config.get('script_file')
        
        if not script_content and not script_file:
            raise ValueError("Python script task requires 'script' or 'script_file' parameter")
        
        if script_file:
            script_path = Path(script_file)
            if not script_path.is_absolute():
                script_path = Path('/home/dappnode/barbossa-engineer') / script_path
            
            if not script_path.exists():
                raise FileNotFoundError(f"Script file not found: {script_path}")
            
            script_content = script_path.read_text()
        
        # Variable substitution
        script_content = self._substitute_variables(script_content, workflow.variables, task.outputs)
        
        task.add_log('INFO', f"Executing Python script")
        
        # Create temporary script file
        temp_script = Path(f"/tmp/barbossa_script_{task.task_id}.py")
        temp_script.write_text(script_content)
        
        try:
            # Execute script
            process = await asyncio.create_subprocess_exec(
                'python3', str(temp_script),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            task.outputs['exit_code'] = process.returncode
            task.outputs['stdout'] = stdout.decode() if stdout else ''
            task.outputs['stderr'] = stderr.decode() if stderr else ''
            
            return process.returncode == 0
        
        finally:
            # Clean up temporary file
            if temp_script.exists():
                temp_script.unlink()
    
    async def _execute_service_management(self, workflow: Workflow, task: WorkflowTask) -> bool:
        """Execute service management task"""
        action = task.config.get('action')  # start, stop, restart, status
        service_name = task.config.get('service_name')
        service_type = task.config.get('service_type', 'systemd')  # systemd, docker
        
        if not action or not service_name:
            raise ValueError("Service management task requires 'action' and 'service_name' parameters")
        
        task.add_log('INFO', f"Managing service {service_name}: {action}")
        
        if service_type == 'systemd':
            if action == 'status':
                command = f"systemctl is-active {service_name}"
            else:
                command = f"sudo systemctl {action} {service_name}"
        elif service_type == 'docker':
            if action == 'status':
                command = f"docker ps -f name={service_name} --format 'table {{.Status}}'"
            else:
                command = f"docker {action} {service_name}"
        else:
            raise ValueError(f"Unknown service type: {service_type}")
        
        # Execute service command
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        task.outputs['exit_code'] = process.returncode
        task.outputs['stdout'] = stdout.decode() if stdout else ''
        task.outputs['stderr'] = stderr.decode() if stderr else ''
        task.outputs['service_status'] = task.outputs['stdout'].strip()
        
        return process.returncode == 0
    
    async def _execute_git_operation(self, workflow: Workflow, task: WorkflowTask) -> bool:
        """Execute git operation task"""
        operation = task.config.get('operation')  # clone, pull, push, checkout, commit
        repository_url = task.config.get('repository_url')
        branch = task.config.get('branch', 'main')
        working_directory = task.config.get('working_directory', '/home/dappnode/barbossa-engineer/projects')
        
        if not operation:
            raise ValueError("Git operation task requires 'operation' parameter")
        
        # Security validation for repository access
        if repository_url:
            try:
                security_guard.validate_operation('repository_access', repository_url)
            except SecurityViolationError as e:
                task.add_log('ERROR', f"Security violation: {e}")
                raise e
        
        task.add_log('INFO', f"Executing git operation: {operation}")
        
        if operation == 'clone':
            if not repository_url:
                raise ValueError("Clone operation requires 'repository_url' parameter")
            command = f"git clone {repository_url}"
        elif operation == 'pull':
            command = f"git pull origin {branch}"
        elif operation == 'push':
            command = f"git push origin {branch}"
        elif operation == 'checkout':
            command = f"git checkout {branch}"
        elif operation == 'commit':
            commit_message = task.config.get('commit_message', 'Automated commit by Barbossa')
            command = f"git add . && git commit -m '{commit_message}'"
        else:
            raise ValueError(f"Unknown git operation: {operation}")
        
        # Execute git command
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_directory
        )
        
        stdout, stderr = await process.communicate()
        
        task.outputs['exit_code'] = process.returncode
        task.outputs['stdout'] = stdout.decode() if stdout else ''
        task.outputs['stderr'] = stderr.decode() if stderr else ''
        
        return process.returncode == 0
    
    async def _execute_health_check(self, workflow: Workflow, task: WorkflowTask) -> bool:
        """Execute health check task"""
        check_type = task.config.get('check_type')  # http, tcp, service, disk, memory, cpu
        
        if check_type == 'http':
            url = task.config.get('url')
            expected_status = task.config.get('expected_status', 200)
            
            import aiohttp
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    task.outputs['status_code'] = response.status
                    task.outputs['response_text'] = await response.text()
                    return response.status == expected_status
        
        elif check_type == 'service':
            service_name = task.config.get('service_name')
            command = f"systemctl is-active {service_name}"
            
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            task.outputs['service_status'] = stdout.decode().strip()
            return task.outputs['service_status'] == 'active'
        
        elif check_type == 'disk':
            threshold = task.config.get('threshold', 90)  # percentage
            
            import shutil
            disk_usage = shutil.disk_usage('/')
            used_percent = (disk_usage.used / disk_usage.total) * 100
            
            task.outputs['disk_usage_percent'] = used_percent
            return used_percent < threshold
        
        # Add more health check types as needed
        return True
    
    async def _execute_wait(self, workflow: Workflow, task: WorkflowTask) -> bool:
        """Execute wait task"""
        duration = task.config.get('duration', 60)  # seconds
        
        task.add_log('INFO', f"Waiting for {duration} seconds")
        await asyncio.sleep(duration)
        
        return True
    
    async def _execute_file_operation(self, workflow: Workflow, task: WorkflowTask) -> bool:
        """Execute file operation task"""
        operation = task.config.get('operation')  # copy, move, delete, create, compress
        source = task.config.get('source')
        destination = task.config.get('destination')
        
        task.add_log('INFO', f"File operation: {operation}")
        
        if operation == 'copy':
            command = f"cp -r {source} {destination}"
        elif operation == 'move':
            command = f"mv {source} {destination}"
        elif operation == 'delete':
            command = f"rm -rf {source}"
        elif operation == 'compress':
            command = f"tar -czf {destination} {source}"
        else:
            raise ValueError(f"Unknown file operation: {operation}")
        
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        task.outputs['exit_code'] = process.returncode
        
        return process.returncode == 0
    
    async def _execute_api_call(self, workflow: Workflow, task: WorkflowTask) -> bool:
        """Execute API call task"""
        import aiohttp
        
        url = task.config.get('url')
        method = task.config.get('method', 'GET').upper()
        headers = task.config.get('headers', {})
        data = task.config.get('data')
        
        task.add_log('INFO', f"Making {method} request to {url}")
        
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, json=data) as response:
                task.outputs['status_code'] = response.status
                task.outputs['response'] = await response.text()
                
                expected_status = task.config.get('expected_status', 200)
                return response.status == expected_status
    
    async def _execute_database_operation(self, workflow: Workflow, task: WorkflowTask) -> bool:
        """Execute database operation task"""
        # Placeholder for database operations
        operation = task.config.get('operation')
        task.add_log('INFO', f"Database operation: {operation}")
        return True
    
    async def _execute_notification(self, workflow: Workflow, task: WorkflowTask) -> bool:
        """Execute notification task"""
        # Placeholder for notifications
        message = task.config.get('message', 'Workflow notification')
        task.add_log('INFO', f"Sending notification: {message}")
        return True
    
    async def _execute_conditional(self, workflow: Workflow, task: WorkflowTask) -> bool:
        """Execute conditional task"""
        condition = task.config.get('condition')
        # Evaluate condition logic here
        task.add_log('INFO', f"Evaluating condition: {condition}")
        return True
    
    async def _execute_parallel_group(self, workflow: Workflow, task: WorkflowTask) -> bool:
        """Execute parallel group task"""
        # Execute multiple tasks in parallel
        parallel_tasks = task.config.get('tasks', [])
        task.add_log('INFO', f"Executing {len(parallel_tasks)} tasks in parallel")
        
        # This would require more complex orchestration
        return True
    
    async def _execute_backup_operation(self, workflow: Workflow, task: WorkflowTask) -> bool:
        """Execute backup operation task"""
        backup_type = task.config.get('backup_type')  # database, files, system
        destination = task.config.get('destination')
        
        task.add_log('INFO', f"Creating {backup_type} backup")
        
        # Implement backup logic based on type
        if backup_type == 'database':
            # Database backup logic
            pass
        elif backup_type == 'files':
            # File backup logic
            source = task.config.get('source')
            command = f"tar -czf {destination} {source}"
            
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            return process.returncode == 0
        
        return True
    
    async def _execute_log_analysis(self, workflow: Workflow, task: WorkflowTask) -> bool:
        """Execute log analysis task"""
        log_file = task.config.get('log_file')
        pattern = task.config.get('pattern')
        
        task.add_log('INFO', f"Analyzing log file: {log_file}")
        
        if pattern:
            command = f"grep '{pattern}' {log_file} | wc -l"
            
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            if process.returncode == 0:
                match_count = int(stdout.decode().strip())
                task.outputs['match_count'] = match_count
                return True
        
        return False
    
    def _substitute_variables(self, text: str, variables: Dict[str, Any], task_outputs: Dict[str, Any]) -> str:
        """Substitute variables in text"""
        import re
        
        # Substitute workflow variables
        for key, value in variables.items():
            text = text.replace(f"${{{key}}}", str(value))
        
        # Substitute task outputs
        for key, value in task_outputs.items():
            text = text.replace(f"${{task.{key}}}", str(value))
        
        # Substitute system variables
        system_vars = {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'datetime': datetime.now().isoformat(),
            'timestamp': str(int(time.time())),
            'home': str(Path.home()),
            'user': os.getenv('USER', 'dappnode')
        }
        
        for key, value in system_vars.items():
            text = text.replace(f"${{system.{key}}}", value)
        
        return text


class WorkflowEngine:
    """Main workflow automation engine"""
    
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.workflows_dir = work_dir / 'workflows'
        self.templates_dir = work_dir / 'workflow_templates'
        self.db_path = work_dir / 'workflows.db'
        
        # Ensure directories exist
        self.workflows_dir.mkdir(exist_ok=True)
        self.templates_dir.mkdir(exist_ok=True)
        
        # Initialize components
        self.task_executor = TaskExecutor(self)
        self.scheduler = None  # Basic scheduler for now
        self.running_workflows: Dict[str, Workflow] = {}
        self.workflow_queue = asyncio.Queue()
        
        # Database and logging
        self._init_database()
        self._setup_logging()
        
        # Background worker
        self.worker_task = None
        self.running = False
    
    def _init_database(self):
        """Initialize workflow database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Workflows table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    status TEXT NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    started_at DATETIME,
                    completed_at DATETIME,
                    config TEXT,
                    error_message TEXT
                )
            ''')
            
            # Workflow executions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS workflow_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME,
                    trigger_type TEXT,
                    results TEXT,
                    error_message TEXT,
                    FOREIGN KEY (workflow_id) REFERENCES workflows (id)
                )
            ''')
            
            # Task executions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS task_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    execution_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    task_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at DATETIME,
                    completed_at DATETIME,
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    outputs TEXT
                )
            ''')
            
            conn.commit()
    
    def _setup_logging(self):
        """Setup logging for workflow engine"""
        log_file = self.work_dir / 'logs' / f"workflow_engine_{datetime.now().strftime('%Y%m%d')}.log"
        log_file.parent.mkdir(exist_ok=True)
        
        self.logger = logging.getLogger('WorkflowEngine')
        if not self.logger.handlers:
            handler = logging.FileHandler(log_file)
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def create_workflow_from_template(self, template_name: str, variables: Dict[str, Any] = None) -> Workflow:
        """Create workflow from template"""
        template_path = self.templates_dir / f"{template_name}.yaml"
        
        if not template_path.exists():
            raise FileNotFoundError(f"Workflow template not found: {template_name}")
        
        with open(template_path, 'r') as f:
            # Use json for now instead of yaml
            try:
                import yaml
                template_config = yaml.safe_load(f)
            except ImportError:
                # Fallback to json if yaml not available
                f.seek(0)
                template_config = json.load(f)
        
        # Substitute variables in template
        if variables:
            template_config = self._substitute_template_variables(template_config, variables)
        
        # Create workflow
        workflow_id = str(uuid.uuid4())
        workflow = Workflow(
            workflow_id=workflow_id,
            name=template_config.get('name', template_name),
            description=template_config.get('description', ''),
            config=template_config
        )
        
        # Store in database
        self._store_workflow(workflow)
        
        return workflow
    
    def create_workflow_from_config(self, config: Dict[str, Any]) -> Workflow:
        """Create workflow from configuration dictionary"""
        workflow_id = str(uuid.uuid4())
        workflow = Workflow(
            workflow_id=workflow_id,
            name=config.get('name', f'Workflow {workflow_id[:8]}'),
            description=config.get('description', ''),
            config=config
        )
        
        # Store in database
        self._store_workflow(workflow)
        
        return workflow
    
    async def execute_workflow(self, workflow: Workflow, trigger_type: TriggerType = TriggerType.MANUAL) -> bool:
        """Execute a workflow"""
        execution_id = str(uuid.uuid4())
        
        self.logger.info(f"Starting workflow execution: {workflow.name} (ID: {execution_id})")
        
        workflow.status = WorkflowStatus.RUNNING
        workflow.started_at = datetime.now()
        workflow.add_log('INFO', f"Workflow execution started (trigger: {trigger_type.value})")
        
        try:
            # Store execution record
            self._store_execution(workflow, execution_id, trigger_type)
            
            # Execute tasks based on execution order and dependencies
            for task_id in workflow.execution_order:
                task = workflow.tasks[task_id]
                
                # Wait for dependencies
                await self._wait_for_dependencies(workflow, task)
                
                # Execute task
                workflow.current_task = task_id
                success = await self.task_executor.execute_task(workflow, task)
                
                if not success and not task.config.get('continue_on_failure', False):
                    # Task failed and we shouldn't continue
                    workflow.status = WorkflowStatus.FAILED
                    workflow.error_message = f"Task {task.name} failed: {task.error_message}"
                    workflow.add_log('ERROR', workflow.error_message)
                    break
            
            else:
                # All tasks completed successfully
                workflow.status = WorkflowStatus.COMPLETED
                workflow.add_log('INFO', "Workflow completed successfully")
            
            workflow.completed_at = datetime.now()
            workflow.current_task = None
            
            # Update execution record
            self._update_execution(workflow, execution_id)
            
            self.logger.info(f"Workflow execution completed: {workflow.name} (Status: {workflow.status.value})")
            
            return workflow.status == WorkflowStatus.COMPLETED
        
        except Exception as e:
            workflow.status = WorkflowStatus.FAILED
            workflow.error_message = str(e)
            workflow.completed_at = datetime.now()
            workflow.add_log('ERROR', f"Workflow execution failed: {e}")
            
            self.logger.error(f"Workflow execution failed: {workflow.name} - {e}")
            
            # Update execution record
            self._update_execution(workflow, execution_id)
            
            return False
    
    async def _wait_for_dependencies(self, workflow: Workflow, task: WorkflowTask):
        """Wait for task dependencies to complete"""
        while True:
            dependencies_completed = all(
                workflow.tasks[dep_id].status == TaskStatus.COMPLETED
                for dep_id in task.dependencies
                if dep_id in workflow.tasks
            )
            
            if dependencies_completed:
                break
            
            await asyncio.sleep(1)
    
    def _substitute_template_variables(self, template: Any, variables: Dict[str, Any]) -> Any:
        """Recursively substitute variables in template"""
        if isinstance(template, dict):
            return {k: self._substitute_template_variables(v, variables) for k, v in template.items()}
        elif isinstance(template, list):
            return [self._substitute_template_variables(item, variables) for item in template]
        elif isinstance(template, str):
            for key, value in variables.items():
                template = template.replace(f"${{{key}}}", str(value))
            return template
        else:
            return template
    
    def _store_workflow(self, workflow: Workflow):
        """Store workflow in database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO workflows (id, name, description, status, config)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                workflow.workflow_id,
                workflow.name,
                workflow.description,
                workflow.status.value,
                json.dumps(workflow.config)
            ))
            conn.commit()
    
    def _store_execution(self, workflow: Workflow, execution_id: str, trigger_type: TriggerType):
        """Store workflow execution in database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO workflow_executions (workflow_id, execution_id, status, trigger_type)
                VALUES (?, ?, ?, ?)
            ''', (
                workflow.workflow_id,
                execution_id,
                workflow.status.value,
                trigger_type.value
            ))
            conn.commit()
    
    def _update_execution(self, workflow: Workflow, execution_id: str):
        """Update workflow execution in database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE workflow_executions 
                SET status = ?, completed_at = CURRENT_TIMESTAMP, 
                    results = ?, error_message = ?
                WHERE execution_id = ?
            ''', (
                workflow.status.value,
                json.dumps(workflow.to_dict()),
                workflow.error_message,
                execution_id
            ))
            conn.commit()
    
    def get_workflow_status(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get workflow status"""
        workflow = self.running_workflows.get(workflow_id)
        if workflow:
            return workflow.to_dict()
        
        # Check database for completed workflows
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM workflow_executions 
                WHERE workflow_id = ? 
                ORDER BY started_at DESC 
                LIMIT 1
            ''', (workflow_id,))
            
            result = cursor.fetchone()
            if result:
                columns = [desc[0] for desc in cursor.description]
                execution_data = dict(zip(columns, result))
                
                if execution_data.get('results'):
                    return json.loads(execution_data['results'])
        
        return None
    
    def list_workflows(self) -> List[Dict[str, Any]]:
        """List all workflows"""
        workflows = []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM workflows ORDER BY created_at DESC')
            
            columns = [desc[0] for desc in cursor.description]
            for row in cursor.fetchall():
                workflow_data = dict(zip(columns, row))
                workflow_data['config'] = json.loads(workflow_data['config'])
                workflows.append(workflow_data)
        
        return workflows
    
    def start_scheduler(self):
        """Start the workflow scheduler"""
        self.running = True
        
        # Set up scheduled workflows
        self._setup_scheduled_workflows()
        
        # Start background worker
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self.worker_task = loop.create_task(self._scheduler_loop())
        
        self.logger.info("Workflow scheduler started")
    
    def stop_scheduler(self):
        """Stop the workflow scheduler"""
        self.running = False
        
        if self.worker_task:
            self.worker_task.cancel()
        
        self.logger.info("Workflow scheduler stopped")
    
    def _setup_scheduled_workflows(self):
        """Set up scheduled workflows"""
        # Load workflows with schedule configurations
        workflows = self.list_workflows()
        
        for workflow_data in workflows:
            schedule_config = workflow_data['config'].get('schedule')
            if schedule_config:
                # Set up schedule based on configuration
                # This is a simplified implementation
                pass
    
    async def _scheduler_loop(self):
        """Background scheduler loop"""
        while self.running:
            try:
                # Run pending scheduled jobs (basic implementation)
                # schedule.run_pending()  # Disabled for now
                
                # Process workflow queue
                if not self.workflow_queue.empty():
                    workflow = await self.workflow_queue.get()
                    await self.execute_workflow(workflow)
                
                await asyncio.sleep(10)  # Check every 10 seconds
            
            except Exception as e:
                self.logger.error(f"Error in scheduler loop: {e}")
                await asyncio.sleep(10)


def main():
    """Main entry point for workflow engine"""
    work_dir = Path.home() / 'barbossa-engineer'
    engine = WorkflowEngine(work_dir)
    
    print("Barbossa Workflow Automation Engine")
    print(f"Work directory: {work_dir}")
    print(f"Database: {engine.db_path}")
    
    # Start scheduler
    engine.start_scheduler()
    
    try:
        # Keep running
        import time
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nShutting down...")
        engine.stop_scheduler()


if __name__ == "__main__":
    main()