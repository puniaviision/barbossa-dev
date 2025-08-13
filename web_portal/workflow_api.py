#!/usr/bin/env python3
"""
Workflow API Module for Barbossa Web Portal
Provides REST API endpoints for workflow management
"""

import json
import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from flask import Blueprint, jsonify, request, session
import threading
import uuid

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

try:
    from workflow_automation import WorkflowEngine, Workflow, WorkflowStatus, TriggerType
    WORKFLOW_ENGINE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Could not import workflow engine: {e}")
    WORKFLOW_ENGINE_AVAILABLE = False

# Create workflow API blueprint
workflow_api = Blueprint('workflow_api', __name__, url_prefix='/api/workflows')

# Global workflow engine instance
workflow_engine = None
workflow_engine_lock = threading.Lock()

def get_workflow_engine():
    """Get or create workflow engine instance"""
    global workflow_engine
    
    if not WORKFLOW_ENGINE_AVAILABLE:
        return None
    
    with workflow_engine_lock:
        if workflow_engine is None:
            work_dir = Path.home() / 'barbossa-engineer'
            workflow_engine = WorkflowEngine(work_dir)
        return workflow_engine

@workflow_api.route('/', methods=['GET', 'POST'])
def list_or_create_workflows():
    """List all workflows or create a new one"""
    if request.method == 'GET':
        return list_workflows()
    else:  # POST
        return create_workflow()

def list_workflows():
    """List all workflows"""
    try:
        engine = get_workflow_engine()
        if not engine:
            return jsonify({
                'error': 'Workflow engine not available',
                'workflows': []
            }), 503
        
        workflows = engine.list_workflows()
        
        return jsonify({
            'workflows': workflows,
            'total': len(workflows),
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error listing workflows: {e}")
        return jsonify({
            'error': str(e),
            'workflows': []
        }), 500

@workflow_api.route('/templates', methods=['GET'])
def list_workflow_templates():
    """List available workflow templates"""
    try:
        templates_dir = Path.home() / 'barbossa-engineer' / 'workflow_templates'
        templates = []
        
        if templates_dir.exists():
            for template_file in templates_dir.glob('*.yaml'):
                try:
                    import yaml
                    with open(template_file, 'r') as f:
                        template_config = yaml.safe_load(f)
                    
                    templates.append({
                        'name': template_file.stem,
                        'filename': template_file.name,
                        'title': template_config.get('name', template_file.stem),
                        'description': template_config.get('description', ''),
                        'version': template_config.get('version', '1.0'),
                        'trigger_type': template_config.get('trigger_type', 'manual'),
                        'task_count': len(template_config.get('tasks', [])),
                        'variables': list(template_config.get('variables', {}).keys())
                    })
                except Exception as e:
                    logging.warning(f"Error reading template {template_file}: {e}")
        
        return jsonify({
            'templates': templates,
            'total': len(templates),
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error listing workflow templates: {e}")
        return jsonify({
            'error': str(e),
            'templates': []
        }), 500

@workflow_api.route('/templates/<template_name>', methods=['GET'])
def get_workflow_template(template_name):
    """Get workflow template details"""
    try:
        template_path = Path.home() / 'barbossa-engineer' / 'workflow_templates' / f"{template_name}.yaml"
        
        if not template_path.exists():
            return jsonify({
                'error': f'Template {template_name} not found'
            }), 404
        
        import yaml
        with open(template_path, 'r') as f:
            template_config = yaml.safe_load(f)
        
        return jsonify({
            'template': template_config,
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting workflow template {template_name}: {e}")
        return jsonify({
            'error': str(e)
        }), 500

@workflow_api.route('/create', methods=['POST'])
def create_workflow_endpoint():
    """Create workflow endpoint wrapper"""
    return create_workflow()

def create_workflow():
    """Create a new workflow from template or configuration"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'error': 'No data provided'
            }), 400
        
        engine = get_workflow_engine()
        if not engine:
            return jsonify({
                'error': 'Workflow engine not available'
            }), 503
        
        # Create workflow from template
        if 'template_name' in data:
            template_name = data['template_name']
            variables = data.get('variables', {})
            
            try:
                workflow = engine.create_workflow_from_template(template_name, variables)
            except FileNotFoundError:
                return jsonify({
                    'error': f'Template {template_name} not found'
                }), 404
        
        # Create workflow from configuration
        elif 'config' in data:
            config = data['config']
            workflow = engine.create_workflow_from_config(config)
        
        else:
            return jsonify({
                'error': 'Either template_name or config must be provided'
            }), 400
        
        return jsonify({
            'workflow': workflow.to_dict(),
            'status': 'success',
            'message': f'Workflow {workflow.name} created successfully'
        })
    
    except Exception as e:
        logging.error(f"Error creating workflow: {e}")
        return jsonify({
            'error': str(e)
        }), 500

@workflow_api.route('/<workflow_id>', methods=['GET'])
def get_workflow(workflow_id):
    """Get workflow details"""
    try:
        engine = get_workflow_engine()
        if not engine:
            return jsonify({
                'error': 'Workflow engine not available'
            }), 503
        
        # Try to get workflow status
        workflow_data = engine.get_workflow_status(workflow_id)
        
        if not workflow_data:
            # Try to load from saved workflows
            workflows = engine.list_workflows()
            workflow_data = next((w for w in workflows if w.get('id') == workflow_id or w.get('workflow_id') == workflow_id), None)
        
        if not workflow_data:
            return jsonify({
                'error': f'Workflow {workflow_id} not found'
            }), 404
        
        return jsonify({
            'workflow': workflow_data,
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting workflow {workflow_id}: {e}")
        return jsonify({
            'error': str(e)
        }), 500

@workflow_api.route('/<workflow_id>', methods=['DELETE'])
def delete_workflow(workflow_id):
    """Delete a workflow"""
    try:
        engine = get_workflow_engine()
        if not engine:
            return jsonify({
                'error': 'Workflow engine not available'
            }), 503
        
        # Check if workflow exists
        workflow_data = engine.get_workflow_status(workflow_id)
        
        if workflow_data and workflow_data.get('status') == 'running':
            return jsonify({
                'error': 'Cannot delete running workflow. Please cancel it first.'
            }), 400
        
        # Delete workflow file if it exists
        workflow_dir = Path.home() / 'barbossa-engineer' / 'workflows'
        workflow_file = workflow_dir / f'{workflow_id}.yaml'
        
        if workflow_file.exists():
            workflow_file.unlink()
            return jsonify({
                'success': True,
                'message': f'Workflow {workflow_id} deleted successfully'
            })
        else:
            return jsonify({
                'error': f'Workflow {workflow_id} not found'
            }), 404
    
    except Exception as e:
        logging.error(f"Error deleting workflow {workflow_id}: {e}")
        return jsonify({
            'error': str(e)
        }), 500

@workflow_api.route('/<workflow_id>/run', methods=['POST'])
def run_workflow(workflow_id):
    """Run a workflow (alias for execute)"""
    return execute_workflow(workflow_id)

@workflow_api.route('/<workflow_id>/execute', methods=['POST'])
def execute_workflow(workflow_id):
    """Execute a workflow"""
    try:
        engine = get_workflow_engine()
        if not engine:
            return jsonify({
                'error': 'Workflow engine not available'
            }), 503
        
        # Get workflow from database or running workflows
        workflow_data = engine.get_workflow_status(workflow_id)
        if not workflow_data:
            return jsonify({
                'error': f'Workflow {workflow_id} not found'
            }), 404
        
        # Get execution parameters
        data = request.get_json() or {}
        trigger_type = TriggerType(data.get('trigger_type', 'manual'))
        
        # Create workflow object for execution
        workflow = Workflow(
            workflow_id=workflow_data['workflow_id'],
            name=workflow_data['name'],
            description=workflow_data['description'],
            config=workflow_data.get('config', {})
        )
        
        # Execute workflow asynchronously
        def execute_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(engine.execute_workflow(workflow, trigger_type))
            loop.close()
        
        thread = threading.Thread(target=execute_async, daemon=True)
        thread.start()
        
        return jsonify({
            'status': 'success',
            'message': f'Workflow {workflow.name} execution started',
            'workflow_id': workflow_id,
            'execution_status': 'running'
        })
    
    except Exception as e:
        logging.error(f"Error executing workflow {workflow_id}: {e}")
        return jsonify({
            'error': str(e)
        }), 500

@workflow_api.route('/<workflow_id>/status', methods=['GET'])
def get_workflow_status(workflow_id):
    """Get workflow execution status"""
    try:
        engine = get_workflow_engine()
        if not engine:
            return jsonify({
                'error': 'Workflow engine not available'
            }), 503
        
        workflow_status = engine.get_workflow_status(workflow_id)
        if not workflow_status:
            return jsonify({
                'error': f'Workflow {workflow_id} not found'
            }), 404
        
        return jsonify({
            'workflow': workflow_status,
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting workflow status {workflow_id}: {e}")
        return jsonify({
            'error': str(e)
        }), 500

@workflow_api.route('/<workflow_id>/cancel', methods=['POST'])
def cancel_workflow(workflow_id):
    """Cancel a running workflow"""
    try:
        engine = get_workflow_engine()
        if not engine:
            return jsonify({
                'error': 'Workflow engine not available'
            }), 503
        
        # Check if workflow is running
        if workflow_id in engine.running_workflows:
            workflow = engine.running_workflows[workflow_id]
            workflow.status = WorkflowStatus.CANCELLED
            workflow.completed_at = datetime.now()
            workflow.add_log('INFO', 'Workflow cancelled by user')
            
            # Remove from running workflows
            del engine.running_workflows[workflow_id]
            
            return jsonify({
                'status': 'success',
                'message': f'Workflow {workflow_id} cancelled',
                'workflow_status': 'cancelled'
            })
        else:
            return jsonify({
                'error': f'Workflow {workflow_id} is not currently running'
            }), 400
    
    except Exception as e:
        logging.error(f"Error cancelling workflow {workflow_id}: {e}")
        return jsonify({
            'error': str(e)
        }), 500

@workflow_api.route('/running', methods=['GET'])
def get_running_workflows():
    """Get currently running workflows"""
    try:
        engine = get_workflow_engine()
        if not engine:
            return jsonify({
                'error': 'Workflow engine not available',
                'workflows': []
            }), 503
        
        running_workflows = []
        for workflow_id, workflow in engine.running_workflows.items():
            running_workflows.append(workflow.to_dict())
        
        return jsonify({
            'workflows': running_workflows,
            'total': len(running_workflows),
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting running workflows: {e}")
        return jsonify({
            'error': str(e),
            'workflows': []
        }), 500

@workflow_api.route('/history', methods=['GET'])
def get_workflow_history():
    """Get workflow execution history"""
    try:
        engine = get_workflow_engine()
        if not engine:
            return jsonify({
                'error': 'Workflow engine not available',
                'executions': []
            }), 503
        
        # Get query parameters
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        workflow_id = request.args.get('workflow_id')
        status = request.args.get('status')
        
        # Query database for execution history
        import sqlite3
        with sqlite3.connect(engine.db_path) as conn:
            cursor = conn.cursor()
            
            # Build query
            query = '''
                SELECT we.*, w.name as workflow_name 
                FROM workflow_executions we
                LEFT JOIN workflows w ON we.workflow_id = w.id
                WHERE 1=1
            '''
            params = []
            
            if workflow_id:
                query += ' AND we.workflow_id = ?'
                params.append(workflow_id)
            
            if status:
                query += ' AND we.status = ?'
                params.append(status)
            
            query += ' ORDER BY we.started_at DESC LIMIT ? OFFSET ?'
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            executions = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            # Parse JSON results
            for execution in executions:
                if execution.get('results'):
                    try:
                        execution['results'] = json.loads(execution['results'])
                    except:
                        pass
        
        return jsonify({
            'executions': executions,
            'total': len(executions),
            'limit': limit,
            'offset': offset,
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting workflow history: {e}")
        return jsonify({
            'error': str(e),
            'executions': []
        }), 500

@workflow_api.route('/stats', methods=['GET'])
def get_workflow_stats():
    """Get workflow statistics"""
    try:
        engine = get_workflow_engine()
        if not engine:
            return jsonify({
                'error': 'Workflow engine not available'
            }), 503
        
        # Get statistics from database
        import sqlite3
        with sqlite3.connect(engine.db_path) as conn:
            cursor = conn.cursor()
            
            # Total workflows
            cursor.execute('SELECT COUNT(*) FROM workflows')
            total_workflows = cursor.fetchone()[0]
            
            # Total executions
            cursor.execute('SELECT COUNT(*) FROM workflow_executions')
            total_executions = cursor.fetchone()[0]
            
            # Executions by status
            cursor.execute('''
                SELECT status, COUNT(*) as count 
                FROM workflow_executions 
                GROUP BY status
            ''')
            status_counts = dict(cursor.fetchall())
            
            # Executions by day (last 30 days)
            cursor.execute('''
                SELECT DATE(started_at) as date, COUNT(*) as count
                FROM workflow_executions
                WHERE started_at > datetime('now', '-30 days')
                GROUP BY DATE(started_at)
                ORDER BY date
            ''')
            daily_executions = [{'date': row[0], 'count': row[1]} for row in cursor.fetchall()]
            
            # Most executed workflows
            cursor.execute('''
                SELECT w.name, COUNT(*) as execution_count
                FROM workflow_executions we
                LEFT JOIN workflows w ON we.workflow_id = w.id
                GROUP BY w.name
                ORDER BY execution_count DESC
                LIMIT 10
            ''')
            top_workflows = [{'name': row[0], 'executions': row[1]} for row in cursor.fetchall()]
        
        # Currently running
        running_count = len(engine.running_workflows) if hasattr(engine, 'running_workflows') else 0
        
        stats = {
            'total_workflows': total_workflows,
            'total_executions': total_executions,
            'currently_running': running_count,
            'status_distribution': status_counts,
            'daily_executions': daily_executions,
            'top_workflows': top_workflows,
            'success_rate': (status_counts.get('completed', 0) / max(total_executions, 1)) * 100
        }
        
        return jsonify({
            'stats': stats,
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting workflow stats: {e}")
        return jsonify({
            'error': str(e)
        }), 500

@workflow_api.route('/scheduler/status', methods=['GET'])
def get_scheduler_status():
    """Get workflow scheduler status"""
    try:
        engine = get_workflow_engine()
        if not engine:
            return jsonify({
                'error': 'Workflow engine not available'
            }), 503
        
        scheduler_status = {
            'running': getattr(engine, 'running', False),
            'worker_task_active': getattr(engine, 'worker_task', None) is not None,
            'scheduled_workflows': 0  # This would need to be implemented
        }
        
        return jsonify({
            'scheduler': scheduler_status,
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error getting scheduler status: {e}")
        return jsonify({
            'error': str(e)
        }), 500

@workflow_api.route('/scheduler/start', methods=['POST'])
def start_scheduler():
    """Start the workflow scheduler"""
    try:
        engine = get_workflow_engine()
        if not engine:
            return jsonify({
                'error': 'Workflow engine not available'
            }), 503
        
        if not getattr(engine, 'running', False):
            engine.start_scheduler()
            return jsonify({
                'status': 'success',
                'message': 'Workflow scheduler started'
            })
        else:
            return jsonify({
                'status': 'info',
                'message': 'Workflow scheduler is already running'
            })
    
    except Exception as e:
        logging.error(f"Error starting scheduler: {e}")
        return jsonify({
            'error': str(e)
        }), 500

@workflow_api.route('/scheduler/stop', methods=['POST'])
def stop_scheduler():
    """Stop the workflow scheduler"""
    try:
        engine = get_workflow_engine()
        if not engine:
            return jsonify({
                'error': 'Workflow engine not available'
            }), 503
        
        if getattr(engine, 'running', False):
            engine.stop_scheduler()
            return jsonify({
                'status': 'success',
                'message': 'Workflow scheduler stopped'
            })
        else:
            return jsonify({
                'status': 'info',
                'message': 'Workflow scheduler is not running'
            })
    
    except Exception as e:
        logging.error(f"Error stopping scheduler: {e}")
        return jsonify({
            'error': str(e)
        }), 500

@workflow_api.route('/validate', methods=['POST'])
def validate_workflow():
    """Validate workflow configuration"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'error': 'No workflow configuration provided'
            }), 400
        
        config = data.get('config')
        if not config:
            return jsonify({
                'error': 'No config in request data'
            }), 400
        
        # Basic validation
        errors = []
        warnings = []
        
        # Check required fields
        if 'name' not in config:
            errors.append('Workflow name is required')
        
        if 'tasks' not in config or not config['tasks']:
            errors.append('At least one task is required')
        
        # Validate tasks
        task_ids = set()
        for i, task in enumerate(config.get('tasks', [])):
            task_errors = []
            
            if 'id' not in task:
                task_errors.append(f'Task {i}: ID is required')
            elif task['id'] in task_ids:
                task_errors.append(f'Task {i}: Duplicate task ID "{task["id"]}"')
            else:
                task_ids.add(task['id'])
            
            if 'name' not in task:
                task_errors.append(f'Task {i}: Name is required')
            
            if 'type' not in task:
                task_errors.append(f'Task {i}: Type is required')
            
            # Check dependencies
            for dep_id in task.get('dependencies', []):
                if dep_id not in task_ids:
                    warnings.append(f'Task {task.get("id", i)}: Dependency "{dep_id}" not found')
            
            errors.extend(task_errors)
        
        validation_result = {
            'valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'task_count': len(config.get('tasks', [])),
            'has_schedule': 'schedule' in config,
            'trigger_type': config.get('trigger_type', 'manual')
        }
        
        return jsonify({
            'validation': validation_result,
            'status': 'success'
        })
    
    except Exception as e:
        logging.error(f"Error validating workflow: {e}")
        return jsonify({
            'error': str(e)
        }), 500

# Error handlers
@workflow_api.errorhandler(404)
def not_found(error):
    return jsonify({
        'error': 'Endpoint not found',
        'status': 'error'
    }), 404

@workflow_api.errorhandler(500)
def internal_error(error):
    return jsonify({
        'error': 'Internal server error',
        'status': 'error'
    }), 500