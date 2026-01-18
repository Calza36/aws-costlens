"""Console setup for Windows UTF-8 compatibility."""

import sys

# Only setup once
_setup_done = False


def setup_console():
    """Configure console for UTF-8 output on Windows."""
    global _setup_done
    if _setup_done:
        return
    
    if sys.platform == "win32":
        import io
        try:
            # Check if stdout needs UTF-8 reconfiguration
            if hasattr(sys.stdout, 'buffer'):
                # Check current encoding
                current_encoding = getattr(sys.stdout, 'encoding', '').lower()
                if current_encoding != 'utf-8':
                    sys.stdout = io.TextIOWrapper(
                        sys.stdout.buffer, 
                        encoding="utf-8", 
                        errors="replace",
                        line_buffering=True
                    )
            
            if hasattr(sys.stderr, 'buffer'):
                current_encoding = getattr(sys.stderr, 'encoding', '').lower()
                if current_encoding != 'utf-8':
                    sys.stderr = io.TextIOWrapper(
                        sys.stderr.buffer, 
                        encoding="utf-8", 
                        errors="replace",
                        line_buffering=True
                    )
        except Exception:
            pass  # Ignore errors if already wrapped
    
    _setup_done = True


# Auto-setup on import
setup_console()
