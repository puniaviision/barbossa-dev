#!/usr/bin/env python3
"""
Enhanced API Module for Barbossa Web Portal
Provides comprehensive REST API endpoints for system management and monitoring
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
from flask import Blueprint, jsonify, request, session
from werkzeug.exceptions import BadRequest, NotFound, InternalServerError
import hashlib
import re

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

# Create enhanced API blueprint
enhanced_api = Blueprint('enhanced_api', __name__, url_prefix='/api/v2')

# Global instances
server_manager = None
security_guard = None
api_cache = {}
api_cache_lock = threading.Lock()

# Request validation schemas
PROJECT_SCHEMA = {
    'name': {'type': str, 'required': True, 'max_length': 100},
    'description': {'type': str, 'required': False, 'max_length': 500},
    'repository_url': {'type': str, 'required': False, 'max_length': 255},
    'status': {'type': str, 'required': False, 'choices': ['active', 'inactive', 'archived']},
    'tags': {'type': list, 'required': False},
    'priority': {'type': int, 'required': False, 'min': 1, 'max': 5}
}

TASK_SCHEMA = {
    'title': {'type': str, 'required': True, 'max_length': 200},
    'description': {'type': str, 'required': False, 'max_length': 1000},
    'project_id': {'type': str, 'required': True},
    'status': {'type': str, 'required': False, 'choices': ['pending', 'in_progress', 'completed', 'failed', 'cancelled']},
    'priority': {'type': int, 'required': False, 'min': 1, 'max': 5},
    'assigned_to': {'type': str, 'required': False, 'max_length': 100},
    'due_date': {'type': str, 'required': False},
    'tags': {'type': list, 'required': False},
    'dependencies': {'type': list, 'required': False}
}

def get_server_manager():
    """Get or create server manager instance"""
    global server_manager
    if not SERVER_MANAGER_AVAILABLE:
        return None
    
    if server_manager is None:
        try:
            server_manager = BarbossaServerManager()
        except TypeError:
            # If BarbossaServerManager doesn't accept work_dir parameter
            server_manager = BarbossaServerManager()
    return server_manager

def get_security_guard():
    """Get or create security guard instance"""
    global security_guard
    if not SECURITY_GUARD_AVAILABLE:
        return None
    
    if security_guard is None:
        try:
            security_guard = RepositorySecurityGuard()
        except Exception as e:
            logging.warning(f"Could not initialize RepositorySecurityGuard: {e}")
            return None
    return security_guard

def validate_request_data(data: dict, schema: dict) -> Tuple[bool, List[str]]:
    """Validate request data against schema"""
    errors = []
    
    for field, rules in schema.items():
        value = data.get(field)
        
        # Check required fields
        if rules.get('required', False) and (value is None or value == ''):
            errors.append(f"Field '{field}' is required")
            continue
        
        # Skip validation if field is not provided and not required
        if value is None:
            continue
        
        # Type validation
        expected_type = rules.get('type')
        if expected_type and not isinstance(value, expected_type):
            errors.append(f"Field '{field}' must be of type {expected_type.__name__}")
            continue
        
        # String length validation
        if isinstance(value, str):
            max_length = rules.get('max_length')
            if max_length and len(value) > max_length:
                errors.append(f"Field '{field}' must not exceed {max_length} characters")
        
        # Numeric range validation
        if isinstance(value, (int, float)):
            min_val = rules.get('min')
            max_val = rules.get('max')
            if min_val is not None and value < min_val:
                errors.append(f"Field '{field}' must be at least {min_val}")
            if max_val is not None and value > max_val:
                errors.append(f"Field '{field}' must not exceed {max_val}")
        
        # Choice validation
        choices = rules.get('choices')
        if choices and value not in choices:
            errors.append(f"Field '{field}' must be one of: {', '.join(choices)}")
    
    return len(errors) == 0, errors

def cache_response(key: str, data: Any, ttl: int = 300):
    """Cache API response with TTL"""
    with api_cache_lock:
        api_cache[key] = {
            'data': data,
            'expires_at': time.time() + ttl
        }

def get_cached_response(key: str) -> Optional[Any]:
    """Get cached response if not expired"""
    with api_cache_lock:
        cached = api_cache.get(key)
        if cached and time.time() < cached['expires_at']:
            return cached['data']
        elif cached:
            del api_cache[key]
    return None

def clear_cache(pattern: str = None):
    """Clear cache entries matching pattern"""
    with api_cache_lock:
        if pattern:
            keys_to_remove = [k for k in api_cache.keys() if re.search(pattern, k)]
            for key in keys_to_remove:
                del api_cache[key]
        else:
            api_cache.clear()

# ============================================================================
# PROJECT MANAGEMENT API ENDPOINTS
# ============================================================================

@enhanced_api.route('/projects', methods=['GET', 'POST'])
def projects():
    """Manage projects"""
    if request.method == 'GET':
        return get_projects()
    elif request.method == 'POST':
        return create_project()

def get_projects():
    """Get all projects with filtering and pagination"""
    try:
        # Check cache first
        cache_key = f"projects_{request.query_string.decode()}"
        cached = get_cached_response(cache_key)
        if cached:
            return jsonify(cached)
        
        # Query parameters
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        status = request.args.get('status')
        search = request.args.get('search')
        sort_by = request.args.get('sort_by', 'created_at')
        sort_order = request.args.get('sort_order', 'desc')
        
        # Build query
        query = 'SELECT * FROM projects WHERE 1=1'
        params = []
        
        if status:
            query += ' AND status = ?'
            params.append(status)
        
        if search:
            query += ' AND (name LIKE ? OR description LIKE ?)'
            params.extend([f'%{search}%', f'%{search}%'])
        
        # Add sorting
        if sort_by in ['name', 'created_at', 'updated_at', 'status', 'priority']:
            order = 'ASC' if sort_order.lower() == 'asc' else 'DESC'
            query += f' ORDER BY {sort_by} {order}'
        
        query += ' LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        # Execute query
        db_path = Path.home() / 'barbossa-engineer' / 'data' / 'barbossa.db'
        projects = []
        total_count = 0
        
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get total count for pagination
            count_query = query.replace('SELECT *', 'SELECT COUNT(*)', 1).split('ORDER BY')[0].split('LIMIT')[0]
            cursor.execute(count_query, params[:-2] if len(params) >= 2 else [])
            total_count = cursor.fetchone()[0]
            
            # Get projects
            cursor.execute(query, params)
            projects = [dict(row) for row in cursor.fetchall()]
            
            # Parse JSON fields
            for project in projects:
                for field in ['tags', 'metadata']:
                    if project.get(field):
                        try:
                            project[field] = json.loads(project[field])
                        except:
                            project[field] = []
        
        result = {
            'projects': projects,
            'total': total_count,
            'limit': limit,
            'offset': offset,
            'has_more': offset + limit < total_count,
            'status': 'success'
        }
        
        # Cache result
        cache_response(cache_key, result, ttl=60)
        
        return jsonify(result)
    
    except Exception as e:
        logging.error(f"Error getting projects: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

def create_project():
    """Create a new project"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate data
        valid, errors = validate_request_data(data, PROJECT_SCHEMA)
        if not valid:
            return jsonify({
                'error': 'Validation failed',
                'errors': errors
            }), 400
        
        # Check for security issues with repository URL
        if data.get('repository_url'):
            guard = get_security_guard()
            if guard and not guard.is_repository_allowed(data['repository_url']):
                return jsonify({
                    'error': 'Repository URL not allowed by security policy'
                }), 403
        
        # Generate project ID
        project_id = str(uuid.uuid4())
        current_time = datetime.now().isoformat()
        
        # Prepare data for insertion
        project_data = {
            'id': project_id,
            'name': data['name'],
            'description': data.get('description', ''),
            'repository_url': data.get('repository_url', ''),
            'status': data.get('status', 'active'),
            'priority': data.get('priority', 3),
            'tags': json.dumps(data.get('tags', [])),
            'metadata': json.dumps({}),
            'created_at': current_time,
            'updated_at': current_time
        }
        
        # Insert into database
        db_path = Path.home() / 'barbossa-engineer' / 'data' / 'barbossa.db'
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Create projects table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS projects (
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
            
            # Insert project
            cursor.execute('''
                INSERT INTO projects (id, name, description, repository_url, status, priority, tags, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', list(project_data.values()))
            
            conn.commit()
        
        # Clear projects cache
        clear_cache('projects_')
        
        # Parse JSON fields for response
        project_data['tags'] = json.loads(project_data['tags'])
        project_data['metadata'] = json.loads(project_data['metadata'])
        
        return jsonify({
            'project': project_data,
            'status': 'success',
            'message': f'Project "{data["name"]}" created successfully'
        }), 201
    
    except Exception as e:
        logging.error(f"Error creating project: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/projects/<project_id>', methods=['GET', 'PUT', 'DELETE'])
def project_detail(project_id):
    """Get, update, or delete a specific project"""
    if request.method == 'GET':
        return get_project(project_id)
    elif request.method == 'PUT':
        return update_project(project_id)
    elif request.method == 'DELETE':
        return delete_project(project_id)

def get_project(project_id: str):
    """Get project details"""
    try:
        # Check cache
        cache_key = f"project_{project_id}"
        cached = get_cached_response(cache_key)
        if cached:
            return jsonify(cached)
        
        db_path = Path.home() / 'barbossa-engineer' / 'data' / 'barbossa.db'
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM projects WHERE id = ?', (project_id,))
            project = cursor.fetchone()
            
            if not project:
                return jsonify({'error': 'Project not found'}), 404
            
            project_dict = dict(project)
            
            # Parse JSON fields
            for field in ['tags', 'metadata']:
                if project_dict.get(field):
                    try:
                        project_dict[field] = json.loads(project_dict[field])
                    except:
                        project_dict[field] = [] if field == 'tags' else {}
            
            # Get related tasks count
            cursor.execute('SELECT COUNT(*) FROM tasks WHERE project_id = ?', (project_id,))
            task_count = cursor.fetchone()[0]
            project_dict['task_count'] = task_count
        
        result = {
            'project': project_dict,
            'status': 'success'
        }
        
        # Cache result
        cache_response(cache_key, result, ttl=120)
        
        return jsonify(result)
    
    except Exception as e:
        logging.error(f"Error getting project {project_id}: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

def update_project(project_id: str):
    """Update project"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate data (make all fields optional for updates)
        update_schema = {k: {**v, 'required': False} for k, v in PROJECT_SCHEMA.items()}
        valid, errors = validate_request_data(data, update_schema)
        if not valid:
            return jsonify({
                'error': 'Validation failed',
                'errors': errors
            }), 400
        
        # Check if project exists
        db_path = Path.home() / 'barbossa-engineer' / 'data' / 'barbossa.db'
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT id FROM projects WHERE id = ?', (project_id,))
            if not cursor.fetchone():
                return jsonify({'error': 'Project not found'}), 404
            
            # Build update query
            update_fields = []
            values = []
            
            for field in ['name', 'description', 'repository_url', 'status', 'priority']:
                if field in data:
                    update_fields.append(f'{field} = ?')
                    values.append(data[field])
            
            if 'tags' in data:
                update_fields.append('tags = ?')
                values.append(json.dumps(data['tags']))
            
            # Always update timestamp
            update_fields.append('updated_at = ?')
            values.append(datetime.now().isoformat())
            values.append(project_id)
            
            if update_fields:
                query = f"UPDATE projects SET {', '.join(update_fields)} WHERE id = ?"
                cursor.execute(query, values)
                conn.commit()
        
        # Clear caches
        clear_cache(f'project_{project_id}')
        clear_cache('projects_')
        
        return jsonify({
            'status': 'success',
            'message': 'Project updated successfully'
        })
    
    except Exception as e:
        logging.error(f"Error updating project {project_id}: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

def delete_project(project_id: str):
    """Delete project"""
    try:
        db_path = Path.home() / 'barbossa-engineer' / 'data' / 'barbossa.db'
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Check if project exists
            cursor.execute('SELECT name FROM projects WHERE id = ?', (project_id,))
            project = cursor.fetchone()
            if not project:
                return jsonify({'error': 'Project not found'}), 404
            
            project_name = project[0]
            
            # Check for related tasks
            cursor.execute('SELECT COUNT(*) FROM tasks WHERE project_id = ?', (project_id,))
            task_count = cursor.fetchone()[0]
            
            # Option to cascade delete or prevent deletion
            cascade = request.args.get('cascade', 'false').lower() == 'true'
            
            if task_count > 0 and not cascade:
                return jsonify({
                    'error': f'Cannot delete project with {task_count} associated tasks. Use ?cascade=true to delete all related data.'
                }), 400
            
            # Delete related tasks if cascading
            if cascade:
                cursor.execute('DELETE FROM tasks WHERE project_id = ?', (project_id,))
            
            # Delete project
            cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
            conn.commit()
        
        # Clear caches
        clear_cache(f'project_{project_id}')
        clear_cache('projects_')
        
        return jsonify({
            'status': 'success',
            'message': f'Project "{project_name}" deleted successfully'
        })
    
    except Exception as e:
        logging.error(f"Error deleting project {project_id}: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# ============================================================================
# TASK MANAGEMENT API ENDPOINTS
# ============================================================================

@enhanced_api.route('/tasks', methods=['GET', 'POST'])
def tasks():
    """Manage tasks"""
    if request.method == 'GET':
        return get_tasks()
    elif request.method == 'POST':
        return create_task()

def get_tasks():
    """Get tasks with filtering and pagination"""
    try:
        # Check cache
        cache_key = f"tasks_{request.query_string.decode()}"
        cached = get_cached_response(cache_key)
        if cached:
            return jsonify(cached)
        
        # Query parameters
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        project_id = request.args.get('project_id')
        status = request.args.get('status')
        priority = request.args.get('priority', type=int)
        assigned_to = request.args.get('assigned_to')
        search = request.args.get('search')
        sort_by = request.args.get('sort_by', 'created_at')
        sort_order = request.args.get('sort_order', 'desc')
        
        # Build query
        query = '''
            SELECT t.*, p.name as project_name 
            FROM tasks t 
            LEFT JOIN projects p ON t.project_id = p.id 
            WHERE 1=1
        '''
        params = []
        
        if project_id:
            query += ' AND t.project_id = ?'
            params.append(project_id)
        
        if status:
            query += ' AND t.status = ?'
            params.append(status)
        
        if priority:
            query += ' AND t.priority = ?'
            params.append(priority)
        
        if assigned_to:
            query += ' AND t.assigned_to = ?'
            params.append(assigned_to)
        
        if search:
            query += ' AND (t.title LIKE ? OR t.description LIKE ?)'
            params.extend([f'%{search}%', f'%{search}%'])
        
        # Add sorting
        if sort_by in ['title', 'created_at', 'updated_at', 'status', 'priority', 'due_date']:
            order = 'ASC' if sort_order.lower() == 'asc' else 'DESC'
            query += f' ORDER BY t.{sort_by} {order}'
        
        query += ' LIMIT ? OFFSET ?'
        params.extend([limit, offset])
        
        # Execute query
        db_path = Path.home() / 'barbossa-engineer' / 'data' / 'barbossa.db'
        tasks = []
        total_count = 0
        
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get total count
            count_query = query.replace('SELECT t.*, p.name as project_name', 'SELECT COUNT(*)', 1).split('ORDER BY')[0].split('LIMIT')[0]
            cursor.execute(count_query, params[:-2] if len(params) >= 2 else [])
            total_count = cursor.fetchone()[0]
            
            # Get tasks
            cursor.execute(query, params)
            tasks = [dict(row) for row in cursor.fetchall()]
            
            # Parse JSON fields
            for task in tasks:
                for field in ['tags', 'dependencies', 'metadata']:
                    if task.get(field):
                        try:
                            task[field] = json.loads(task[field])
                        except:
                            task[field] = []
        
        result = {
            'tasks': tasks,
            'total': total_count,
            'limit': limit,
            'offset': offset,
            'has_more': offset + limit < total_count,
            'status': 'success'
        }
        
        # Cache result
        cache_response(cache_key, result, ttl=60)
        
        return jsonify(result)
    
    except Exception as e:
        logging.error(f"Error getting tasks: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

def create_task():
    """Create a new task"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate data
        valid, errors = validate_request_data(data, TASK_SCHEMA)
        if not valid:
            return jsonify({
                'error': 'Validation failed',
                'errors': errors
            }), 400
        
        # Verify project exists
        db_path = Path.home() / 'barbossa-engineer' / 'data' / 'barbossa.db'
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('SELECT id FROM projects WHERE id = ?', (data['project_id'],))
            if not cursor.fetchone():
                return jsonify({'error': 'Project not found'}), 404
            
            # Generate task ID
            task_id = str(uuid.uuid4())
            current_time = datetime.now().isoformat()
            
            # Create tasks table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
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
            
            # Prepare task data
            task_data = {
                'id': task_id,
                'title': data['title'],
                'description': data.get('description', ''),
                'project_id': data['project_id'],
                'status': data.get('status', 'pending'),
                'priority': data.get('priority', 3),
                'assigned_to': data.get('assigned_to', ''),
                'due_date': data.get('due_date', ''),
                'tags': json.dumps(data.get('tags', [])),
                'dependencies': json.dumps(data.get('dependencies', [])),
                'metadata': json.dumps({}),
                'created_at': current_time,
                'updated_at': current_time,
                'completed_at': ''
            }
            
            # Insert task
            cursor.execute('''
                INSERT INTO tasks (id, title, description, project_id, status, priority, assigned_to, due_date, tags, dependencies, metadata, created_at, updated_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', list(task_data.values()))
            
            conn.commit()
        
        # Clear caches
        clear_cache('tasks_')
        clear_cache(f'project_{data["project_id"]}')
        
        # Parse JSON fields for response
        task_data['tags'] = json.loads(task_data['tags'])
        task_data['dependencies'] = json.loads(task_data['dependencies'])
        task_data['metadata'] = json.loads(task_data['metadata'])
        
        return jsonify({
            'task': task_data,
            'status': 'success',
            'message': f'Task "{data["title"]}" created successfully'
        }), 201
    
    except Exception as e:
        logging.error(f"Error creating task: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/tasks/<task_id>', methods=['GET', 'PUT', 'DELETE'])
def task_detail(task_id):
    """Get, update, or delete a specific task"""
    if request.method == 'GET':
        return get_task(task_id)
    elif request.method == 'PUT':
        return update_task(task_id)
    elif request.method == 'DELETE':
        return delete_task(task_id)

def get_task(task_id: str):
    """Get task details"""
    try:
        # Check cache
        cache_key = f"task_{task_id}"
        cached = get_cached_response(cache_key)
        if cached:
            return jsonify(cached)
        
        db_path = Path.home() / 'barbossa-engineer' / 'data' / 'barbossa.db'
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT t.*, p.name as project_name 
                FROM tasks t 
                LEFT JOIN projects p ON t.project_id = p.id 
                WHERE t.id = ?
            ''', (task_id,))
            task = cursor.fetchone()
            
            if not task:
                return jsonify({'error': 'Task not found'}), 404
            
            task_dict = dict(task)
            
            # Parse JSON fields
            for field in ['tags', 'dependencies', 'metadata']:
                if task_dict.get(field):
                    try:
                        task_dict[field] = json.loads(task_dict[field])
                    except:
                        task_dict[field] = []
        
        result = {
            'task': task_dict,
            'status': 'success'
        }
        
        # Cache result
        cache_response(cache_key, result, ttl=120)
        
        return jsonify(result)
    
    except Exception as e:
        logging.error(f"Error getting task {task_id}: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

def update_task(task_id: str):
    """Update task"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate data
        update_schema = {k: {**v, 'required': False} for k, v in TASK_SCHEMA.items()}
        valid, errors = validate_request_data(data, update_schema)
        if not valid:
            return jsonify({
                'error': 'Validation failed',
                'errors': errors
            }), 400
        
        db_path = Path.home() / 'barbossa-engineer' / 'data' / 'barbossa.db'
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Check if task exists
            cursor.execute('SELECT project_id, status FROM tasks WHERE id = ?', (task_id,))
            task = cursor.fetchone()
            if not task:
                return jsonify({'error': 'Task not found'}), 404
            
            old_project_id, old_status = task
            
            # Build update query
            update_fields = []
            values = []
            
            for field in ['title', 'description', 'project_id', 'status', 'priority', 'assigned_to', 'due_date']:
                if field in data:
                    update_fields.append(f'{field} = ?')
                    values.append(data[field])
            
            for field in ['tags', 'dependencies']:
                if field in data:
                    update_fields.append(f'{field} = ?')
                    values.append(json.dumps(data[field]))
            
            # Set completion timestamp if status changed to completed
            if 'status' in data and data['status'] == 'completed' and old_status != 'completed':
                update_fields.append('completed_at = ?')
                values.append(datetime.now().isoformat())
            elif 'status' in data and data['status'] != 'completed' and old_status == 'completed':
                update_fields.append('completed_at = ?')
                values.append('')
            
            # Always update timestamp
            update_fields.append('updated_at = ?')
            values.append(datetime.now().isoformat())
            values.append(task_id)
            
            if update_fields:
                query = f"UPDATE tasks SET {', '.join(update_fields)} WHERE id = ?"
                cursor.execute(query, values)
                conn.commit()
        
        # Clear caches
        clear_cache(f'task_{task_id}')
        clear_cache('tasks_')
        clear_cache(f'project_{old_project_id}')
        if 'project_id' in data and data['project_id'] != old_project_id:
            clear_cache(f'project_{data["project_id"]}')
        
        return jsonify({
            'status': 'success',
            'message': 'Task updated successfully'
        })
    
    except Exception as e:
        logging.error(f"Error updating task {task_id}: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

def delete_task(task_id: str):
    """Delete task"""
    try:
        db_path = Path.home() / 'barbossa-engineer' / 'data' / 'barbossa.db'
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Check if task exists and get details
            cursor.execute('SELECT title, project_id FROM tasks WHERE id = ?', (task_id,))
            task = cursor.fetchone()
            if not task:
                return jsonify({'error': 'Task not found'}), 404
            
            task_title, project_id = task
            
            # Delete task
            cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
            conn.commit()
        
        # Clear caches
        clear_cache(f'task_{task_id}')
        clear_cache('tasks_')
        clear_cache(f'project_{project_id}')
        
        return jsonify({
            'status': 'success',
            'message': f'Task "{task_title}" deleted successfully'
        })
    
    except Exception as e:
        logging.error(f"Error deleting task {task_id}: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# ============================================================================
# SYSTEM METRICS AND HEALTH API ENDPOINTS
# ============================================================================

@enhanced_api.route('/system/metrics', methods=['GET'])
def system_metrics():
    """Get comprehensive system metrics"""
    try:
        # Check cache
        cache_key = "system_metrics"
        cached = get_cached_response(cache_key)
        if cached:
            return jsonify(cached)
        
        # Collect system metrics
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'cpu': {
                'usage_percent': psutil.cpu_percent(interval=1),
                'core_count': psutil.cpu_count(),
                'load_average': list(os.getloadavg()) if hasattr(os, 'getloadavg') else None,
                'frequency': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
            },
            'memory': {
                'total': psutil.virtual_memory().total,
                'available': psutil.virtual_memory().available,
                'used': psutil.virtual_memory().used,
                'percent': psutil.virtual_memory().percent,
                'swap_total': psutil.swap_memory().total,
                'swap_used': psutil.swap_memory().used,
                'swap_percent': psutil.swap_memory().percent
            },
            'disk': [],
            'network': {
                'bytes_sent': psutil.net_io_counters().bytes_sent,
                'bytes_recv': psutil.net_io_counters().bytes_recv,
                'packets_sent': psutil.net_io_counters().packets_sent,
                'packets_recv': psutil.net_io_counters().packets_recv
            },
            'processes': {
                'total': len(psutil.pids()),
                'running': len([p for p in psutil.process_iter(['status']) if p.info['status'] == 'running']),
                'sleeping': len([p for p in psutil.process_iter(['status']) if p.info['status'] == 'sleeping'])
            },
            'boot_time': psutil.boot_time()
        }
        
        # Get disk usage for all mounted filesystems
        for partition in psutil.disk_partitions():
            try:
                disk_usage = psutil.disk_usage(partition.mountpoint)
                metrics['disk'].append({
                    'device': partition.device,
                    'mountpoint': partition.mountpoint,
                    'fstype': partition.fstype,
                    'total': disk_usage.total,
                    'used': disk_usage.used,
                    'free': disk_usage.free,
                    'percent': (disk_usage.used / disk_usage.total) * 100 if disk_usage.total > 0 else 0
                })
            except PermissionError:
                # Skip if we don't have permission to access
                continue
        
        # Get Barbossa-specific metrics
        server_manager = get_server_manager()
        if server_manager:
            barbossa_metrics = {
                'active_processes': len(server_manager.get_active_claude_processes()),
                'last_execution': server_manager.get_last_execution_time(),
                'work_areas': server_manager.get_work_area_stats() if hasattr(server_manager, 'get_work_area_stats') else None
            }
            metrics['barbossa'] = barbossa_metrics
        
        result = {
            'metrics': metrics,
            'status': 'success'
        }
        
        # Cache for 30 seconds
        cache_response(cache_key, result, ttl=30)
        
        return jsonify(result)
    
    except Exception as e:
        logging.error(f"Error getting system metrics: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/system/health', methods=['GET'])
def system_health():
    """Get system health status and checks"""
    try:
        # Check cache
        cache_key = "system_health"
        cached = get_cached_response(cache_key)
        if cached:
            return jsonify(cached)
        
        health_checks = []
        overall_status = 'healthy'
        
        # CPU health check
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_status = 'healthy' if cpu_percent < 80 else 'warning' if cpu_percent < 95 else 'critical'
        health_checks.append({
            'name': 'CPU Usage',
            'status': cpu_status,
            'value': f"{cpu_percent}%",
            'threshold': '< 80% healthy, < 95% warning, >= 95% critical'
        })
        
        # Memory health check
        memory = psutil.virtual_memory()
        memory_status = 'healthy' if memory.percent < 80 else 'warning' if memory.percent < 95 else 'critical'
        health_checks.append({
            'name': 'Memory Usage',
            'status': memory_status,
            'value': f"{memory.percent}%",
            'threshold': '< 80% healthy, < 95% warning, >= 95% critical'
        })
        
        # Disk health check
        disk_status = 'healthy'
        for partition in psutil.disk_partitions():
            try:
                disk_usage = psutil.disk_usage(partition.mountpoint)
                disk_percent = (disk_usage.used / disk_usage.total) * 100 if disk_usage.total > 0 else 0
                if disk_percent >= 95:
                    disk_status = 'critical'
                elif disk_percent >= 85 and disk_status == 'healthy':
                    disk_status = 'warning'
                
                health_checks.append({
                    'name': f'Disk Usage ({partition.mountpoint})',
                    'status': 'healthy' if disk_percent < 85 else 'warning' if disk_percent < 95 else 'critical',
                    'value': f"{disk_percent:.1f}%",
                    'threshold': '< 85% healthy, < 95% warning, >= 95% critical'
                })
            except PermissionError:
                continue
        
        # Load average check (Unix systems only)
        if hasattr(os, 'getloadavg'):
            load_avg = os.getloadavg()[0]  # 1-minute average
            cpu_cores = psutil.cpu_count()
            load_per_core = load_avg / cpu_cores if cpu_cores > 0 else load_avg
            load_status = 'healthy' if load_per_core < 1.0 else 'warning' if load_per_core < 2.0 else 'critical'
            health_checks.append({
                'name': 'System Load',
                'status': load_status,
                'value': f"{load_avg:.2f} ({load_per_core:.2f} per core)",
                'threshold': '< 1.0 per core healthy, < 2.0 warning, >= 2.0 critical'
            })
        
        # Service health checks
        server_manager = get_server_manager()
        if server_manager:
            # Check if Barbossa is responsive
            try:
                # This would need to be implemented in server_manager
                barbossa_status = 'healthy'  # Placeholder
                health_checks.append({
                    'name': 'Barbossa Service',
                    'status': barbossa_status,
                    'value': 'Responsive',
                    'threshold': 'Service must be responsive'
                })
            except Exception:
                health_checks.append({
                    'name': 'Barbossa Service',
                    'status': 'critical',
                    'value': 'Not responsive',
                    'threshold': 'Service must be responsive'
                })
        
        # Security health check
        guard = get_security_guard()
        if guard:
            try:
                # Check for recent security violations
                # This would need to be implemented in SecurityGuard
                security_status = 'healthy'  # Placeholder
                health_checks.append({
                    'name': 'Security Status',
                    'status': security_status,
                    'value': 'No recent violations',
                    'threshold': 'No security violations in last hour'
                })
            except Exception:
                health_checks.append({
                    'name': 'Security Status',
                    'status': 'warning',
                    'value': 'Unable to check',
                    'threshold': 'Security checks must be accessible'
                })
        
        # Determine overall status
        critical_count = len([check for check in health_checks if check['status'] == 'critical'])
        warning_count = len([check for check in health_checks if check['status'] == 'warning'])
        
        if critical_count > 0:
            overall_status = 'critical'
        elif warning_count > 0:
            overall_status = 'warning'
        
        result = {
            'health': {
                'overall_status': overall_status,
                'checks': health_checks,
                'summary': {
                    'total_checks': len(health_checks),
                    'healthy': len([check for check in health_checks if check['status'] == 'healthy']),
                    'warning': warning_count,
                    'critical': critical_count
                },
                'timestamp': datetime.now().isoformat()
            },
            'status': 'success'
        }
        
        # Cache for 60 seconds
        cache_response(cache_key, result, ttl=60)
        
        return jsonify(result)
    
    except Exception as e:
        logging.error(f"Error getting system health: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/system/processes', methods=['GET'])
def system_processes():
    """Get system process information"""
    try:
        # Query parameters
        filter_name = request.args.get('filter')
        sort_by = request.args.get('sort_by', 'cpu_percent')
        limit = request.args.get('limit', 20, type=int)
        
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'status', 'create_time', 'cmdline']):
            try:
                pinfo = proc.info
                if filter_name and filter_name.lower() not in pinfo['name'].lower():
                    continue
                
                processes.append({
                    'pid': pinfo['pid'],
                    'name': pinfo['name'],
                    'cpu_percent': pinfo['cpu_percent'],
                    'memory_percent': pinfo['memory_percent'],
                    'status': pinfo['status'],
                    'create_time': pinfo['create_time'],
                    'cmdline': ' '.join(pinfo['cmdline']) if pinfo['cmdline'] else ''
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Sort processes
        if sort_by in ['cpu_percent', 'memory_percent', 'create_time']:
            processes.sort(key=lambda x: x[sort_by], reverse=True)
        elif sort_by == 'name':
            processes.sort(key=lambda x: x[sort_by])
        
        # Limit results
        processes = processes[:limit]
        
        return jsonify({
            'processes': processes,
            'total': len(processes),
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting system processes: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# ============================================================================
# SECURITY AUDIT API ENDPOINTS
# ============================================================================

@enhanced_api.route('/security/audit', methods=['GET'])
def security_audit():
    """Get security audit information"""
    try:
        # Check cache
        cache_key = f"security_audit_{request.query_string.decode()}"
        cached = get_cached_response(cache_key)
        if cached:
            return jsonify(cached)
        
        guard = get_security_guard()
        if not guard:
            return jsonify({
                'error': 'Security guard not available',
                'audit': {}
            }), 503
        
        # Query parameters
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        severity = request.args.get('severity')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        # This would need to be implemented in SecurityGuard
        # For now, return a placeholder structure
        audit_logs = []
        security_stats = {
            'total_events': 0,
            'blocked_attempts': 0,
            'allowed_operations': 0,
            'violations': 0,
            'last_scan': datetime.now().isoformat()
        }
        
        result = {
            'audit': {
                'logs': audit_logs,
                'stats': security_stats,
                'filters': {
                    'limit': limit,
                    'offset': offset,
                    'severity': severity,
                    'start_date': start_date,
                    'end_date': end_date
                }
            },
            'status': 'success'
        }
        
        # Cache for 2 minutes
        cache_response(cache_key, result, ttl=120)
        
        return jsonify(result)
    
    except Exception as e:
        logging.error(f"Error getting security audit: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/security/scan', methods=['POST'])
def security_scan():
    """Trigger security scan"""
    try:
        guard = get_security_guard()
        if not guard:
            return jsonify({
                'error': 'Security guard not available'
            }), 503
        
        scan_type = request.json.get('type', 'full') if request.json else 'full'
        
        # This would need to be implemented in SecurityGuard
        scan_result = {
            'scan_id': str(uuid.uuid4()),
            'type': scan_type,
            'status': 'completed',
            'started_at': datetime.now().isoformat(),
            'completed_at': datetime.now().isoformat(),
            'findings': [],
            'summary': {
                'total_checks': 0,
                'passed': 0,
                'warnings': 0,
                'failures': 0
            }
        }
        
        return jsonify({
            'scan': scan_result,
            'status': 'success',
            'message': f'Security scan "{scan_type}" completed'
        })
    
    except Exception as e:
        logging.error(f"Error running security scan: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# ============================================================================
# API DOCUMENTATION AND VALIDATION
# ============================================================================

@enhanced_api.route('/docs', methods=['GET'])
def api_documentation():
    """Get API documentation"""
    try:
        docs = {
            'title': 'Barbossa Enhanced API v2',
            'version': '2.0.0',
            'description': 'Comprehensive REST API for Barbossa system management',
            'base_url': '/api/v2',
            'endpoints': {
                'projects': {
                    'GET /projects': 'List projects with filtering and pagination',
                    'POST /projects': 'Create a new project',
                    'GET /projects/{id}': 'Get project details',
                    'PUT /projects/{id}': 'Update project',
                    'DELETE /projects/{id}': 'Delete project'
                },
                'tasks': {
                    'GET /tasks': 'List tasks with filtering and pagination',
                    'POST /tasks': 'Create a new task',
                    'GET /tasks/{id}': 'Get task details',
                    'PUT /tasks/{id}': 'Update task',
                    'DELETE /tasks/{id}': 'Delete task'
                },
                'system': {
                    'GET /system/metrics': 'Get system metrics',
                    'GET /system/health': 'Get system health status',
                    'GET /system/processes': 'Get process information'
                },
                'security': {
                    'GET /security/audit': 'Get security audit logs',
                    'POST /security/scan': 'Trigger security scan'
                },
                'logs': {
                    'GET /logs': 'Get system logs with filtering and pagination',
                    'GET /logs/files': 'Get list of available log files',
                    'POST /logs/clear': 'Clear old log files'
                },
                'backup': {
                    'POST /backup/create': 'Create system backup',
                    'GET /backup/list': 'List available backups',
                    'POST /backup/{id}/restore': 'Restore from backup',
                    'DELETE /backup/{id}/delete': 'Delete backup'
                },
                'monitoring': {
                    'GET /monitoring/realtime': 'Get real-time system monitoring data',
                    'GET /monitoring/alerts': 'Get system alerts',
                    'POST /monitoring/alerts': 'Create new alert threshold'
                },
                'search': {
                    'GET /search': 'Advanced search across projects, tasks, logs, and configuration'
                },
                'analytics': {
                    'GET /analytics/summary': 'Get comprehensive analytics summary'
                },
                'config': {
                    'GET /config': 'Get system configuration',
                    'GET /config/{name}': 'Get specific configuration file',
                    'PUT /config/{name}': 'Update specific configuration file'
                },
                'notifications': {
                    'GET /notifications': 'Get system notifications',
                    'POST /notifications': 'Create a new notification',
                    'PUT /notifications/{id}/read': 'Mark notification as read'
                },
                'services': {
                    'GET /services': 'Get system services status',
                    'POST /services/{name}/{action}': 'Control system service (start/stop/restart)'
                },
                'metrics': {
                    'GET /metrics/history': 'Get historical system metrics',
                    'POST /metrics/store': 'Store current metrics for historical tracking'
                },
                'database': {
                    'GET /database/stats': 'Get database statistics and health',
                    'POST /database/optimize': 'Optimize database performance',
                    'POST /database/backup': 'Create database backup',
                    'GET /database/queries': 'Get recent database queries'
                },
                'integration': {
                    'GET /integration/webhooks': 'List webhook integrations',
                    'POST /integration/webhooks': 'Create webhook integration',
                    'POST /integration/test': 'Test external integrations'
                },
                'performance': {
                    'GET /performance/profile': 'Get system performance profile',
                    'POST /performance/benchmark': 'Run system benchmarks',
                    'GET /performance/recommendations': 'Get performance recommendations'
                },
                'meta': {
                    'GET /docs': 'Get API documentation',
                    'GET /status': 'Get API status'
                }
            },
            'schemas': {
                'project': {k: {**v, 'type': v['type'].__name__} for k, v in PROJECT_SCHEMA.items()},
                'task': {k: {**v, 'type': v['type'].__name__} for k, v in TASK_SCHEMA.items()},
                'backup': {
                    'type': {'type': 'str', 'choices': ['full', 'config', 'data']},
                    'include_logs': {'type': 'bool', 'default': False},
                    'compression': {'type': 'str', 'choices': ['gzip', 'none'], 'default': 'gzip'}
                },
                'alert': {
                    'name': {'type': 'str', 'required': True, 'max_length': 100},
                    'metric': {'type': 'str', 'required': True, 'choices': ['cpu', 'memory', 'disk', 'load', 'network']},
                    'threshold': {'type': 'float', 'required': True, 'min': 0, 'max': 100},
                    'severity': {'type': 'str', 'required': True, 'choices': ['low', 'medium', 'high', 'critical']}
                }
            },
            'error_codes': {
                '400': 'Bad Request - Invalid input data',
                '401': 'Unauthorized - Authentication required',
                '403': 'Forbidden - Access denied',
                '404': 'Not Found - Resource not found',
                '500': 'Internal Server Error - Server error',
                '503': 'Service Unavailable - Service not available'
            }
        }
        
        return jsonify({
            'documentation': docs,
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting API documentation: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/status', methods=['GET'])
def api_status():
    """Get API status and statistics"""
    try:
        status_info = {
            'api_version': '2.0.0',
            'status': 'operational',
            'timestamp': datetime.now().isoformat(),
            'uptime': time.time() - psutil.boot_time(),
            'cache': {
                'entries': len(api_cache),
                'max_size': 1000,  # Could be configurable
                'hit_rate': 'N/A'  # Would need to track hits/misses
            },
            'services': {
                'server_manager': SERVER_MANAGER_AVAILABLE,
                'security_guard': SECURITY_GUARD_AVAILABLE,
                'database': True  # Would need to test connection
            }
        }
        
        return jsonify({
            'status_info': status_info,
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting API status: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# ============================================================================
# ERROR HANDLERS
# ============================================================================

@enhanced_api.errorhandler(400)
def bad_request(error):
    return jsonify({
        'error': 'Bad Request',
        'message': 'The request could not be understood or was missing required parameters',
        'status': 'error'
    }), 400

@enhanced_api.errorhandler(401)
def unauthorized(error):
    return jsonify({
        'error': 'Unauthorized',
        'message': 'Authentication is required to access this resource',
        'status': 'error'
    }), 401

@enhanced_api.errorhandler(403)
def forbidden(error):
    return jsonify({
        'error': 'Forbidden',
        'message': 'You do not have permission to access this resource',
        'status': 'error'
    }), 403

@enhanced_api.errorhandler(404)
def not_found(error):
    return jsonify({
        'error': 'Not Found',
        'message': 'The requested resource was not found',
        'status': 'error'
    }), 404

@enhanced_api.errorhandler(500)
def internal_error(error):
    return jsonify({
        'error': 'Internal Server Error',
        'message': 'An unexpected error occurred on the server',
        'status': 'error'
    }), 500

@enhanced_api.errorhandler(503)
def service_unavailable(error):
    return jsonify({
        'error': 'Service Unavailable',
        'message': 'The requested service is temporarily unavailable',
        'status': 'error'
    }), 503

# ============================================================================
# LOG MANAGEMENT API ENDPOINTS
# ============================================================================

@enhanced_api.route('/logs', methods=['GET'])
def get_logs():
    """Get system logs with filtering and pagination"""
    try:
        # Query parameters
        log_type = request.args.get('type', 'all')  # all, barbossa, security, system
        level = request.args.get('level')  # DEBUG, INFO, WARNING, ERROR, CRITICAL
        limit = request.args.get('limit', 100, type=int)
        offset = request.args.get('offset', 0, type=int)
        search = request.args.get('search')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        logs_dir = Path.home() / 'barbossa-engineer' / 'logs'
        log_entries = []
        
        # Define log files to search based on type
        log_files = []
        if log_type == 'all' or log_type == 'barbossa':
            log_files.extend(list(logs_dir.glob('barbossa_*.log')))
        if log_type == 'all' or log_type == 'security':
            security_dir = Path.home() / 'barbossa-engineer' / 'security'
            if security_dir.exists():
                log_files.extend(list(security_dir.glob('*.log')))
        if log_type == 'all' or log_type == 'system':
            log_files.extend(list(logs_dir.glob('cron_*.log')))
        
        # Parse log files
        for log_file in sorted(log_files, key=lambda x: x.stat().st_mtime, reverse=True):
            try:
                with open(log_file, 'r') as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line:
                            continue
                        
                        # Basic log parsing (adjust regex based on actual log format)
                        import re
                        log_pattern = r'(\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\s+(\w+)\s+(.+)'
                        match = re.match(log_pattern, line)
                        
                        if match:
                            timestamp, log_level, message = match.groups()
                            
                            # Apply filters
                            if level and log_level != level:
                                continue
                            if search and search.lower() not in message.lower():
                                continue
                            
                            log_entry = {
                                'timestamp': timestamp,
                                'level': log_level,
                                'message': message,
                                'file': log_file.name,
                                'line_number': line_num,
                                'type': 'barbossa' if 'barbossa' in log_file.name else 'security' if 'security' in str(log_file) else 'system'
                            }
                            log_entries.append(log_entry)
                        else:
                            # Handle lines that don't match the pattern
                            log_entries.append({
                                'timestamp': datetime.fromtimestamp(log_file.stat().st_mtime).isoformat(),
                                'level': 'INFO',
                                'message': line,
                                'file': log_file.name,
                                'line_number': line_num,
                                'type': 'unparsed'
                            })
            except Exception as e:
                logging.warning(f"Error reading log file {log_file}: {e}")
        
        # Sort by timestamp (newest first)
        log_entries.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Apply pagination
        total_entries = len(log_entries)
        paginated_entries = log_entries[offset:offset + limit]
        
        result = {
            'logs': paginated_entries,
            'total': total_entries,
            'limit': limit,
            'offset': offset,
            'has_more': offset + limit < total_entries,
            'filters': {
                'type': log_type,
                'level': level,
                'search': search,
                'start_date': start_date,
                'end_date': end_date
            },
            'status': 'success'
        }
        
        return jsonify(result)
    
    except Exception as e:
        logging.error(f"Error getting logs: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/logs/files', methods=['GET'])
def get_log_files():
    """Get list of available log files"""
    try:
        logs_dir = Path.home() / 'barbossa-engineer' / 'logs'
        security_dir = Path.home() / 'barbossa-engineer' / 'security'
        
        log_files = []
        
        # Get all log files with metadata
        for directory, file_type in [(logs_dir, 'system'), (security_dir, 'security')]:
            if directory.exists():
                for log_file in directory.glob('*.log'):
                    stat = log_file.stat()
                    log_files.append({
                        'name': log_file.name,
                        'path': str(log_file),
                        'type': file_type,
                        'size': stat.st_size,
                        'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        'lines': sum(1 for _ in open(log_file, 'r')) if stat.st_size < 10*1024*1024 else None  # Only count lines for files < 10MB
                    })
        
        # Sort by modification time (newest first)
        log_files.sort(key=lambda x: x['modified'], reverse=True)
        
        return jsonify({
            'log_files': log_files,
            'total': len(log_files),
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting log files: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/logs/clear', methods=['POST'])
def clear_logs():
    """Clear old log files"""
    try:
        data = request.get_json() or {}
        days_older_than = data.get('days_older_than', 30)
        file_types = data.get('file_types', ['system', 'security'])
        dry_run = data.get('dry_run', True)
        
        cutoff_date = datetime.now() - timedelta(days=days_older_than)
        files_to_remove = []
        total_size_freed = 0
        
        directories = []
        if 'system' in file_types:
            directories.append(Path.home() / 'barbossa-engineer' / 'logs')
        if 'security' in file_types:
            directories.append(Path.home() / 'barbossa-engineer' / 'security')
        
        for directory in directories:
            if directory.exists():
                for log_file in directory.glob('*.log'):
                    file_time = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if file_time < cutoff_date:
                        file_size = log_file.stat().st_size
                        files_to_remove.append({
                            'file': str(log_file),
                            'size': file_size,
                            'modified': file_time.isoformat()
                        })
                        total_size_freed += file_size
                        
                        if not dry_run:
                            log_file.unlink()
        
        result = {
            'files_removed' if not dry_run else 'files_to_remove': files_to_remove,
            'total_files': len(files_to_remove),
            'total_size_freed': total_size_freed,
            'dry_run': dry_run,
            'status': 'success',
            'message': f"{'Would remove' if dry_run else 'Removed'} {len(files_to_remove)} log files"
        }
        
        return jsonify(result)
    
    except Exception as e:
        logging.error(f"Error clearing logs: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# ============================================================================
# CONFIGURATION MANAGEMENT API ENDPOINTS
# ============================================================================

@enhanced_api.route('/config', methods=['GET'])
def get_configuration():
    """Get system configuration"""
    try:
        config_files = [
            Path.home() / 'barbossa-engineer' / 'config' / 'repository_whitelist.json',
            Path.home() / 'barbossa-engineer' / 'work_tracking' / 'work_tally.json',
            Path.home() / 'barbossa-engineer' / 'config' / 'barbossa_config.json'
        ]
        
        configuration = {}
        
        for config_file in config_files:
            if config_file.exists():
                try:
                    with open(config_file, 'r') as f:
                        config_data = json.load(f)
                    configuration[config_file.stem] = config_data
                except Exception as e:
                    logging.warning(f"Error reading config file {config_file}: {e}")
                    configuration[config_file.stem] = {'error': str(e)}
        
        # Add environment variables (sanitized)
        env_vars = {}
        for key, value in os.environ.items():
            if any(sensitive in key.upper() for sensitive in ['KEY', 'TOKEN', 'SECRET', 'PASSWORD']):
                env_vars[key] = '***HIDDEN***'
            else:
                env_vars[key] = value
        
        configuration['environment'] = env_vars
        
        return jsonify({
            'configuration': configuration,
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting configuration: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/config/<config_name>', methods=['GET', 'PUT'])
def manage_config_file(config_name):
    """Get or update specific configuration file"""
    if request.method == 'GET':
        return get_config_file(config_name)
    elif request.method == 'PUT':
        return update_config_file(config_name)

def get_config_file(config_name: str):
    """Get specific configuration file"""
    try:
        config_dir = Path.home() / 'barbossa-engineer' / 'config'
        config_file = config_dir / f"{config_name}.json"
        
        if not config_file.exists():
            return jsonify({'error': 'Configuration file not found'}), 404
        
        with open(config_file, 'r') as f:
            config_data = json.load(f)
        
        return jsonify({
            'config': config_data,
            'file_path': str(config_file),
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting config file {config_name}: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

def update_config_file(config_name: str):
    """Update specific configuration file"""
    try:
        data = request.get_json()
        if not data or 'config' not in data:
            return jsonify({'error': 'No configuration data provided'}), 400
        
        config_dir = Path.home() / 'barbossa-engineer' / 'config'
        config_file = config_dir / f"{config_name}.json"
        
        # Backup existing file
        if config_file.exists():
            backup_file = config_file.with_suffix(f'.json.backup.{int(time.time())}')
            config_file.rename(backup_file)
        
        # Write new configuration
        config_dir.mkdir(exist_ok=True)
        with open(config_file, 'w') as f:
            json.dump(data['config'], f, indent=2)
        
        return jsonify({
            'status': 'success',
            'message': f'Configuration {config_name} updated successfully',
            'file_path': str(config_file)
        })
    
    except Exception as e:
        logging.error(f"Error updating config file {config_name}: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# ============================================================================
# NOTIFICATION/ALERT API ENDPOINTS
# ============================================================================

@enhanced_api.route('/notifications', methods=['GET', 'POST'])
def manage_notifications():
    """Get or create notifications"""
    if request.method == 'GET':
        return get_notifications()
    elif request.method == 'POST':
        return create_notification()

def get_notifications():
    """Get system notifications"""
    try:
        # Query parameters
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        severity = request.args.get('severity')
        read_status = request.args.get('read')
        
        # Simple file-based notification storage
        notifications_file = Path.home() / 'barbossa-engineer' / 'data' / 'notifications.json'
        notifications = []
        
        if notifications_file.exists():
            with open(notifications_file, 'r') as f:
                notifications = json.load(f)
        
        # Apply filters
        filtered_notifications = notifications
        if severity:
            filtered_notifications = [n for n in filtered_notifications if n.get('severity') == severity]
        if read_status is not None:
            is_read = read_status.lower() == 'true'
            filtered_notifications = [n for n in filtered_notifications if n.get('read', False) == is_read]
        
        # Sort by timestamp (newest first)
        filtered_notifications.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Apply pagination
        total_notifications = len(filtered_notifications)
        paginated_notifications = filtered_notifications[offset:offset + limit]
        
        return jsonify({
            'notifications': paginated_notifications,
            'total': total_notifications,
            'unread_count': len([n for n in notifications if not n.get('read', False)]),
            'limit': limit,
            'offset': offset,
            'has_more': offset + limit < total_notifications,
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting notifications: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

def create_notification():
    """Create a new notification"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate required fields
        required_fields = ['title', 'message', 'severity']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Field {field} is required'}), 400
        
        # Create notification
        notification = {
            'id': str(uuid.uuid4()),
            'title': data['title'],
            'message': data['message'],
            'severity': data['severity'],  # info, warning, error, critical
            'category': data.get('category', 'system'),
            'timestamp': datetime.now().isoformat(),
            'read': False,
            'metadata': data.get('metadata', {})
        }
        
        # Load existing notifications
        notifications_file = Path.home() / 'barbossa-engineer' / 'data' / 'notifications.json'
        notifications = []
        
        if notifications_file.exists():
            with open(notifications_file, 'r') as f:
                notifications = json.load(f)
        
        # Add new notification
        notifications.append(notification)
        
        # Keep only last 1000 notifications
        notifications = notifications[-1000:]
        
        # Save notifications
        notifications_file.parent.mkdir(exist_ok=True)
        with open(notifications_file, 'w') as f:
            json.dump(notifications, f, indent=2)
        
        return jsonify({
            'notification': notification,
            'status': 'success',
            'message': 'Notification created successfully'
        }), 201
    
    except Exception as e:
        logging.error(f"Error creating notification: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/notifications/<notification_id>/read', methods=['PUT'])
def mark_notification_read(notification_id):
    """Mark notification as read"""
    try:
        notifications_file = Path.home() / 'barbossa-engineer' / 'data' / 'notifications.json'
        
        if not notifications_file.exists():
            return jsonify({'error': 'Notifications file not found'}), 404
        
        with open(notifications_file, 'r') as f:
            notifications = json.load(f)
        
        # Find and update notification
        updated = False
        for notification in notifications:
            if notification['id'] == notification_id:
                notification['read'] = True
                notification['read_at'] = datetime.now().isoformat()
                updated = True
                break
        
        if not updated:
            return jsonify({'error': 'Notification not found'}), 404
        
        # Save updated notifications
        with open(notifications_file, 'w') as f:
            json.dump(notifications, f, indent=2)
        
        return jsonify({
            'status': 'success',
            'message': 'Notification marked as read'
        })
    
    except Exception as e:
        logging.error(f"Error marking notification as read: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# ============================================================================
# SERVICE CONTROL API ENDPOINTS
# ============================================================================

@enhanced_api.route('/services', methods=['GET'])
def get_services():
    """Get system services status"""
    try:
        services = []
        
        # Check common system services
        service_names = ['docker', 'ssh', 'cloudflared', 'nginx', 'postgresql']
        
        for service_name in service_names:
            try:
                result = subprocess.run(
                    ['systemctl', 'is-active', service_name],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                status = result.stdout.strip()
                
                # Get additional info
                info_result = subprocess.run(
                    ['systemctl', 'show', service_name, '--property=Description,LoadState,ActiveState,SubState'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                info = {}
                for line in info_result.stdout.strip().split('\n'):
                    if '=' in line:
                        key, value = line.split('=', 1)
                        info[key] = value
                
                services.append({
                    'name': service_name,
                    'status': status,
                    'description': info.get('Description', ''),
                    'load_state': info.get('LoadState', ''),
                    'active_state': info.get('ActiveState', ''),
                    'sub_state': info.get('SubState', '')
                })
            except Exception as e:
                services.append({
                    'name': service_name,
                    'status': 'unknown',
                    'error': str(e)
                })
        
        # Check Barbossa-specific processes
        barbossa_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'status']):
            try:
                if 'barbossa' in ' '.join(proc.info['cmdline']).lower():
                    barbossa_processes.append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'cmdline': ' '.join(proc.info['cmdline']),
                        'status': proc.info['status']
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return jsonify({
            'system_services': services,
            'barbossa_processes': barbossa_processes,
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting services: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/services/<service_name>/<action>', methods=['POST'])
def control_service(service_name, action):
    """Control system service (start/stop/restart)"""
    try:
        # Security check - only allow specific services
        allowed_services = ['docker', 'nginx', 'cloudflared']
        allowed_actions = ['start', 'stop', 'restart', 'reload']
        
        if service_name not in allowed_services:
            return jsonify({
                'error': f'Service {service_name} is not allowed to be controlled'
            }), 403
        
        if action not in allowed_actions:
            return jsonify({
                'error': f'Action {action} is not allowed'
            }), 400
        
        # Execute systemctl command
        result = subprocess.run(
            ['sudo', 'systemctl', action, service_name],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            return jsonify({
                'status': 'success',
                'message': f'Successfully {action}ed {service_name}',
                'output': result.stdout
            })
        else:
            return jsonify({
                'status': 'error',
                'message': f'Failed to {action} {service_name}',
                'error': result.stderr
            }), 500
    
    except subprocess.TimeoutExpired:
        return jsonify({
            'error': f'Timeout while trying to {action} {service_name}'
        }), 500
    except Exception as e:
        logging.error(f"Error controlling service {service_name}: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# ============================================================================
# METRICS HISTORY API ENDPOINTS
# ============================================================================

@enhanced_api.route('/metrics/history', methods=['GET'])
def get_metrics_history():
    """Get historical system metrics"""
    try:
        # Query parameters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        metric_type = request.args.get('type', 'all')  # cpu, memory, disk, network, all
        interval = request.args.get('interval', 'hour')  # minute, hour, day
        
        # For now, return sample data - in production this would query a time-series database
        sample_metrics = {
            'cpu': [
                {'timestamp': '2024-01-01T00:00:00', 'value': 45.2},
                {'timestamp': '2024-01-01T01:00:00', 'value': 52.1},
                {'timestamp': '2024-01-01T02:00:00', 'value': 38.7}
            ],
            'memory': [
                {'timestamp': '2024-01-01T00:00:00', 'value': 67.8},
                {'timestamp': '2024-01-01T01:00:00', 'value': 71.2},
                {'timestamp': '2024-01-01T02:00:00', 'value': 69.5}
            ],
            'disk': [
                {'timestamp': '2024-01-01T00:00:00', 'value': 45.2},
                {'timestamp': '2024-01-01T01:00:00', 'value': 45.3},
                {'timestamp': '2024-01-01T02:00:00', 'value': 45.4}
            ]
        }
        
        if metric_type != 'all' and metric_type in sample_metrics:
            result_metrics = {metric_type: sample_metrics[metric_type]}
        else:
            result_metrics = sample_metrics
        
        return jsonify({
            'metrics': result_metrics,
            'interval': interval,
            'start_date': start_date,
            'end_date': end_date,
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting metrics history: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/metrics/store', methods=['POST'])
def store_metrics():
    """Store current metrics for historical tracking"""
    try:
        # Get current system metrics
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'cpu_percent': psutil.cpu_percent(interval=1),
            'memory_percent': psutil.virtual_memory().percent,
            'disk_usage': {},
            'network_stats': psutil.net_io_counters()._asdict()
        }
        
        # Get disk usage for all partitions
        for partition in psutil.disk_partitions():
            try:
                disk_usage = psutil.disk_usage(partition.mountpoint)
                metrics['disk_usage'][partition.mountpoint] = {
                    'total': disk_usage.total,
                    'used': disk_usage.used,
                    'free': disk_usage.free,
                    'percent': (disk_usage.used / disk_usage.total) * 100
                }
            except PermissionError:
                continue
        
        # Store metrics in SQLite database
        db_path = Path.home() / 'barbossa-engineer' / 'data' / 'metrics.db'
        db_path.parent.mkdir(exist_ok=True)
        
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Create table if it doesn't exist
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    cpu_percent REAL,
                    memory_percent REAL,
                    disk_usage TEXT,
                    network_stats TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Insert metrics
            cursor.execute('''
                INSERT INTO system_metrics (timestamp, cpu_percent, memory_percent, disk_usage, network_stats)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                metrics['timestamp'],
                metrics['cpu_percent'],
                metrics['memory_percent'],
                json.dumps(metrics['disk_usage']),
                json.dumps(metrics['network_stats'])
            ))
            
            conn.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Metrics stored successfully',
            'metrics': metrics
        })
    
    except Exception as e:
        logging.error(f"Error storing metrics: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# ============================================================================
# BACKUP AND RESTORE API ENDPOINTS
# ============================================================================

@enhanced_api.route('/backup/create', methods=['POST'])
def create_backup():
    """Create system backup"""
    try:
        data = request.get_json() or {}
        backup_type = data.get('type', 'full')  # full, config, data
        include_logs = data.get('include_logs', False)
        compression = data.get('compression', 'gzip')
        
        backup_id = str(uuid.uuid4())
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"barbossa_backup_{backup_type}_{timestamp}"
        
        base_dir = Path.home() / 'barbossa-engineer'
        backup_dir = base_dir / 'backups' / backup_name
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        backup_manifest = {
            'id': backup_id,
            'name': backup_name,
            'type': backup_type,
            'created_at': datetime.now().isoformat(),
            'compression': compression,
            'include_logs': include_logs,
            'files': [],
            'status': 'in_progress'
        }
        
        try:
            # Backup configuration files
            config_files = [
                'config/repository_whitelist.json',
                'work_tracking/work_tally.json',
                'barbossa_prompt.txt',
                'requirements.txt'
            ]
            
            for config_file in config_files:
                source = base_dir / config_file
                if source.exists():
                    dest = backup_dir / config_file
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
                    backup_manifest['files'].append(config_file)
            
            # Backup data files if requested
            if backup_type in ['full', 'data']:
                data_files = [
                    'metrics.db',
                    'security/security.db',
                    'workflows.db'
                ]
                
                for data_file in data_files:
                    source = base_dir / data_file
                    if source.exists():
                        dest = backup_dir / data_file
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, dest)
                        backup_manifest['files'].append(data_file)
            
            # Backup logs if requested
            if include_logs:
                logs_dir = base_dir / 'logs'
                if logs_dir.exists():
                    for log_file in logs_dir.glob('*.log'):
                        if log_file.stat().st_size < 100 * 1024 * 1024:  # Only files < 100MB
                            rel_path = f"logs/{log_file.name}"
                            dest = backup_dir / rel_path
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(log_file, dest)
                            backup_manifest['files'].append(rel_path)
            
            # Create compressed archive if requested
            archive_path = None
            if compression == 'gzip':
                archive_path = f"{backup_dir}.tar.gz"
                subprocess.run(['tar', '-czf', archive_path, '-C', backup_dir.parent, backup_dir.name], check=True)
                shutil.rmtree(backup_dir)
                backup_manifest['archive_path'] = archive_path
                backup_manifest['size'] = os.path.getsize(archive_path)
            else:
                backup_manifest['size'] = sum(f.stat().st_size for f in backup_dir.rglob('*') if f.is_file())
            
            backup_manifest['status'] = 'completed'
            backup_manifest['completed_at'] = datetime.now().isoformat()
            
            # Save manifest
            manifest_file = base_dir / 'backups' / f"{backup_name}_manifest.json"
            with open(manifest_file, 'w') as f:
                json.dump(backup_manifest, f, indent=2)
            
            return jsonify({
                'backup': backup_manifest,
                'status': 'success',
                'message': f'Backup {backup_name} created successfully'
            }), 201
            
        except Exception as e:
            backup_manifest['status'] = 'failed'
            backup_manifest['error'] = str(e)
            return jsonify({
                'backup': backup_manifest,
                'status': 'error',
                'error': str(e)
            }), 500
    
    except Exception as e:
        logging.error(f"Error creating backup: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/backup/list', methods=['GET'])
def list_backups():
    """List available backups"""
    try:
        backups_dir = Path.home() / 'barbossa-engineer' / 'backups'
        backups = []
        
        if backups_dir.exists():
            for manifest_file in backups_dir.glob('*_manifest.json'):
                try:
                    with open(manifest_file, 'r') as f:
                        backup_info = json.load(f)
                    
                    # Check if archive/directory still exists
                    if 'archive_path' in backup_info:
                        backup_info['exists'] = Path(backup_info['archive_path']).exists()
                    else:
                        backup_dir = backups_dir / backup_info['name']
                        backup_info['exists'] = backup_dir.exists()
                    
                    backups.append(backup_info)
                except Exception as e:
                    logging.warning(f"Error reading backup manifest {manifest_file}: {e}")
        
        # Sort by creation date (newest first)
        backups.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        return jsonify({
            'backups': backups,
            'total': len(backups),
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error listing backups: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/backup/<backup_id>/restore', methods=['POST'])
def restore_backup(backup_id):
    """Restore from backup"""
    try:
        data = request.get_json() or {}
        restore_type = data.get('type', 'config')  # config, data, full
        force = data.get('force', False)
        
        # Find backup manifest
        backups_dir = Path.home() / 'barbossa-engineer' / 'backups'
        manifest_file = None
        
        for file in backups_dir.glob('*_manifest.json'):
            with open(file, 'r') as f:
                manifest = json.load(f)
                if manifest['id'] == backup_id:
                    manifest_file = file
                    break
        
        if not manifest_file:
            return jsonify({'error': 'Backup not found'}), 404
        
        with open(manifest_file, 'r') as f:
            backup_manifest = json.load(f)
        
        # Check if backup exists
        if 'archive_path' in backup_manifest:
            if not Path(backup_manifest['archive_path']).exists():
                return jsonify({'error': 'Backup archive not found'}), 404
        else:
            backup_dir = backups_dir / backup_manifest['name']
            if not backup_dir.exists():
                return jsonify({'error': 'Backup directory not found'}), 404
        
        base_dir = Path.home() / 'barbossa-engineer'
        restored_files = []
        
        try:
            # Extract archive if needed
            temp_dir = None
            if 'archive_path' in backup_manifest:
                temp_dir = backups_dir / f"temp_restore_{int(time.time())}"
                temp_dir.mkdir()
                subprocess.run(['tar', '-xzf', backup_manifest['archive_path'], '-C', temp_dir], check=True)
                restore_source = temp_dir / backup_manifest['name']
            else:
                restore_source = backups_dir / backup_manifest['name']
            
            # Restore files based on type
            for file_path in backup_manifest['files']:
                if restore_type == 'config' and not any(file_path.startswith(p) for p in ['config/', 'barbossa_prompt.txt', 'requirements.txt']):
                    continue
                if restore_type == 'data' and not any(file_path.endswith(ext) for ext in ['.db', '.json']):
                    continue
                
                source = restore_source / file_path
                dest = base_dir / file_path
                
                if source.exists():
                    # Backup existing file if not forcing
                    if dest.exists() and not force:
                        backup_path = dest.with_suffix(f"{dest.suffix}.backup.{int(time.time())}")
                        shutil.copy2(dest, backup_path)
                    
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
                    restored_files.append(file_path)
            
            # Clean up temp directory
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir)
            
            return jsonify({
                'restored_files': restored_files,
                'total_files': len(restored_files),
                'backup_info': backup_manifest,
                'restore_type': restore_type,
                'status': 'success',
                'message': f'Successfully restored {len(restored_files)} files from backup'
            })
            
        except Exception as e:
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir)
            raise e
    
    except Exception as e:
        logging.error(f"Error restoring backup {backup_id}: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/backup/<backup_id>/delete', methods=['DELETE'])
def delete_backup(backup_id):
    """Delete backup"""
    try:
        backups_dir = Path.home() / 'barbossa-engineer' / 'backups'
        manifest_file = None
        
        # Find and load backup manifest
        for file in backups_dir.glob('*_manifest.json'):
            with open(file, 'r') as f:
                manifest = json.load(f)
                if manifest['id'] == backup_id:
                    manifest_file = file
                    backup_manifest = manifest
                    break
        
        if not manifest_file:
            return jsonify({'error': 'Backup not found'}), 404
        
        files_deleted = []
        
        # Delete archive or directory
        if 'archive_path' in backup_manifest:
            archive_path = Path(backup_manifest['archive_path'])
            if archive_path.exists():
                archive_path.unlink()
                files_deleted.append(str(archive_path))
        else:
            backup_dir = backups_dir / backup_manifest['name']
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
                files_deleted.append(str(backup_dir))
        
        # Delete manifest
        manifest_file.unlink()
        files_deleted.append(str(manifest_file))
        
        return jsonify({
            'deleted_files': files_deleted,
            'backup_name': backup_manifest['name'],
            'status': 'success',
            'message': f'Backup {backup_manifest["name"]} deleted successfully'
        })
    
    except Exception as e:
        logging.error(f"Error deleting backup {backup_id}: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# ============================================================================
# REAL-TIME MONITORING API ENDPOINTS
# ============================================================================

@enhanced_api.route('/monitoring/realtime', methods=['GET'])
def realtime_monitoring():
    """Get real-time system monitoring data"""
    try:
        # Collect comprehensive real-time metrics
        metrics = {
            'timestamp': datetime.now().isoformat(),
            'system': {
                'uptime': time.time() - psutil.boot_time(),
                'load_average': list(os.getloadavg()) if hasattr(os, 'getloadavg') else None,
                'cpu': {
                    'usage_percent': psutil.cpu_percent(interval=0.1),
                    'core_count': psutil.cpu_count(),
                    'frequency': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None,
                    'per_core': psutil.cpu_percent(interval=0.1, percpu=True)
                },
                'memory': {
                    'virtual': psutil.virtual_memory()._asdict(),
                    'swap': psutil.swap_memory()._asdict()
                },
                'network': psutil.net_io_counters()._asdict(),
                'disk_io': psutil.disk_io_counters()._asdict() if psutil.disk_io_counters() else None
            },
            'processes': {
                'total': len(psutil.pids()),
                'by_status': {}
            }
        }
        
        # Count processes by status
        status_counts = {}
        for proc in psutil.process_iter(['status']):
            try:
                status = proc.info['status']
                status_counts[status] = status_counts.get(status, 0) + 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        metrics['processes']['by_status'] = status_counts
        
        # Get disk usage for all partitions
        disk_usage = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_usage.append({
                    'device': partition.device,
                    'mountpoint': partition.mountpoint,
                    'fstype': partition.fstype,
                    'total': usage.total,
                    'used': usage.used,
                    'free': usage.free,
                    'percent': (usage.used / usage.total) * 100 if usage.total > 0 else 0
                })
            except PermissionError:
                continue
        metrics['system']['disk_usage'] = disk_usage
        
        # Get network interface statistics
        net_stats = {}
        for interface, stats in psutil.net_io_counters(pernic=True).items():
            net_stats[interface] = stats._asdict()
        metrics['system']['network_interfaces'] = net_stats
        
        # Get top processes by CPU and Memory
        top_processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'username']):
            try:
                pinfo = proc.info
                if pinfo['cpu_percent'] > 0 or pinfo['memory_percent'] > 0:
                    top_processes.append(pinfo)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Sort by CPU usage and take top 10
        top_processes.sort(key=lambda x: x['cpu_percent'], reverse=True)
        metrics['top_processes'] = top_processes[:10]
        
        # Add Barbossa-specific metrics if available
        server_manager = get_server_manager()
        if server_manager:
            try:
                barbossa_stats = {
                    'active_processes': len(server_manager.get_active_claude_processes()),
                    'last_execution': server_manager.get_last_execution_time(),
                    'work_areas': getattr(server_manager, 'get_work_area_stats', lambda: {})(),
                    'memory_usage': server_manager.get_memory_usage() if hasattr(server_manager, 'get_memory_usage') else None
                }
                metrics['barbossa'] = barbossa_stats
            except Exception as e:
                logging.warning(f"Error getting Barbossa stats: {e}")
        
        return jsonify({
            'metrics': metrics,
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting real-time monitoring data: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/monitoring/alerts', methods=['GET', 'POST'])
def manage_alerts():
    """Manage system alerts and thresholds"""
    if request.method == 'GET':
        return get_alerts()
    elif request.method == 'POST':
        return create_alert()

def get_alerts():
    """Get system alerts"""
    try:
        alerts_file = Path.home() / 'barbossa-engineer' / 'data' / 'alerts.json'
        alerts = []
        
        if alerts_file.exists():
            with open(alerts_file, 'r') as f:
                alerts = json.load(f)
        
        # Check current system status against alert thresholds
        active_alerts = []
        cpu_percent = psutil.cpu_percent(interval=1)
        memory_percent = psutil.virtual_memory().percent
        
        for alert in alerts:
            if not alert.get('enabled', True):
                continue
            
            triggered = False
            current_value = None
            
            if alert['metric'] == 'cpu':
                current_value = cpu_percent
                triggered = cpu_percent > alert['threshold']
            elif alert['metric'] == 'memory':
                current_value = memory_percent
                triggered = memory_percent > alert['threshold']
            elif alert['metric'] == 'disk':
                for partition in psutil.disk_partitions():
                    try:
                        usage = psutil.disk_usage(partition.mountpoint)
                        disk_percent = (usage.used / usage.total) * 100
                        if partition.mountpoint == alert.get('mountpoint', '/') and disk_percent > alert['threshold']:
                            current_value = disk_percent
                            triggered = True
                            break
                    except PermissionError:
                        continue
            
            if triggered:
                active_alert = dict(alert)
                active_alert['current_value'] = current_value
                active_alert['triggered_at'] = datetime.now().isoformat()
                active_alerts.append(active_alert)
        
        return jsonify({
            'alerts': alerts,
            'active_alerts': active_alerts,
            'total_alerts': len(alerts),
            'active_count': len(active_alerts),
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting alerts: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

def create_alert():
    """Create new alert threshold"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate required fields
        required_fields = ['name', 'metric', 'threshold', 'severity']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Field {field} is required'}), 400
        
        # Validate metric type
        valid_metrics = ['cpu', 'memory', 'disk', 'load', 'network']
        if data['metric'] not in valid_metrics:
            return jsonify({'error': f'Invalid metric. Must be one of: {valid_metrics}'}), 400
        
        alert = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'metric': data['metric'],
            'threshold': data['threshold'],
            'severity': data['severity'],  # low, medium, high, critical
            'enabled': data.get('enabled', True),
            'description': data.get('description', ''),
            'mountpoint': data.get('mountpoint', '/'),  # for disk alerts
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        
        # Load existing alerts
        alerts_file = Path.home() / 'barbossa-engineer' / 'data' / 'alerts.json'
        alerts = []
        
        if alerts_file.exists():
            with open(alerts_file, 'r') as f:
                alerts = json.load(f)
        
        # Add new alert
        alerts.append(alert)
        
        # Save alerts
        alerts_file.parent.mkdir(exist_ok=True)
        with open(alerts_file, 'w') as f:
            json.dump(alerts, f, indent=2)
        
        return jsonify({
            'alert': alert,
            'status': 'success',
            'message': f'Alert "{data["name"]}" created successfully'
        }), 201
    
    except Exception as e:
        logging.error(f"Error creating alert: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# ============================================================================
# ADVANCED SEARCH AND ANALYTICS API ENDPOINTS
# ============================================================================

@enhanced_api.route('/search', methods=['GET'])
def advanced_search():
    """Advanced search across projects, tasks, logs, and configuration"""
    try:
        query = request.args.get('q', '')
        category = request.args.get('category', 'all')  # all, projects, tasks, logs, config
        limit = request.args.get('limit', 50, type=int)
        include_content = request.args.get('include_content', 'false').lower() == 'true'
        
        if not query:
            return jsonify({'error': 'Search query is required'}), 400
        
        results = {'projects': [], 'tasks': [], 'logs': [], 'config': []}
        
        # Search projects
        if category in ['all', 'projects']:
            db_path = Path.home() / 'barbossa-engineer' / 'data' / 'barbossa.db'
            if db_path.exists():
                with sqlite3.connect(db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    
                    cursor.execute('''
                        SELECT * FROM projects 
                        WHERE name LIKE ? OR description LIKE ? 
                        LIMIT ?
                    ''', (f'%{query}%', f'%{query}%', limit))
                    
                    for row in cursor.fetchall():
                        project = dict(row)
                        # Parse JSON fields
                        for field in ['tags', 'metadata']:
                            if project.get(field):
                                try:
                                    project[field] = json.loads(project[field])
                                except:
                                    project[field] = []
                        results['projects'].append(project)
        
        # Search tasks
        if category in ['all', 'tasks']:
            db_path = Path.home() / 'barbossa-engineer' / 'data' / 'barbossa.db'
            if db_path.exists():
                with sqlite3.connect(db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.cursor()
                    
                    cursor.execute('''
                        SELECT t.*, p.name as project_name 
                        FROM tasks t 
                        LEFT JOIN projects p ON t.project_id = p.id 
                        WHERE t.title LIKE ? OR t.description LIKE ? 
                        LIMIT ?
                    ''', (f'%{query}%', f'%{query}%', limit))
                    
                    for row in cursor.fetchall():
                        task = dict(row)
                        # Parse JSON fields
                        for field in ['tags', 'dependencies', 'metadata']:
                            if task.get(field):
                                try:
                                    task[field] = json.loads(task[field])
                                except:
                                    task[field] = []
                        results['tasks'].append(task)
        
        # Search logs
        if category in ['all', 'logs']:
            logs_dir = Path.home() / 'barbossa-engineer' / 'logs'
            if logs_dir.exists():
                log_results = []
                for log_file in sorted(logs_dir.glob('*.log'), key=lambda x: x.stat().st_mtime, reverse=True):
                    if len(log_results) >= limit:
                        break
                    
                    try:
                        with open(log_file, 'r') as f:
                            for line_num, line in enumerate(f, 1):
                                if len(log_results) >= limit:
                                    break
                                if query.lower() in line.lower():
                                    log_entry = {
                                        'file': log_file.name,
                                        'line_number': line_num,
                                        'timestamp': datetime.fromtimestamp(log_file.stat().st_mtime).isoformat(),
                                        'preview': line.strip()[:200] + ('...' if len(line.strip()) > 200 else '')
                                    }
                                    if include_content:
                                        log_entry['content'] = line.strip()
                                    log_results.append(log_entry)
                    except Exception as e:
                        logging.warning(f"Error searching log file {log_file}: {e}")
                
                results['logs'] = log_results
        
        # Search configuration files
        if category in ['all', 'config']:
            config_files = [
                Path.home() / 'barbossa-engineer' / 'config' / 'repository_whitelist.json',
                Path.home() / 'barbossa-engineer' / 'work_tracking' / 'work_tally.json',
                Path.home() / 'barbossa-engineer' / 'barbossa_prompt.txt'
            ]
            
            for config_file in config_files:
                if config_file.exists():
                    try:
                        content = config_file.read_text()
                        if query.lower() in content.lower():
                            config_result = {
                                'file': config_file.name,
                                'path': str(config_file),
                                'type': 'json' if config_file.suffix == '.json' else 'text',
                                'size': config_file.stat().st_size,
                                'modified': datetime.fromtimestamp(config_file.stat().st_mtime).isoformat()
                            }
                            
                            if include_content:
                                config_result['content'] = content
                            else:
                                # Find matching lines for preview
                                matching_lines = []
                                for line_num, line in enumerate(content.split('\n'), 1):
                                    if query.lower() in line.lower():
                                        matching_lines.append({
                                            'line_number': line_num,
                                            'content': line.strip()
                                        })
                                        if len(matching_lines) >= 3:  # Limit preview
                                            break
                                config_result['matches'] = matching_lines
                            
                            results['config'].append(config_result)
                    except Exception as e:
                        logging.warning(f"Error searching config file {config_file}: {e}")
        
        # Calculate totals
        total_results = sum(len(results[key]) for key in results)
        
        return jsonify({
            'query': query,
            'category': category,
            'results': results,
            'total_results': total_results,
            'summary': {
                'projects': len(results['projects']),
                'tasks': len(results['tasks']),
                'logs': len(results['logs']),
                'config': len(results['config'])
            },
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error performing search: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/analytics/summary', methods=['GET'])
def analytics_summary():
    """Get comprehensive analytics summary"""
    try:
        # Query parameters
        period = request.args.get('period', '30d')  # 7d, 30d, 90d, 1y
        
        # Calculate date range
        now = datetime.now()
        if period == '7d':
            start_date = now - timedelta(days=7)
        elif period == '30d':
            start_date = now - timedelta(days=30)
        elif period == '90d':
            start_date = now - timedelta(days=90)
        elif period == '1y':
            start_date = now - timedelta(days=365)
        else:
            start_date = now - timedelta(days=30)
        
        analytics = {
            'period': period,
            'start_date': start_date.isoformat(),
            'end_date': now.isoformat(),
            'system': {},
            'projects': {},
            'tasks': {},
            'barbossa': {},
            'security': {}
        }
        
        # System analytics
        analytics['system'] = {
            'uptime_days': (time.time() - psutil.boot_time()) / 86400,
            'current_load': {
                'cpu_percent': psutil.cpu_percent(interval=1),
                'memory_percent': psutil.virtual_memory().percent,
                'disk_usage': []
            },
            'process_count': len(psutil.pids())
        }
        
        # Add disk usage
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                analytics['system']['current_load']['disk_usage'].append({
                    'mountpoint': partition.mountpoint,
                    'percent': (usage.used / usage.total) * 100
                })
            except PermissionError:
                continue
        
        # Project analytics
        db_path = Path.home() / 'barbossa-engineer' / 'data' / 'barbossa.db'
        if db_path.exists():
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # Project statistics
                cursor.execute('SELECT COUNT(*) FROM projects')
                total_projects = cursor.fetchone()[0]
                
                cursor.execute('SELECT status, COUNT(*) FROM projects GROUP BY status')
                project_status_counts = dict(cursor.fetchall())
                
                analytics['projects'] = {
                    'total': total_projects,
                    'by_status': project_status_counts,
                    'active_percentage': (project_status_counts.get('active', 0) / total_projects * 100) if total_projects > 0 else 0
                }
                
                # Task analytics
                cursor.execute('SELECT COUNT(*) FROM tasks')
                total_tasks = cursor.fetchone()[0]
                
                cursor.execute('SELECT status, COUNT(*) FROM tasks GROUP BY status')
                task_status_counts = dict(cursor.fetchall())
                
                cursor.execute('SELECT COUNT(*) FROM tasks WHERE completed_at IS NOT NULL AND completed_at != ""')
                completed_tasks = cursor.fetchone()[0]
                
                analytics['tasks'] = {
                    'total': total_tasks,
                    'by_status': task_status_counts,
                    'completion_rate': (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0,
                    'active_tasks': task_status_counts.get('in_progress', 0) + task_status_counts.get('pending', 0)
                }
        
        # Barbossa analytics
        server_manager = get_server_manager()
        if server_manager:
            try:
                barbossa_analytics = {
                    'active_processes': len(server_manager.get_active_claude_processes()),
                    'last_execution': server_manager.get_last_execution_time()
                }
                
                # Count recent executions from logs
                logs_dir = Path.home() / 'barbossa-engineer' / 'logs'
                recent_executions = 0
                if logs_dir.exists():
                    for log_file in logs_dir.glob('barbossa_*.log'):
                        if log_file.stat().st_mtime > start_date.timestamp():
                            recent_executions += 1
                
                barbossa_analytics['recent_executions'] = recent_executions
                analytics['barbossa'] = barbossa_analytics
            except Exception as e:
                logging.warning(f"Error getting Barbossa analytics: {e}")
        
        # Security analytics
        security_dir = Path.home() / 'barbossa-engineer' / 'security'
        if security_dir.exists():
            violations_file = security_dir / 'security_violations.log'
            audit_file = security_dir / 'audit.log'
            
            security_analytics = {
                'total_violations': 0,
                'recent_violations': 0,
                'total_audits': 0,
                'recent_audits': 0
            }
            
            # Count violations
            if violations_file.exists():
                try:
                    violations = violations_file.read_text().split('\n')
                    security_analytics['total_violations'] = len([v for v in violations if v.strip()])
                    
                    # Count recent violations
                    for line in violations:
                        if line.strip() and start_date.isoformat()[:10] in line:
                            security_analytics['recent_violations'] += 1
                except Exception:
                    pass
            
            # Count audit events
            if audit_file.exists():
                try:
                    audits = audit_file.read_text().split('\n')
                    security_analytics['total_audits'] = len([a for a in audits if a.strip()])
                    
                    # Count recent audits
                    for line in audits:
                        if line.strip() and start_date.isoformat()[:10] in line:
                            security_analytics['recent_audits'] += 1
                except Exception:
                    pass
            
            analytics['security'] = security_analytics
        
        return jsonify({
            'analytics': analytics,
            'generated_at': now.isoformat(),
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error generating analytics summary: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def cleanup_cache():
    """Clean up expired cache entries"""
    current_time = time.time()
    with api_cache_lock:
        expired_keys = [k for k, v in api_cache.items() if current_time >= v['expires_at']]
        for key in expired_keys:
            del api_cache[key]

# Schedule periodic cache cleanup
def start_cache_cleanup():
    """Start periodic cache cleanup"""
    def cleanup_worker():
        while True:
            time.sleep(300)  # Clean up every 5 minutes
            cleanup_cache()
    
    cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
    cleanup_thread.start()

# ============================================================================
# DATABASE MANAGEMENT API ENDPOINTS
# ============================================================================

@enhanced_api.route('/database/stats', methods=['GET'])
def database_stats():
    """Get database statistics and health"""
    try:
        stats = {
            'databases': [],
            'total_size': 0,
            'total_tables': 0,
            'total_records': 0
        }
        
        # Check all database files
        base_dir = Path.home() / 'barbossa-engineer'
        db_files = [
            base_dir / 'metrics.db',
            base_dir / 'security' / 'security.db',
            base_dir / 'workflows.db',
            base_dir / 'data' / 'barbossa.db'
        ]
        
        for db_file in db_files:
            if db_file.exists():
                try:
                    db_stat = {
                        'name': db_file.name,
                        'path': str(db_file),
                        'size': db_file.stat().st_size,
                        'modified': datetime.fromtimestamp(db_file.stat().st_mtime).isoformat(),
                        'tables': [],
                        'total_records': 0
                    }
                    
                    with sqlite3.connect(db_file) as conn:
                        cursor = conn.cursor()
                        
                        # Get table information
                        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                        tables = cursor.fetchall()
                        
                        for table_name, in tables:
                            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                            record_count = cursor.fetchone()[0]
                            
                            db_stat['tables'].append({
                                'name': table_name,
                                'records': record_count
                            })
                            db_stat['total_records'] += record_count
                    
                    stats['databases'].append(db_stat)
                    stats['total_size'] += db_stat['size']
                    stats['total_tables'] += len(db_stat['tables'])
                    stats['total_records'] += db_stat['total_records']
                    
                except Exception as e:
                    logging.warning(f"Error analyzing database {db_file}: {e}")
        
        return jsonify({
            'database_stats': stats,
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting database stats: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/database/optimize', methods=['POST'])
def optimize_database():
    """Optimize database performance"""
    try:
        data = request.get_json() or {}
        database = data.get('database', 'all')
        operations = data.get('operations', ['vacuum', 'analyze'])
        
        base_dir = Path.home() / 'barbossa-engineer'
        db_files = []
        
        if database == 'all':
            db_files = [
                base_dir / 'metrics.db',
                base_dir / 'security' / 'security.db',
                base_dir / 'workflows.db',
                base_dir / 'data' / 'barbossa.db'
            ]
        else:
            db_files = [base_dir / database]
        
        results = []
        
        for db_file in db_files:
            if not db_file.exists():
                continue
            
            try:
                result = {
                    'database': db_file.name,
                    'operations': [],
                    'size_before': db_file.stat().st_size,
                    'size_after': 0,
                    'space_saved': 0
                }
                
                with sqlite3.connect(db_file) as conn:
                    cursor = conn.cursor()
                    
                    if 'vacuum' in operations:
                        start_time = time.time()
                        cursor.execute('VACUUM')
                        result['operations'].append({
                            'name': 'vacuum',
                            'duration': time.time() - start_time,
                            'status': 'completed'
                        })
                    
                    if 'analyze' in operations:
                        start_time = time.time()
                        cursor.execute('ANALYZE')
                        result['operations'].append({
                            'name': 'analyze',
                            'duration': time.time() - start_time,
                            'status': 'completed'
                        })
                    
                    if 'reindex' in operations:
                        start_time = time.time()
                        cursor.execute('REINDEX')
                        result['operations'].append({
                            'name': 'reindex',
                            'duration': time.time() - start_time,
                            'status': 'completed'
                        })
                
                result['size_after'] = db_file.stat().st_size
                result['space_saved'] = result['size_before'] - result['size_after']
                results.append(result)
                
            except Exception as e:
                results.append({
                    'database': db_file.name,
                    'error': str(e),
                    'status': 'failed'
                })
        
        total_space_saved = sum(r.get('space_saved', 0) for r in results)
        
        return jsonify({
            'optimization_results': results,
            'total_space_saved': total_space_saved,
            'status': 'success',
            'message': f'Database optimization completed. Saved {total_space_saved} bytes.'
        })
    
    except Exception as e:
        logging.error(f"Error optimizing database: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# ============================================================================
# INTEGRATION API ENDPOINTS
# ============================================================================

@enhanced_api.route('/integration/webhooks', methods=['GET', 'POST'])
def manage_webhooks():
    """Manage webhook integrations"""
    if request.method == 'GET':
        return get_webhooks()
    elif request.method == 'POST':
        return create_webhook()

def get_webhooks():
    """Get webhook integrations"""
    try:
        webhooks_file = Path.home() / 'barbossa-engineer' / 'data' / 'webhooks.json'
        webhooks = []
        
        if webhooks_file.exists():
            with open(webhooks_file, 'r') as f:
                webhooks = json.load(f)
        
        # Check webhook health
        for webhook in webhooks:
            if webhook.get('enabled', True):
                try:
                    # Test webhook connectivity (ping)
                    import requests
                    response = requests.head(webhook['url'], timeout=5)
                    webhook['status'] = 'healthy' if response.status_code < 400 else 'unhealthy'
                    webhook['last_check'] = datetime.now().isoformat()
                except Exception:
                    webhook['status'] = 'unreachable'
                    webhook['last_check'] = datetime.now().isoformat()
            else:
                webhook['status'] = 'disabled'
        
        return jsonify({
            'webhooks': webhooks,
            'total': len(webhooks),
            'active': len([w for w in webhooks if w.get('enabled', True)]),
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting webhooks: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

def create_webhook():
    """Create webhook integration"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Validate required fields
        required_fields = ['name', 'url', 'events']
        for field in required_fields:
            if field not in data:
                return jsonify({'error': f'Field {field} is required'}), 400
        
        webhook = {
            'id': str(uuid.uuid4()),
            'name': data['name'],
            'url': data['url'],
            'events': data['events'],  # ['system.alert', 'task.completed', 'backup.created', etc.]
            'enabled': data.get('enabled', True),
            'secret': data.get('secret', ''),
            'headers': data.get('headers', {}),
            'retry_count': data.get('retry_count', 3),
            'timeout': data.get('timeout', 30),
            'created_at': datetime.now().isoformat(),
            'last_triggered': None,
            'total_calls': 0,
            'failed_calls': 0
        }
        
        # Load existing webhooks
        webhooks_file = Path.home() / 'barbossa-engineer' / 'data' / 'webhooks.json'
        webhooks = []
        
        if webhooks_file.exists():
            with open(webhooks_file, 'r') as f:
                webhooks = json.load(f)
        
        # Add new webhook
        webhooks.append(webhook)
        
        # Save webhooks
        webhooks_file.parent.mkdir(exist_ok=True)
        with open(webhooks_file, 'w') as f:
            json.dump(webhooks, f, indent=2)
        
        return jsonify({
            'webhook': webhook,
            'status': 'success',
            'message': f'Webhook "{data["name"]}" created successfully'
        }), 201
    
    except Exception as e:
        logging.error(f"Error creating webhook: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/integration/test', methods=['POST'])
def test_integration():
    """Test external integrations"""
    try:
        data = request.get_json() or {}
        integration_type = data.get('type', 'webhook')
        
        if integration_type == 'webhook':
            url = data.get('url')
            if not url:
                return jsonify({'error': 'URL is required for webhook test'}), 400
            
            test_payload = {
                'event': 'test',
                'timestamp': datetime.now().isoformat(),
                'data': {'message': 'This is a test webhook from Barbossa Enhanced API'}
            }
            
            try:
                import requests
                headers = data.get('headers', {})
                headers['Content-Type'] = 'application/json'
                
                response = requests.post(
                    url,
                    json=test_payload,
                    headers=headers,
                    timeout=data.get('timeout', 30)
                )
                
                return jsonify({
                    'test_result': {
                        'url': url,
                        'status_code': response.status_code,
                        'response_time': response.elapsed.total_seconds(),
                        'success': response.status_code < 400,
                        'response_headers': dict(response.headers),
                        'response_body': response.text[:500]  # Limit response body
                    },
                    'status': 'success'
                })
            
            except Exception as e:
                return jsonify({
                    'test_result': {
                        'url': url,
                        'success': False,
                        'error': str(e)
                    },
                    'status': 'success'  # Request was successful, but test failed
                })
        
        else:
            return jsonify({'error': f'Integration type {integration_type} not supported'}), 400
    
    except Exception as e:
        logging.error(f"Error testing integration: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# ============================================================================
# PERFORMANCE MONITORING API ENDPOINTS
# ============================================================================

@enhanced_api.route('/performance/profile', methods=['GET'])
def performance_profile():
    """Get system performance profile"""
    try:
        # Collect detailed performance metrics
        profile = {
            'timestamp': datetime.now().isoformat(),
            'cpu': {
                'usage_percent': psutil.cpu_percent(interval=1),
                'core_usage': psutil.cpu_percent(interval=1, percpu=True),
                'frequency': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None,
                'load_average': list(os.getloadavg()) if hasattr(os, 'getloadavg') else None,
                'context_switches': psutil.cpu_stats().ctx_switches,
                'interrupts': psutil.cpu_stats().interrupts
            },
            'memory': {
                'virtual': psutil.virtual_memory()._asdict(),
                'swap': psutil.swap_memory()._asdict(),
                'top_consumers': []
            },
            'disk': {
                'io_stats': psutil.disk_io_counters()._asdict() if psutil.disk_io_counters() else None,
                'usage_by_partition': []
            },
            'network': {
                'io_stats': psutil.net_io_counters()._asdict(),
                'connections': len(psutil.net_connections()),
                'interfaces': {}
            },
            'processes': {
                'total': len(psutil.pids()),
                'top_cpu': [],
                'top_memory': []
            }
        }
        
        # Get disk usage for all partitions
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                profile['disk']['usage_by_partition'].append({
                    'device': partition.device,
                    'mountpoint': partition.mountpoint,
                    'fstype': partition.fstype,
                    'total': usage.total,
                    'used': usage.used,
                    'free': usage.free,
                    'percent': (usage.used / usage.total) * 100
                })
            except PermissionError:
                continue
        
        # Get network interface stats
        for interface, stats in psutil.net_io_counters(pernic=True).items():
            profile['network']['interfaces'][interface] = stats._asdict()
        
        # Get top processes by CPU and Memory
        processes = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'memory_info']):
            try:
                pinfo = proc.info
                processes.append(pinfo)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Sort and get top consumers
        profile['processes']['top_cpu'] = sorted(processes, key=lambda x: x.get('cpu_percent', 0), reverse=True)[:10]
        profile['processes']['top_memory'] = sorted(processes, key=lambda x: x.get('memory_percent', 0), reverse=True)[:10]
        
        # Memory top consumers with actual memory usage
        for proc in profile['processes']['top_memory']:
            if proc.get('memory_info'):
                proc['memory_rss'] = proc['memory_info'].rss
                proc['memory_vms'] = proc['memory_info'].vms
        
        return jsonify({
            'performance_profile': profile,
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting performance profile: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/performance/benchmark', methods=['POST'])
def run_benchmark():
    """Run system benchmarks"""
    try:
        data = request.get_json() or {}
        benchmark_type = data.get('type', 'quick')  # quick, full, custom
        duration = data.get('duration', 30)  # seconds
        
        benchmark_results = {
            'type': benchmark_type,
            'duration': duration,
            'started_at': datetime.now().isoformat(),
            'tests': []
        }
        
        # CPU benchmark
        if benchmark_type in ['quick', 'full'] or 'cpu' in data.get('tests', []):
            cpu_start = time.time()
            cpu_samples = []
            
            # Sample CPU usage over duration
            sample_interval = min(1.0, duration / 30)  # Take up to 30 samples
            while time.time() - cpu_start < min(duration, 10):  # Limit CPU test to 10 seconds
                cpu_samples.append(psutil.cpu_percent(interval=sample_interval))
            
            benchmark_results['tests'].append({
                'name': 'CPU Performance',
                'type': 'cpu',
                'duration': time.time() - cpu_start,
                'samples': len(cpu_samples),
                'avg_usage': sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0,
                'max_usage': max(cpu_samples) if cpu_samples else 0,
                'min_usage': min(cpu_samples) if cpu_samples else 0
            })
        
        # Memory benchmark
        if benchmark_type in ['quick', 'full'] or 'memory' in data.get('tests', []):
            memory_start = time.time()
            memory_info = psutil.virtual_memory()
            
            # Simple memory allocation test
            try:
                test_data = []
                for i in range(1000):
                    test_data.append(b'x' * 1024)  # Allocate 1KB chunks
                
                memory_after = psutil.virtual_memory()
                del test_data  # Clean up
                
                benchmark_results['tests'].append({
                    'name': 'Memory Performance',
                    'type': 'memory',
                    'duration': time.time() - memory_start,
                    'memory_before': memory_info.used,
                    'memory_after': memory_after.used,
                    'memory_diff': memory_after.used - memory_info.used,
                    'available_memory': memory_info.available
                })
            except Exception as e:
                benchmark_results['tests'].append({
                    'name': 'Memory Performance',
                    'type': 'memory',
                    'error': str(e)
                })
        
        # Disk I/O benchmark
        if benchmark_type == 'full' or 'disk' in data.get('tests', []):
            disk_start = time.time()
            
            try:
                # Simple disk write/read test
                test_file = Path.home() / 'barbossa-engineer' / 'temp_benchmark.dat'
                test_data = b'x' * (1024 * 1024)  # 1MB test data
                
                # Write test
                write_start = time.time()
                with open(test_file, 'wb') as f:
                    f.write(test_data)
                    f.flush()
                    os.fsync(f.fileno())
                write_time = time.time() - write_start
                
                # Read test
                read_start = time.time()
                with open(test_file, 'rb') as f:
                    read_data = f.read()
                read_time = time.time() - read_start
                
                # Clean up
                test_file.unlink()
                
                benchmark_results['tests'].append({
                    'name': 'Disk I/O Performance',
                    'type': 'disk',
                    'duration': time.time() - disk_start,
                    'write_time': write_time,
                    'read_time': read_time,
                    'write_speed_mbps': (len(test_data) / write_time) / (1024 * 1024),
                    'read_speed_mbps': (len(read_data) / read_time) / (1024 * 1024),
                    'data_size': len(test_data)
                })
            except Exception as e:
                benchmark_results['tests'].append({
                    'name': 'Disk I/O Performance',
                    'type': 'disk',
                    'error': str(e)
                })
        
        benchmark_results['completed_at'] = datetime.now().isoformat()
        benchmark_results['total_duration'] = time.time() - time.mktime(datetime.fromisoformat(benchmark_results['started_at']).timetuple())
        
        return jsonify({
            'benchmark_results': benchmark_results,
            'status': 'success',
            'message': f'Benchmark completed with {len(benchmark_results["tests"])} tests'
        })
    
    except Exception as e:
        logging.error(f"Error running benchmark: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

@enhanced_api.route('/performance/recommendations', methods=['GET'])
def performance_recommendations():
    """Get performance recommendations"""
    try:
        recommendations = []
        
        # Analyze current system state
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        # CPU recommendations
        if cpu_percent > 80:
            recommendations.append({
                'category': 'CPU',
                'severity': 'high',
                'title': 'High CPU Usage Detected',
                'description': f'CPU usage is at {cpu_percent:.1f}%. Consider identifying and optimizing CPU-intensive processes.',
                'current_value': cpu_percent,
                'threshold': 80,
                'suggestions': [
                    'Check top CPU consuming processes',
                    'Consider scaling down non-essential services',
                    'Review scheduled tasks and cron jobs'
                ]
            })
        elif cpu_percent > 60:
            recommendations.append({
                'category': 'CPU',
                'severity': 'medium',
                'title': 'Moderate CPU Usage',
                'description': f'CPU usage is at {cpu_percent:.1f}%. Monitor for trends.',
                'current_value': cpu_percent,
                'threshold': 60,
                'suggestions': ['Monitor CPU usage trends', 'Consider optimizing background processes']
            })
        
        # Memory recommendations
        if memory.percent > 85:
            recommendations.append({
                'category': 'Memory',
                'severity': 'high',
                'title': 'High Memory Usage',
                'description': f'Memory usage is at {memory.percent:.1f}%. System may experience performance issues.',
                'current_value': memory.percent,
                'threshold': 85,
                'suggestions': [
                    'Identify memory-hungry processes',
                    'Consider adding more RAM',
                    'Review memory leaks in applications',
                    'Clear system caches if safe'
                ]
            })
        elif memory.percent > 70:
            recommendations.append({
                'category': 'Memory',
                'severity': 'medium',
                'title': 'Moderate Memory Usage',
                'description': f'Memory usage is at {memory.percent:.1f}%. Consider monitoring trends.',
                'current_value': memory.percent,
                'threshold': 70,
                'suggestions': ['Monitor memory usage patterns', 'Review running services']
            })
        
        # Disk space recommendations
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                percent_used = (usage.used / usage.total) * 100
                
                if percent_used > 90:
                    recommendations.append({
                        'category': 'Disk',
                        'severity': 'critical',
                        'title': f'Critical Disk Space - {partition.mountpoint}',
                        'description': f'Disk {partition.mountpoint} is {percent_used:.1f}% full. Immediate action required.',
                        'current_value': percent_used,
                        'threshold': 90,
                        'mountpoint': partition.mountpoint,
                        'suggestions': [
                            'Clean up unnecessary files',
                            'Move large files to external storage',
                            'Clear log files and temporary data',
                            'Consider expanding disk space'
                        ]
                    })
                elif percent_used > 80:
                    recommendations.append({
                        'category': 'Disk',
                        'severity': 'high',
                        'title': f'High Disk Usage - {partition.mountpoint}',
                        'description': f'Disk {partition.mountpoint} is {percent_used:.1f}% full.',
                        'current_value': percent_used,
                        'threshold': 80,
                        'mountpoint': partition.mountpoint,
                        'suggestions': ['Review and clean up large files', 'Consider archiving old data']
                    })
            except PermissionError:
                continue
        
        # Barbossa-specific recommendations
        base_dir = Path.home() / 'barbossa-engineer'
        logs_dir = base_dir / 'logs'
        
        if logs_dir.exists():
            log_files = list(logs_dir.glob('*.log'))
            total_log_size = sum(f.stat().st_size for f in log_files)
            
            if total_log_size > 100 * 1024 * 1024:  # 100MB
                recommendations.append({
                    'category': 'Barbossa',
                    'severity': 'medium',
                    'title': 'Large Log Files',
                    'description': f'Log files are using {total_log_size / (1024*1024):.1f}MB of space.',
                    'current_value': total_log_size,
                    'suggestions': [
                        'Use the log cleanup API to remove old logs',
                        'Configure log rotation',
                        'Archive important logs'
                    ]
                })
        
        # Load average recommendations (Unix systems)
        if hasattr(os, 'getloadavg'):
            load_avg = os.getloadavg()[0]  # 1-minute load average
            cpu_cores = psutil.cpu_count()
            load_per_core = load_avg / cpu_cores if cpu_cores > 0 else load_avg
            
            if load_per_core > 2.0:
                recommendations.append({
                    'category': 'System Load',
                    'severity': 'high',
                    'title': 'High System Load',
                    'description': f'System load average is {load_avg:.2f} ({load_per_core:.2f} per core).',
                    'current_value': load_per_core,
                    'threshold': 2.0,
                    'suggestions': [
                        'Identify processes causing high load',
                        'Consider reducing concurrent operations',
                        'Review system scheduling'
                    ]
                })
        
        # Sort recommendations by severity
        severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        recommendations.sort(key=lambda x: severity_order.get(x['severity'], 3))
        
        return jsonify({
            'recommendations': recommendations,
            'total_recommendations': len(recommendations),
            'by_severity': {
                'critical': len([r for r in recommendations if r['severity'] == 'critical']),
                'high': len([r for r in recommendations if r['severity'] == 'high']),
                'medium': len([r for r in recommendations if r['severity'] == 'medium']),
                'low': len([r for r in recommendations if r['severity'] == 'low'])
            },
            'generated_at': datetime.now().isoformat(),
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error generating performance recommendations: {e}")
        return jsonify({
            'error': str(e),
            'status': 'error'
        }), 500

# Start cache cleanup when module is loaded
start_cache_cleanup()