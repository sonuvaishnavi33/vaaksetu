import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.config import settings
from backend.models.session import init_db
from backend.api.routes import router

# Configure logging — never log secrets
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("vaaksetu")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("VaakSetu starting up...")
    init_db()
    logger.info("Database initialised.")
    logger.info("Active LLM provider: %s", settings.get_active_llm())
    yield
    logger.info("VaakSetu shutting down.")


app = FastAPI(
    title="VaakSetu API",
    description="AI-powered multilingual government helpline assistant",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    return {"service": "VaakSetu", "status": "running", "version": "1.0.0"}
