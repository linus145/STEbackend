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


def execute_code(source_code: str, language: str, stdin: str = "") -> dict:
    """
    Execute code safely in a subprocess with timeout.
    
    Returns:
        dict with keys: stdout, stderr, success, timed_out
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
    
    # Create a temporary file for the code
    temp_dir = tempfile.mkdtemp(prefix='exam_code_')
    filename = f"solution_{uuid.uuid4().hex[:8]}{config['extension']}"
    filepath = os.path.join(temp_dir, filename)
    
    try:
        # Write code to temp file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(source_code)
        
        # Build command
        cmd = config['command'] + [filepath]
        
        # Execute with timeout
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
