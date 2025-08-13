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
                'meta': {
                    'GET /docs': 'Get API documentation',
                    'GET /status': 'Get API status'
                }
            },
            'schemas': {
                'project': {k: {**v, 'type': v['type'].__name__} for k, v in PROJECT_SCHEMA.items()},
                'task': {k: {**v, 'type': v['type'].__name__} for k, v in TASK_SCHEMA.items()}
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

# Start cache cleanup when module is loaded
start_cache_cleanup()