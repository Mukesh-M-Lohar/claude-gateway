# Docker Deployment

Run Claude Gateway alongside Redis and Qdrant in a containerized environment.

---

## 1. Quick Start

Run the compose command from the project root:
```bash
docker compose up -d --build
```
This boots three containers:
- **`claude-gateway`** (FastAPI) on port `8000`
- **`claude-gateway-redis`** on port `6379`
- **`claude-gateway-qdrant`** on port `6333`

---

## 2. Process Namespace Isolation (CWD Workaround)

Docker containers run in isolated PID and Network namespaces. By default, `psutil` inside the container **cannot** inspect host ports or PIDs to find which local directory Claude Code is running in.

### Linux Hosts
On Linux, you can resolve this by sharing the host network and process space. Add the following parameters to the `gateway` service in `docker-compose.yml`:
```yaml
network_mode: "host"
pid: "host"
```

### Windows & macOS (Cross-Platform)
Since shared PID namespaces are not supported on Windows/macOS virtual hypervisors, you must pass the working directory explicitly in HTTP headers using Claude Code's custom header configurations.

Add the following shortcut functions to your shell config file (`~/.bashrc`, `~/.zshrc`, or PowerShell profile):

=== "PowerShell Profile"
    ```powershell
    function claude-proxy {
        $env:ANTHROPIC_BASE_URL="http://localhost:8000"
        $env:ANTHROPIC_CUSTOM_HEADERS="X-Working-Dir: $(Get-Location)"
        claude $args
    }
    ```

=== "Bash / Zsh Config"
    ```bash
    function claude-proxy() {
      export ANTHROPIC_BASE_URL="http://localhost:8000"
      export ANTHROPIC_CUSTOM_HEADERS="X-Working-Dir: $(pwd)"
      claude "$@"
    }
    ```

Run `claude-proxy` instead of `claude`. This ensures your active path is always transmitted to the containerized daemon.
