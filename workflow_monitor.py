#!/usr/bin/env python3
"""
Barbossa Workflow Monitor
Real-time monitoring and alerting system for workflow automation
"""

import asyncio
import json
import logging
import sqlite3
import threading
import time
import smtplib
from collections import defaultdict, deque
from datetime import datetime, timedelta
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import subprocess

from workflow_automation import WorkflowEngine, WorkflowStatus, TaskStatus


class MetricsCollector:
    """Collects and aggregates workflow metrics"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.metrics = defaultdict(lambda: defaultdict(int))
        self.execution_times = defaultdict(list)
        self.error_counts = defaultdict(int)
        self.success_rates = defaultdict(float)
        self.lock = threading.Lock()
        
        self._init_metrics_db()
    
    def _init_metrics_db(self):
        """Initialize metrics database"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Workflow metrics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS workflow_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    workflow_id TEXT NOT NULL,
                    workflow_name TEXT,
                    metric_type TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    tags TEXT
                )
            ''')
            
            # Performance metrics table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    unit TEXT,
                    category TEXT
                )
            ''')
            
            conn.commit()
    
    def record_workflow_execution(self, workflow_id: str, workflow_name: str, 
                                status: str, duration: float, task_count: int = 0):
        """Record workflow execution metrics"""
        with self.lock:
            timestamp = datetime.now()
            
            # Store in database
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Execution duration
                cursor.execute('''
                    INSERT INTO workflow_metrics 
                    (workflow_id, workflow_name, metric_type, metric_value)
                    VALUES (?, ?, ?, ?)
                ''', (workflow_id, workflow_name, 'execution_duration', duration))
                
                # Task count
                if task_count > 0:
                    cursor.execute('''
                        INSERT INTO workflow_metrics 
                        (workflow_id, workflow_name, metric_type, metric_value)
                        VALUES (?, ?, ?, ?)
                    ''', (workflow_id, workflow_name, 'task_count', task_count))
                
                # Status
                status_value = 1 if status == 'completed' else 0
                cursor.execute('''
                    INSERT INTO workflow_metrics 
                    (workflow_id, workflow_name, metric_type, metric_value)
                    VALUES (?, ?, ?, ?)
                ''', (workflow_id, workflow_name, 'success', status_value))
                
                conn.commit()
            
            # Update in-memory metrics
            self.metrics[workflow_id]['executions'] += 1
            self.execution_times[workflow_id].append(duration)
            
            if status == 'completed':
                self.metrics[workflow_id]['successes'] += 1
            else:
                self.metrics[workflow_id]['failures'] += 1
                self.error_counts[workflow_id] += 1
            
            # Calculate success rate
            total = self.metrics[workflow_id]['executions']
            successes = self.metrics[workflow_id]['successes']
            self.success_rates[workflow_id] = (successes / total) * 100 if total > 0 else 0
            
            # Keep only last 100 execution times
            if len(self.execution_times[workflow_id]) > 100:
                self.execution_times[workflow_id] = self.execution_times[workflow_id][-100:]
    
    def record_system_metric(self, metric_name: str, value: float, unit: str = None, category: str = 'system'):
        """Record system performance metric"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO performance_metrics 
                (metric_name, metric_value, unit, category)
                VALUES (?, ?, ?, ?)
            ''', (metric_name, value, unit, category))
            conn.commit()
    
    def get_workflow_metrics(self, workflow_id: str = None, hours: int = 24) -> Dict[str, Any]:
        """Get workflow metrics for the specified time period"""
        cutoff = datetime.now() - timedelta(hours=hours)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            query = '''
                SELECT workflow_id, workflow_name, metric_type, 
                       AVG(metric_value) as avg_value,
                       COUNT(*) as count,
                       MIN(metric_value) as min_value,
                       MAX(metric_value) as max_value
                FROM workflow_metrics 
                WHERE timestamp > ?
            '''
            params = [cutoff]
            
            if workflow_id:
                query += ' AND workflow_id = ?'
                params.append(workflow_id)
            
            query += ' GROUP BY workflow_id, metric_type ORDER BY workflow_id'
            
            cursor.execute(query, params)
            
            metrics = defaultdict(lambda: defaultdict(dict))
            for row in cursor.fetchall():
                wf_id, wf_name, metric_type, avg_val, count, min_val, max_val = row
                metrics[wf_id][metric_type] = {
                    'workflow_name': wf_name,
                    'average': avg_val,
                    'count': count,
                    'min': min_val,
                    'max': max_val
                }
            
            return dict(metrics)
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary"""
        with self.lock:
            summary = {}
            
            for workflow_id, metrics in self.metrics.items():
                if metrics['executions'] > 0:
                    avg_duration = sum(self.execution_times[workflow_id]) / len(self.execution_times[workflow_id])
                    summary[workflow_id] = {
                        'executions': metrics['executions'],
                        'successes': metrics['successes'],
                        'failures': metrics['failures'],
                        'success_rate': self.success_rates[workflow_id],
                        'avg_duration': avg_duration,
                        'error_count': self.error_counts[workflow_id]
                    }
            
            return summary


class AlertManager:
    """Manages alerts and notifications for workflow monitoring"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.alert_rules = config.get('alert_rules', {})
        self.notification_channels = config.get('notification_channels', {})
        self.active_alerts = {}
        self.alert_history = deque(maxlen=1000)
        self.logger = logging.getLogger(__name__)
    
    def check_alerts(self, metrics: Dict[str, Any]):
        """Check metrics against alert rules"""
        current_time = datetime.now()
        alerts_triggered = []
        
        for rule_name, rule_config in self.alert_rules.items():
            try:
                if self._evaluate_rule(rule_config, metrics):
                    alert = {
                        'rule_name': rule_name,
                        'timestamp': current_time.isoformat(),
                        'severity': rule_config.get('severity', 'warning'),
                        'message': rule_config.get('message', f'Alert triggered: {rule_name}'),
                        'metrics': metrics
                    }
                    
                    # Check if this is a new alert or already active
                    if rule_name not in self.active_alerts:
                        self.active_alerts[rule_name] = alert
                        alerts_triggered.append(alert)
                        self.alert_history.append(alert)
                        self.logger.warning(f"Alert triggered: {rule_name}")
                    
                else:
                    # Clear active alert if condition no longer met
                    if rule_name in self.active_alerts:
                        resolved_alert = self.active_alerts[rule_name].copy()
                        resolved_alert['resolved_at'] = current_time.isoformat()
                        resolved_alert['status'] = 'resolved'
                        self.alert_history.append(resolved_alert)
                        del self.active_alerts[rule_name]
                        self.logger.info(f"Alert resolved: {rule_name}")
            
            except Exception as e:
                self.logger.error(f"Error evaluating alert rule {rule_name}: {e}")
        
        # Send notifications for new alerts
        for alert in alerts_triggered:
            self._send_notifications(alert)
        
        return alerts_triggered
    
    def _evaluate_rule(self, rule_config: Dict[str, Any], metrics: Dict[str, Any]) -> bool:
        """Evaluate a single alert rule"""
        condition = rule_config.get('condition', {})
        metric_path = condition.get('metric_path', '')
        operator = condition.get('operator', '>')
        threshold = condition.get('threshold', 0)
        
        # Navigate to metric value
        try:
            value = metrics
            for path_part in metric_path.split('.'):
                value = value[path_part]
            
            # Evaluate condition
            if operator == '>':
                return value > threshold
            elif operator == '<':
                return value < threshold
            elif operator == '>=':
                return value >= threshold
            elif operator == '<=':
                return value <= threshold
            elif operator == '==':
                return value == threshold
            elif operator == '!=':
                return value != threshold
            
        except (KeyError, TypeError):
            return False
        
        return False
    
    def _send_notifications(self, alert: Dict[str, Any]):
        """Send alert notifications"""
        for channel_name, channel_config in self.notification_channels.items():
            try:
                channel_type = channel_config.get('type')
                
                if channel_type == 'email':
                    self._send_email_notification(alert, channel_config)
                elif channel_type == 'webhook':
                    self._send_webhook_notification(alert, channel_config)
                elif channel_type == 'log':
                    self._send_log_notification(alert, channel_config)
                
            except Exception as e:
                self.logger.error(f"Error sending notification via {channel_name}: {e}")
    
    def _send_email_notification(self, alert: Dict[str, Any], config: Dict[str, Any]):
        """Send email notification"""
        # This is a basic implementation - would need proper SMTP configuration
        self.logger.info(f"EMAIL ALERT: {alert['message']}")
    
    def _send_webhook_notification(self, alert: Dict[str, Any], config: Dict[str, Any]):
        """Send webhook notification"""
        webhook_url = config.get('url')
        # This would send HTTP POST to webhook URL
        self.logger.info(f"WEBHOOK ALERT to {webhook_url}: {alert['message']}")
    
    def _send_log_notification(self, alert: Dict[str, Any], config: Dict[str, Any]):
        """Send log notification"""
        severity = alert.get('severity', 'warning')
        if severity == 'critical':
            self.logger.critical(f"CRITICAL ALERT: {alert['message']}")
        elif severity == 'error':
            self.logger.error(f"ERROR ALERT: {alert['message']}")
        else:
            self.logger.warning(f"WARNING ALERT: {alert['message']}")
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get currently active alerts"""
        return list(self.active_alerts.values())
    
    def get_alert_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get alert history"""
        return list(self.alert_history)[-limit:]


class WorkflowMonitor:
    """Main workflow monitoring system"""
    
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.db_path = work_dir / 'monitoring.db'
        self.config_file = work_dir / 'monitor_config.json'
        
        # Initialize components
        self.metrics_collector = MetricsCollector(self.db_path)
        self.alert_manager = None
        self.workflow_engine = None
        
        # Monitoring state
        self.running = False
        self.monitor_thread = None
        self.last_check_time = datetime.now()
        
        # Load configuration
        self._load_configuration()
        self._setup_logging()
    
    def _load_configuration(self):
        """Load monitoring configuration"""
        if self.config_file.exists():
            with open(self.config_file, 'r') as f:
                config = json.load(f)
        else:
            # Default configuration
            config = {
                'check_interval': 60,  # seconds
                'alert_rules': {
                    'high_failure_rate': {
                        'condition': {
                            'metric_path': 'failure_rate',
                            'operator': '>',
                            'threshold': 50
                        },
                        'severity': 'warning',
                        'message': 'High failure rate detected in workflows'
                    },
                    'workflow_stuck': {
                        'condition': {
                            'metric_path': 'max_execution_time',
                            'operator': '>',
                            'threshold': 3600  # 1 hour
                        },
                        'severity': 'critical',
                        'message': 'Workflow execution time exceeded threshold'
                    }
                },
                'notification_channels': {
                    'log': {'type': 'log'},
                    'email': {
                        'type': 'email',
                        'smtp_server': 'localhost',
                        'smtp_port': 587,
                        'recipients': ['admin@localhost']
                    }
                }
            }
            
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
        
        self.config = config
        self.alert_manager = AlertManager(config)
    
    def _setup_logging(self):
        """Setup logging for monitor"""
        log_file = self.work_dir / 'logs' / f"monitor_{datetime.now().strftime('%Y%m%d')}.log"
        log_file.parent.mkdir(exist_ok=True)
        
        self.logger = logging.getLogger('WorkflowMonitor')
        if not self.logger.handlers:
            handler = logging.FileHandler(log_file)
            handler.setFormatter(logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def start_monitoring(self, workflow_engine=None):
        """Start the monitoring system"""
        if self.running:
            return
        
        self.workflow_engine = workflow_engine
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self.monitor_thread.start()
        
        self.logger.info("Workflow monitoring started")
    
    def stop_monitoring(self):
        """Stop the monitoring system"""
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        self.logger.info("Workflow monitoring stopped")
    
    def _monitoring_loop(self):
        """Main monitoring loop"""
        check_interval = self.config.get('check_interval', 60)
        
        while self.running:
            try:
                current_time = datetime.now()
                
                # Collect system metrics
                self._collect_system_metrics()
                
                # Collect workflow metrics
                workflow_metrics = self._collect_workflow_metrics()
                
                # Check alerts
                if self.alert_manager:
                    self.alert_manager.check_alerts(workflow_metrics)
                
                # Update last check time
                self.last_check_time = current_time
                
                # Sleep until next check
                time.sleep(check_interval)
                
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(check_interval)
    
    def _collect_system_metrics(self):
        """Collect system performance metrics"""
        try:
            # CPU usage
            cpu_percent = self._get_cpu_usage()
            self.metrics_collector.record_system_metric('cpu_usage', cpu_percent, 'percent', 'system')
            
            # Memory usage
            memory_percent = self._get_memory_usage()
            self.metrics_collector.record_system_metric('memory_usage', memory_percent, 'percent', 'system')
            
            # Disk usage
            disk_percent = self._get_disk_usage()
            self.metrics_collector.record_system_metric('disk_usage', disk_percent, 'percent', 'system')
            
        except Exception as e:
            self.logger.error(f"Error collecting system metrics: {e}")
    
    def _collect_workflow_metrics(self) -> Dict[str, Any]:
        """Collect workflow-specific metrics"""
        metrics = {
            'total_workflows': 0,
            'running_workflows': 0,
            'failed_workflows': 0,
            'avg_execution_time': 0,
            'max_execution_time': 0,
            'failure_rate': 0
        }
        
        try:
            if self.workflow_engine:
                # Get workflow statistics
                workflow_metrics = self.metrics_collector.get_workflow_metrics(hours=1)
                
                total_executions = 0
                total_failures = 0
                execution_times = []
                
                for workflow_id, wf_metrics in workflow_metrics.items():
                    if 'success' in wf_metrics:
                        success_count = wf_metrics['success']['count']
                        success_avg = wf_metrics['success']['average']
                        total_executions += success_count
                        total_failures += success_count * (1 - success_avg)
                    
                    if 'execution_duration' in wf_metrics:
                        duration_metrics = wf_metrics['execution_duration']
                        execution_times.extend([duration_metrics['average']] * duration_metrics['count'])
                        metrics['max_execution_time'] = max(metrics['max_execution_time'], duration_metrics['max'])
                
                metrics['total_workflows'] = len(workflow_metrics)
                metrics['failure_rate'] = (total_failures / max(total_executions, 1)) * 100
                metrics['avg_execution_time'] = sum(execution_times) / max(len(execution_times), 1)
                
                # Count running workflows
                if hasattr(self.workflow_engine, 'running_workflows'):
                    metrics['running_workflows'] = len(self.workflow_engine.running_workflows)
        
        except Exception as e:
            self.logger.error(f"Error collecting workflow metrics: {e}")
        
        return metrics
    
    def _get_cpu_usage(self) -> float:
        """Get CPU usage percentage"""
        try:
            # Use top command to get CPU usage
            result = subprocess.run(['top', '-bn1'], capture_output=True, text=True, timeout=5)
            for line in result.stdout.split('\n'):
                if 'Cpu(s)' in line:
                    # Parse CPU usage from top output
                    parts = line.split(',')
                    for part in parts:
                        if 'us' in part:  # user space
                            return float(part.split('%')[0].strip())
        except:
            pass
        return 0.0
    
    def _get_memory_usage(self) -> float:
        """Get memory usage percentage"""
        try:
            with open('/proc/meminfo', 'r') as f:
                lines = f.readlines()
                
            mem_total = 0
            mem_available = 0
            
            for line in lines:
                if line.startswith('MemTotal:'):
                    mem_total = int(line.split()[1])
                elif line.startswith('MemAvailable:'):
                    mem_available = int(line.split()[1])
            
            if mem_total > 0:
                return ((mem_total - mem_available) / mem_total) * 100
        except:
            pass
        return 0.0
    
    def _get_disk_usage(self) -> float:
        """Get disk usage percentage"""
        try:
            result = subprocess.run(['df', '/'], capture_output=True, text=True, timeout=5)
            lines = result.stdout.strip().split('\n')
            if len(lines) > 1:
                parts = lines[1].split()
                if len(parts) >= 5:
                    usage_str = parts[4]
                    if usage_str.endswith('%'):
                        return float(usage_str[:-1])
        except:
            pass
        return 0.0
    
    def get_monitoring_status(self) -> Dict[str, Any]:
        """Get monitoring system status"""
        return {
            'running': self.running,
            'last_check': self.last_check_time.isoformat(),
            'active_alerts': len(self.alert_manager.get_active_alerts()) if self.alert_manager else 0,
            'check_interval': self.config.get('check_interval', 60),
            'uptime_seconds': (datetime.now() - self.last_check_time).total_seconds() if self.running else 0
        }
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive monitoring dashboard data"""
        # Get recent workflow metrics
        workflow_metrics = self.metrics_collector.get_workflow_metrics(hours=24)
        performance_summary = self.metrics_collector.get_performance_summary()
        
        # Get alerts
        active_alerts = self.alert_manager.get_active_alerts() if self.alert_manager else []
        alert_history = self.alert_manager.get_alert_history(50) if self.alert_manager else []
        
        # Get system metrics from last hour
        current_metrics = self._collect_workflow_metrics()
        
        return {
            'timestamp': datetime.now().isoformat(),
            'monitoring_status': self.get_monitoring_status(),
            'workflow_metrics': workflow_metrics,
            'performance_summary': performance_summary,
            'current_metrics': current_metrics,
            'active_alerts': active_alerts,
            'recent_alerts': alert_history,
            'alert_summary': {
                'active_count': len(active_alerts),
                'critical_count': len([a for a in active_alerts if a.get('severity') == 'critical']),
                'warning_count': len([a for a in active_alerts if a.get('severity') == 'warning'])
            }
        }


def main():
    """Main entry point for workflow monitor"""
    work_dir = Path.home() / 'barbossa-engineer'
    monitor = WorkflowMonitor(work_dir)
    
    print("Barbossa Workflow Monitor")
    print(f"Work directory: {work_dir}")
    print(f"Database: {monitor.db_path}")
    
    # Start monitoring
    monitor.start_monitoring()
    
    try:
        # Keep running and show periodic status
        while True:
            time.sleep(60)
            status = monitor.get_monitoring_status()
            print(f"Monitor status: Running={status['running']}, "
                  f"Active alerts={status['active_alerts']}, "
                  f"Last check={status['last_check']}")
    
    except KeyboardInterrupt:
        print("\nShutting down...")
        monitor.stop_monitoring()


if __name__ == "__main__":
    main()