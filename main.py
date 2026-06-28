import uvicorn
from gateway.config import settings

if __name__ == "__main__":
    print("=" * 70)
    print("                      CLAUDE GATEWAY DAEMON")
    print("=" * 70)
    print(f" Running locally on: http://{settings.HOST}:{settings.PORT}")
    print(f" Dashboard console: http://{settings.HOST}:{settings.PORT}/dashboard")
    print("-" * 70)
    print(" To point Claude Code at this gateway, set the following env var:")
    print(f"   Windows (PowerShell): $env:ANTHROPIC_BASE_URL=\"http://{settings.HOST}:{settings.PORT}\"")
    print(f"   macOS / Linux / WSL:  export ANTHROPIC_BASE_URL=\"http://{settings.HOST}:{settings.PORT}\"")
    print("=" * 70)
    
    uvicorn.run(
        "gateway.api.server:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False
    )
