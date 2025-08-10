#!/usr/bin/env python3
"""
Enhanced Security Module for Barbossa - Advanced Security Features
Provides rate limiting, session management, alerting, and advanced validation
"""

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import smtplib
import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urlparse

import jwt
from cryptography.fernet import Fernet


class SecurityEnhanced:
    """Advanced security features for Barbossa system"""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize enhanced security system"""
        self.config_dir = config_dir or Path(__file__).parent / 'security'
        self.config_dir.mkdir(parents=True, exist_ok=True)
        
        # Security databases
        self.security_db = self.config_dir / 'security.db'
        self.init_security_db()
        
        # Rate limiting storage
        self.rate_limits = defaultdict(list)
        self.failed_attempts = defaultdict(int)
        self.blocked_ips = set()
        
        # Session management
        self.active_sessions = {}
        self.session_timeout = timedelta(hours=2)
        
        # Encryption key for sensitive data
        self.encryption_key = self._get_or_create_encryption_key()
        self.cipher = Fernet(self.encryption_key)
        
        # JWT secret for API tokens
        self.jwt_secret = self._get_or_create_jwt_secret()
        
        # Alert configuration
        self.alert_config = self._load_alert_config()
        
        # Logging
        self.logger = logging.getLogger('security.enhanced')
        
    def init_security_db(self):
        """Initialize security database with required tables"""
        conn = sqlite3.connect(self.security_db)
        cursor = conn.cursor()
        
        # Security events table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS security_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                source_ip TEXT,
                user TEXT,
                details TEXT,
                hash TEXT UNIQUE
            )
        ''')
        
        # Access attempts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS access_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                ip_address TEXT NOT NULL,
                username TEXT,
                success BOOLEAN,
                endpoint TEXT
            )
        ''')
        
        # API tokens table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS api_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token_hash TEXT UNIQUE NOT NULL,
                user TEXT NOT NULL,
                created DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires DATETIME,
                permissions TEXT,
                active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Trusted repositories checksum table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS repository_checksums (
                repository TEXT PRIMARY KEY,
                checksum TEXT NOT NULL,
                last_verified DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def _get_or_create_encryption_key(self) -> bytes:
        """Get or create encryption key for sensitive data"""
        key_file = self.config_dir / '.encryption.key'
        if key_file.exists():
            with open(key_file, 'rb') as f:
                return f.read()
        else:
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
            os.chmod(key_file, 0o600)
            return key
    
    def _get_or_create_jwt_secret(self) -> str:
        """Get or create JWT secret for API tokens"""
        secret_file = self.config_dir / '.jwt.secret'
        if secret_file.exists():
            with open(secret_file, 'r') as f:
                return f.read().strip()
        else:
            secret = secrets.token_hex(32)
            with open(secret_file, 'w') as f:
                f.write(secret)
            os.chmod(secret_file, 0o600)
            return secret
    
    def _load_alert_config(self) -> Dict:
        """Load alert configuration"""
        config_file = self.config_dir / 'alert_config.json'
        if config_file.exists():
            with open(config_file, 'r') as f:
                return json.load(f)
        return {
            'enabled': False,
            'email': None,
            'webhook': None,
            'threshold': 5  # Number of violations before alert
        }
    
    def rate_limit_check(self, identifier: str, limit: int = 10, window: int = 60) -> bool:
        """
        Check if rate limit exceeded for identifier
        
        Args:
            identifier: IP address or user identifier
            limit: Maximum requests allowed
            window: Time window in seconds
            
        Returns:
            True if within limits, False if exceeded
        """
        now = time.time()
        
        # Clean old entries
        self.rate_limits[identifier] = [
            t for t in self.rate_limits[identifier] 
            if now - t < window
        ]
        
        # Check limit
        if len(self.rate_limits[identifier]) >= limit:
            self.log_security_event(
                'rate_limit_exceeded',
                'warning',
                details={'identifier': identifier, 'limit': limit}
            )
            return False
        
        # Add current request
        self.rate_limits[identifier].append(now)
        return True
    
    def check_brute_force(self, ip: str, username: Optional[str] = None) -> bool:
        """
        Check for brute force attempts and block if necessary
        
        Returns:
            True if blocked, False if allowed
        """
        if ip in self.blocked_ips:
            return True
        
        key = f"{ip}:{username}" if username else ip
        
        # Block after 5 failed attempts
        if self.failed_attempts[key] >= 5:
            self.blocked_ips.add(ip)
            self.log_security_event(
                'ip_blocked',
                'critical',
                source_ip=ip,
                user=username,
                details={'reason': 'brute_force', 'attempts': self.failed_attempts[key]}
            )
            self.send_security_alert(
                f"IP {ip} blocked due to brute force attempts",
                severity='critical'
            )
            return True
        
        return False
    
    def record_failed_attempt(self, ip: str, username: Optional[str] = None, endpoint: str = '/'):
        """Record failed authentication attempt"""
        key = f"{ip}:{username}" if username else ip
        self.failed_attempts[key] += 1
        
        # Log to database
        conn = sqlite3.connect(self.security_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO access_attempts (ip_address, username, success, endpoint) VALUES (?, ?, ?, ?)",
            (ip, username, False, endpoint)
        )
        conn.commit()
        conn.close()
        
        self.check_brute_force(ip, username)
    
    def record_successful_attempt(self, ip: str, username: str, endpoint: str = '/'):
        """Record successful authentication"""
        key = f"{ip}:{username}"
        self.failed_attempts[key] = 0
        
        # Log to database
        conn = sqlite3.connect(self.security_db)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO access_attempts (ip_address, username, success, endpoint) VALUES (?, ?, ?, ?)",
            (ip, username, True, endpoint)
        )
        conn.commit()
        conn.close()
    
    def create_session(self, user: str, ip: str) -> str:
        """Create secure session with timeout"""
        session_id = secrets.token_hex(32)
        self.active_sessions[session_id] = {
            'user': user,
            'ip': ip,
            'created': datetime.now(),
            'last_activity': datetime.now(),
            'csrf_token': secrets.token_hex(16)
        }
        
        self.log_security_event(
            'session_created',
            'info',
            source_ip=ip,
            user=user
        )
        
        return session_id
    
    def validate_session(self, session_id: str, ip: str) -> Optional[Dict]:
        """Validate session and check timeout"""
        if session_id not in self.active_sessions:
            return None
        
        session = self.active_sessions[session_id]
        
        # Check IP match
        if session['ip'] != ip:
            self.log_security_event(
                'session_ip_mismatch',
                'warning',
                source_ip=ip,
                user=session['user'],
                details={'expected_ip': session['ip']}
            )
            del self.active_sessions[session_id]
            return None
        
        # Check timeout
        if datetime.now() - session['last_activity'] > self.session_timeout:
            self.log_security_event(
                'session_timeout',
                'info',
                source_ip=ip,
                user=session['user']
            )
            del self.active_sessions[session_id]
            return None
        
        # Update activity
        session['last_activity'] = datetime.now()
        return session
    
    def get_csrf_token(self, session_id: str) -> Optional[str]:
        """Get CSRF token for session"""
        if session_id in self.active_sessions:
            return self.active_sessions[session_id]['csrf_token']
        return None
    
    def validate_csrf_token(self, session_id: str, token: str) -> bool:
        """Validate CSRF token"""
        if session_id not in self.active_sessions:
            return False
        return self.active_sessions[session_id]['csrf_token'] == token
    
    def create_api_token(self, user: str, permissions: List[str], expires_days: int = 30) -> str:
        """Create JWT API token"""
        payload = {
            'user': user,
            'permissions': permissions,
            'exp': datetime.utcnow() + timedelta(days=expires_days),
            'iat': datetime.utcnow()
        }
        
        token = jwt.encode(payload, self.jwt_secret, algorithm='HS256')
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        # Store token hash in database
        conn = sqlite3.connect(self.security_db)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO api_tokens (token_hash, user, expires, permissions) 
               VALUES (?, ?, ?, ?)""",
            (token_hash, user, payload['exp'], json.dumps(permissions))
        )
        conn.commit()
        conn.close()
        
        self.log_security_event(
            'api_token_created',
            'info',
            user=user,
            details={'permissions': permissions}
        )
        
        return token
    
    def validate_api_token(self, token: str) -> Optional[Dict]:
        """Validate JWT API token"""
        try:
            # Decode token
            payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'])
            
            # Check if token is in database and active
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            conn = sqlite3.connect(self.security_db)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT active FROM api_tokens WHERE token_hash = ?",
                (token_hash,)
            )
            result = cursor.fetchone()
            conn.close()
            
            if result and result[0]:
                return payload
            
        except jwt.ExpiredSignatureError:
            self.log_security_event(
                'api_token_expired',
                'warning',
                details={'token_hash': hashlib.sha256(token.encode()).hexdigest()[:8]}
            )
        except jwt.InvalidTokenError:
            self.log_security_event(
                'api_token_invalid',
                'warning'
            )
        
        return None
    
    def validate_repository_checksum(self, repo_url: str, current_checksum: str) -> bool:
        """Validate repository hasn't been tampered with"""
        conn = sqlite3.connect(self.security_db)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT checksum FROM repository_checksums WHERE repository = ?",
            (repo_url,)
        )
        result = cursor.fetchone()
        
        if result:
            if result[0] != current_checksum:
                self.log_security_event(
                    'repository_checksum_mismatch',
                    'critical',
                    details={'repository': repo_url, 'expected': result[0][:8], 'actual': current_checksum[:8]}
                )
                conn.close()
                return False
        else:
            # New repository, store checksum
            cursor.execute(
                "INSERT INTO repository_checksums (repository, checksum) VALUES (?, ?)",
                (repo_url, current_checksum)
            )
            conn.commit()
        
        conn.close()
        return True
    
    def sanitize_input(self, input_str: str, input_type: str = 'general') -> str:
        """Sanitize user input to prevent injection attacks"""
        if not input_str:
            return input_str
        
        # Remove null bytes
        input_str = input_str.replace('\x00', '')
        
        if input_type == 'filename':
            # Allow only safe filename characters
            return re.sub(r'[^a-zA-Z0-9._-]', '', input_str)
        
        elif input_type == 'path':
            # Prevent directory traversal
            input_str = input_str.replace('..', '')
            return re.sub(r'[^a-zA-Z0-9./_-]', '', input_str)
        
        elif input_type == 'html':
            # Basic HTML escaping
            html_escape_table = {
                "&": "&amp;",
                '"': "&quot;",
                "'": "&apos;",
                ">": "&gt;",
                "<": "&lt;",
            }
            return "".join(html_escape_table.get(c, c) for c in input_str)
        
        else:
            # General sanitization
            return re.sub(r'[<>&\'"]', '', input_str)
    
    def detect_suspicious_patterns(self, content: str) -> List[str]:
        """Detect suspicious patterns in content"""
        suspicious_patterns = [
            (r'exec\s*\(', 'Code execution attempt'),
            (r'eval\s*\(', 'Eval execution attempt'),
            (r'__import__', 'Dynamic import attempt'),
            (r'subprocess\.', 'Subprocess execution attempt'),
            (r'os\.system', 'System command execution'),
            (r'<script', 'Script injection attempt'),
            (r'javascript:', 'JavaScript URL attempt'),
            (r'on\w+\s*=', 'Event handler injection'),
            (r'base64\.b64decode', 'Base64 decoding attempt'),
            (r'pickle\.loads', 'Pickle deserialization attempt'),
        ]
        
        detected = []
        for pattern, description in suspicious_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                detected.append(description)
                
        if detected:
            self.log_security_event(
                'suspicious_pattern_detected',
                'warning',
                details={'patterns': detected}
            )
        
        return detected
    
    def log_security_event(self, event_type: str, severity: str, 
                          source_ip: Optional[str] = None,
                          user: Optional[str] = None,
                          details: Optional[Dict] = None):
        """Log security event with tamper-proof hash"""
        timestamp = datetime.now().isoformat()
        details_json = json.dumps(details) if details else '{}'
        
        # Create event hash for integrity
        event_data = f"{timestamp}{event_type}{severity}{source_ip}{user}{details_json}"
        event_hash = hashlib.sha256(event_data.encode()).hexdigest()
        
        # Log to database
        conn = sqlite3.connect(self.security_db)
        cursor = conn.cursor()
        try:
            cursor.execute(
                """INSERT INTO security_events 
                   (timestamp, event_type, severity, source_ip, user, details, hash) 
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (timestamp, event_type, severity, source_ip, user, details_json, event_hash)
            )
            conn.commit()
        except sqlite3.IntegrityError:
            # Duplicate event hash - possible tampering
            self.logger.critical(f"Duplicate event hash detected: {event_hash}")
        finally:
            conn.close()
        
        # Log to file
        self.logger.log(
            getattr(logging, severity.upper(), logging.INFO),
            f"{event_type} - IP: {source_ip} - User: {user} - {details_json}"
        )
        
        # Check if alert needed
        self._check_alert_threshold(event_type, severity)
    
    def _check_alert_threshold(self, event_type: str, severity: str):
        """Check if security alerts should be sent"""
        if not self.alert_config['enabled']:
            return
        
        # Count recent security events
        conn = sqlite3.connect(self.security_db)
        cursor = conn.cursor()
        cursor.execute(
            """SELECT COUNT(*) FROM security_events 
               WHERE severity IN ('warning', 'critical') 
               AND timestamp > datetime('now', '-1 hour')"""
        )
        count = cursor.fetchone()[0]
        conn.close()
        
        if count >= self.alert_config['threshold']:
            self.send_security_alert(
                f"Security threshold exceeded: {count} events in last hour",
                severity='critical'
            )
    
    def send_security_alert(self, message: str, severity: str = 'warning'):
        """Send security alert via configured channels"""
        if not self.alert_config['enabled']:
            return
        
        alert_data = {
            'timestamp': datetime.now().isoformat(),
            'severity': severity,
            'message': message,
            'host': os.uname().nodename
        }
        
        # Send email alert
        if self.alert_config.get('email'):
            try:
                self._send_email_alert(alert_data)
            except Exception as e:
                self.logger.error(f"Failed to send email alert: {e}")
        
        # Send webhook alert
        if self.alert_config.get('webhook'):
            try:
                self._send_webhook_alert(alert_data)
            except Exception as e:
                self.logger.error(f"Failed to send webhook alert: {e}")
    
    def _send_email_alert(self, alert_data: Dict):
        """Send email security alert"""
        # Implementation would require SMTP configuration
        pass
    
    def _send_webhook_alert(self, alert_data: Dict):
        """Send webhook security alert"""
        import requests
        requests.post(
            self.alert_config['webhook'],
            json=alert_data,
            timeout=5
        )
    
    def verify_log_integrity(self) -> Tuple[bool, List[str]]:
        """Verify integrity of security logs"""
        conn = sqlite3.connect(self.security_db)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM security_events ORDER BY id")
        
        invalid_entries = []
        for row in cursor.fetchall():
            id_, timestamp, event_type, severity, source_ip, user, details, stored_hash = row
            
            # Recalculate hash
            event_data = f"{timestamp}{event_type}{severity}{source_ip}{user}{details}"
            calculated_hash = hashlib.sha256(event_data.encode()).hexdigest()
            
            if calculated_hash != stored_hash:
                invalid_entries.append(f"Event {id_}: Hash mismatch")
        
        conn.close()
        
        if invalid_entries:
            self.log_security_event(
                'log_integrity_failure',
                'critical',
                details={'invalid_entries': len(invalid_entries)}
            )
        
        return len(invalid_entries) == 0, invalid_entries
    
    def encrypt_sensitive_data(self, data: str) -> str:
        """Encrypt sensitive data"""
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt_sensitive_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""
        return self.cipher.decrypt(encrypted_data.encode()).decode()
    
    def get_security_status(self) -> Dict:
        """Get comprehensive security status"""
        conn = sqlite3.connect(self.security_db)
        cursor = conn.cursor()
        
        # Recent events
        cursor.execute(
            """SELECT COUNT(*) FROM security_events 
               WHERE timestamp > datetime('now', '-24 hours')"""
        )
        recent_events = cursor.fetchone()[0]
        
        # Failed attempts
        cursor.execute(
            """SELECT COUNT(*) FROM access_attempts 
               WHERE success = 0 AND timestamp > datetime('now', '-24 hours')"""
        )
        failed_attempts = cursor.fetchone()[0]
        
        # Active sessions
        active_sessions = len(self.active_sessions)
        
        # Blocked IPs
        blocked_ips = len(self.blocked_ips)
        
        conn.close()
        
        # Verify log integrity
        integrity_valid, _ = self.verify_log_integrity()
        
        return {
            'status': 'secure' if integrity_valid and blocked_ips < 5 else 'warning',
            'recent_events': recent_events,
            'failed_attempts_24h': failed_attempts,
            'active_sessions': active_sessions,
            'blocked_ips': blocked_ips,
            'log_integrity': 'valid' if integrity_valid else 'compromised',
            'rate_limits_active': len(self.rate_limits),
            'alert_system': 'enabled' if self.alert_config['enabled'] else 'disabled'
        }


# Flask decorator for enhanced security
def require_secure_session(f):
    """Decorator to require valid session with security checks"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import request, session, abort
        
        # Get security instance
        security = SecurityEnhanced()
        
        # Check rate limiting
        client_ip = request.remote_addr
        if not security.rate_limit_check(client_ip):
            abort(429)  # Too Many Requests
        
        # Validate session
        session_id = session.get('session_id')
        if not session_id:
            abort(401)
        
        session_data = security.validate_session(session_id, client_ip)
        if not session_data:
            abort(401)
        
        # CSRF validation for POST requests
        if request.method == 'POST':
            csrf_token = request.form.get('csrf_token') or request.headers.get('X-CSRF-Token')
            if not security.validate_csrf_token(session_id, csrf_token):
                security.log_security_event(
                    'csrf_validation_failed',
                    'warning',
                    source_ip=client_ip,
                    user=session_data['user']
                )
                abort(403)
        
        # Add security context
        request.security_context = {
            'user': session_data['user'],
            'ip': client_ip,
            'session': session_data
        }
        
        return f(*args, **kwargs)
    return decorated_function


def require_api_token(required_permissions: List[str] = None):
    """Decorator to require valid API token with permissions"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from flask import request, abort
            
            # Get security instance
            security = SecurityEnhanced()
            
            # Extract token
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                abort(401)
            
            token = auth_header.split(' ')[1]
            
            # Validate token
            token_data = security.validate_api_token(token)
            if not token_data:
                abort(401)
            
            # Check permissions
            if required_permissions:
                user_permissions = token_data.get('permissions', [])
                if not all(p in user_permissions for p in required_permissions):
                    security.log_security_event(
                        'insufficient_permissions',
                        'warning',
                        user=token_data['user'],
                        details={'required': required_permissions, 'actual': user_permissions}
                    )
                    abort(403)
            
            # Add token context
            request.token_context = token_data
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator


if __name__ == "__main__":
    # Test enhanced security features
    security = SecurityEnhanced()
    
    print("Enhanced Security System Test")
    print("=" * 50)
    
    # Test rate limiting
    print("\n1. Testing rate limiting...")
    for i in range(12):
        allowed = security.rate_limit_check('test_ip', limit=10, window=60)
        print(f"   Request {i+1}: {'Allowed' if allowed else 'Blocked'}")
    
    # Test session management
    print("\n2. Testing session management...")
    session_id = security.create_session('test_user', '192.168.1.100')
    print(f"   Created session: {session_id[:16]}...")
    
    session = security.validate_session(session_id, '192.168.1.100')
    print(f"   Session valid: {session is not None}")
    
    # Test API token
    print("\n3. Testing API token...")
    token = security.create_api_token('test_user', ['read', 'write'], expires_days=30)
    print(f"   Created token: {token[:20]}...")
    
    token_data = security.validate_api_token(token)
    print(f"   Token valid: {token_data is not None}")
    
    # Test input sanitization
    print("\n4. Testing input sanitization...")
    test_inputs = [
        ("<script>alert('xss')</script>", "html"),
        ("../../etc/passwd", "path"),
        ("file'; DROP TABLE users; --", "filename")
    ]
    
    for input_str, input_type in test_inputs:
        sanitized = security.sanitize_input(input_str, input_type)
        print(f"   {input_type}: '{input_str}' -> '{sanitized}'")
    
    # Test suspicious pattern detection
    print("\n5. Testing pattern detection...")
    suspicious_content = "exec(__import__('os').system('rm -rf /'))"
    patterns = security.detect_suspicious_patterns(suspicious_content)
    print(f"   Detected patterns: {patterns}")
    
    # Get security status
    print("\n6. Security Status:")
    status = security.get_security_status()
    for key, value in status.items():
        print(f"   {key}: {value}")