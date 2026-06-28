import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from gateway.api.routes import router
from gateway.storage.sqlite import init_db
from gateway.git.watcher import git_watcher

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("claude-gateway.api.server")

# Instantiate FastAPI App
app = FastAPI(
    title="Claude Gateway",
    description="Local daemon proxy for Claude Code with Exact & Semantic caching",
    version="1.0.0"
)

# Set CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)

@app.on_event("startup")
async def startup_event():
    logger.info("Initializing SQLite database...")
    init_db()
    
    logger.info("Starting background Git Watcher...")
    git_watcher.start()
    
    logger.info("Claude Gateway is ready.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Stopping background Git Watcher...")
    git_watcher.stop()
    logger.info("Claude Gateway stopped.")
