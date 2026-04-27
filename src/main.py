from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from src.auth.exceptions import AuthException
from src.config import settings
from src.database import create_tables, close_db
from src.redis.client import redis_client
from src.kafka.client import create_topics, kafka_producer
from src.auth.router import router as auth_router
from src.urls.router import router as urls_router
from src.health.router import router as health_router

# Ensure all models are registered with SQLAlchemy metadata
import src.auth.models  # noqa: F401
import src.urls.models  # noqa: F401


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    print("Starting MiniLink URL Shortener...")

    # Initialize database tables
    await create_tables()
    print("Database tables created")

    # Connect to Redis
    await redis_client.connect()
    print("Connected to Redis")

    # Create Kafka topics
    await create_topics()
    print("Kafka topics created")

    # Start Kafka producer
    await kafka_producer.start()
    print("Kafka producer started")

    yield

    # Shutdown
    print("Shutting down MiniLink...")

    # Stop Kafka producer
    await kafka_producer.stop()

    # Close database connections
    await close_db()

    # Close Redis connection
    await redis_client.disconnect()

    print("Shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="A fast and reliable URL shortener service",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,   # required for cookies (HttpOnly tokens)
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router, tags=["Health"])
app.include_router(auth_router, tags=["Auth"])
app.include_router(urls_router, tags=["URLs"])


@app.exception_handler(AuthException)
async def auth_exception_handler(request: Request, exc: AuthException):
    """Return a structured error body with both `detail` and `code` for auth errors."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
    )


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to MiniLink URL Shortener",
        "version": settings.app_version,
        "docs": "/docs"
    }


