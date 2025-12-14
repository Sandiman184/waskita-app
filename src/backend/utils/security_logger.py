import logging
import json
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from flask import request
from flask_login import current_user
from functools import wraps
import threading
from collections import defaultdict, deque
import time

class SecurityLogger:
    """Enhanced security logging system with threat detection"""
    
    def __init__(self):
        self.security_events = deque(maxlen=1000)  # Keep last 1000 events in memory
        self.threat_counters = defaultdict(int)
        self.blocked_ips = set()
        self.lock = threading.Lock()
        self.setup_loggers()
    
    def setup_loggers(self):
        """Setup security and audit loggers with rotation"""
        # Determine absolute path for logs directory (project root/logs)
        basedir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
        log_dir = os.path.join(basedir, 'logs')
        
        # Create logs directory
        os.makedirs(log_dir, exist_ok=True)
        
        # Security logger with rotation
        self.security_logger = logging.getLogger('security')
        self.security_logger.setLevel(logging.INFO)
        
        # Remove existing handlers
        for handler in self.security_logger.handlers[:]:
            self.security_logger.removeHandler(handler)
        
        # Rotating file handler (10MB max, keep 5 files)
        security_handler = RotatingFileHandler(
            os.path.join(log_dir, 'security.log'),
            maxBytes=10*1024*1024,
            backupCount=5
        )
        security_handler.setLevel(logging.INFO)
        
        # JSON formatter for structured logging
        security_formatter = SecurityFormatter()
        security_handler.setFormatter(security_formatter)
        
        self.security_logger.addHandler(security_handler)
        self.security_logger.propagate = False
        
        # Audit logger
        self.audit_logger = logging.getLogger('audit')
        self.audit_logger.setLevel(logging.INFO)
        
        for handler in self.audit_logger.handlers[:]:
            self.audit_logger.removeHandler(handler)
        
        audit_handler = RotatingFileHandler(
            os.path.join(log_dir, 'audit.log'),
            maxBytes=10*1024*1024,
            backupCount=10
        )
        audit_handler.setFormatter(security_formatter)
        self.audit_logger.addHandler(audit_handler)
        self.audit_logger.propagate = False

    def log_security_event(self, event_type, details=None, user_id=None, ip_address=None, severity='INFO'):
        """Log security events with threat analysis"""
        if not ip_address:
            ip_address = request.remote_addr if request else 'Unknown'
        
        if not user_id and current_user and hasattr(current_user, 'id'):
            user_id = current_user.id
        
        event_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'event_type': event_type,
            'ip_address': ip_address,
            'user_id': user_id,
            'details': details,
            'severity': severity,
            'user_agent': request.headers.get('User-Agent') if request else None,
            'endpoint': request.endpoint if request else None,
            'method': request.method if request else None
        }
        
        # Add to memory for analysis
        with self.lock:
            self.security_events.append(event_data)
            self.analyze_threat_patterns(event_data)
        
        # Log to file
        if severity == 'CRITICAL':
            self.security_logger.critical(json.dumps(event_data))
        elif severity == 'WARNING':
            self.security_logger.warning(json.dumps(event_data))
        else:
            self.security_logger.info(json.dumps(event_data))
    
    def analyze_threat_patterns(self, event_data):
        """Analyze patterns for potential threats"""
        ip = event_data['ip_address']
        event_type = event_data['event_type']
        
        # Count events per IP
        threat_key = f"{ip}:{event_type}"
        self.threat_counters[threat_key] += 1
        
        # Auto-block IPs with suspicious activity
        if event_type in ['FAILED_LOGIN', 'INVALID_INPUT', 'RATE_LIMIT_EXCEEDED']:
            if self.threat_counters[threat_key] >= 5:  # 5 attempts
                self.blocked_ips.add(ip)
                self.log_security_event(
                    'IP_BLOCKED',
                    f'IP {ip} blocked due to suspicious activity: {event_type}',
                    severity='CRITICAL'
                )
    
    def is_ip_blocked(self, ip_address):
        """Check if IP is blocked"""
        return ip_address in self.blocked_ips
    
    def audit_log(self, action, resource=None, user_id=None, details=None):
        """Log audit events for compliance"""
        audit_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'action': action,
            'resource': resource,
            'user_id': user_id or (current_user.id if current_user and hasattr(current_user, 'id') else None),
            'ip_address': request.remote_addr if request else 'Unknown',
            'details': details
        }
        
        self.audit_logger.info(json.dumps(audit_data))

class SecurityFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging"""
    
    def format(self, record):
        try:
            # Try to parse as JSON first
            log_data = json.loads(record.getMessage())
            return json.dumps(log_data, ensure_ascii=False)
        except (json.JSONDecodeError, ValueError):
            # Fallback to regular formatting
            return super().format(record)

# Global security logger instance
security_logger_instance = SecurityLogger()

def log_security_event(event_type, details=None, user_id=None, ip_address=None, severity='INFO'):
    """
    Global function for logging security events
    
    Args:
        event_type (str): Type of security event
        details (str): Additional details about the event
        user_id (int): User ID if applicable
        ip_address (str): IP address of the request
        severity (str): Event severity (INFO, WARNING, CRITICAL)
    """
    security_logger_instance.log_security_event(event_type, details, user_id, ip_address, severity)

def log_failed_login(username, ip_address=None):
    """Log failed login attempts"""
    log_security_event(
        'FAILED_LOGIN',
        f'Username: {username}',
        ip_address=ip_address,
        severity='WARNING'
    )

def log_registration_attempt(username, email, ip_address=None):
    """Log user registration attempts"""
    log_security_event(
        'REGISTRATION_ATTEMPT',
        f'Username: {username}, Email: {email}',
        ip_address=ip_address
    )

def log_admin_action(action, details=None, user_id=None, ip_address=None):
    """Log administrative actions"""
    log_security_event(
        'ADMIN_ACTION',
        f'Action: {action} | {details}' if details else f'Action: {action}',
        user_id=user_id,
        ip_address=ip_address,
        severity='WARNING'
    )

def log_rate_limit_exceeded(endpoint, ip_address=None):
    """Log rate limit violations"""
    log_security_event(
        'RATE_LIMIT_EXCEEDED',
        f'Endpoint: {endpoint}',
        ip_address=ip_address,
        severity='WARNING'
    )

def security_audit(action, resource=None):
    """Decorator for auditing sensitive actions"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                security_logger_instance.audit_log(
                    action=action,
                    resource=resource,
                    details=f'Success: {func.__name__}'
                )
                return result
            except Exception as e:
                security_logger_instance.audit_log(
                    action=action,
                    resource=resource,
                    details=f'Failed: {func.__name__} - {str(e)}'
                )
                raise
        return wrapper
    return decorator

def check_ip_blocked():
    """Check if current request IP is blocked"""
    if request:
        ip = request.remote_addr
        if security_logger_instance.is_ip_blocked(ip):
            log_security_event(
                'BLOCKED_IP_ACCESS_ATTEMPT',
                f'Blocked IP {ip} attempted access',
                severity='CRITICAL'
            )
            return True
    return False

def get_security_stats():
    """Get security statistics for monitoring"""
    with security_logger_instance.lock:
        return {
            'total_events': len(security_logger_instance.security_events),
            'blocked_ips': len(security_logger_instance.blocked_ips),
            'threat_counters': dict(security_logger_instance.threat_counters),
            'recent_events': list(security_logger_instance.security_events)[-10:]  # Last 10 events
        }