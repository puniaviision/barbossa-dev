#!/usr/bin/env python3
"""
Barbossa Custom Prompt API
Handles custom prompt submission and session management for the Barbossa engineer
"""

import json
import logging
import os
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import psutil

class BarbossaPromptManager:
    """Manages custom Barbossa prompt sessions"""
    
    def __init__(self, barbossa_dir: Path, logs_dir: Path):
        self.barbossa_dir = barbossa_dir
        self.logs_dir = logs_dir
        self.sessions_file = barbossa_dir / 'sessions.json'
        self.sessions = self._load_sessions()
        self.logger = logging.getLogger(__name__)
        
    def _load_sessions(self) -> Dict:
        """Load existing sessions from file"""
        if self.sessions_file.exists():
            try:
                with open(self.sessions_file, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_sessions(self):
        """Save sessions to file"""
        with open(self.sessions_file, 'w') as f:
            json.dump(self.sessions, f, indent=2)
    
    def create_custom_session(self, prompt: str, repository: str = None, task_type: str = "custom") -> Dict:
        """
        Create a new Barbossa session with a custom prompt
        
        Args:
            prompt: The custom prompt for Barbossa
            repository: Optional repository to work on
            task_type: Type of task (custom, feature, bugfix, refactor, etc.)
        
        Returns:
            Session information including ID and status
        """
        # Check if Barbossa is already running
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if 'barbossa.py' in str(proc.info.get('cmdline', [])):
                    return {
                        'success': False,
                        'error': 'Barbossa is already running',
                        'pid': proc.info['pid']
                    }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Generate session ID
        session_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        
        # Create enhanced prompt
        enhanced_prompt = self._create_enhanced_prompt(prompt, repository, task_type)
        
        # Save prompt to file
        prompt_file = self.barbossa_dir / f'custom_prompt_{session_id}.txt'
        with open(prompt_file, 'w') as f:
            f.write(enhanced_prompt)
        
        # Create output log file
        output_file = self.logs_dir / f"claude_custom_{session_id}_{timestamp}.log"
        
        # Execute Claude with the custom prompt
        cmd = f"claude --dangerously-skip-permissions --model sonnet < {prompt_file} > {output_file} 2>&1"
        
        # Start the process in background
        process = subprocess.Popen(
            cmd,
            shell=True,
            cwd=self.barbossa_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Store session information
        session = {
            'id': session_id,
            'prompt': prompt,
            'repository': repository,
            'task_type': task_type,
            'created': datetime.now().isoformat(),
            'status': 'running',
            'pid': process.pid,
            'prompt_file': str(prompt_file),
            'output_file': str(output_file),
            'completed': False
        }
        
        self.sessions[session_id] = session
        self._save_sessions()
        
        return {
            'success': True,
            'session_id': session_id,
            'output_file': str(output_file),
            'message': f'Custom Barbossa session {session_id} started'
        }
    
    def _create_enhanced_prompt(self, custom_prompt: str, repository: str = None, task_type: str = "custom") -> str:
        """Create an enhanced prompt with proper context and safety checks"""
        
        base_prompt = f"""You are Barbossa, an autonomous software engineer working on the homeserver.

TASK TYPE: {task_type.upper()}
TIMESTAMP: {datetime.now().isoformat()}

CRITICAL SECURITY REQUIREMENTS:
- You MUST NOT access any zkp2p or ZKP2P organization repositories
- Only work with allowed repositories (ADWilkinson personal projects)
- All repository operations must pass security validation

"""
        
        if repository:
            # Validate repository is allowed
            if 'zkp2p' in repository.lower():
                return "ERROR: Access to ZKP2P repositories is strictly forbidden."
            
            base_prompt += f"""
TARGET REPOSITORY: {repository}
Please clone or navigate to this repository and work within it.

"""
        
        base_prompt += f"""
CUSTOM TASK DESCRIPTION:
{custom_prompt}

REQUIREMENTS:
1. Complete the task as described above
2. Follow all coding best practices
3. Create tests if applicable
4. Document your changes
5. Create a detailed summary of work completed

Please proceed with the task."""
        
        return base_prompt
    
    def get_session_status(self, session_id: str) -> Dict:
        """Get the status of a specific session"""
        if session_id not in self.sessions:
            return {'success': False, 'error': 'Session not found'}
        
        session = self.sessions[session_id]
        
        # Check if process is still running
        if not session['completed']:
            try:
                # Check both the shell process and any child claude processes
                proc = psutil.Process(session['pid'])
                is_running = proc.is_running()
                
                # Also check for child processes (claude might be a child)
                children = proc.children(recursive=True)
                claude_running = any('claude' in ' '.join(p.cmdline()).lower() for p in children)
                
                if is_running or claude_running:
                    session['status'] = 'running'
                else:
                    session['status'] = 'completed'
                    session['completed'] = True
                    self._save_sessions()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                session['status'] = 'completed'
                session['completed'] = True
                self._save_sessions()
        
        # Get output if available
        output = ""
        output_file = Path(session['output_file'])
        if output_file.exists():
            try:
                with open(output_file, 'r') as f:
                    output = f.read()
            except:
                output = "Error reading output file"
        
        return {
            'success': True,
            'session': session,
            'output': output
        }
    
    def list_sessions(self, limit: int = 10) -> List[Dict]:
        """List recent sessions"""
        # Update session statuses
        for session_id in list(self.sessions.keys()):
            if not self.sessions[session_id]['completed']:
                self.get_session_status(session_id)
        
        # Sort by creation time and return latest
        sorted_sessions = sorted(
            self.sessions.values(),
            key=lambda x: x['created'],
            reverse=True
        )
        
        return sorted_sessions[:limit]
    
    def terminate_session(self, session_id: str) -> Dict:
        """Terminate a running session"""
        if session_id not in self.sessions:
            return {'success': False, 'error': 'Session not found'}
        
        session = self.sessions[session_id]
        
        if session['completed']:
            return {'success': False, 'error': 'Session already completed'}
        
        try:
            proc = psutil.Process(session['pid'])
            proc.terminate()
            time.sleep(1)
            
            if proc.is_running():
                proc.kill()
            
            session['status'] = 'terminated'
            session['completed'] = True
            self._save_sessions()
            
            return {'success': True, 'message': f'Session {session_id} terminated'}
        except psutil.NoSuchProcess:
            session['status'] = 'completed'
            session['completed'] = True
            self._save_sessions()
            return {'success': True, 'message': 'Session already finished'}
        except Exception as e:
            return {'success': False, 'error': str(e)}
    
    def get_session_output_stream(self, session_id: str, offset: int = 0) -> Dict:
        """Get streaming output from a session (for real-time updates)"""
        if session_id not in self.sessions:
            return {'success': False, 'error': 'Session not found'}
        
        session = self.sessions[session_id]
        output_file = Path(session['output_file'])
        
        if not output_file.exists():
            return {'success': True, 'output': '', 'offset': 0, 'completed': False}
        
        try:
            with open(output_file, 'r') as f:
                f.seek(offset)
                new_content = f.read()
                new_offset = f.tell()
            
            # Check if session is completed
            completed = session['completed']
            if not completed:
                try:
                    proc = psutil.Process(session['pid'])
                    completed = not proc.is_running()
                except:
                    completed = True
            
            return {
                'success': True,
                'output': new_content,
                'offset': new_offset,
                'completed': completed
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}