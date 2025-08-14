#!/usr/bin/env python3
"""
Monitoring API Module for Barbossa Web Portal
Specialized endpoints for comprehensive system monitoring, alerting, and observability
"""

import json
import os
import sys
import logging
import psutil
import sqlite3
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from flask import Blueprint, jsonify, request, Response
from werkzeug.exceptions import BadRequest, NotFound
import hashlib
import re
from collections import defaultdict, deque
# Optional analytics dependencies
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    # Simple numpy replacement
    class np:
        @staticmethod
        def array(data): return data
        @staticmethod
        def mean(data): return sum(data) / len(data) if data else 0
        @staticmethod
        def std(data): 
            if not data:
                return 0
            mean = sum(data) / len(data)
            variance = sum((x - mean) ** 2 for x in data) / len(data)
            return variance ** 0.5
        @staticmethod
        def median(data): 
            if not data:
                return 0
            sorted_data = sorted(data)
            n = len(sorted_data)
            return sorted_data[n//2] if n % 2 == 1 else (sorted_data[n//2-1] + sorted_data[n//2]) / 2
        @staticmethod
        def percentile(data, percentile):
            if not data:
                return 0
            sorted_data = sorted(data)
            k = (len(sorted_data) - 1) * percentile / 100
            f = int(k)
            c = k - f
            if f + 1 < len(sorted_data):
                return sorted_data[f] * (1 - c) + sorted_data[f + 1] * c
            else:
                return sorted_data[f]
        @staticmethod
        def min(data): return min(data) if data else 0
        @staticmethod
        def max(data): return max(data) if data else 0

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

try:
    from server_manager import BarbossaServerManager
    SERVER_MANAGER_AVAILABLE = True
except ImportError:
    SERVER_MANAGER_AVAILABLE = False

# Create monitoring API blueprint
monitoring_api = Blueprint('monitoring_api', __name__, url_prefix='/api/monitoring')

# Global monitoring state
active_monitors = {}
alert_rules = {}
monitoring_lock = threading.Lock()
metrics_history = deque(maxlen=10000)
performance_baselines = {}

# Monitoring configuration
MONITORING_CONFIG = {
    'default_interval': 30,  # seconds
    'max_monitors': 50,
    'alert_cooldown': 300,  # 5 minutes
    'baseline_learning_period': 3600,  # 1 hour
    'anomaly_sensitivity': 2.0
}

# ============================================================================
# CORE MONITORING FUNCTIONS
# ============================================================================

def get_server_manager():
    """Get server manager instance"""
    if not SERVER_MANAGER_AVAILABLE:
        return None
    try:
        return BarbossaServerManager()
    except Exception:
        return None

def calculate_baseline_metrics():
    """Calculate baseline performance metrics for anomaly detection"""
    if len(metrics_history) < 100:  # Need sufficient data
        return
    
    # Convert to structured data
    metrics_data = defaultdict(list)
    for metric_snapshot in metrics_history:
        for key, value in metric_snapshot.items():
            if isinstance(value, (int, float)) and value is not None:
                metrics_data[key].append(value)
    
    # Calculate baselines
    with monitoring_lock:
        for metric, values in metrics_data.items():
            if len(values) >= 50:  # Need minimum data points
                values_array = np.array(values)
                performance_baselines[metric] = {
                    'mean': float(np.mean(values_array)),
                    'std': float(np.std(values_array)),
                    'median': float(np.median(values_array)),
                    'p95': float(np.percentile(values_array, 95)),
                    'p99': float(np.percentile(values_array, 99)),
                    'min': float(np.min(values_array)),
                    'max': float(np.max(values_array)),
                    'last_updated': datetime.now().isoformat()
                }

def detect_anomalies(current_metrics: Dict) -> List[Dict]:
    """Detect anomalies in current metrics against baselines"""
    anomalies = []
    
    if not performance_baselines:
        return anomalies
    
    for metric, value in current_metrics.items():
        if metric in performance_baselines and isinstance(value, (int, float)) and value is not None:
            baseline = performance_baselines[metric]
            
            # Z-score based anomaly detection
            if baseline['std'] > 0:
                z_score = abs(value - baseline['mean']) / baseline['std']
                
                if z_score > MONITORING_CONFIG['anomaly_sensitivity']:
                    anomalies.append({
                        'metric': metric,
                        'current_value': value,
                        'baseline_mean': baseline['mean'],
                        'z_score': z_score,
                        'severity': 'high' if z_score > 3 else 'medium',
                        'timestamp': datetime.now().isoformat()
                    })
    
    return anomalies

# ============================================================================
# REAL-TIME MONITORING ENDPOINTS
# ============================================================================

@monitoring_api.route('/monitors', methods=['GET', 'POST'])
def monitors():
    """Manage monitoring configurations"""
    if request.method == 'GET':
        return get_monitors()
    elif request.method == 'POST':
        return create_monitor()

def get_monitors():
    """Get all active monitors"""
    with monitoring_lock:
        return jsonify({
            'monitors': list(active_monitors.values()),
            'total': len(active_monitors),
            'max_allowed': MONITORING_CONFIG['max_monitors']
        })

def create_monitor():
    """Create a new monitor"""
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['name', 'type', 'config']
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return jsonify({'error': f'Missing required fields: {missing_fields}'}), 400
    
    with monitoring_lock:
        if len(active_monitors) >= MONITORING_CONFIG['max_monitors']:
            return jsonify({'error': 'Maximum number of monitors reached'}), 429
    
    monitor_id = str(uuid.uuid4())
    monitor = {
        'id': monitor_id,
        'name': data['name'],
        'type': data['type'],
        'config': data['config'],
        'status': 'active',
        'created_at': datetime.now().isoformat(),
        'last_check': None,
        'check_count': 0,
        'alerts_triggered': 0
    }
    
    # Validate monitor type and config
    if monitor['type'] not in ['metric_threshold', 'service_health', 'process_monitor', 'log_monitor']:
        return jsonify({'error': 'Invalid monitor type'}), 400
    
    # Start monitor
    try:
        with monitoring_lock:
            active_monitors[monitor_id] = monitor
        
        # Start monitoring thread
        monitor_thread = threading.Thread(
            target=run_monitor,
            args=(monitor_id,),
            daemon=True
        )
        monitor_thread.start()
        
        return jsonify({
            'success': True,
            'monitor': monitor
        }), 201
        
    except Exception as e:
        return jsonify({'error': f'Failed to create monitor: {str(e)}'}), 500

@monitoring_api.route('/monitors/<monitor_id>', methods=['GET', 'PUT', 'DELETE'])
def monitor_detail(monitor_id):
    """Manage specific monitor"""
    with monitoring_lock:
        if monitor_id not in active_monitors:
            return jsonify({'error': 'Monitor not found'}), 404
    
    if request.method == 'GET':
        return jsonify(active_monitors[monitor_id])
    
    elif request.method == 'PUT':
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400
        
        data = request.get_json()
        with monitoring_lock:
            active_monitors[monitor_id].update(data)
            active_monitors[monitor_id]['updated_at'] = datetime.now().isoformat()
        
        return jsonify(active_monitors[monitor_id])
    
    elif request.method == 'DELETE':
        with monitoring_lock:
            monitor = active_monitors.pop(monitor_id, None)
        
        if monitor:
            return jsonify({'success': True, 'message': 'Monitor deleted'})
        else:
            return jsonify({'error': 'Monitor not found'}), 404

def run_monitor(monitor_id: str):
    """Run monitoring checks for a specific monitor"""
    while monitor_id in active_monitors:
        try:
            with monitoring_lock:
                monitor = active_monitors.get(monitor_id)
            
            if not monitor or monitor.get('status') != 'active':
                break
            
            # Perform check based on monitor type
            check_result = perform_monitor_check(monitor)
            
            # Update monitor status
            with monitoring_lock:
                if monitor_id in active_monitors:
                    active_monitors[monitor_id]['last_check'] = datetime.now().isoformat()
                    active_monitors[monitor_id]['check_count'] += 1
                    
                    if check_result.get('alert'):
                        active_monitors[monitor_id]['alerts_triggered'] += 1
            
            # Sleep until next check
            interval = monitor['config'].get('interval', MONITORING_CONFIG['default_interval'])
            time.sleep(interval)
            
        except Exception as e:
            logging.error(f"Monitor {monitor_id} error: {e}")
            time.sleep(60)  # Wait before retrying

def perform_monitor_check(monitor: Dict) -> Dict:
    """Perform monitoring check based on monitor type"""
    monitor_type = monitor['type']
    config = monitor['config']
    
    try:
        if monitor_type == 'metric_threshold':
            return check_metric_threshold(config)
        elif monitor_type == 'service_health':
            return check_service_health(config)
        elif monitor_type == 'process_monitor':
            return check_process_monitor(config)
        elif monitor_type == 'log_monitor':
            return check_log_monitor(config)
        else:
            return {'status': 'error', 'message': 'Unknown monitor type'}
    
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

def check_metric_threshold(config: Dict) -> Dict:
    """Check if metrics exceed configured thresholds"""
    manager = get_server_manager()
    if not manager:
        return {'status': 'error', 'message': 'Server manager unavailable'}
    
    metrics = manager.metrics_collector.collect_metrics()
    metric_name = config.get('metric')
    threshold = config.get('threshold')
    operator = config.get('operator', '>')
    
    if metric_name not in metrics:
        return {'status': 'error', 'message': f'Metric {metric_name} not found'}
    
    current_value = metrics[metric_name]
    alert_triggered = False
    
    if operator == '>' and current_value > threshold:
        alert_triggered = True
    elif operator == '<' and current_value < threshold:
        alert_triggered = True
    elif operator == '==' and current_value == threshold:
        alert_triggered = True
    
    return {
        'status': 'success',
        'current_value': current_value,
        'threshold': threshold,
        'alert': alert_triggered,
        'message': f'{metric_name}: {current_value} (threshold: {operator} {threshold})'
    }

def check_service_health(config: Dict) -> Dict:
    """Check service health status"""
    service_name = config.get('service_name')
    expected_status = config.get('expected_status', 'active')
    
    try:
        result = subprocess.run(
            ['systemctl', 'is-active', service_name],
            capture_output=True, text=True, timeout=10
        )
        
        current_status = result.stdout.strip()
        is_healthy = current_status == expected_status
        
        return {
            'status': 'success',
            'service_status': current_status,
            'expected_status': expected_status,
            'alert': not is_healthy,
            'message': f'Service {service_name}: {current_status}'
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'alert': True,
            'message': f'Failed to check service {service_name}: {str(e)}'
        }

def check_process_monitor(config: Dict) -> Dict:
    """Monitor specific processes"""
    process_name = config.get('process_name')
    min_instances = config.get('min_instances', 1)
    max_instances = config.get('max_instances', None)
    
    try:
        matching_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if process_name in proc.info['name'] or any(process_name in arg for arg in proc.info['cmdline']):
                    matching_processes.append(proc.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        instance_count = len(matching_processes)
        alert_triggered = False
        
        if instance_count < min_instances:
            alert_triggered = True
            message = f'Too few instances of {process_name}: {instance_count} < {min_instances}'
        elif max_instances and instance_count > max_instances:
            alert_triggered = True
            message = f'Too many instances of {process_name}: {instance_count} > {max_instances}'
        else:
            message = f'Process {process_name}: {instance_count} instances (healthy)'
        
        return {
            'status': 'success',
            'instance_count': instance_count,
            'processes': matching_processes,
            'alert': alert_triggered,
            'message': message
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'alert': True,
            'message': f'Failed to monitor process {process_name}: {str(e)}'
        }

def check_log_monitor(config: Dict) -> Dict:
    """Monitor log files for specific patterns"""
    log_file = config.get('log_file')
    pattern = config.get('pattern')
    alert_on_match = config.get('alert_on_match', True)
    
    try:
        log_path = Path(log_file)
        if not log_path.exists():
            return {
                'status': 'error',
                'alert': True,
                'message': f'Log file not found: {log_file}'
            }
        
        # Read last few lines of log file
        tail_lines = config.get('tail_lines', 100)
        with open(log_path, 'r') as f:
            lines = f.readlines()
            recent_lines = lines[-tail_lines:] if len(lines) > tail_lines else lines
        
        matches = []
        for i, line in enumerate(recent_lines):
            if re.search(pattern, line):
                matches.append({
                    'line_number': len(lines) - len(recent_lines) + i + 1,
                    'content': line.strip(),
                    'timestamp': datetime.now().isoformat()
                })
        
        alert_triggered = (len(matches) > 0) == alert_on_match
        
        return {
            'status': 'success',
            'matches_found': len(matches),
            'matches': matches[-10:],  # Last 10 matches
            'alert': alert_triggered,
            'message': f'Log monitor {log_file}: {len(matches)} matches for pattern "{pattern}"'
        }
        
    except Exception as e:
        return {
            'status': 'error',
            'alert': True,
            'message': f'Failed to monitor log {log_file}: {str(e)}'
        }

# ============================================================================
# ALERTING ENDPOINTS
# ============================================================================

@monitoring_api.route('/alerts', methods=['GET', 'POST'])
def alerts():
    """Manage alert configurations"""
    if request.method == 'GET':
        return get_alerts()
    elif request.method == 'POST':
        return create_alert_rule()

def get_alerts():
    """Get recent alerts and alert rules"""
    manager = get_server_manager()
    if manager:
        recent_alerts = manager.alert_manager.get_recent_alerts(hours=24)
    else:
        recent_alerts = []
    
    with monitoring_lock:
        return jsonify({
            'recent_alerts': recent_alerts,
            'alert_rules': list(alert_rules.values()),
            'total_rules': len(alert_rules)
        })

def create_alert_rule():
    """Create new alert rule"""
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    
    required_fields = ['name', 'condition', 'action']
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return jsonify({'error': f'Missing required fields: {missing_fields}'}), 400
    
    rule_id = str(uuid.uuid4())
    alert_rule = {
        'id': rule_id,
        'name': data['name'],
        'description': data.get('description', ''),
        'condition': data['condition'],
        'action': data['action'],
        'severity': data.get('severity', 'warning'),
        'enabled': data.get('enabled', True),
        'cooldown_seconds': data.get('cooldown_seconds', MONITORING_CONFIG['alert_cooldown']),
        'created_at': datetime.now().isoformat(),
        'triggered_count': 0,
        'last_triggered': None
    }
    
    with monitoring_lock:
        alert_rules[rule_id] = alert_rule
    
    return jsonify({
        'success': True,
        'alert_rule': alert_rule
    }), 201

@monitoring_api.route('/alerts/<rule_id>', methods=['GET', 'PUT', 'DELETE'])
def alert_rule_detail(rule_id):
    """Manage specific alert rule"""
    with monitoring_lock:
        if rule_id not in alert_rules:
            return jsonify({'error': 'Alert rule not found'}), 404
    
    if request.method == 'GET':
        return jsonify(alert_rules[rule_id])
    
    elif request.method == 'PUT':
        if not request.is_json:
            return jsonify({'error': 'Request must be JSON'}), 400
        
        data = request.get_json()
        with monitoring_lock:
            alert_rules[rule_id].update(data)
            alert_rules[rule_id]['updated_at'] = datetime.now().isoformat()
        
        return jsonify(alert_rules[rule_id])
    
    elif request.method == 'DELETE':
        with monitoring_lock:
            rule = alert_rules.pop(rule_id, None)
        
        if rule:
            return jsonify({'success': True, 'message': 'Alert rule deleted'})
        else:
            return jsonify({'error': 'Alert rule not found'}), 404

# ============================================================================
# METRICS AND PERFORMANCE ENDPOINTS
# ============================================================================

@monitoring_api.route('/metrics/live')
def live_metrics():
    """Get live system metrics with anomaly detection"""
    manager = get_server_manager()
    if not manager:
        return jsonify({'error': 'Server manager not available'}), 503
    
    try:
        # Collect current metrics
        current_metrics = manager.metrics_collector.collect_metrics()
        current_metrics['timestamp'] = datetime.now().isoformat()
        
        # Add to history for baseline calculation
        metrics_history.append(current_metrics.copy())
        
        # Detect anomalies
        anomalies = detect_anomalies(current_metrics)
        
        # Calculate performance scores
        performance_score = calculate_performance_score(current_metrics)
        
        response = {
            'metrics': current_metrics,
            'anomalies': anomalies,
            'performance_score': performance_score,
            'baseline_available': len(performance_baselines) > 0,
            'history_length': len(metrics_history)
        }
        
        return jsonify(response)
        
    except Exception as e:
        logging.error(f"Live metrics error: {e}")
        return jsonify({'error': 'Failed to collect live metrics'}), 500

def calculate_performance_score(metrics: Dict) -> Dict:
    """Calculate overall performance score based on current metrics"""
    weights = {
        'cpu_percent': 0.3,
        'memory_percent': 0.3,
        'disk_percent': 0.2,
        'load_1min': 0.1,
        'temperature': 0.1
    }
    
    scores = {}
    total_weighted_score = 0
    total_weight = 0
    
    for metric, weight in weights.items():
        value = metrics.get(metric)
        if value is None:
            continue
        
        # Calculate individual score (0-100)
        if metric == 'cpu_percent' or metric == 'memory_percent':
            score = max(0, 100 - value)
        elif metric == 'disk_percent':
            score = max(0, 100 - value) if value < 95 else 0
        elif metric == 'load_1min':
            # Assume optimal load is 1.0, critical is 4.0
            score = max(0, min(100, 100 - ((value - 1.0) / 3.0) * 100)) if value > 1.0 else 100
        elif metric == 'temperature':
            # Assume optimal temp is 50°C, critical is 85°C
            if value and value > 50:
                score = max(0, min(100, 100 - ((value - 50) / 35) * 100))
            else:
                score = 100
        else:
            score = 100
        
        scores[metric] = score
        total_weighted_score += score * weight
        total_weight += weight
    
    overall_score = total_weighted_score / total_weight if total_weight > 0 else 0
    
    return {
        'overall': round(overall_score, 1),
        'individual_scores': scores,
        'status': 'excellent' if overall_score >= 90 else 'good' if overall_score >= 75 else 'warning' if overall_score >= 50 else 'critical'
    }

@monitoring_api.route('/metrics/baseline')
def get_baseline_metrics():
    """Get baseline performance metrics"""
    with monitoring_lock:
        return jsonify({
            'baselines': performance_baselines,
            'total_metrics': len(performance_baselines),
            'history_length': len(metrics_history),
            'learning_period_hours': MONITORING_CONFIG['baseline_learning_period'] / 3600
        })

@monitoring_api.route('/metrics/baseline/update', methods=['POST'])
def update_baseline_metrics():
    """Force update of baseline metrics"""
    try:
        calculate_baseline_metrics()
        
        with monitoring_lock:
            baseline_count = len(performance_baselines)
        
        return jsonify({
            'success': True,
            'baselines_calculated': baseline_count,
            'message': 'Baseline metrics updated successfully'
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to update baselines: {str(e)}'}), 500

# ============================================================================
# OBSERVABILITY ENDPOINTS
# ============================================================================

@monitoring_api.route('/observability/traces')
def get_traces():
    """Get system traces and execution paths"""
    # This would integrate with distributed tracing systems
    # For now, return process and service information
    
    try:
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'create_time']):
            try:
                process_info = proc.info
                process_info['uptime_seconds'] = time.time() - process_info['create_time']
                processes.append(process_info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Sort by CPU usage
        processes.sort(key=lambda x: x.get('cpu_percent', 0), reverse=True)
        
        return jsonify({
            'processes': processes[:20],  # Top 20 processes
            'total_processes': len(processes),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get traces: {str(e)}'}), 500

@monitoring_api.route('/observability/dependencies')
def get_dependencies():
    """Get system dependencies and service relationships"""
    try:
        # Get systemd service dependencies
        dependencies = {}
        
        services = ['docker', 'ssh', 'nginx', 'cloudflared', 'postgresql', 'redis']
        
        for service in services:
            try:
                # Get service dependencies
                result = subprocess.run(
                    ['systemctl', 'list-dependencies', service, '--plain'],
                    capture_output=True, text=True, timeout=10
                )
                
                if result.returncode == 0:
                    deps = []
                    for line in result.stdout.strip().split('\n')[1:]:  # Skip first line
                        if line.strip() and not line.startswith('●'):
                            dep = line.strip().replace('●', '').replace('├─', '').replace('└─', '').strip()
                            if dep:
                                deps.append(dep)
                    
                    dependencies[service] = deps[:10]  # Limit to 10 dependencies
                
            except Exception:
                dependencies[service] = []
        
        return jsonify({
            'service_dependencies': dependencies,
            'total_services': len(dependencies),
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get dependencies: {str(e)}'}), 500

# ============================================================================
# MONITORING DASHBOARD ENDPOINTS
# ============================================================================

@monitoring_api.route('/dashboard/summary')
def dashboard_summary():
    """Get monitoring dashboard summary"""
    try:
        with monitoring_lock:
            active_monitor_count = len(active_monitors)
            alert_rule_count = len(alert_rules)
        
        manager = get_server_manager()
        if manager:
            recent_alerts = manager.alert_manager.get_recent_alerts(hours=1, acknowledged=False)
            metrics = manager.metrics_collector.collect_metrics()
        else:
            recent_alerts = []
            metrics = {}
        
        # Calculate uptime
        uptime_seconds = time.time() - psutil.boot_time()
        
        summary = {
            'monitoring': {
                'active_monitors': active_monitor_count,
                'alert_rules': alert_rule_count,
                'recent_alerts': len(recent_alerts),
                'critical_alerts': len([a for a in recent_alerts if a.get('level') == 'critical'])
            },
            'system': {
                'uptime_hours': round(uptime_seconds / 3600, 1),
                'cpu_percent': metrics.get('cpu_percent', 0),
                'memory_percent': metrics.get('memory_percent', 0),
                'disk_percent': metrics.get('disk_percent', 0)
            },
            'performance': {
                'baselines_available': len(performance_baselines),
                'anomalies_detected': len(detect_anomalies(metrics)),
                'metrics_history': len(metrics_history)
            },
            'timestamp': datetime.now().isoformat()
        }
        
        return jsonify(summary)
        
    except Exception as e:
        return jsonify({'error': f'Failed to get dashboard summary: {str(e)}'}), 500

# ============================================================================
# CONFIGURATION AND SETTINGS
# ============================================================================

@monitoring_api.route('/config')
def get_monitoring_config():
    """Get monitoring configuration"""
    return jsonify({
        'config': MONITORING_CONFIG,
        'limits': {
            'max_monitors': MONITORING_CONFIG['max_monitors'],
            'max_history': metrics_history.maxlen
        },
        'current_usage': {
            'active_monitors': len(active_monitors),
            'alert_rules': len(alert_rules),
            'metrics_history': len(metrics_history)
        }
    })

@monitoring_api.route('/config', methods=['PUT'])
def update_monitoring_config():
    """Update monitoring configuration"""
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    
    # Update allowed configuration values
    allowed_updates = ['default_interval', 'alert_cooldown', 'anomaly_sensitivity']
    
    updated = {}
    for key, value in data.items():
        if key in allowed_updates:
            MONITORING_CONFIG[key] = value
            updated[key] = value
    
    if updated:
        return jsonify({
            'success': True,
            'updated': updated,
            'config': MONITORING_CONFIG
        })
    else:
        return jsonify({'error': 'No valid configuration updates provided'}), 400

# ============================================================================
# HEALTH CHECK
# ============================================================================

@monitoring_api.route('/health')
def monitoring_health():
    """Health check for monitoring system"""
    try:
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'components': {
                'monitors': {
                    'active': len(active_monitors),
                    'status': 'healthy' if len(active_monitors) >= 0 else 'warning'
                },
                'baselines': {
                    'calculated': len(performance_baselines),
                    'status': 'healthy' if len(performance_baselines) > 0 else 'learning'
                },
                'metrics_history': {
                    'length': len(metrics_history),
                    'status': 'healthy' if len(metrics_history) > 100 else 'building'
                }
            }
        }
        
        # Check if any component is unhealthy
        component_statuses = [comp['status'] for comp in health_status['components'].values()]
        if 'unhealthy' in component_statuses:
            health_status['status'] = 'unhealthy'
        elif 'warning' in component_statuses:
            health_status['status'] = 'warning'
        
        return jsonify(health_status)
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 503

# Start baseline calculation in background
def start_baseline_calculation():
    """Start background baseline calculation"""
    def calculate_periodically():
        while True:
            try:
                calculate_baseline_metrics()
                time.sleep(300)  # Calculate every 5 minutes
            except Exception as e:
                logging.error(f"Baseline calculation error: {e}")
                time.sleep(60)
    
    baseline_thread = threading.Thread(target=calculate_periodically, daemon=True)
    baseline_thread.start()

# Initialize monitoring system
start_baseline_calculation()

if __name__ == '__main__':
    print("Monitoring API module loaded successfully")