"""
Security Middleware Fixes untuk OWASP ZAP Compatibility
File ini berisi perbaikan untuk mencegah server down saat scanning keamanan
"""

from flask import request, abort, g, current_app
from functools import wraps
import time
from collections import defaultdict, deque
import re
import threading
from utils.security_logger import log_security_event, check_ip_blocked, log_rate_limit_exceeded
from utils.security_utils import add_security_headers

# Rate limiting storage dengan thread safety dan OWASP ZAP protection
rate_limit_storage = defaultdict(list)
rate_limit_lock = threading.Lock()

# Known security scanner IP ranges dan user agents
SECURITY_SCANNERS = {
    'user_agents': [
        'ZAP', 'OWASP', 'arachni', 'nikto', 'nessus', 'w3af', 'skipfish',
        'wget', 'curl', 'python-requests', 'security scanner', 'acunetix',
        'burp', 'sqlmap', 'nmap', 'metasploit'
    ],
    'ip_ranges': [
        '127.0.0.1', 'localhost',  # Local testing
        '192.168.', '10.', '172.16.',  # Private networks
        '0.0.0.0'  # Docker internal
    ]
}

# SQL Injection detection patterns
SQL_INJECTION_PATTERNS = [
    r"([';]+.*(--|#|/*|;))",
    r"(union.*select)",
    r"(select.*from)",
    r"(insert.*into)",
    r"(update.*set)",
    r"(delete.*from)",
    r"(drop.*table)",
    r"(exec.*xp_)",
    r"(waitfor.*delay)",
    r"(shutdown.*with)",
    r"(truncate.*table)",
    r"(alter.*table)",
    r"(create.*table)",
    r"(begin.*transaction)",
    r"(declare.*@)",
    r"(cast.*as)",
    r"(exec.*sp_)",
    r"(1=1)",
    r"(1'='1)",
    r"('\s+or\s+')",
    r"(\s+or\s+1=1)",
    r"(\s+and\s+1=1)"
]

# XSS detection patterns
XSS_PATTERNS = [
    r"(<script>)",
    r"(javascript:)",
    r"(vbscript:)",
    r"(onload=)",
    r"(onerror=)",
    r"(onclick=)",
    r"(alert\()",
    r"(document\.cookie)",
    r"(window\.location)",
    r"(eval\()"
]

def _is_security_scanner(ip_address=None):
    """Detect jika request berasal dari security scanner"""
    if not ip_address:
        ip_address = request.remote_addr if request else 'unknown'
    
    user_agent = request.headers.get('User-Agent', '').lower() if request else ''
    
    # Check user agent patterns
    for scanner_pattern in SECURITY_SCANNERS['user_agents']:
        if scanner_pattern.lower() in user_agent:
            current_app.logger.info(f"Security scanner detected: {scanner_pattern} - {user_agent}")
            return True
    
    # Check IP ranges
    for ip_range in SECURITY_SCANNERS['ip_ranges']:
        if ip_address.startswith(ip_range):
            current_app.logger.info(f"Security scanner IP detected: {ip_address}")
            return True
    
    return False

def detect_sql_injection(input_data):
    """Detect SQL injection patterns in input data"""
    if not input_data:
        return False
        
    input_str = str(input_data).lower()
    for pattern in SQL_INJECTION_PATTERNS:
        if re.search(pattern, input_str, re.IGNORECASE):
            return True
    return False

def detect_xss(input_data):
    """Detect XSS patterns in input data"""
    if not input_data:
        return False
        
    input_str = str(input_data).lower()
    for pattern in XSS_PATTERNS:
        if re.search(pattern, input_str, re.IGNORECASE):
            return True
    return False

def sanitize_input(input_data):
    """Sanitize input untuk mencegah SQL injection dan XSS"""
    if not input_data:
        return ""
    
    # Convert to string and strip
    sanitized = str(input_data).strip()
    
    # Remove dangerous SQL characters
    dangerous_sql = ["'", '"', ";", "--", "/*", "*/", "xp_", "exec", "union", "select"]
    for char in dangerous_sql:
        sanitized = sanitized.replace(char, "")
    
    # Remove dangerous HTML/JS characters
    dangerous_html = ["<", ">", "&", "'", '"', "(", ")", "{", "}", "[", "]", "`"]
    for char in dangerous_html:
        sanitized = sanitized.replace(char, "")
    
    return sanitized

class SecurityMiddleware:
    """Middleware untuk menangani security headers dan proteksi"""
    
    def __init__(self, app=None):
        self.app = app
        if app is not None:
            self.init_app(app)
    
    def init_app(self, app):
        """Initialize security middleware with Flask app"""
        app.before_request(self.before_request)
        app.after_request(self.after_request)
    
    def before_request(self):
        """Security checks before processing request"""
        # Log request details for debugging
        current_app.logger.info(f"Request: {request.method} {request.path} - Content-Type: {request.content_type}")
        
        # Check if IP is blocked
        if check_ip_blocked():
            abort(403)
        
        # Rate limiting dengan proteksi OWASP ZAP
        if self.is_rate_limited():
            log_rate_limit_exceeded(request.endpoint or request.path)
            abort(429)
        
        # Check for suspicious patterns (skip untuk security scanners)
        if self.check_suspicious_requests():
            log_security_event(
                'SUSPICIOUS_REQUEST',
                f'Suspicious pattern detected in request to {request.path}',
                severity='WARNING'
            )
            abort(400)
        
        # Store request start time for performance monitoring
        g.start_time = time.time()
    
    def after_request(self, response):
        """Process response after handling"""
        # Add security headers
        response = add_security_headers(response)
        
        # Log slow requests
        if hasattr(g, 'start_time'):
            request_time = time.time() - g.start_time
            if request_time > 1.0:  # Log requests taking more than 1 second
                log_security_event(
                    "SLOW_REQUEST",
                    f"Slow request detected: {request.endpoint} took {request_time:.2f}s",
                    ip_address=request.remote_addr
                )
        
        return response
    
    def is_rate_limited(self):
        """Check if request should be rate limited with OWASP ZAP protection"""
        client_ip = request.remote_addr
        current_time = time.time()
        
        # Skip rate limiting untuk security scanners
        if _is_security_scanner(client_ip):
            return False
        
        with rate_limit_lock:
            # Clean old entries (older than 1 minute)
            rate_limit_storage[client_ip] = [
                timestamp for timestamp in rate_limit_storage[client_ip]
                if current_time - timestamp < 60
            ]
            
            # Check if rate limit exceeded (max 100 requests per minute)
            if len(rate_limit_storage[client_ip]) >= 100:
                return True
            
            # Add current request timestamp
            rate_limit_storage[client_ip].append(current_time)
            return False
    
    def check_suspicious_requests(self):
        """Check for suspicious request patterns with OWASP ZAP compatibility"""
        # Skip checking for Admin Upload endpoints to prevent 413 or false positives on large files
        if request.path.startswith('/admin/upload/') or request.path.startswith('/admin/classification/settings'):
            return False

        # Skip pattern checking untuk security scanners
        if _is_security_scanner(request.remote_addr):
            return False
        
        # Check for SQL injection patterns (safe patterns only)
        suspicious_patterns = [
            'union select', 'drop table', 'insert into', 'delete from',
            'script>', '<iframe', 'javascript:', 'vbscript:',
            '../', '..\\', '/etc/passwd', '/proc/version'
        ]
        
        try:
            # Check URL and form data safely
            request_data = str(request.url).lower()
            
            # CAUTION: Accessing request.form causes Flask to parse the body.
            # If body size > MAX_CONTENT_LENGTH, Flask raises 413 immediately here.
            # We should skip body parsing for file upload endpoints if we haven't already.
            # Since we already skipped admin upload endpoints above, this is safer.
            
            if request.form:
                request_data += ' ' + ' '.join(str(v) for v in request.form.values()).lower()
            
            # Only check JSON if content-type is application/json
            if request.content_type and 'application/json' in request.content_type:
                try:
                    json_data = request.get_json(silent=True)
                    if json_data:
                        request_data += ' ' + str(json_data).lower()
                except Exception:
                    pass  # Ignore JSON parsing errors
            
            for pattern in suspicious_patterns:
                if pattern in request_data:
                    log_security_event(
                        "SUSPICIOUS_REQUEST",
                        f"Suspicious pattern detected: {pattern} in request from {request.remote_addr}",
                        ip_address=request.remote_addr
                    )
                    return True
            
            return False
        except Exception as e:
            # Log but don't block on errors untuk maintain availability
            current_app.logger.warning(f"Error in suspicious request check: {e}")
            return False

def rate_limit(max_requests=60, window=60):
    """
    Decorator untuk rate limiting pada endpoint tertentu
    
    Args:
        max_requests: Maximum number of requests allowed
        window: Time window in seconds
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            client_ip = request.remote_addr
            current_time = time.time()
            
            # Skip rate limiting untuk security scanners
            if _is_security_scanner(client_ip):
                return f(*args, **kwargs)
            
            # Create unique key for this endpoint
            endpoint_key = f"{client_ip}:{request.endpoint}"
            
            with rate_limit_lock:
                # Clean old entries
                rate_limit_storage[endpoint_key] = [
                    timestamp for timestamp in rate_limit_storage[endpoint_key]
                    if current_time - timestamp < window
                ]
                
                # Check rate limit
                if len(rate_limit_storage[endpoint_key]) >= max_requests:
                    log_security_event(
                        "ENDPOINT_RATE_LIMIT",
                        f"Rate limit exceeded for endpoint {request.endpoint} from {client_ip}",
                        ip_address=client_ip
                    )
                    from flask import jsonify
                    return jsonify({
                        'success': False, 
                        'message': 'Rate limit exceeded. Please try again later.'
                    }), 429
                
                # Add current request
                rate_limit_storage[endpoint_key].append(current_time)
                
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_https():
    """Decorator to require HTTPS for sensitive endpoints"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not request.is_secure and not request.headers.get('X-Forwarded-Proto') == 'https':
                log_security_event(
                    "INSECURE_REQUEST",
                    f"HTTP request to secure endpoint: {request.endpoint}",
                    ip_address=request.remote_addr
                )
                from flask import redirect, url_for
                return redirect(url_for(request.endpoint, _external=True, _scheme='https'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator