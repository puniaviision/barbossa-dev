#!/usr/bin/env python3
"""
Development Tools API Module for Barbossa Web Portal
Specialized endpoints for development workflow automation, code analysis, and project management
"""

import json
import os
import sys
import logging
import subprocess
import threading
import time
import uuid
# Optional git dependency
try:
    import git
    GIT_AVAILABLE = True
except ImportError:
    GIT_AVAILABLE = False
    # Simple git replacement for basic info
    class git:
        class Repo:
            def __init__(self, path):
                self.path = path
            @property
            def active_branch(self):
                class Branch:
                    name = "main"
                return Branch()
            @property
            def head(self):
                class Head:
                    class Commit:
                        hexsha = "abcd1234"
                        message = "Latest commit"
                        author = "Unknown"
                        committed_datetime = "2024-01-01T00:00:00"
                    commit = Commit()
                return Head()
            def is_dirty(self):
                return False
            @property
            def remotes(self):
                return []
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from flask import Blueprint, jsonify, request, Response
from werkzeug.exceptions import BadRequest, NotFound
import hashlib
import re
from collections import defaultdict
import yaml

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent))

try:
    from security_guard import RepositorySecurityGuard
    SECURITY_GUARD_AVAILABLE = True
except ImportError:
    SECURITY_GUARD_AVAILABLE = False

# Create development tools API blueprint
devtools_api = Blueprint('devtools_api', __name__, url_prefix='/api/devtools')

# Global development state
active_projects = {}
build_history = {}
test_results = {}
code_analysis_cache = {}
development_lock = threading.Lock()

# Development configuration
DEVTOOLS_CONFIG = {
    'max_concurrent_builds': 3,
    'build_timeout_minutes': 30,
    'test_timeout_minutes': 15,
    'code_analysis_cache_ttl': 3600,  # 1 hour
    'allowed_project_types': ['node', 'python', 'rust', 'go', 'typescript'],
    'supported_languages': ['.js', '.ts', '.py', '.rs', '.go', '.json', '.yaml', '.md']
}

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def get_security_guard():
    """Get security guard instance"""
    if not SECURITY_GUARD_AVAILABLE:
        return None
    try:
        return RepositorySecurityGuard()
    except Exception:
        return None

def detect_project_type(project_path: Path) -> str:
    """Detect project type based on files present"""
    if (project_path / 'package.json').exists():
        return 'node'
    elif (project_path / 'requirements.txt').exists() or (project_path / 'setup.py').exists():
        return 'python'
    elif (project_path / 'Cargo.toml').exists():
        return 'rust'
    elif (project_path / 'go.mod').exists():
        return 'go'
    elif (project_path / 'tsconfig.json').exists():
        return 'typescript'
    else:
        return 'unknown'

def validate_project_path(project_path: str) -> Tuple[bool, str]:
    """Validate project path for security"""
    path = Path(project_path).resolve()
    
    # Must be within allowed directories
    allowed_dirs = [
        Path.home() / 'barbossa-engineer' / 'projects',
        Path.home() / 'projects'
    ]
    
    for allowed_dir in allowed_dirs:
        try:
            path.relative_to(allowed_dir.resolve())
            return True, "Valid project path"
        except ValueError:
            continue
    
    return False, "Project path not in allowed directories"

def run_command_safely(command: List[str], cwd: str, timeout: int = 300) -> Tuple[bool, str, str]:
    """Run command safely with timeout and logging"""
    try:
        logging.info(f"Running command: {' '.join(command)} in {cwd}")
        
        result = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        return result.returncode == 0, result.stdout, result.stderr
        
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout} seconds"
    except Exception as e:
        return False, "", str(e)

# ============================================================================
# PROJECT MANAGEMENT ENDPOINTS
# ============================================================================

@devtools_api.route('/projects', methods=['GET', 'POST'])
def projects():
    """Manage development projects"""
    if request.method == 'GET':
        return get_projects()
    elif request.method == 'POST':
        return analyze_project()

def get_projects():
    """Get all development projects"""
    try:
        projects_dir = Path.home() / 'barbossa-engineer' / 'projects'
        projects = []
        
        if not projects_dir.exists():
            return jsonify({'projects': [], 'total': 0})
        
        for project_dir in projects_dir.iterdir():
            if project_dir.is_dir() and not project_dir.name.startswith('.'):
                project_info = analyze_project_structure(project_dir)
                projects.append(project_info)
        
        # Sort by last modified
        projects.sort(key=lambda x: x.get('last_modified', ''), reverse=True)
        
        return jsonify({
            'projects': projects,
            'total': len(projects),
            'project_types': list(set(p.get('type', 'unknown') for p in projects))
        })
        
    except Exception as e:
        logging.error(f"Failed to get projects: {e}")
        return jsonify({'error': 'Failed to get projects'}), 500

def analyze_project():
    """Analyze a specific project"""
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    project_path = data.get('project_path')
    
    if not project_path:
        return jsonify({'error': 'project_path is required'}), 400
    
    # Validate path
    valid, message = validate_project_path(project_path)
    if not valid:
        return jsonify({'error': message}), 403
    
    try:
        path = Path(project_path)
        if not path.exists():
            return jsonify({'error': 'Project path does not exist'}), 404
        
        analysis = analyze_project_structure(path)
        return jsonify(analysis)
        
    except Exception as e:
        logging.error(f"Failed to analyze project: {e}")
        return jsonify({'error': 'Failed to analyze project'}), 500

def analyze_project_structure(project_path: Path) -> Dict:
    """Analyze project structure and metadata"""
    analysis = {
        'name': project_path.name,
        'path': str(project_path),
        'type': detect_project_type(project_path),
        'last_modified': datetime.fromtimestamp(project_path.stat().st_mtime).isoformat(),
        'size_bytes': sum(f.stat().st_size for f in project_path.rglob('*') if f.is_file()),
        'file_count': len(list(project_path.rglob('*'))),
        'languages': [],
        'dependencies': {},
        'scripts': {},
        'git_info': {},
        'health_score': 0
    }
    
    # Analyze file types
    language_counts = defaultdict(int)
    for file_path in project_path.rglob('*'):
        if file_path.is_file():
            suffix = file_path.suffix.lower()
            if suffix in DEVTOOLS_CONFIG['supported_languages']:
                language_counts[suffix] += 1
    
    analysis['languages'] = dict(language_counts)
    
    # Get git information
    try:
        if (project_path / '.git').exists():
            repo = git.Repo(project_path)
            analysis['git_info'] = {
                'branch': repo.active_branch.name,
                'last_commit': {
                    'hash': repo.head.commit.hexsha[:8],
                    'message': repo.head.commit.message.strip(),
                    'author': str(repo.head.commit.author),
                    'date': repo.head.commit.committed_datetime.isoformat()
                },
                'is_dirty': repo.is_dirty(),
                'remote_url': next(iter(repo.remotes.origin.urls), '') if repo.remotes else ''
            }
    except Exception as e:
        logging.warning(f"Failed to get git info for {project_path}: {e}")
    
    # Analyze dependencies and scripts based on project type
    if analysis['type'] == 'node':
        analyze_node_project(project_path, analysis)
    elif analysis['type'] == 'python':
        analyze_python_project(project_path, analysis)
    elif analysis['type'] == 'rust':
        analyze_rust_project(project_path, analysis)
    elif analysis['type'] == 'go':
        analyze_go_project(project_path, analysis)
    
    # Calculate health score
    analysis['health_score'] = calculate_project_health_score(analysis)
    
    return analysis

def analyze_node_project(project_path: Path, analysis: Dict):
    """Analyze Node.js project specifics"""
    package_json_path = project_path / 'package.json'
    if package_json_path.exists():
        try:
            with open(package_json_path, 'r') as f:
                package_data = json.load(f)
            
            analysis['dependencies'] = {
                'production': len(package_data.get('dependencies', {})),
                'development': len(package_data.get('devDependencies', {})),
                'peer': len(package_data.get('peerDependencies', {}))
            }
            
            analysis['scripts'] = package_data.get('scripts', {})
            analysis['version'] = package_data.get('version', 'unknown')
            analysis['description'] = package_data.get('description', '')
            
        except Exception as e:
            logging.warning(f"Failed to parse package.json: {e}")

def analyze_python_project(project_path: Path, analysis: Dict):
    """Analyze Python project specifics"""
    requirements_path = project_path / 'requirements.txt'
    if requirements_path.exists():
        try:
            with open(requirements_path, 'r') as f:
                requirements = f.readlines()
            
            analysis['dependencies'] = {
                'production': len([line for line in requirements if line.strip() and not line.startswith('#')])
            }
        except Exception as e:
            logging.warning(f"Failed to parse requirements.txt: {e}")
    
    # Check for common Python files
    if (project_path / 'setup.py').exists():
        analysis['has_setup_py'] = True
    if (project_path / 'pyproject.toml').exists():
        analysis['has_pyproject_toml'] = True

def analyze_rust_project(project_path: Path, analysis: Dict):
    """Analyze Rust project specifics"""
    cargo_toml_path = project_path / 'Cargo.toml'
    if cargo_toml_path.exists():
        try:
            with open(cargo_toml_path, 'r') as f:
                cargo_data = yaml.safe_load(f)
            
            analysis['dependencies'] = {
                'production': len(cargo_data.get('dependencies', {})),
                'build': len(cargo_data.get('build-dependencies', {})),
                'dev': len(cargo_data.get('dev-dependencies', {}))
            }
            
            analysis['version'] = cargo_data.get('package', {}).get('version', 'unknown')
            analysis['description'] = cargo_data.get('package', {}).get('description', '')
            
        except Exception as e:
            logging.warning(f"Failed to parse Cargo.toml: {e}")

def analyze_go_project(project_path: Path, analysis: Dict):
    """Analyze Go project specifics"""
    go_mod_path = project_path / 'go.mod'
    if go_mod_path.exists():
        try:
            with open(go_mod_path, 'r') as f:
                content = f.read()
            
            # Simple parsing of go.mod
            require_section = False
            dep_count = 0
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('require ('):
                    require_section = True
                elif require_section and line == ')':
                    require_section = False
                elif require_section and line and not line.startswith('//'):
                    dep_count += 1
            
            analysis['dependencies'] = {'production': dep_count}
            
        except Exception as e:
            logging.warning(f"Failed to parse go.mod: {e}")

def calculate_project_health_score(analysis: Dict) -> int:
    """Calculate project health score based on various factors"""
    score = 50  # Base score
    
    # Git repository (+10)
    if analysis.get('git_info', {}).get('branch'):
        score += 10
    
    # Clean git status (+5)
    if not analysis.get('git_info', {}).get('is_dirty', True):
        score += 5
    
    # Has dependencies (+5)
    if analysis.get('dependencies'):
        score += 5
    
    # Has scripts/build system (+10)
    if analysis.get('scripts') or analysis.get('type') != 'unknown':
        score += 10
    
    # Recent activity (+10 if modified within last 7 days)
    try:
        last_modified = datetime.fromisoformat(analysis.get('last_modified', ''))
        if datetime.now() - last_modified < timedelta(days=7):
            score += 10
    except:
        pass
    
    # File organization (+10 if has reasonable structure)
    if analysis.get('file_count', 0) > 5:
        score += 10
    
    return min(100, max(0, score))

# ============================================================================
# BUILD AND TEST ENDPOINTS
# ============================================================================

@devtools_api.route('/build', methods=['POST'])
def build_project():
    """Build a project"""
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    project_path = data.get('project_path')
    build_command = data.get('build_command')
    
    if not project_path:
        return jsonify({'error': 'project_path is required'}), 400
    
    # Validate path
    valid, message = validate_project_path(project_path)
    if not valid:
        return jsonify({'error': message}), 403
    
    try:
        build_id = str(uuid.uuid4())
        build_info = {
            'id': build_id,
            'project_path': project_path,
            'status': 'running',
            'started_at': datetime.now().isoformat(),
            'build_command': build_command,
            'logs': []
        }
        
        with development_lock:
            build_history[build_id] = build_info
        
        # Start build in background
        build_thread = threading.Thread(
            target=execute_build,
            args=(build_id, project_path, build_command),
            daemon=True
        )
        build_thread.start()
        
        return jsonify({
            'success': True,
            'build_id': build_id,
            'build_info': build_info
        }), 202
        
    except Exception as e:
        logging.error(f"Failed to start build: {e}")
        return jsonify({'error': 'Failed to start build'}), 500

def execute_build(build_id: str, project_path: str, build_command: Optional[str]):
    """Execute build process"""
    try:
        path = Path(project_path)
        project_type = detect_project_type(path)
        
        # Determine build command if not provided
        if not build_command:
            if project_type == 'node':
                build_command = 'npm run build'
            elif project_type == 'python':
                build_command = 'python setup.py build'
            elif project_type == 'rust':
                build_command = 'cargo build'
            elif project_type == 'go':
                build_command = 'go build'
            else:
                with development_lock:
                    build_history[build_id]['status'] = 'failed'
                    build_history[build_id]['error'] = 'Unknown project type, cannot determine build command'
                return
        
        # Execute build
        command_parts = build_command.split()
        timeout = DEVTOOLS_CONFIG['build_timeout_minutes'] * 60
        
        success, stdout, stderr = run_command_safely(command_parts, project_path, timeout)
        
        # Update build status
        with development_lock:
            build_history[build_id]['status'] = 'success' if success else 'failed'
            build_history[build_id]['completed_at'] = datetime.now().isoformat()
            build_history[build_id]['stdout'] = stdout
            build_history[build_id]['stderr'] = stderr
            
            if not success:
                build_history[build_id]['error'] = stderr or 'Build failed'
        
    except Exception as e:
        with development_lock:
            build_history[build_id]['status'] = 'failed'
            build_history[build_id]['error'] = str(e)
            build_history[build_id]['completed_at'] = datetime.now().isoformat()

@devtools_api.route('/build/<build_id>')
def get_build_status(build_id):
    """Get build status"""
    with development_lock:
        if build_id not in build_history:
            return jsonify({'error': 'Build not found'}), 404
        
        return jsonify(build_history[build_id])

@devtools_api.route('/builds')
def get_build_history():
    """Get build history"""
    with development_lock:
        builds = list(build_history.values())
    
    # Sort by start time, newest first
    builds.sort(key=lambda x: x.get('started_at', ''), reverse=True)
    
    return jsonify({
        'builds': builds[:50],  # Last 50 builds
        'total': len(builds)
    })

@devtools_api.route('/test', methods=['POST'])
def run_tests():
    """Run tests for a project"""
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    project_path = data.get('project_path')
    test_command = data.get('test_command')
    
    if not project_path:
        return jsonify({'error': 'project_path is required'}), 400
    
    # Validate path
    valid, message = validate_project_path(project_path)
    if not valid:
        return jsonify({'error': message}), 403
    
    try:
        test_id = str(uuid.uuid4())
        test_info = {
            'id': test_id,
            'project_path': project_path,
            'status': 'running',
            'started_at': datetime.now().isoformat(),
            'test_command': test_command
        }
        
        with development_lock:
            test_results[test_id] = test_info
        
        # Start tests in background
        test_thread = threading.Thread(
            target=execute_tests,
            args=(test_id, project_path, test_command),
            daemon=True
        )
        test_thread.start()
        
        return jsonify({
            'success': True,
            'test_id': test_id,
            'test_info': test_info
        }), 202
        
    except Exception as e:
        logging.error(f"Failed to start tests: {e}")
        return jsonify({'error': 'Failed to start tests'}), 500

def execute_tests(test_id: str, project_path: str, test_command: Optional[str]):
    """Execute test process"""
    try:
        path = Path(project_path)
        project_type = detect_project_type(path)
        
        # Determine test command if not provided
        if not test_command:
            if project_type == 'node':
                test_command = 'npm test'
            elif project_type == 'python':
                test_command = 'python -m pytest'
            elif project_type == 'rust':
                test_command = 'cargo test'
            elif project_type == 'go':
                test_command = 'go test ./...'
            else:
                with development_lock:
                    test_results[test_id]['status'] = 'failed'
                    test_results[test_id]['error'] = 'Unknown project type, cannot determine test command'
                return
        
        # Execute tests
        command_parts = test_command.split()
        timeout = DEVTOOLS_CONFIG['test_timeout_minutes'] * 60
        
        success, stdout, stderr = run_command_safely(command_parts, project_path, timeout)
        
        # Parse test results
        test_summary = parse_test_output(stdout, stderr, project_type)
        
        # Update test status
        with development_lock:
            test_results[test_id]['status'] = 'success' if success else 'failed'
            test_results[test_id]['completed_at'] = datetime.now().isoformat()
            test_results[test_id]['stdout'] = stdout
            test_results[test_id]['stderr'] = stderr
            test_results[test_id]['summary'] = test_summary
            
            if not success:
                test_results[test_id]['error'] = stderr or 'Tests failed'
        
    except Exception as e:
        with development_lock:
            test_results[test_id]['status'] = 'failed'
            test_results[test_id]['error'] = str(e)
            test_results[test_id]['completed_at'] = datetime.now().isoformat()

def parse_test_output(stdout: str, stderr: str, project_type: str) -> Dict:
    """Parse test output to extract summary information"""
    summary = {
        'total_tests': 0,
        'passed': 0,
        'failed': 0,
        'skipped': 0,
        'coverage': None
    }
    
    try:
        output = stdout + stderr
        
        if project_type == 'node':
            # Parse Jest/Mocha output
            if 'Tests:' in output:
                lines = output.split('\n')
                for line in lines:
                    if 'Tests:' in line:
                        # Extract test counts
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part.isdigit():
                                if 'passed' in line[line.find(part):]:
                                    summary['passed'] = int(part)
                                elif 'failed' in line[line.find(part):]:
                                    summary['failed'] = int(part)
                                elif 'skipped' in line[line.find(part):]:
                                    summary['skipped'] = int(part)
        
        elif project_type == 'python':
            # Parse pytest output
            if 'test session starts' in output:
                lines = output.split('\n')
                for line in lines:
                    if 'passed' in line or 'failed' in line:
                        # Extract test counts from pytest summary
                        numbers = re.findall(r'(\d+) passed|(\d+) failed|(\d+) skipped', line)
                        for match in numbers:
                            if match[0]:  # passed
                                summary['passed'] = int(match[0])
                            elif match[1]:  # failed
                                summary['failed'] = int(match[1])
                            elif match[2]:  # skipped
                                summary['skipped'] = int(match[2])
        
        elif project_type == 'rust':
            # Parse cargo test output
            if 'test result:' in output:
                lines = output.split('\n')
                for line in lines:
                    if 'test result:' in line:
                        # Extract from "test result: ok. 5 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out"
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if part.isdigit():
                                if i < len(parts) - 1:
                                    if parts[i + 1] == 'passed':
                                        summary['passed'] = int(part)
                                    elif parts[i + 1] == 'failed':
                                        summary['failed'] = int(part)
        
        summary['total_tests'] = summary['passed'] + summary['failed'] + summary['skipped']
        
    except Exception as e:
        logging.warning(f"Failed to parse test output: {e}")
    
    return summary

@devtools_api.route('/test/<test_id>')
def get_test_results(test_id):
    """Get test results"""
    with development_lock:
        if test_id not in test_results:
            return jsonify({'error': 'Test not found'}), 404
        
        return jsonify(test_results[test_id])

# ============================================================================
# CODE ANALYSIS ENDPOINTS
# ============================================================================

@devtools_api.route('/analyze/code', methods=['POST'])
def analyze_code():
    """Analyze code quality and structure"""
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    project_path = data.get('project_path')
    
    if not project_path:
        return jsonify({'error': 'project_path is required'}), 400
    
    # Validate path
    valid, message = validate_project_path(project_path)
    if not valid:
        return jsonify({'error': message}), 403
    
    # Check cache
    cache_key = hashlib.md5(project_path.encode()).hexdigest()
    if cache_key in code_analysis_cache:
        cached_time, cached_result = code_analysis_cache[cache_key]
        if time.time() - cached_time < DEVTOOLS_CONFIG['code_analysis_cache_ttl']:
            return jsonify(cached_result)
    
    try:
        path = Path(project_path)
        if not path.exists():
            return jsonify({'error': 'Project path does not exist'}), 404
        
        analysis = perform_code_analysis(path)
        
        # Cache result
        code_analysis_cache[cache_key] = (time.time(), analysis)
        
        return jsonify(analysis)
        
    except Exception as e:
        logging.error(f"Failed to analyze code: {e}")
        return jsonify({'error': 'Failed to analyze code'}), 500

def perform_code_analysis(project_path: Path) -> Dict:
    """Perform comprehensive code analysis"""
    analysis = {
        'project_path': str(project_path),
        'analyzed_at': datetime.now().isoformat(),
        'file_analysis': {},
        'complexity_score': 0,
        'maintainability_score': 0,
        'security_issues': [],
        'recommendations': []
    }
    
    # Analyze files by type
    file_stats = defaultdict(lambda: {'count': 0, 'lines': 0, 'size': 0})
    total_lines = 0
    
    for file_path in project_path.rglob('*'):
        if file_path.is_file() and not any(skip in str(file_path) for skip in ['.git', 'node_modules', '__pycache__', 'target']):
            suffix = file_path.suffix.lower()
            if suffix in DEVTOOLS_CONFIG['supported_languages']:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                        lines = len(content.split('\n'))
                    
                    file_stats[suffix]['count'] += 1
                    file_stats[suffix]['lines'] += lines
                    file_stats[suffix]['size'] += file_path.stat().st_size
                    total_lines += lines
                    
                except Exception:
                    continue
    
    analysis['file_analysis'] = dict(file_stats)
    analysis['total_lines'] = total_lines
    
    # Calculate complexity score (simplified)
    complexity_factors = {
        'large_files': sum(1 for stats in file_stats.values() if stats['lines'] > 500),
        'total_files': sum(stats['count'] for stats in file_stats.values()),
        'average_file_size': total_lines / max(1, sum(stats['count'] for stats in file_stats.values()))
    }
    
    # Simple complexity scoring
    complexity_score = 100
    if complexity_factors['average_file_size'] > 200:
        complexity_score -= 20
    if complexity_factors['large_files'] > 5:
        complexity_score -= 30
    if complexity_factors['total_files'] > 100:
        complexity_score -= 10
    
    analysis['complexity_score'] = max(0, complexity_score)
    
    # Calculate maintainability score
    maintainability_score = 80  # Base score
    
    # Check for common best practices
    if (project_path / 'README.md').exists():
        maintainability_score += 10
    if (project_path / '.gitignore').exists():
        maintainability_score += 5
    
    # Check for testing files
    test_files = list(project_path.rglob('*test*')) + list(project_path.rglob('*spec*'))
    if test_files:
        maintainability_score += 10
    
    analysis['maintainability_score'] = min(100, maintainability_score)
    
    # Security analysis (basic checks)
    security_issues = perform_basic_security_scan(project_path)
    analysis['security_issues'] = security_issues
    
    # Generate recommendations
    recommendations = generate_code_recommendations(analysis, complexity_factors)
    analysis['recommendations'] = recommendations
    
    return analysis

def perform_basic_security_scan(project_path: Path) -> List[Dict]:
    """Perform basic security scanning"""
    issues = []
    
    # Check for common security anti-patterns
    dangerous_patterns = [
        (r'password\s*=\s*["\'][^"\']+["\']', 'Hardcoded password detected'),
        (r'api_key\s*=\s*["\'][^"\']+["\']', 'Hardcoded API key detected'),
        (r'eval\s*\(', 'Use of eval() function detected'),
        (r'exec\s*\(', 'Use of exec() function detected'),
        (r'__import__\s*\(', 'Dynamic import detected'),
    ]
    
    for file_path in project_path.rglob('*'):
        if file_path.is_file() and file_path.suffix.lower() in ['.py', '.js', '.ts']:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                for pattern, description in dangerous_patterns:
                    matches = re.finditer(pattern, content, re.IGNORECASE)
                    for match in matches:
                        line_num = content[:match.start()].count('\n') + 1
                        issues.append({
                            'file': str(file_path.relative_to(project_path)),
                            'line': line_num,
                            'issue': description,
                            'severity': 'high',
                            'code_snippet': match.group(0)
                        })
                        
            except Exception:
                continue
    
    return issues

def generate_code_recommendations(analysis: Dict, complexity_factors: Dict) -> List[str]:
    """Generate code improvement recommendations"""
    recommendations = []
    
    if analysis['complexity_score'] < 70:
        recommendations.append("Consider refactoring large files into smaller, more focused modules")
    
    if analysis['maintainability_score'] < 80:
        recommendations.append("Add comprehensive documentation and README")
        recommendations.append("Implement automated testing")
    
    if complexity_factors['average_file_size'] > 300:
        recommendations.append("Break down large files into smaller components")
    
    if analysis['security_issues']:
        recommendations.append("Address security issues found in code scan")
        recommendations.append("Implement secure coding practices")
    
    if not any('.test.' in str(f) for f in Path(analysis['project_path']).rglob('*')):
        recommendations.append("Add unit tests to improve code reliability")
    
    return recommendations

# ============================================================================
# DEPENDENCY MANAGEMENT ENDPOINTS
# ============================================================================

@devtools_api.route('/dependencies/check', methods=['POST'])
def check_dependencies():
    """Check project dependencies for updates and vulnerabilities"""
    if not request.is_json:
        return jsonify({'error': 'Request must be JSON'}), 400
    
    data = request.get_json()
    project_path = data.get('project_path')
    
    if not project_path:
        return jsonify({'error': 'project_path is required'}), 400
    
    # Validate path
    valid, message = validate_project_path(project_path)
    if not valid:
        return jsonify({'error': message}), 403
    
    try:
        path = Path(project_path)
        project_type = detect_project_type(path)
        
        if project_type == 'node':
            return check_npm_dependencies(path)
        elif project_type == 'python':
            return check_python_dependencies(path)
        elif project_type == 'rust':
            return check_cargo_dependencies(path)
        else:
            return jsonify({'error': f'Dependency checking not supported for {project_type} projects'}), 400
        
    except Exception as e:
        logging.error(f"Failed to check dependencies: {e}")
        return jsonify({'error': 'Failed to check dependencies'}), 500

def check_npm_dependencies(project_path: Path) -> Response:
    """Check npm dependencies"""
    try:
        # Run npm audit
        success, stdout, stderr = run_command_safely(['npm', 'audit', '--json'], str(project_path), 60)
        
        audit_result = {'vulnerabilities': [], 'total_vulnerabilities': 0}
        if success and stdout:
            try:
                audit_data = json.loads(stdout)
                audit_result = {
                    'vulnerabilities': audit_data.get('vulnerabilities', {}),
                    'total_vulnerabilities': audit_data.get('metadata', {}).get('vulnerabilities', {}).get('total', 0)
                }
            except json.JSONDecodeError:
                pass
        
        # Check for outdated packages
        success, stdout, stderr = run_command_safely(['npm', 'outdated', '--json'], str(project_path), 60)
        
        outdated_result = {}
        if success and stdout:
            try:
                outdated_result = json.loads(stdout)
            except json.JSONDecodeError:
                pass
        
        return jsonify({
            'project_type': 'node',
            'security_audit': audit_result,
            'outdated_packages': outdated_result,
            'recommendations': generate_npm_recommendations(audit_result, outdated_result)
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to check npm dependencies: {str(e)}'}), 500

def check_python_dependencies(project_path: Path) -> Response:
    """Check Python dependencies"""
    try:
        # Check for requirements.txt
        requirements_path = project_path / 'requirements.txt'
        if not requirements_path.exists():
            return jsonify({'error': 'requirements.txt not found'}), 404
        
        # Run pip check (if available)
        success, stdout, stderr = run_command_safely(['pip', 'check'], str(project_path), 60)
        
        conflicts = []
        if not success and stderr:
            conflicts = stderr.split('\n')
        
        # Run safety check (if safety is installed)
        success, stdout, stderr = run_command_safely(['safety', 'check', '-r', 'requirements.txt'], str(project_path), 60)
        
        vulnerabilities = []
        if not success and stdout:
            vulnerabilities = stdout.split('\n')
        
        return jsonify({
            'project_type': 'python',
            'dependency_conflicts': conflicts,
            'security_vulnerabilities': vulnerabilities,
            'recommendations': generate_python_recommendations(conflicts, vulnerabilities)
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to check Python dependencies: {str(e)}'}), 500

def check_cargo_dependencies(project_path: Path) -> Response:
    """Check Rust dependencies"""
    try:
        # Run cargo audit (if cargo-audit is installed)
        success, stdout, stderr = run_command_safely(['cargo', 'audit'], str(project_path), 60)
        
        audit_result = {'vulnerabilities': [], 'status': 'unknown'}
        if success:
            audit_result['status'] = 'clean'
        elif 'vulnerabilities found' in stderr:
            audit_result['status'] = 'vulnerabilities_found'
            audit_result['details'] = stderr
        
        # Check for outdated dependencies
        success, stdout, stderr = run_command_safely(['cargo', 'outdated'], str(project_path), 60)
        
        outdated_result = {'packages': [], 'status': 'unknown'}
        if success and stdout:
            outdated_result['status'] = 'checked'
            outdated_result['details'] = stdout
        
        return jsonify({
            'project_type': 'rust',
            'security_audit': audit_result,
            'outdated_check': outdated_result,
            'recommendations': generate_cargo_recommendations(audit_result, outdated_result)
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to check Cargo dependencies: {str(e)}'}), 500

def generate_npm_recommendations(audit_result: Dict, outdated_result: Dict) -> List[str]:
    """Generate recommendations for npm dependencies"""
    recommendations = []
    
    if audit_result.get('total_vulnerabilities', 0) > 0:
        recommendations.append(f"Fix {audit_result['total_vulnerabilities']} security vulnerabilities with 'npm audit fix'")
    
    if outdated_result:
        recommendations.append(f"Update {len(outdated_result)} outdated packages with 'npm update'")
    
    recommendations.append("Run 'npm audit' regularly to check for security issues")
    recommendations.append("Consider using 'npm ci' in production for consistent installs")
    
    return recommendations

def generate_python_recommendations(conflicts: List[str], vulnerabilities: List[str]) -> List[str]:
    """Generate recommendations for Python dependencies"""
    recommendations = []
    
    if conflicts:
        recommendations.append("Resolve dependency conflicts listed above")
    
    if vulnerabilities:
        recommendations.append("Address security vulnerabilities found by safety check")
    
    recommendations.append("Consider using virtual environments for dependency isolation")
    recommendations.append("Pin exact versions in requirements.txt for reproducible builds")
    recommendations.append("Use 'pip-tools' for better dependency management")
    
    return recommendations

def generate_cargo_recommendations(audit_result: Dict, outdated_result: Dict) -> List[str]:
    """Generate recommendations for Cargo dependencies"""
    recommendations = []
    
    if audit_result.get('status') == 'vulnerabilities_found':
        recommendations.append("Address security vulnerabilities found by cargo audit")
    
    if outdated_result.get('status') == 'checked':
        recommendations.append("Consider updating outdated dependencies")
    
    recommendations.append("Install 'cargo-audit' for security vulnerability checking")
    recommendations.append("Install 'cargo-outdated' for dependency update checking")
    recommendations.append("Use 'cargo update' to update dependencies within semver constraints")
    
    return recommendations

# ============================================================================
# DEVELOPMENT WORKFLOW ENDPOINTS
# ============================================================================

@devtools_api.route('/workflow/templates')
def get_workflow_templates():
    """Get development workflow templates"""
    templates = {
        'ci_cd_basic': {
            'name': 'Basic CI/CD Workflow',
            'description': 'Build, test, and deploy workflow',
            'steps': [
                {'name': 'checkout', 'description': 'Checkout source code'},
                {'name': 'dependencies', 'description': 'Install dependencies'},
                {'name': 'build', 'description': 'Build project'},
                {'name': 'test', 'description': 'Run tests'},
                {'name': 'deploy', 'description': 'Deploy to staging'}
            ]
        },
        'code_quality': {
            'name': 'Code Quality Check',
            'description': 'Comprehensive code quality analysis',
            'steps': [
                {'name': 'lint', 'description': 'Run linting tools'},
                {'name': 'format', 'description': 'Check code formatting'},
                {'name': 'security', 'description': 'Security analysis'},
                {'name': 'coverage', 'description': 'Test coverage analysis'}
            ]
        },
        'dependency_update': {
            'name': 'Dependency Update',
            'description': 'Update and audit dependencies',
            'steps': [
                {'name': 'audit', 'description': 'Security audit'},
                {'name': 'outdated', 'description': 'Check outdated packages'},
                {'name': 'update', 'description': 'Update dependencies'},
                {'name': 'test', 'description': 'Run tests after update'}
            ]
        }
    }
    
    return jsonify({'templates': templates})

# ============================================================================
# HEALTH CHECK
# ============================================================================

@devtools_api.route('/health')
def devtools_health():
    """Health check for development tools"""
    try:
        health_status = {
            'status': 'healthy',
            'timestamp': datetime.now().isoformat(),
            'components': {
                'build_system': {
                    'active_builds': len([b for b in build_history.values() if b.get('status') == 'running']),
                    'total_builds': len(build_history),
                    'status': 'healthy'
                },
                'test_system': {
                    'active_tests': len([t for t in test_results.values() if t.get('status') == 'running']),
                    'total_tests': len(test_results),
                    'status': 'healthy'
                },
                'code_analysis': {
                    'cache_size': len(code_analysis_cache),
                    'status': 'healthy'
                }
            }
        }
        
        return jsonify(health_status)
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 503

if __name__ == '__main__':
    print("Development Tools API module loaded successfully")