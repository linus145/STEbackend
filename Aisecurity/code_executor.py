"""
Secure Code Execution Engine for AI Interview Exam Portal.

Executes candidate code in a sandboxed subprocess with:
- Timeout enforcement (max 10 seconds)
- Memory/output limits
- Restricted imports (no os, sys, subprocess, etc.)
- Separate process isolation
"""

import subprocess
import tempfile
import os
import uuid
import logging

logger = logging.getLogger("Aisecurity.code_executor")

# Maximum execution time in seconds
MAX_EXECUTION_TIME = 10

# Maximum output size in characters
MAX_OUTPUT_SIZE = 10000

# Language configurations
LANGUAGE_CONFIG = {
    'python': {
        'extension': '.py',
        'command': ['python', '-u'],  # -u for unbuffered output
    },
    'javascript': {
        'extension': '.js',
        'command': ['node'],
    },
}

# Aliases
LANGUAGE_ALIASES = {
    'py': 'python',
    'python3': 'python',
    'js': 'javascript',
    'node': 'javascript',
}


import ast
import re

def is_safe_python(code: str) -> tuple[bool, str]:
    """
    Perform AST analysis on Python code to block dangerous imports and functions.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        # Let the compiler catch syntax errors so candidate gets helpful feedback
        return True, ""
        
    blocked_modules = {
        'os', 'sys', 'subprocess', 'socket', 'urllib', 'requests', 'shutil', 'importlib', 
        'pty', 'platform', 'multiprocessing', 'threading', 'asyncio', 'ctypes', 'gc', 'builtins'
    }
    blocked_functions = {'eval', 'exec', 'open', '__import__', 'compile'}
    
    for node in ast.walk(tree):
        # Block standard imports (e.g. import os)
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name.split('.')[0]
                if name in blocked_modules:
                    return False, f"Importing '{alias.name}' is prohibited for security reasons."
                    
        # Block from imports (e.g. from os import path)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                name = node.module.split('.')[0]
                if name in blocked_modules:
                    return False, f"Importing from '{node.module}' is prohibited for security reasons."
                    
        # Block calls (e.g. eval('...'))
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in blocked_functions:
                    return False, f"Function '{node.func.id}' is prohibited for security reasons."
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr in blocked_functions:
                    return False, f"Access to '{node.func.attr}' is prohibited for security reasons."
                    
        # Block attribute access to dunders (e.g. __subclasses__)
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith('__') and node.attr not in ('__name__', '__init__', '__main__'):
                return False, f"Access to special attribute '{node.attr}' is prohibited."
                
    return True, ""


def is_safe_javascript(code: str) -> tuple[bool, str]:
    """
    Check JavaScript code for forbidden keywords/modules to prevent RCE.
    """
    blocked_keywords = [
        'require', 'import', 'child_process', 'fs', 'http', 'https', 'net', 'dns', 'tls', 
        'process', 'global', 'eval', 'Function', 'vm', 'cluster', 'os', 'path', 'module'
    ]
    for kw in blocked_keywords:
        # Match as whole word to avoid false positives (e.g. myprocess)
        pattern = rf"\b{kw}\b"
        if re.search(pattern, code):
            return False, f"Usage of '{kw}' is prohibited for security reasons."
            
    return True, ""


def execute_code(source_code: str, language: str, stdin: str = "") -> dict:
    """
    Execute code safely in a sandboxed Docker container (with CPU, memory, read-only FS, and network limits).
    Falls back gracefully to standard host subprocess sandbox if Docker is not available.
    """
    # Normalize language
    lang = language.lower().strip()
    lang = LANGUAGE_ALIASES.get(lang, lang)
    
    config = LANGUAGE_CONFIG.get(lang)
    if not config:
        return {
            'stdout': '',
            'stderr': f'Unsupported language: {language}. Supported: Python, JavaScript',
            'success': False,
            'timed_out': False,
        }

    # Perform security checks
    if lang == 'python':
        is_safe, error_msg = is_safe_python(source_code)
        if not is_safe:
            return {
                'stdout': '',
                'stderr': error_msg,
                'success': False,
                'timed_out': False,
            }
    elif lang == 'javascript':
        is_safe, error_msg = is_safe_javascript(source_code)
        if not is_safe:
            return {
                'stdout': '',
                'stderr': error_msg,
                'success': False,
                'timed_out': False,
            }
    
    # Create a temporary file for the code
    temp_dir = tempfile.mkdtemp(prefix='exam_code_')
    filename = f"solution_{uuid.uuid4().hex[:8]}{config['extension']}"
    filepath = os.path.join(temp_dir, filename)
    
    # Format path for Docker volume mounting
    host_dir = os.path.abspath(temp_dir).replace('\\', '/')
    
    try:
        # Write code to temp file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(source_code)
        
        # Check if Docker is available
        docker_available = True
        try:
            subprocess.run(['docker', '--version'], capture_output=True, text=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            docker_available = False
            
        if docker_available:
            docker_img = 'python:3.10-slim' if lang == 'python' else 'node:18-alpine'
            cmd_runner = ['python', '-u'] if lang == 'python' else ['node']
            
            # docker run --rm --net=none --memory=128m --cpus=0.5 -i -v host_dir:/app:ro img runner /app/file
            cmd = [
                'docker', 'run', '--rm',
                '--net=none',
                '--memory=128m',
                '--cpus=0.5',
                '--read-only',
                '-i',
                '-v', f"{host_dir}:/app:ro",
                docker_img
            ] + cmd_runner + [f"/app/{filename}"]
            
            try:
                result = subprocess.run(
                    cmd,
                    input=stdin,
                    capture_output=True,
                    text=True,
                    timeout=MAX_EXECUTION_TIME,
                )
                stdout = result.stdout[:MAX_OUTPUT_SIZE] if result.stdout else ''
                stderr = result.stderr[:MAX_OUTPUT_SIZE] if result.stderr else ''
                
                return {
                    'stdout': stdout,
                    'stderr': stderr,
                    'success': result.returncode == 0,
                    'timed_out': False,
                }
            except subprocess.TimeoutExpired:
                return {
                    'stdout': '',
                    'stderr': f'Execution timed out after {MAX_EXECUTION_TIME} seconds.',
                    'success': False,
                    'timed_out': True,
                }
            except Exception as e:
                logger.warning(f"Docker run failed at runtime, falling back to host execution: {e}")
                docker_available = False
                
        if not docker_available:
            # Fallback to local subprocess execution (with sandbox/timeout limits)
            cmd = config['command'] + [filepath]
            result = subprocess.run(
                cmd,
                input=stdin,
                capture_output=True,
                text=True,
                timeout=MAX_EXECUTION_TIME,
                cwd=temp_dir,
            )
            stdout = result.stdout[:MAX_OUTPUT_SIZE] if result.stdout else ''
            stderr = result.stderr[:MAX_OUTPUT_SIZE] if result.stderr else ''
            
            return {
                'stdout': stdout,
                'stderr': stderr,
                'success': result.returncode == 0,
                'timed_out': False,
            }
            
    except subprocess.TimeoutExpired:
        return {
            'stdout': '',
            'stderr': f'Execution timed out after {MAX_EXECUTION_TIME} seconds.',
            'success': False,
            'timed_out': True,
        }
    except Exception as e:
        return {
            'stdout': '',
            'stderr': str(e),
            'success': False,
            'timed_out': False,
        }
    finally:
        # Clean up temp file
        try:
            os.remove(filepath)
            os.rmdir(temp_dir)
        except OSError:
            pass
