import logging
import psutil
from fastapi import Request
from gateway.config import settings

logger = logging.getLogger("claude-gateway.git.context")

# In-memory cache for the last detected CWD, to avoid psutil overhead on every message chunk
_last_detected_cwd = None

def get_client_cwd(request: Request) -> str | None:
    global _last_detected_cwd
    
    # 1. Check custom headers first (for explicit client wrappers or remote usage)
    headers = request.headers
    if "x-working-dir" in headers:
        cwd = headers["x-working-dir"]
        logger.debug(f"CWD from header X-Working-Dir: {cwd}")
        return cwd
        
    # 2. Check client TCP connection port using psutil
    client = request.client
    if not client:
        return _last_detected_cwd
        
    client_host = client.host
    client_port = client.port
    server_port = settings.PORT
    
    # Only try port inspection if connection is local
    if client_host in ("127.0.0.1", "localhost", "::1"):
        try:
            for conn in psutil.net_connections(kind="tcp"):
                if (conn.laddr and conn.laddr.port == client_port and 
                    conn.raddr and conn.raddr.port == server_port):
                    pid = conn.pid
                    if pid:
                        proc = psutil.Process(pid)
                        cwd = proc.cwd()
                        logger.debug(f"Detected client PID {pid} CWD: {cwd}")
                        _last_detected_cwd = cwd
                        return cwd
        except (psutil.AccessDenied, psutil.NoSuchProcess) as e:
            logger.debug(f"Access denied or process not found in psutil search: {e}")
        except Exception as e:
            logger.error(f"Error lookup client CWD: {e}")
            
    return _last_detected_cwd
