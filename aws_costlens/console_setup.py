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
            if hasattr(sys.stdout, 'buffer') and not isinstance(sys.stdout, io.TextIOWrapper):
                sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            if hasattr(sys.stderr, 'buffer') and not isinstance(sys.stderr, io.TextIOWrapper):
                sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass  # Ignore errors if already wrapped
    
    _setup_done = True


# Auto-setup on import
setup_console()
