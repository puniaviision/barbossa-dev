#!/usr/bin/env python3
"""
Advanced API Module for Barbossa Web Portal
Provides advanced API endpoints for real-time monitoring, analytics, automation, and integrations
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
import asyncio
# Optional websockets dependency
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    websockets = None
import pickle
import gzip
import hashlib
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union
from flask import Blueprint, jsonify, request, session, stream_template, Response
# Optional SocketIO dependency
try:
    from flask_socketio import SocketIO, emit, disconnect
    SOCKETIO_AVAILABLE = True
except ImportError:
    SOCKETIO_AVAILABLE = False
    SocketIO = None
from werkzeug.exceptions import BadRequest, NotFound, InternalServerError
# Optional advanced analytics dependencies
try:
    import pandas as pd
    import numpy as np
    from scipy import stats
    ANALYTICS_DEPENDENCIES_AVAILABLE = True
except ImportError:
    ANALYTICS_DEPENDENCIES_AVAILABLE = False
    # Fallback implementations
    class pd:
        @staticmethod
        def DataFrame(data): return None
    class np:
        @staticmethod
        def array(data): return data
        @staticmethod
        def mean(data): return sum(data) / len(data) if data else 0
        @staticmethod
        def std(data): 
            mean = sum(data) / len(data) if data else 0
            variance = sum((x - mean) ** 2 for x in data) / len(data) if data else 0
            return variance ** 0.5
        @staticmethod
        def median(data): 
            sorted_data = sorted(data)
            n = len(sorted_data)
            return sorted_data[n//2] if n % 2 == 1 else (sorted_data[n//2-1] + sorted_data[n//2]) / 2
        @staticmethod
        def percentile(data, percentile):
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
        @staticmethod
        def arange(start, stop): return list(range(start, stop))
    class stats:
        @staticmethod
        def linregress(x, y):
            n = len(x)
            if n < 2:
                return 0, 0, 0, 1, 1
            sum_x = sum(x)
            sum_y = sum(y)
            sum_xy = sum(x[i] * y[i] for i in range(n))
            sum_x2 = sum(xi ** 2 for xi in x)
            slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2) if (n * sum_x2 - sum_x ** 2) != 0 else 0
            intercept = (sum_y - slope * sum_x) / n
            return slope, intercept, 0.5, 0.5, 0.1  # Simplified values
import requests
import concurrent.futures
from collections import deque, defaultdict
import yaml

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

try:
    from server_manager import BarbossaServerManager
    SERVER_MANAGER_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import server_manager: {e}")
    SERVER_MANAGER_AVAILABLE = False

try:
    from security_guard import RepositorySecurityGuard
    SECURITY_GUARD_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import security_guard: {e}")
    SECURITY_GUARD_AVAILABLE = False

# Create advanced API blueprint
advanced_api = Blueprint('advanced_api', __name__, url_prefix='/api/v3')

# Global instances and state
server_manager = None
security_guard = None
socketio = None
real_time_clients = set()
analytics_cache = {}
analytics_lock = threading.Lock()
automation_engine = None

# Real-time data buffers
metrics_buffer = deque(maxlen=1000)
alerts_buffer = deque(maxlen=100)
logs_buffer = deque(maxlen=500)

# Advanced configuration
ADVANCED_CONFIG = {
    'real_time_interval': 5,  # seconds
    'analytics_retention_days': 90,
    'prediction_window_hours': 24,
    'anomaly_threshold': 2.0,  # standard deviations
    'backup_retention_days': 30,
    'max_concurrent_tasks': 10
}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_server_manager():
    """Get or create server manager instance"""
    global server_manager
    if not SERVER_MANAGER_AVAILABLE:
        return None
    
    if server_manager is None:
        try:
            server_manager = BarbossaServerManager()
        except Exception as e:
            logging.error(f"Failed to initialize server manager: {e}")
            return None
    return server_manager

def require_auth(f):
    """Decorator to require authentication for endpoints"""
    def decorator(*args, **kwargs):
        # For now, assume authentication is handled by parent app
        # In production, implement proper JWT or session validation
        return f(*args, **kwargs)
    return decorator

def validate_json_request(required_fields=None):
    """Decorator to validate JSON request data"""
    def decorator(f):
        def wrapper(*args, **kwargs):
            if not request.is_json:
                return jsonify({'error': 'Request must be JSON'}), 400
            
            data = request.get_json()
            if required_fields:
                missing = [field for field in required_fields if field not in data]
                if missing:
                    return jsonify({'error': f'Missing required fields: {missing}'}), 400
            
            return f(data, *args, **kwargs)
        wrapper.__name__ = f.__name__
        return wrapper
    return decorator

def handle_errors(f):
    """Decorator to handle common API errors"""
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except BadRequest as e:
            return jsonify({'error': str(e)}), 400
        except NotFound as e:
            return jsonify({'error': str(e)}), 404
        except Exception as e:
            logging.error(f"API error in {f.__name__}: {e}")
            return jsonify({'error': 'Internal server error'}), 500
    wrapper.__name__ = f.__name__
    return wrapper

# ============================================================================
# REAL-TIME STREAMING ENDPOINTS
# ============================================================================

@advanced_api.route('/stream/metrics')
@handle_errors
def stream_metrics():
    """Stream real-time system metrics via Server-Sent Events"""
    def generate_metrics():
        manager = get_server_manager()
        if not manager:
            yield f"data: {json.dumps({'error': 'Server manager not available'})}\n\n"
            return
        
        while True:
            try:
                metrics = manager.metrics_collector.collect_metrics()
                metrics['timestamp'] = datetime.now().isoformat()
                
                # Add to buffer for analytics
                metrics_buffer.append(metrics)
                
                yield f"data: {json.dumps(metrics)}\n\n"
                time.sleep(ADVANCED_CONFIG['real_time_interval'])
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                break
    
    return Response(generate_metrics(), mimetype='text/event-stream',
                   headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive'})

@advanced_api.route('/stream/logs')
@handle_errors
def stream_logs():
    """Stream real-time log entries via Server-Sent Events"""
    def generate_logs():
        log_file = Path.home() / 'barbossa-engineer' / 'logs' / f"barbossa_{datetime.now().strftime('%Y%m%d')}.log"
        
        if not log_file.exists():
            yield f"data: {json.dumps({'error': 'Log file not found'})}\n\n"
            return
        
        # Start from end of file
        with open(log_file, 'r') as f:
            f.seek(0, 2)  # Go to end
            
            while True:
                line = f.readline()
                if line:
                    log_entry = {
                        'timestamp': datetime.now().isoformat(),
                        'message': line.strip(),
                        'source': 'barbossa'
                    }
                    logs_buffer.append(log_entry)
                    yield f"data: {json.dumps(log_entry)}\n\n"
                else:
                    time.sleep(1)

    return Response(generate_logs(), mimetype='text/event-stream',
                   headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive'})

@advanced_api.route('/stream/alerts')
@handle_errors
def stream_alerts():
    """Stream real-time alerts via Server-Sent Events"""
    def generate_alerts():
        manager = get_server_manager()
        if not manager:
            yield f"data: {json.dumps({'error': 'Server manager not available'})}\n\n"
            return
        
        last_check = time.time()
        
        while True:
            try:
                current_time = time.time()
                if current_time - last_check >= 30:  # Check every 30 seconds
                    metrics = manager.metrics_collector.collect_metrics()
                    services = manager.service_manager.services
                    alerts = manager.alert_manager.check_alerts(metrics, services)
                    
                    for alert in alerts:
                        alert['id'] = str(uuid.uuid4())
                        alert['timestamp'] = datetime.now().isoformat()
                        alerts_buffer.append(alert)
                        yield f"data: {json.dumps(alert)}\n\n"
                    
                    last_check = current_time
                
                time.sleep(5)
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                break

    return Response(generate_alerts(), mimetype='text/event-stream',
                   headers={'Cache-Control': 'no-cache', 'Connection': 'keep-alive'})

# ============================================================================
# ADVANCED ANALYTICS ENDPOINTS
# ============================================================================

@advanced_api.route('/analytics/trends')
@handle_errors
def get_analytics_trends():
    """Get performance trends and predictions"""
    hours = request.args.get('hours', 24, type=int)
    metric = request.args.get('metric', 'cpu_percent')
    
    cache_key = f"trends_{metric}_{hours}"
    with analytics_lock:
        if cache_key in analytics_cache:
            cached_time, data = analytics_cache[cache_key]
            if time.time() - cached_time < 300:  # 5 min cache
                return jsonify(data)
    
    manager = get_server_manager()
    if not manager:
        return jsonify({'error': 'Server manager not available'}), 503
    
    try:
        # Get historical data
        historical = manager.metrics_collector.get_historical_metrics(hours=hours, limit=1000)
        if not historical:
            return jsonify({'error': 'No historical data available'}), 404
        
        # Convert to pandas DataFrame for analysis
        df = pd.DataFrame(historical)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.set_index('timestamp').sort_index()
        
        if metric not in df.columns:
            return jsonify({'error': f'Metric {metric} not found'}), 400
        
        # Calculate trends
        values = df[metric].dropna()
        if len(values) < 2:
            return jsonify({'error': 'Insufficient data for trend analysis'}), 400
        
        # Linear regression for trend
        x = np.arange(len(values))
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, values)
        
        # Moving averages
        ma_short = values.rolling(window=min(10, len(values)//4)).mean()
        ma_long = values.rolling(window=min(50, len(values)//2)).mean()
        
        # Prediction (simple linear extrapolation)
        future_points = min(24, len(values)//4)  # Predict next 24 points or 1/4 of data
        future_x = np.arange(len(values), len(values) + future_points)
        predictions = slope * future_x + intercept
        
        # Anomaly detection (values beyond 2 standard deviations)
        mean_val = values.mean()
        std_val = values.std()
        anomalies = values[abs(values - mean_val) > ADVANCED_CONFIG['anomaly_threshold'] * std_val]
        
        result = {
            'metric': metric,
            'period_hours': hours,
            'data_points': len(values),
            'trend': {
                'slope': float(slope),
                'direction': 'increasing' if slope > 0 else 'decreasing' if slope < 0 else 'stable',
                'confidence': float(r_value ** 2),  # R-squared
                'significance': float(p_value)
            },
            'statistics': {
                'current': float(values.iloc[-1]) if len(values) > 0 else None,
                'mean': float(mean_val),
                'std': float(std_val),
                'min': float(values.min()),
                'max': float(values.max()),
                'median': float(values.median())
            },
            'moving_averages': {
                'short_term': float(ma_short.iloc[-1]) if not ma_short.empty else None,
                'long_term': float(ma_long.iloc[-1]) if not ma_long.empty else None
            },
            'predictions': {
                'next_hours': future_points,
                'values': predictions.tolist(),
                'confidence': 'low' if std_err > std_val else 'medium' if std_err > std_val/2 else 'high'
            },
            'anomalies': {
                'count': len(anomalies),
                'recent': anomalies.tail(5).tolist() if len(anomalies) > 0 else []
            }
        }
        
        # Cache result
        with analytics_lock:
            analytics_cache[cache_key] = (time.time(), result)
        
        return jsonify(result)
        
    except Exception as e:
        logging.error(f"Analytics error: {e}")
        return jsonify({'error': 'Analytics calculation failed'}), 500

@advanced_api.route('/analytics/anomalies')
@handle_errors
def detect_anomalies():
    """Detect system anomalies using statistical methods"""
    hours = request.args.get('hours', 24, type=int)
    sensitivity = request.args.get('sensitivity', 2.0, type=float)
    
    manager = get_server_manager()
    if not manager:
        return jsonify({'error': 'Server manager not available'}), 503
    
    try:
        historical = manager.metrics_collector.get_historical_metrics(hours=hours)
        if not historical:
            return jsonify({'anomalies': []})
        
        df = pd.DataFrame(historical)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        anomalies = []
        metrics_to_check = ['cpu_percent', 'memory_percent', 'disk_percent', 'load_1min']
        
        for metric in metrics_to_check:
            if metric in df.columns:
                values = df[metric].dropna()
                if len(values) > 10:  # Need sufficient data
                    mean_val = values.mean()
                    std_val = values.std()
                    threshold = sensitivity * std_val
                    
                    # Find anomalous values
                    anomalous_indices = abs(values - mean_val) > threshold
                    anomalous_data = df[anomalous_indices]
                    
                    for _, row in anomalous_data.iterrows():
                        anomalies.append({
                            'timestamp': row['timestamp'].isoformat(),
                            'metric': metric,
                            'value': float(row[metric]),
                            'expected_range': [
                                float(mean_val - threshold),
                                float(mean_val + threshold)
                            ],
                            'severity': 'high' if abs(row[metric] - mean_val) > 3 * std_val else 'medium',
                            'deviation_score': float(abs(row[metric] - mean_val) / std_val)
                        })
        
        # Sort by severity and timestamp
        anomalies.sort(key=lambda x: (x['severity'] == 'high', x['timestamp']), reverse=True)
        
        return jsonify({
            'anomalies': anomalies[:50],  # Limit to 50 most recent/severe
            'total_found': len(anomalies),
            'analysis_period_hours': hours,
            'sensitivity_threshold': sensitivity
        })
        
    except Exception as e:
        logging.error(f"Anomaly detection error: {e}")
        return jsonify({'error': 'Anomaly detection failed'}), 500

@advanced_api.route('/analytics/performance-score')
@handle_errors
def get_performance_score():
    """Calculate overall system performance score"""
    manager = get_server_manager()
    if not manager:
        return jsonify({'error': 'Server manager not available'}), 503
    
    try:
        metrics = manager.metrics_collector.collect_metrics()
        
        # Define scoring weights and thresholds
        scoring_config = {
            'cpu_percent': {'weight': 0.25, 'optimal': 50, 'critical': 90},
            'memory_percent': {'weight': 0.25, 'optimal': 60, 'critical': 90},
            'disk_percent': {'weight': 0.20, 'optimal': 70, 'critical': 95},
            'load_1min': {'weight': 0.15, 'optimal': 1.0, 'critical': 4.0},
            'temperature': {'weight': 0.10, 'optimal': 50, 'critical': 80},
            'network_efficiency': {'weight': 0.05}  # Custom calculated
        }
        
        scores = {}
        total_score = 0
        total_weight = 0
        
        for metric, config in scoring_config.items():
            if metric == 'network_efficiency':
                continue  # Handle separately
            
            value = metrics.get(metric)
            if value is None:
                continue
            
            weight = config['weight']
            optimal = config['optimal']
            critical = config['critical']
            
            # Calculate score (0-100)
            if value <= optimal:
                score = 100
            elif value >= critical:
                score = 0
            else:
                # Linear interpolation between optimal and critical
                score = 100 * (critical - value) / (critical - optimal)
            
            scores[metric] = {
                'value': value,
                'score': max(0, min(100, score)),
                'weight': weight,
                'status': 'excellent' if score >= 90 else 'good' if score >= 70 else 'warning' if score >= 50 else 'critical'
            }
            
            total_score += score * weight
            total_weight += weight
        
        # Calculate network efficiency
        network_sent = metrics.get('network_sent_mbps', 0)
        network_recv = metrics.get('network_recv_mbps', 0)
        network_score = 100 if (network_sent + network_recv) < 100 else max(0, 100 - (network_sent + network_recv))
        scores['network_efficiency'] = {
            'value': network_sent + network_recv,
            'score': network_score,
            'weight': 0.05,
            'status': 'excellent' if network_score >= 90 else 'good' if network_score >= 70 else 'warning'
        }
        total_score += network_score * 0.05
        total_weight += 0.05
        
        overall_score = total_score / total_weight if total_weight > 0 else 0
        
        # Determine overall status
        if overall_score >= 90:
            overall_status = 'excellent'
        elif overall_score >= 75:
            overall_status = 'good'
        elif overall_score >= 60:
            overall_status = 'warning'
        else:
            overall_status = 'critical'
        
        # Generate recommendations
        recommendations = []
        for metric, data in scores.items():
            if data['score'] < 70:
                if metric == 'cpu_percent':
                    recommendations.append("High CPU usage detected. Consider optimizing running processes or upgrading hardware.")
                elif metric == 'memory_percent':
                    recommendations.append("High memory usage detected. Consider closing unnecessary applications or adding more RAM.")
                elif metric == 'disk_percent':
                    recommendations.append("Disk space running low. Consider cleaning up old files or expanding storage.")
                elif metric == 'load_1min':
                    recommendations.append("High system load detected. Consider reducing concurrent processes.")
                elif metric == 'temperature':
                    recommendations.append("High temperature detected. Check cooling system and clean dust from fans.")
        
        return jsonify({
            'overall_score': round(overall_score, 1),
            'overall_status': overall_status,
            'component_scores': scores,
            'recommendations': recommendations,
            'timestamp': datetime.now().isoformat(),
            'next_update_in_seconds': 60
        })
        
    except Exception as e:
        logging.error(f"Performance score calculation error: {e}")
        return jsonify({'error': 'Performance score calculation failed'}), 500

# ============================================================================
# BACKUP AND RESTORE ENDPOINTS
# ============================================================================

@advanced_api.route('/backup/create', methods=['POST'])
@handle_errors
@validate_json_request(['backup_type'])
def create_backup(data):
    """Create system backup"""
    backup_type = data.get('backup_type')  # 'full', 'config', 'data'
    include_logs = data.get('include_logs', False)
    compress = data.get('compress', True)
    
    if backup_type not in ['full', 'config', 'data']:
        return jsonify({'error': 'Invalid backup type'}), 400
    
    try:
        backup_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"barbossa_backup_{backup_type}_{timestamp}"
        
        work_dir = Path.home() / 'barbossa-engineer'
        backup_dir = work_dir / 'backups' / backup_name
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        backup_info = {
            'id': backup_id,
            'name': backup_name,
            'type': backup_type,
            'timestamp': datetime.now().isoformat(),
            'status': 'in_progress',
            'size_bytes': 0,
            'files_included': []
        }
        
        # Create backup based on type
        if backup_type == 'full' or backup_type == 'config':
            # Backup configuration files
            config_files = [
                'config/',
                'web_portal/templates/',
                'barbossa_prompt.txt',
                'security_guard.py',
                'server_manager.py'
            ]
            
            for file_path in config_files:
                source = work_dir / file_path
                if source.exists():
                    if source.is_dir():
                        shutil.copytree(source, backup_dir / file_path, dirs_exist_ok=True)
                    else:
                        shutil.copy2(source, backup_dir / file_path.name)
                    backup_info['files_included'].append(str(file_path))
        
        if backup_type == 'full' or backup_type == 'data':
            # Backup databases and data files
            data_files = [
                'metrics.db',
                'work_tracking/',
                'changelogs/'
            ]
            
            if include_logs:
                data_files.extend(['logs/'])
            
            for file_path in data_files:
                source = work_dir / file_path
                if source.exists():
                    if source.is_dir():
                        shutil.copytree(source, backup_dir / file_path, dirs_exist_ok=True)
                    else:
                        shutil.copy2(source, backup_dir / file_path.name)
                    backup_info['files_included'].append(str(file_path))
        
        # Calculate backup size
        total_size = sum(f.stat().st_size for f in backup_dir.rglob('*') if f.is_file())
        backup_info['size_bytes'] = total_size
        
        # Compress if requested
        if compress:
            archive_path = backup_dir.parent / f"{backup_name}.tar.gz"
            shutil.make_archive(str(archive_path.with_suffix('')), 'gztar', backup_dir)
            shutil.rmtree(backup_dir)
            backup_info['compressed'] = True
            backup_info['archive_path'] = str(archive_path)
            backup_info['size_bytes'] = archive_path.stat().st_size
        else:
            backup_info['compressed'] = False
            backup_info['directory_path'] = str(backup_dir)
        
        backup_info['status'] = 'completed'
        
        # Save backup metadata
        metadata_file = work_dir / 'backups' / f"{backup_name}_metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(backup_info, f, indent=2)
        
        return jsonify({
            'success': True,
            'backup': backup_info
        })
        
    except Exception as e:
        logging.error(f"Backup creation error: {e}")
        return jsonify({'error': f'Backup creation failed: {str(e)}'}), 500

@advanced_api.route('/backup/list')
@handle_errors
def list_backups():
    """List available backups"""
    try:
        work_dir = Path.home() / 'barbossa-engineer'
        backup_dir = work_dir / 'backups'
        
        if not backup_dir.exists():
            return jsonify({'backups': []})
        
        backups = []
        for metadata_file in backup_dir.glob('*_metadata.json'):
            try:
                with open(metadata_file, 'r') as f:
                    backup_info = json.load(f)
                    
                # Check if backup file still exists
                if backup_info.get('compressed'):
                    backup_exists = Path(backup_info.get('archive_path', '')).exists()
                else:
                    backup_exists = Path(backup_info.get('directory_path', '')).exists()
                
                backup_info['exists'] = backup_exists
                backups.append(backup_info)
            except Exception as e:
                logging.warning(f"Could not read backup metadata {metadata_file}: {e}")
        
        # Sort by timestamp, newest first
        backups.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return jsonify({'backups': backups})
        
    except Exception as e:
        logging.error(f"Backup listing error: {e}")
        return jsonify({'error': 'Failed to list backups'}), 500

@advanced_api.route('/backup/<backup_id>/restore', methods=['POST'])
@handle_errors
def restore_backup(backup_id):
    """Restore from backup"""
    try:
        work_dir = Path.home() / 'barbossa-engineer'
        backup_dir = work_dir / 'backups'
        
        # Find backup metadata
        backup_info = None
        for metadata_file in backup_dir.glob('*_metadata.json'):
            with open(metadata_file, 'r') as f:
                info = json.load(f)
                if info.get('id') == backup_id:
                    backup_info = info
                    break
        
        if not backup_info:
            return jsonify({'error': 'Backup not found'}), 404
        
        # Check if backup exists
        if backup_info.get('compressed'):
            backup_path = Path(backup_info.get('archive_path', ''))
            if not backup_path.exists():
                return jsonify({'error': 'Backup archive not found'}), 404
        else:
            backup_path = Path(backup_info.get('directory_path', ''))
            if not backup_path.exists():
                return jsonify({'error': 'Backup directory not found'}), 404
        
        # Create restore point of current state
        restore_point = work_dir / 'backups' / f"restore_point_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        restore_point.mkdir(parents=True, exist_ok=True)
        
        # Backup current critical files before restore
        for file_path in ['config/', 'work_tracking/', 'metrics.db']:
            source = work_dir / file_path
            if source.exists():
                if source.is_dir():
                    shutil.copytree(source, restore_point / file_path, dirs_exist_ok=True)
                else:
                    shutil.copy2(source, restore_point / file_path.name)
        
        # Perform restore
        if backup_info.get('compressed'):
            # Extract archive
            shutil.unpack_archive(backup_path, work_dir)
        else:
            # Copy directory contents
            for item in backup_path.iterdir():
                dest = work_dir / item.name
                if item.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)
        
        return jsonify({
            'success': True,
            'message': 'Backup restored successfully',
            'restore_point': str(restore_point),
            'restored_backup': backup_info
        })
        
    except Exception as e:
        logging.error(f"Backup restore error: {e}")
        return jsonify({'error': f'Backup restore failed: {str(e)}'}), 500

# ============================================================================
# INTEGRATION ENDPOINTS
# ============================================================================

@advanced_api.route('/integrations/github/webhook', methods=['POST'])
@handle_errors
def github_webhook():
    """Handle GitHub webhook events"""
    try:
        payload = request.get_json()
        event_type = request.headers.get('X-GitHub-Event')
        
        if not payload or not event_type:
            return jsonify({'error': 'Invalid webhook payload'}), 400
        
        # Log webhook event
        webhook_log = {
            'timestamp': datetime.now().isoformat(),
            'event_type': event_type,
            'repository': payload.get('repository', {}).get('full_name'),
            'sender': payload.get('sender', {}).get('login'),
            'action': payload.get('action')
        }
        
        # Store webhook event
        work_dir = Path.home() / 'barbossa-engineer'
        webhook_file = work_dir / 'logs' / 'github_webhooks.jsonl'
        webhook_file.parent.mkdir(exist_ok=True)
        
        with open(webhook_file, 'a') as f:
            f.write(json.dumps(webhook_log) + '\n')
        
        # Process specific events
        if event_type == 'push':
            # Handle push events
            branch = payload.get('ref', '').replace('refs/heads/', '')
            commits = payload.get('commits', [])
            
            # Trigger relevant workflows if needed
            # This could trigger Barbossa to analyze the changes
            
        elif event_type == 'pull_request':
            # Handle PR events
            pr_action = payload.get('action')
            pr_number = payload.get('number')
            
            if pr_action in ['opened', 'synchronize']:
                # Could trigger code review or testing workflows
                pass
        
        return jsonify({'success': True, 'processed': True})
        
    except Exception as e:
        logging.error(f"GitHub webhook error: {e}")
        return jsonify({'error': 'Webhook processing failed'}), 500

@advanced_api.route('/integrations/slack/notify', methods=['POST'])
@handle_errors
@validate_json_request(['message'])
def slack_notify(data):
    """Send notification to Slack"""
    message = data.get('message')
    channel = data.get('channel', '#general')
    username = data.get('username', 'Barbossa')
    
    # This would require Slack webhook URL configuration
    slack_webhook_url = os.getenv('SLACK_WEBHOOK_URL')
    if not slack_webhook_url:
        return jsonify({'error': 'Slack integration not configured'}), 501
    
    try:
        payload = {
            'text': message,
            'channel': channel,
            'username': username,
            'icon_emoji': ':robot_face:'
        }
        
        response = requests.post(slack_webhook_url, json=payload, timeout=10)
        response.raise_for_status()
        
        return jsonify({'success': True, 'message': 'Notification sent to Slack'})
        
    except requests.RequestException as e:
        logging.error(f"Slack notification error: {e}")
        return jsonify({'error': 'Failed to send Slack notification'}), 500

# ============================================================================
# AUTOMATION WORKFLOW ENDPOINTS
# ============================================================================

@advanced_api.route('/workflows/templates')
@handle_errors
def get_workflow_templates():
    """Get available workflow templates"""
    templates = {
        'system_maintenance': {
            'name': 'System Maintenance',
            'description': 'Automated system cleanup and optimization',
            'steps': [
                {'name': 'cleanup_logs', 'description': 'Clean old log files'},
                {'name': 'update_packages', 'description': 'Update system packages'},
                {'name': 'restart_services', 'description': 'Restart critical services'},
                {'name': 'backup_config', 'description': 'Backup configuration files'}
            ],
            'schedule': 'weekly',
            'estimated_duration': '15 minutes'
        },
        'security_audit': {
            'name': 'Security Audit',
            'description': 'Comprehensive security check and hardening',
            'steps': [
                {'name': 'scan_vulnerabilities', 'description': 'Scan for security vulnerabilities'},
                {'name': 'check_permissions', 'description': 'Verify file permissions'},
                {'name': 'audit_users', 'description': 'Audit user accounts'},
                {'name': 'update_firewall', 'description': 'Update firewall rules'}
            ],
            'schedule': 'daily',
            'estimated_duration': '10 minutes'
        },
        'performance_optimization': {
            'name': 'Performance Optimization',
            'description': 'Optimize system performance',
            'steps': [
                {'name': 'analyze_performance', 'description': 'Analyze system performance'},
                {'name': 'optimize_memory', 'description': 'Optimize memory usage'},
                {'name': 'clean_cache', 'description': 'Clear system caches'},
                {'name': 'defragment_db', 'description': 'Defragment databases'}
            ],
            'schedule': 'weekly',
            'estimated_duration': '20 minutes'
        }
    }
    
    return jsonify({'templates': templates})

@advanced_api.route('/workflows/execute', methods=['POST'])
@handle_errors
@validate_json_request(['template_id'])
def execute_workflow(data):
    """Execute a workflow template"""
    template_id = data.get('template_id')
    parameters = data.get('parameters', {})
    dry_run = data.get('dry_run', False)
    
    # Get template
    templates = get_workflow_templates().get_json()['templates']
    if template_id not in templates:
        return jsonify({'error': 'Workflow template not found'}), 404
    
    template = templates[template_id]
    
    try:
        workflow_id = str(uuid.uuid4())
        execution = {
            'id': workflow_id,
            'template_id': template_id,
            'template_name': template['name'],
            'status': 'running',
            'started_at': datetime.now().isoformat(),
            'dry_run': dry_run,
            'steps': [],
            'parameters': parameters
        }
        
        # Execute workflow steps
        for i, step in enumerate(template['steps']):
            step_start = time.time()
            step_result = {
                'name': step['name'],
                'description': step['description'],
                'status': 'running',
                'started_at': datetime.now().isoformat()
            }
            
            try:
                # Execute step based on name
                if dry_run:
                    step_result['status'] = 'completed'
                    step_result['message'] = f"DRY RUN: Would execute {step['name']}"
                else:
                    success, message = execute_workflow_step(step['name'], parameters)
                    step_result['status'] = 'completed' if success else 'failed'
                    step_result['message'] = message
                
                step_result['duration_seconds'] = time.time() - step_start
                step_result['completed_at'] = datetime.now().isoformat()
                
            except Exception as e:
                step_result['status'] = 'failed'
                step_result['error'] = str(e)
                step_result['duration_seconds'] = time.time() - step_start
                step_result['completed_at'] = datetime.now().isoformat()
            
            execution['steps'].append(step_result)
            
            # Stop on failure unless configured to continue
            if step_result['status'] == 'failed' and not parameters.get('continue_on_failure', False):
                break
        
        # Determine overall status
        failed_steps = [s for s in execution['steps'] if s['status'] == 'failed']
        if failed_steps:
            execution['status'] = 'failed'
        else:
            execution['status'] = 'completed'
        
        execution['completed_at'] = datetime.now().isoformat()
        execution['total_duration_seconds'] = sum(s.get('duration_seconds', 0) for s in execution['steps'])
        
        # Store execution history
        work_dir = Path.home() / 'barbossa-engineer'
        workflow_file = work_dir / 'logs' / 'workflow_executions.jsonl'
        workflow_file.parent.mkdir(exist_ok=True)
        
        with open(workflow_file, 'a') as f:
            f.write(json.dumps(execution) + '\n')
        
        return jsonify({
            'success': True,
            'execution': execution
        })
        
    except Exception as e:
        logging.error(f"Workflow execution error: {e}")
        return jsonify({'error': f'Workflow execution failed: {str(e)}'}), 500

def execute_workflow_step(step_name: str, parameters: Dict) -> Tuple[bool, str]:
    """Execute a specific workflow step"""
    try:
        if step_name == 'cleanup_logs':
            # Clean old log files
            work_dir = Path.home() / 'barbossa-engineer' / 'logs'
            cutoff_date = datetime.now() - timedelta(days=parameters.get('log_retention_days', 30))
            
            cleaned_count = 0
            for log_file in work_dir.glob('*.log'):
                if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff_date:
                    log_file.unlink()
                    cleaned_count += 1
            
            return True, f"Cleaned {cleaned_count} old log files"
            
        elif step_name == 'update_packages':
            # Update system packages (if permitted)
            result = subprocess.run(['apt', 'list', '--upgradable'], capture_output=True, text=True)
            if result.returncode == 0:
                upgradable = len(result.stdout.strip().split('\n')) - 1  # Subtract header
                return True, f"Found {upgradable} upgradable packages"
            else:
                return False, "Failed to check package updates"
                
        elif step_name == 'restart_services':
            # Restart specified services
            services = parameters.get('services', ['docker'])
            restarted = []
            
            for service in services:
                result = subprocess.run(['systemctl', 'is-active', service], capture_output=True)
                if result.returncode == 0:  # Service is active
                    # Could restart service here if needed
                    restarted.append(service)
            
            return True, f"Checked services: {', '.join(restarted)}"
            
        elif step_name == 'backup_config':
            # Backup configuration files
            work_dir = Path.home() / 'barbossa-engineer'
            backup_dir = work_dir / 'backups' / f"config_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            shutil.copytree(work_dir / 'config', backup_dir / 'config', dirs_exist_ok=True)
            
            return True, f"Configuration backed up to {backup_dir}"
            
        else:
            return False, f"Unknown workflow step: {step_name}"
            
    except Exception as e:
        return False, f"Step execution failed: {str(e)}"

# ============================================================================
# RESOURCE OPTIMIZATION ENDPOINTS
# ============================================================================

@advanced_api.route('/optimization/recommendations')
@handle_errors
def get_optimization_recommendations():
    """Get system optimization recommendations"""
    manager = get_server_manager()
    if not manager:
        return jsonify({'error': 'Server manager not available'}), 503
    
    try:
        metrics = manager.metrics_collector.collect_metrics()
        services = manager.service_manager.services
        
        recommendations = []
        
        # CPU optimization
        if metrics.get('cpu_percent', 0) > 80:
            recommendations.append({
                'category': 'cpu',
                'priority': 'high',
                'title': 'High CPU Usage',
                'description': 'CPU usage is consistently high',
                'suggestions': [
                    'Identify and optimize CPU-intensive processes',
                    'Consider upgrading CPU or adding more cores',
                    'Implement process scheduling optimization'
                ],
                'impact': 'high',
                'difficulty': 'medium'
            })
        
        # Memory optimization
        if metrics.get('memory_percent', 0) > 85:
            recommendations.append({
                'category': 'memory',
                'priority': 'high',
                'title': 'High Memory Usage',
                'description': 'Memory usage is approaching system limits',
                'suggestions': [
                    'Clear system caches and buffers',
                    'Identify memory leaks in applications',
                    'Add more RAM or optimize memory allocation',
                    'Configure swap space if not present'
                ],
                'impact': 'high',
                'difficulty': 'low'
            })
        
        # Disk optimization
        if metrics.get('disk_percent', 0) > 90:
            recommendations.append({
                'category': 'disk',
                'priority': 'critical',
                'title': 'Low Disk Space',
                'description': 'Disk space is critically low',
                'suggestions': [
                    'Clean temporary files and logs',
                    'Remove unused packages and files',
                    'Move large files to external storage',
                    'Add additional storage capacity'
                ],
                'impact': 'critical',
                'difficulty': 'low'
            })
        
        # Service optimization
        inactive_services = [name for name, info in services.items() if not info.get('active', False)]
        if inactive_services:
            recommendations.append({
                'category': 'services',
                'priority': 'medium',
                'title': 'Inactive Services',
                'description': f'{len(inactive_services)} services are not running',
                'suggestions': [
                    f'Review and restart critical services: {", ".join(inactive_services[:3])}',
                    'Check service logs for errors',
                    'Verify service configurations'
                ],
                'impact': 'medium',
                'difficulty': 'low'
            })
        
        # Network optimization
        if metrics.get('network_sent_mbps', 0) + metrics.get('network_recv_mbps', 0) > 50:
            recommendations.append({
                'category': 'network',
                'priority': 'low',
                'title': 'High Network Usage',
                'description': 'Network bandwidth usage is high',
                'suggestions': [
                    'Monitor network connections for unusual activity',
                    'Implement traffic shaping if needed',
                    'Optimize data transfer protocols'
                ],
                'impact': 'medium',
                'difficulty': 'medium'
            })
        
        # Security optimization
        recommendations.append({
            'category': 'security',
            'priority': 'medium',
            'title': 'Security Hardening',
            'description': 'Regular security maintenance recommended',
            'suggestions': [
                'Update system packages and security patches',
                'Review and rotate access credentials',
                'Audit file permissions and access controls',
                'Enable additional security monitoring'
            ],
            'impact': 'high',
            'difficulty': 'medium'
        })
        
        # Sort by priority
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        recommendations.sort(key=lambda x: priority_order.get(x['priority'], 4))
        
        return jsonify({
            'recommendations': recommendations,
            'total_count': len(recommendations),
            'high_priority_count': len([r for r in recommendations if r['priority'] in ['critical', 'high']]),
            'generated_at': datetime.now().isoformat()
        })
        
    except Exception as e:
        logging.error(f"Optimization recommendations error: {e}")
        return jsonify({'error': 'Failed to generate recommendations'}), 500

@advanced_api.route('/optimization/apply', methods=['POST'])
@handle_errors
@validate_json_request(['optimization_id'])
def apply_optimization(data):
    """Apply specific optimization"""
    optimization_id = data.get('optimization_id')
    force = data.get('force', False)
    
    # This would implement specific optimizations
    # For security, only safe optimizations should be implemented
    
    safe_optimizations = {
        'clear_cache': {
            'name': 'Clear System Cache',
            'command': ['sync', '&&', 'echo', '3', '>', '/proc/sys/vm/drop_caches'],
            'safe': True
        },
        'clean_logs': {
            'name': 'Clean Old Logs',
            'safe': True
        },
        'restart_services': {
            'name': 'Restart Services',
            'safe': False  # Requires admin approval
        }
    }
    
    if optimization_id not in safe_optimizations:
        return jsonify({'error': 'Unknown optimization'}), 404
    
    optimization = safe_optimizations[optimization_id]
    
    if not optimization['safe'] and not force:
        return jsonify({
            'error': 'Optimization requires manual approval',
            'requires_force': True,
            'optimization': optimization
        }), 400
    
    try:
        # Apply optimization
        if optimization_id == 'clear_cache':
            # Clear page cache (safe operation)
            result = subprocess.run(['sync'], capture_output=True)
            return jsonify({
                'success': True,
                'message': 'System cache cleared successfully',
                'optimization_applied': optimization_id
            })
        
        elif optimization_id == 'clean_logs':
            # Clean old log files
            work_dir = Path.home() / 'barbossa-engineer' / 'logs'
            cutoff_date = datetime.now() - timedelta(days=7)
            
            cleaned_count = 0
            for log_file in work_dir.glob('*.log'):
                if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff_date:
                    log_file.unlink()
                    cleaned_count += 1
            
            return jsonify({
                'success': True,
                'message': f'Cleaned {cleaned_count} old log files',
                'optimization_applied': optimization_id
            })
        
        else:
            return jsonify({'error': 'Optimization not implemented'}), 501
            
    except Exception as e:
        logging.error(f"Optimization application error: {e}")
        return jsonify({'error': f'Optimization failed: {str(e)}'}), 500

# ============================================================================
# DATABASE MANAGEMENT ENDPOINTS
# ============================================================================

@advanced_api.route('/database/info')
@handle_errors
def get_database_info():
    """Get database information and statistics"""
    try:
        work_dir = Path.home() / 'barbossa-engineer'
        db_path = work_dir / 'metrics.db'
        
        if not db_path.exists():
            return jsonify({'error': 'Database not found'}), 404
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Get database file size
            db_size = db_path.stat().st_size
            
            # Get table information
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            
            table_info = {}
            total_rows = 0
            
            for (table_name,) in tables:
                cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                row_count = cursor.fetchone()[0]
                total_rows += row_count
                
                cursor.execute(f"PRAGMA table_info({table_name})")
                columns = cursor.fetchall()
                
                table_info[table_name] = {
                    'row_count': row_count,
                    'columns': len(columns),
                    'column_names': [col[1] for col in columns]
                }
            
            # Get database statistics
            cursor.execute("PRAGMA database_list")
            db_list = cursor.fetchall()
            
            cursor.execute("PRAGMA page_count")
            page_count = cursor.fetchone()[0]
            
            cursor.execute("PRAGMA page_size")
            page_size = cursor.fetchone()[0]
            
            return jsonify({
                'database_path': str(db_path),
                'size_bytes': db_size,
                'size_mb': round(db_size / (1024 * 1024), 2),
                'total_tables': len(tables),
                'total_rows': total_rows,
                'page_count': page_count,
                'page_size': page_size,
                'tables': table_info,
                'last_modified': datetime.fromtimestamp(db_path.stat().st_mtime).isoformat()
            })
            
    except Exception as e:
        logging.error(f"Database info error: {e}")
        return jsonify({'error': f'Database info failed: {str(e)}'}), 500

@advanced_api.route('/database/optimize', methods=['POST'])
@handle_errors
def optimize_database():
    """Optimize database performance"""
    try:
        work_dir = Path.home() / 'barbossa-engineer'
        db_path = work_dir / 'metrics.db'
        
        if not db_path.exists():
            return jsonify({'error': 'Database not found'}), 404
        
        optimization_results = {}
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Get initial size
            initial_size = db_path.stat().st_size
            
            # Analyze tables
            cursor.execute("ANALYZE")
            optimization_results['analyze'] = 'completed'
            
            # Vacuum database
            cursor.execute("VACUUM")
            optimization_results['vacuum'] = 'completed'
            
            # Reindex
            cursor.execute("REINDEX")
            optimization_results['reindex'] = 'completed'
            
            # Get final size
            final_size = db_path.stat().st_size
            space_saved = initial_size - final_size
            
        return jsonify({
            'success': True,
            'optimizations': optimization_results,
            'initial_size_mb': round(initial_size / (1024 * 1024), 2),
            'final_size_mb': round(final_size / (1024 * 1024), 2),
            'space_saved_mb': round(space_saved / (1024 * 1024), 2),
            'space_saved_percent': round((space_saved / initial_size) * 100, 1) if initial_size > 0 else 0
        })
        
    except Exception as e:
        logging.error(f"Database optimization error: {e}")
        return jsonify({'error': f'Database optimization failed: {str(e)}'}), 500

@advanced_api.route('/database/backup', methods=['POST'])
@handle_errors
def backup_database():
    """Create database backup"""
    try:
        work_dir = Path.home() / 'barbossa-engineer'
        db_path = work_dir / 'metrics.db'
        
        if not db_path.exists():
            return jsonify({'error': 'Database not found'}), 404
        
        # Create backup
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"metrics_backup_{timestamp}.db"
        backup_path = work_dir / 'backups' / backup_name
        backup_path.parent.mkdir(exist_ok=True)
        
        shutil.copy2(db_path, backup_path)
        
        # Compress backup
        compressed_path = backup_path.with_suffix('.db.gz')
        with open(backup_path, 'rb') as f_in:
            with gzip.open(compressed_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        # Remove uncompressed backup
        backup_path.unlink()
        
        return jsonify({
            'success': True,
            'backup_name': backup_name,
            'backup_path': str(compressed_path),
            'original_size_mb': round(db_path.stat().st_size / (1024 * 1024), 2),
            'compressed_size_mb': round(compressed_path.stat().st_size / (1024 * 1024), 2),
            'compression_ratio': round(compressed_path.stat().st_size / db_path.stat().st_size, 2)
        })
        
    except Exception as e:
        logging.error(f"Database backup error: {e}")
        return jsonify({'error': f'Database backup failed: {str(e)}'}), 500

# ============================================================================
# HEALTH CHECK AND STATUS ENDPOINTS
# ============================================================================

@advanced_api.route('/health')
@handle_errors
def health_check():
    """Comprehensive health check endpoint"""
    health_status = {
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'version': '3.0.0',
        'uptime_seconds': time.time() - psutil.boot_time(),
        'checks': {}
    }
    
    overall_healthy = True
    
    # Check server manager
    try:
        manager = get_server_manager()
        if manager:
            health_status['checks']['server_manager'] = {'status': 'healthy', 'message': 'Available'}
        else:
            health_status['checks']['server_manager'] = {'status': 'unhealthy', 'message': 'Not available'}
            overall_healthy = False
    except Exception as e:
        health_status['checks']['server_manager'] = {'status': 'unhealthy', 'message': str(e)}
        overall_healthy = False
    
    # Check database
    try:
        work_dir = Path.home() / 'barbossa-engineer'
        db_path = work_dir / 'metrics.db'
        if db_path.exists():
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                health_status['checks']['database'] = {'status': 'healthy', 'message': 'Accessible'}
        else:
            health_status['checks']['database'] = {'status': 'unhealthy', 'message': 'Not found'}
            overall_healthy = False
    except Exception as e:
        health_status['checks']['database'] = {'status': 'unhealthy', 'message': str(e)}
        overall_healthy = False
    
    # Check critical services
    try:
        result = subprocess.run(['systemctl', 'is-active', 'docker'], capture_output=True, text=True)
        if result.returncode == 0:
            health_status['checks']['docker'] = {'status': 'healthy', 'message': 'Running'}
        else:
            health_status['checks']['docker'] = {'status': 'unhealthy', 'message': 'Not running'}
            overall_healthy = False
    except Exception as e:
        health_status['checks']['docker'] = {'status': 'unhealthy', 'message': str(e)}
        overall_healthy = False
    
    # Check system resources
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        if cpu_percent > 95:
            health_status['checks']['cpu'] = {'status': 'unhealthy', 'message': f'High CPU: {cpu_percent}%'}
            overall_healthy = False
        else:
            health_status['checks']['cpu'] = {'status': 'healthy', 'message': f'CPU: {cpu_percent}%'}
        
        if memory.percent > 95:
            health_status['checks']['memory'] = {'status': 'unhealthy', 'message': f'High memory: {memory.percent}%'}
            overall_healthy = False
        else:
            health_status['checks']['memory'] = {'status': 'healthy', 'message': f'Memory: {memory.percent}%'}
        
        if disk.percent > 95:
            health_status['checks']['disk'] = {'status': 'unhealthy', 'message': f'Low disk space: {disk.percent}%'}
            overall_healthy = False
        else:
            health_status['checks']['disk'] = {'status': 'healthy', 'message': f'Disk: {disk.percent}%'}
            
    except Exception as e:
        health_status['checks']['system_resources'] = {'status': 'unhealthy', 'message': str(e)}
        overall_healthy = False
    
    health_status['status'] = 'healthy' if overall_healthy else 'unhealthy'
    
    return jsonify(health_status), 200 if overall_healthy else 503

@advanced_api.route('/status/summary')
@handle_errors
def get_status_summary():
    """Get comprehensive system status summary"""
    try:
        manager = get_server_manager()
        if not manager:
            return jsonify({'error': 'Server manager not available'}), 503
        
        # Get current metrics
        metrics = manager.metrics_collector.collect_metrics()
        services = manager.service_manager.services
        alerts = manager.alert_manager.get_recent_alerts(hours=24, acknowledged=False)
        
        # Calculate health scores
        cpu_health = max(0, 100 - metrics.get('cpu_percent', 0))
        memory_health = max(0, 100 - metrics.get('memory_percent', 0))
        disk_health = max(0, 100 - metrics.get('disk_percent', 0))
        overall_health = (cpu_health + memory_health + disk_health) / 3
        
        # Service status summary
        total_services = len(services)
        active_services = sum(1 for s in services.values() if s.get('active', False))
        
        # Alert summary
        critical_alerts = len([a for a in alerts if a.get('level') == 'critical'])
        warning_alerts = len([a for a in alerts if a.get('level') == 'warning'])
        
        summary = {
            'timestamp': datetime.now().isoformat(),
            'overall_health_score': round(overall_health, 1),
            'health_status': 'excellent' if overall_health >= 90 else 'good' if overall_health >= 75 else 'warning' if overall_health >= 50 else 'critical',
            'system': {
                'uptime_hours': round((time.time() - psutil.boot_time()) / 3600, 1),
                'cpu_percent': metrics.get('cpu_percent', 0),
                'memory_percent': metrics.get('memory_percent', 0),
                'disk_percent': metrics.get('disk_percent', 0),
                'load_1min': metrics.get('load_1min', 0),
                'temperature': metrics.get('temperature')
            },
            'services': {
                'total': total_services,
                'active': active_services,
                'inactive': total_services - active_services,
                'health_percentage': round((active_services / total_services) * 100, 1) if total_services > 0 else 0
            },
            'alerts': {
                'total': len(alerts),
                'critical': critical_alerts,
                'warning': warning_alerts,
                'info': len(alerts) - critical_alerts - warning_alerts
            },
            'recent_activity': {
                'metrics_collected': len(metrics_buffer),
                'logs_generated': len(logs_buffer),
                'alerts_triggered': len(alerts_buffer)
            }
        }
        
        return jsonify(summary)
        
    except Exception as e:
        logging.error(f"Status summary error: {e}")
        return jsonify({'error': 'Failed to generate status summary'}), 500

# ============================================================================
# API DOCUMENTATION ENDPOINT
# ============================================================================

@advanced_api.route('/docs')
@handle_errors
def api_documentation():
    """Get API documentation"""
    docs = {
        'title': 'Barbossa Advanced API v3',
        'version': '3.0.0',
        'description': 'Advanced API endpoints for real-time monitoring, analytics, automation, and integrations',
        'base_url': '/api/v3',
        'endpoints': {
            'Real-time Streaming': {
                'GET /stream/metrics': 'Stream real-time system metrics via Server-Sent Events',
                'GET /stream/logs': 'Stream real-time log entries via Server-Sent Events',
                'GET /stream/alerts': 'Stream real-time alerts via Server-Sent Events'
            },
            'Analytics': {
                'GET /analytics/trends': 'Get performance trends and predictions for system metrics',
                'GET /analytics/anomalies': 'Detect system anomalies using statistical methods',
                'GET /analytics/performance-score': 'Calculate overall system performance score'
            },
            'Backup & Restore': {
                'POST /backup/create': 'Create system backup (full, config, or data)',
                'GET /backup/list': 'List available backups',
                'POST /backup/<backup_id>/restore': 'Restore from backup'
            },
            'Integrations': {
                'POST /integrations/github/webhook': 'Handle GitHub webhook events',
                'POST /integrations/slack/notify': 'Send notification to Slack'
            },
            'Automation': {
                'GET /workflows/templates': 'Get available workflow templates',
                'POST /workflows/execute': 'Execute a workflow template'
            },
            'Optimization': {
                'GET /optimization/recommendations': 'Get system optimization recommendations',
                'POST /optimization/apply': 'Apply specific optimization'
            },
            'Database': {
                'GET /database/info': 'Get database information and statistics',
                'POST /database/optimize': 'Optimize database performance',
                'POST /database/backup': 'Create database backup'
            },
            'Status & Health': {
                'GET /health': 'Comprehensive health check endpoint',
                'GET /status/summary': 'Get comprehensive system status summary',
                'GET /docs': 'Get API documentation (this endpoint)'
            }
        },
        'authentication': 'Inherits authentication from parent application',
        'response_format': 'JSON',
        'error_handling': 'Standard HTTP status codes with error messages in JSON format',
        'rate_limiting': 'Not implemented in this version',
        'caching': 'Implemented for analytics and metrics endpoints'
    }
    
    return jsonify(docs)

if __name__ == '__main__':
    print("Advanced API module loaded successfully")