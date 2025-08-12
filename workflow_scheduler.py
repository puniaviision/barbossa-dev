#!/usr/bin/env python3
"""
Barbossa Workflow Scheduler
Advanced scheduling service for workflow automation with cron-like functionality
"""

import asyncio
import json
import logging
import signal
import sys
import threading
import time
import croniter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
import sqlite3
import yaml

# Import workflow components
from workflow_automation import WorkflowEngine, TriggerType, WorkflowStatus


class CronScheduler:
    """Cron-like scheduler for workflows"""
    
    def __init__(self):
        self.scheduled_jobs = {}
        self.running = False
        self.thread = None
        self.logger = logging.getLogger(__name__)
    
    def add_job(self, job_id: str, cron_expression: str, callback, **kwargs):
        """Add a scheduled job"""
        try:
            # Validate cron expression
            croniter.croniter(cron_expression)
            
            self.scheduled_jobs[job_id] = {
                'cron_expression': cron_expression,
                'callback': callback,
                'kwargs': kwargs,
                'next_run': None,
                'last_run': None,
                'run_count': 0
            }
            
            # Calculate next run time
            self._update_next_run(job_id)
            
            self.logger.info(f"Scheduled job {job_id}: {cron_expression}")
            
        except ValueError as e:
            self.logger.error(f"Invalid cron expression for job {job_id}: {e}")
            raise
    
    def remove_job(self, job_id: str):
        """Remove a scheduled job"""
        if job_id in self.scheduled_jobs:
            del self.scheduled_jobs[job_id]
            self.logger.info(f"Removed scheduled job {job_id}")
    
    def _update_next_run(self, job_id: str):
        """Update next run time for a job"""
        if job_id in self.scheduled_jobs:
            job = self.scheduled_jobs[job_id]
            cron = croniter.croniter(job['cron_expression'], datetime.now())
            job['next_run'] = cron.get_next(datetime)
    
    def start(self):
        """Start the scheduler"""
        if self.running:
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._scheduler_loop, daemon=True)
        self.thread.start()
        self.logger.info("Scheduler started")
    
    def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self.logger.info("Scheduler stopped")
    
    def _scheduler_loop(self):
        """Main scheduler loop"""
        while self.running:
            try:
                current_time = datetime.now()
                
                # Check all scheduled jobs
                for job_id, job in list(self.scheduled_jobs.items()):
                    if job['next_run'] and current_time >= job['next_run']:
                        try:
                            # Execute job
                            self.logger.info(f"Executing scheduled job: {job_id}")
                            job['callback'](**job['kwargs'])
                            
                            # Update statistics
                            job['last_run'] = current_time
                            job['run_count'] += 1
                            
                            # Calculate next run
                            self._update_next_run(job_id)
                            
                        except Exception as e:
                            self.logger.error(f"Error executing job {job_id}: {e}")
                
                # Sleep for 30 seconds before next check
                time.sleep(30)
                
            except Exception as e:
                self.logger.error(f"Error in scheduler loop: {e}")
                time.sleep(30)
    
    def get_job_status(self) -> Dict[str, Any]:
        """Get status of all scheduled jobs"""
        jobs_status = {}
        current_time = datetime.now()
        
        for job_id, job in self.scheduled_jobs.items():
            jobs_status[job_id] = {
                'cron_expression': job['cron_expression'],
                'next_run': job['next_run'].isoformat() if job['next_run'] else None,
                'last_run': job['last_run'].isoformat() if job['last_run'] else None,
                'run_count': job['run_count'],
                'time_until_next': str(job['next_run'] - current_time) if job['next_run'] else None
            }
        
        return jobs_status


class WorkflowSchedulerService:
    """Main workflow scheduler service"""
    
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.db_path = work_dir / 'scheduler.db'
        self.config_file = work_dir / 'scheduler_config.json'
        
        # Initialize components
        self.workflow_engine = WorkflowEngine(work_dir)
        self.cron_scheduler = CronScheduler()
        self.scheduled_workflows = {}
        
        # Service state
        self.running = False
        self.shutdown_event = threading.Event()
        
        # Initialize database and logging
        self._init_database()
        self._setup_logging()
        
        # Load configuration
        self._load_configuration()
    
    def _init_database(self):
        """Initialize scheduler database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Scheduled workflows table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scheduled_workflows (
                    id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    workflow_name TEXT,
                    cron_expression TEXT NOT NULL,
                    enabled BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    last_executed DATETIME,
                    next_execution DATETIME,
                    execution_count INTEGER DEFAULT 0,
                    config TEXT
                )
            ''')
            
            # Execution history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scheduler_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    schedule_id TEXT NOT NULL,
                    workflow_id TEXT NOT NULL,
                    executed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    status TEXT NOT NULL,
                    duration_seconds INTEGER,
                    error_message TEXT,
                    FOREIGN KEY (schedule_id) REFERENCES scheduled_workflows (id)
                )
            ''')
            
            conn.commit()
    
    def _setup_logging(self):
        """Setup logging for scheduler service"""
        log_file = self.work_dir / 'logs' / f"scheduler_{datetime.now().strftime('%Y%m%d')}.log"
        log_file.parent.mkdir(exist_ok=True)
        
        self.logger = logging.getLogger('WorkflowScheduler')
        if not self.logger.handlers:
            handler = logging.FileHandler(log_file)
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def _load_configuration(self):
        """Load scheduler configuration"""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                
                # Load scheduled workflows from config
                for schedule_config in config.get('scheduled_workflows', []):
                    self.add_scheduled_workflow(**schedule_config)
    
    def _save_configuration(self):
        """Save scheduler configuration"""
        config = {
            'scheduled_workflows': [],
            'last_updated': datetime.now().isoformat()
        }
        
        # Get scheduled workflows from database
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM scheduled_workflows WHERE enabled = 1')
            
            columns = [desc[0] for desc in cursor.description]
            for row in cursor.fetchall():
                schedule_data = dict(zip(columns, row))
                config['scheduled_workflows'].append({
                    'workflow_id': schedule_data['workflow_id'],
                    'cron_expression': schedule_data['cron_expression'],
                    'enabled': bool(schedule_data['enabled'])
                })
        
        with open(self.config_file, 'w') as f:
            json.dump(config, f, indent=2)
    
    def add_scheduled_workflow(self, workflow_id: str, cron_expression: str, enabled: bool = True):
        """Add a workflow to the schedule"""
        try:
            schedule_id = f"schedule_{workflow_id}_{int(time.time())}"
            
            # Get workflow name
            workflow_name = None
            workflows = self.workflow_engine.list_workflows()
            for workflow in workflows:
                if workflow['id'] == workflow_id:
                    workflow_name = workflow['name']
                    break
            
            # Store in database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO scheduled_workflows 
                    (id, workflow_id, workflow_name, cron_expression, enabled)
                    VALUES (?, ?, ?, ?, ?)
                ''', (schedule_id, workflow_id, workflow_name, cron_expression, enabled))
                conn.commit()
            
            # Add to cron scheduler if enabled
            if enabled:
                self.cron_scheduler.add_job(
                    schedule_id,
                    cron_expression,
                    self._execute_scheduled_workflow,
                    schedule_id=schedule_id,
                    workflow_id=workflow_id
                )
            
            self.logger.info(f"Added scheduled workflow: {workflow_name} ({workflow_id}) - {cron_expression}")
            return schedule_id
            
        except Exception as e:
            self.logger.error(f"Error adding scheduled workflow: {e}")
            raise
    
    def remove_scheduled_workflow(self, schedule_id: str):
        """Remove a workflow from the schedule"""
        try:
            # Remove from cron scheduler
            self.cron_scheduler.remove_job(schedule_id)
            
            # Remove from database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM scheduled_workflows WHERE id = ?', (schedule_id,))
                conn.commit()
            
            self.logger.info(f"Removed scheduled workflow: {schedule_id}")
            
        except Exception as e:
            self.logger.error(f"Error removing scheduled workflow: {e}")
            raise
    
    def enable_scheduled_workflow(self, schedule_id: str):
        """Enable a scheduled workflow"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT workflow_id, cron_expression FROM scheduled_workflows 
                    WHERE id = ?
                ''', (schedule_id,))
                result = cursor.fetchone()
                
                if result:
                    workflow_id, cron_expression = result
                    
                    # Add to cron scheduler
                    self.cron_scheduler.add_job(
                        schedule_id,
                        cron_expression,
                        self._execute_scheduled_workflow,
                        schedule_id=schedule_id,
                        workflow_id=workflow_id
                    )
                    
                    # Update database
                    cursor.execute('''
                        UPDATE scheduled_workflows SET enabled = 1 WHERE id = ?
                    ''', (schedule_id,))
                    conn.commit()
                    
                    self.logger.info(f"Enabled scheduled workflow: {schedule_id}")
            
        except Exception as e:
            self.logger.error(f"Error enabling scheduled workflow: {e}")
            raise
    
    def disable_scheduled_workflow(self, schedule_id: str):
        """Disable a scheduled workflow"""
        try:
            # Remove from cron scheduler
            self.cron_scheduler.remove_job(schedule_id)
            
            # Update database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE scheduled_workflows SET enabled = 0 WHERE id = ?
                ''', (schedule_id,))
                conn.commit()
            
            self.logger.info(f"Disabled scheduled workflow: {schedule_id}")
            
        except Exception as e:
            self.logger.error(f"Error disabling scheduled workflow: {e}")
            raise
    
    def _execute_scheduled_workflow(self, schedule_id: str, workflow_id: str):
        """Execute a scheduled workflow"""
        start_time = datetime.now()
        
        try:
            self.logger.info(f"Executing scheduled workflow: {workflow_id}")
            
            # Get workflow configuration
            workflows = self.workflow_engine.list_workflows()
            workflow_config = None
            
            for workflow_data in workflows:
                if workflow_data['id'] == workflow_id:
                    workflow_config = workflow_data
                    break
            
            if not workflow_config:
                raise Exception(f"Workflow {workflow_id} not found")
            
            # Create workflow instance
            from workflow_automation import Workflow
            workflow = Workflow(
                workflow_id=workflow_config['id'],
                name=workflow_config['name'],
                description=workflow_config['description'],
                config=workflow_config.get('config', {})
            )
            
            # Execute workflow
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success = loop.run_until_complete(
                self.workflow_engine.execute_workflow(workflow, TriggerType.SCHEDULE)
            )
            loop.close()
            
            # Calculate duration
            duration = (datetime.now() - start_time).total_seconds()
            
            # Record execution
            self._record_execution(schedule_id, workflow_id, 'completed' if success else 'failed', duration)
            
            # Update last execution time
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE scheduled_workflows 
                    SET last_executed = ?, execution_count = execution_count + 1
                    WHERE id = ?
                ''', (start_time, schedule_id))
                conn.commit()
            
            self.logger.info(f"Scheduled workflow completed: {workflow_id} (success: {success})")
            
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            self._record_execution(schedule_id, workflow_id, 'failed', duration, str(e))
            self.logger.error(f"Error executing scheduled workflow {workflow_id}: {e}")
    
    def _record_execution(self, schedule_id: str, workflow_id: str, status: str, duration: float, error_message: str = None):
        """Record workflow execution in database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO scheduler_executions 
                (schedule_id, workflow_id, status, duration_seconds, error_message)
                VALUES (?, ?, ?, ?, ?)
            ''', (schedule_id, workflow_id, status, int(duration), error_message))
            conn.commit()
    
    def get_scheduled_workflows(self) -> List[Dict[str, Any]]:
        """Get all scheduled workflows"""
        scheduled_workflows = []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT sw.*, 
                       COUNT(se.id) as total_executions,
                       SUM(CASE WHEN se.status = 'completed' THEN 1 ELSE 0 END) as successful_executions
                FROM scheduled_workflows sw
                LEFT JOIN scheduler_executions se ON sw.id = se.schedule_id
                GROUP BY sw.id
                ORDER BY sw.created_at DESC
            ''')
            
            columns = [desc[0] for desc in cursor.description]
            for row in cursor.fetchall():
                schedule_data = dict(zip(columns, row))
                
                # Get job status from cron scheduler
                job_status = self.cron_scheduler.get_job_status().get(schedule_data['id'], {})
                schedule_data.update(job_status)
                
                scheduled_workflows.append(schedule_data)
        
        return scheduled_workflows
    
    def get_execution_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get workflow execution history"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT se.*, sw.workflow_name
                FROM scheduler_executions se
                LEFT JOIN scheduled_workflows sw ON se.schedule_id = sw.id
                ORDER BY se.executed_at DESC
                LIMIT ?
            ''', (limit,))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def get_scheduler_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Total scheduled workflows
            cursor.execute('SELECT COUNT(*) FROM scheduled_workflows')
            total_scheduled = cursor.fetchone()[0]
            
            # Active scheduled workflows
            cursor.execute('SELECT COUNT(*) FROM scheduled_workflows WHERE enabled = 1')
            active_scheduled = cursor.fetchone()[0]
            
            # Total executions
            cursor.execute('SELECT COUNT(*) FROM scheduler_executions')
            total_executions = cursor.fetchone()[0]
            
            # Successful executions
            cursor.execute('SELECT COUNT(*) FROM scheduler_executions WHERE status = "completed"')
            successful_executions = cursor.fetchone()[0]
            
            # Recent executions (last 24 hours)
            cursor.execute('''
                SELECT COUNT(*) FROM scheduler_executions 
                WHERE executed_at > datetime('now', '-1 day')
            ''')
            recent_executions = cursor.fetchone()[0]
        
        success_rate = (successful_executions / max(total_executions, 1)) * 100
        
        return {
            'total_scheduled': total_scheduled,
            'active_scheduled': active_scheduled,
            'total_executions': total_executions,
            'successful_executions': successful_executions,
            'recent_executions': recent_executions,
            'success_rate': success_rate,
            'scheduler_running': self.running,
            'cron_jobs_count': len(self.cron_scheduler.scheduled_jobs)
        }
    
    def start(self):
        """Start the scheduler service"""
        if self.running:
            return
        
        self.running = True
        self.logger.info("Starting workflow scheduler service")
        
        # Start workflow engine scheduler
        self.workflow_engine.start_scheduler()
        
        # Start cron scheduler
        self.cron_scheduler.start()
        
        # Load and schedule existing workflows
        self._load_existing_schedules()
        
        self.logger.info("Workflow scheduler service started")
    
    def stop(self):
        """Stop the scheduler service"""
        if not self.running:
            return
        
        self.running = False
        self.logger.info("Stopping workflow scheduler service")
        
        # Stop schedulers
        self.cron_scheduler.stop()
        self.workflow_engine.stop_scheduler()
        
        # Save configuration
        self._save_configuration()
        
        self.logger.info("Workflow scheduler service stopped")
    
    def _load_existing_schedules(self):
        """Load existing schedules from database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, workflow_id, cron_expression 
                FROM scheduled_workflows 
                WHERE enabled = 1
            ''')
            
            for schedule_id, workflow_id, cron_expression in cursor.fetchall():
                try:
                    self.cron_scheduler.add_job(
                        schedule_id,
                        cron_expression,
                        self._execute_scheduled_workflow,
                        schedule_id=schedule_id,
                        workflow_id=workflow_id
                    )
                except Exception as e:
                    self.logger.error(f"Error loading schedule {schedule_id}: {e}")


def main():
    """Main entry point for scheduler service"""
    work_dir = Path.home() / 'barbossa-engineer'
    scheduler_service = WorkflowSchedulerService(work_dir)
    
    def signal_handler(signum, frame):
        print(f"\nReceived signal {signum}, shutting down...")
        scheduler_service.stop()
        sys.exit(0)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    print("Barbossa Workflow Scheduler Service")
    print(f"Work directory: {work_dir}")
    print(f"Database: {scheduler_service.db_path}")
    
    # Start service
    scheduler_service.start()
    
    try:
        # Keep running
        while True:
            time.sleep(60)
            # Print periodic status
            stats = scheduler_service.get_scheduler_stats()
            print(f"Status: {stats['active_scheduled']} active schedules, "
                  f"{stats['recent_executions']} recent executions")
    
    except KeyboardInterrupt:
        print("\nShutting down...")
        scheduler_service.stop()


if __name__ == "__main__":
    main()