from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

# Import modular routers
from src.api.routes import router as api_router

# Initialize FastAPI application
app = FastAPI(
    title="Local RAG API",
    description="OpenAI-compatible RAG API backed by Ollama and PostgreSQL/pgvector",
    version="1.0.0"
)

# Setup Middlewares (Extracted from core logic)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Update with actual ALLOWED_ORIGINS
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["*"]) # Update with ALLOWED_HOSTS

# Include modular API routes
app.include_router(api_router)

@app.on_event("startup")
async def startup_event():
    # Setup DB, validate config, etc.
    pass

@app.on_event("shutdown")
async def shutdown_event():
    # Cleanup DB connection pools, inference queues
    pass
