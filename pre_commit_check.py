#!/usr/bin/env python3
"""
Pre-commit check script untuk memastikan tidak ada placeholder values
atau file sensitif yang akan di-commit ke repository
"""

import os
import re
import sys
from pathlib import Path

def check_placeholder_values():
    """Cek apakah masih ada placeholder values di file-file penting"""
    
    print("🔍 Checking for placeholder values...")
    
    # File yang perlu dicek
    files_to_check = [
        'setup_postgresql.py',
        '.env.example',
        'config.py',
        'README.md'
    ]
    
    # Pattern placeholder yang tidak boleh ada
    bad_patterns = [
        r'\[admin_username\]',
        r'\[admin@example\.com\]',
        r'\[admin_password\]',
        r'\[Administrator Name\]',
        r'\[db_host\]',
        r'\[db_port\]',
        r'\[.*\].*@.*\]',  # Email dengan bracket
        r'your-super-secret-key',
        r'your-csrf-secret-key',
        r'your-jwt-secret-key'
    ]
    
    issues_found = []
    
    for file_path in files_to_check:
        if not os.path.exists(file_path):
            continue
            
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        for pattern in bad_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                # Filter out f-string variables like {db_config['key']}
                filtered_matches = []
                for match in matches:
                    # Skip if it's an f-string variable pattern
                    if not ('{' in match and '}' in match and "'" in match):
                        filtered_matches.append(match)
                
                if filtered_matches:
                    issues_found.append(f"❌ {file_path}: Found placeholder '{filtered_matches[0]}'")
    
    if issues_found:
        print("\n🚨 PLACEHOLDER VALUES FOUND:")
        for issue in issues_found:
            print(f"  {issue}")
        return False
    else:
        print("✅ No placeholder values found")
        return True

def check_sensitive_files():
    """Cek apakah ada file sensitif yang akan di-commit"""
    
    print("\n🔍 Checking for sensitive files...")
    
    # Read .gitignore to see what's already ignored
    gitignore_patterns = []
    if os.path.exists('.gitignore'):
        with open('.gitignore', 'r', encoding='utf-8') as f:
            gitignore_patterns = [line.strip() for line in f.readlines() if line.strip() and not line.startswith('#')]
    
    sensitive_files = [
        '.env',
        '.env.local',
        '.env.production',
        'config_local.py',
        '*.key',
        '*.pem',
        '*.p12'
    ]
    
    issues_found = []
    
    for pattern in sensitive_files:
        if '*' in pattern:
            # Handle wildcard patterns
            import glob
            matches = glob.glob(pattern)
            for match in matches:
                if os.path.exists(match):
                    # Check if this file is in gitignore
                    is_ignored = any(
                        match == ignore_pattern or 
                        (ignore_pattern.endswith('*') and match.startswith(ignore_pattern[:-1])) or
                        (ignore_pattern.startswith('*') and match.endswith(ignore_pattern[1:]))
                        for ignore_pattern in gitignore_patterns
                    )
                    if not is_ignored:
                        issues_found.append(f"❌ Sensitive file: {match}")
        else:
            if os.path.exists(pattern):
                # Check if this file is in gitignore
                is_ignored = pattern in gitignore_patterns
                if not is_ignored:
                    issues_found.append(f"❌ Sensitive file: {pattern}")
    
    if issues_found:
        print("\n🚨 SENSITIVE FILES FOUND:")
        for issue in issues_found:
            print(f"  {issue}")
        print("\n💡 These files should be in .gitignore")
        return False
    else:
        print("✅ No sensitive files found or all are properly ignored")
        return True

def check_required_files():
    """Cek apakah semua file yang diperlukan ada"""
    
    print("\n🔍 Checking for required files...")
    
    required_files = [
        '.env.example',
        'README.md',
        'requirements.txt',
        'setup_postgresql.py',
        '.gitignore',
        'CHANGELOG.md'
    ]
    
    missing_files = []
    
    for file_path in required_files:
        if not os.path.exists(file_path):
            missing_files.append(file_path)
    
    if missing_files:
        print("\n🚨 MISSING REQUIRED FILES:")
        for file_path in missing_files:
            print(f"  ❌ {file_path}")
        return False
    else:
        print("✅ All required files present")
        return True

def check_env_example():
    """Cek apakah .env.example memiliki konfigurasi yang benar"""
    
    print("\n🔍 Checking .env.example configuration...")
    
    if not os.path.exists('.env.example'):
        print("❌ .env.example not found")
        return False
    
    with open('.env.example', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Cek apakah ada konfigurasi penting
    required_configs = [
        'DATABASE_URL=',
        'SECRET_KEY=',
        'FLASK_ENV=',
        'DATABASE_USER=admin_ws',
        'DATABASE_NAME=waskita_db'
    ]
    
    missing_configs = []
    
    for config in required_configs:
        if config not in content:
            missing_configs.append(config)
    
    if missing_configs:
        print("\n🚨 MISSING CONFIGURATIONS IN .env.example:")
        for config in missing_configs:
            print(f"  ❌ {config}")
        return False
    else:
        print("✅ .env.example configuration looks good")
        return True

def main():
    """Main function"""
    print("🚀 Waskita Pre-Commit Check")
    print("=" * 50)
    
    all_checks_passed = True
    
    # Run all checks
    checks = [
        check_placeholder_values,
        check_sensitive_files,
        check_required_files,
        check_env_example
    ]
    
    for check in checks:
        if not check():
            all_checks_passed = False
    
    print("\n" + "=" * 50)
    
    if all_checks_passed:
        print("🎉 ALL CHECKS PASSED!")
        print("✅ Repository is ready for commit and push")
        print("\n💡 Recommended commit message:")
        print("git commit -m \"fix: resolve placeholder values and improve setup process\"")
        print("git commit -m \"\"")
        print("git commit -m \"- Fixed placeholder values in setup_postgresql.py\"")
        print("git commit -m \"- Updated .env.example with correct defaults\"") 
        print("git commit -m \"- Added comprehensive setup documentation\"")
        print("git commit -m \"- Added utility scripts for debugging and cleanup\"")
        print("git commit -m \"- Removed deprecated create_admin.py\"")
        return True
    else:
        print("❌ SOME CHECKS FAILED!")
        print("🔧 Please fix the issues above before committing")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)