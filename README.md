# MiniLink URL Shortener

A fast and reliable URL shortener service built with FastAPI, featuring real-time analytics, caching, and asynchronous processing with UUID-based architecture.

## Features

- **URL Shortening**: Create short URLs with custom or auto-generated codes
- **User Management**: UUID-based user system with secure authentication
- **Real-time Analytics**: Track clicks with detailed statistics using Kafka
- **High Performance**: Redis caching and async processing
- **Scalable Architecture**: Microservices design with Docker support
- **Database Migrations**: Alembic support for schema management
- **Health Monitoring**: Built-in health checks for all services

## Database Architecture

### Models
- **User**: UUID-based user accounts with email and password
- **URL**: UUID-based shortened URLs with user ownership and expiration
- **ClickEvent**: Analytics tracking with country, device, and referrer data

### Key Features
- UUID primary keys for better scalability
- Proper foreign key relationships with cascading deletes
- Optimized indexes for high-performance queries
- Async SQLAlchemy with PostgreSQL backend

## Architecture

```
├── app/
│   ├── api/
│   │   └── routes/          # API endpoints (URLs, users, health)
│   ├── models/              # Database models (User, URL, ClickEvent)
│   ├── schemas/             # Pydantic schemas with UUID support
│   ├── services/            # Business logic (URL, User services)
│   ├── worker/              # Background workers (click processing)
│   └── core/                # Configuration and database clients
├── alembic/                 # Database migrations
│   ├── versions/            # Migration files
│   └── env.py              # Async migration environment
├── docker-compose.yml       # Multi-service setup
├── Dockerfile              # Container definition
├── requirements.txt        # Python dependencies
├── db_manager.py           # Database management script
└── main.py                 # FastAPI application
```

## Quick Start

1. **Clone and setup environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

2. **Start services with Docker:**
   ```bash
   docker-compose up -d
   ```

3. **Run database migrations:**
   ```bash
   # Using the database manager script
   python db_manager.py migrate
   
   # Or using Alembic directly
   alembic upgrade head
   ```

4. **Access the application:**
   - API: http://localhost:8000
   - Documentation: http://localhost:8000/docs
   - Health Check: http://localhost:8000/health

## Database Setup

### One Command: Migrate to Latest Version
Use one of these commands to always apply all pending migrations to the newest revision (`head`):

```bash
python db_manager.py migrate
```

```bash
alembic upgrade head
```

If this is the first Alembic run on a database where tables were already created manually, run:

```bash
alembic stamp 001_initial_migration
alembic upgrade head
```

### Using Alembic Migrations (Recommended)
```bash
# Run existing migrations
python db_manager.py migrate

# Create new migration after model changes
python db_manager.py makemigration "Add new feature"
alembic revision --autogenerate -m "initial_migration"
# Apply migrations
alembic upgrade head
```

### Manual Table Creation (Development)
```bash
# Create all tables
python db_manager.py create

# Drop all tables (careful!)
python db_manager.py drop
```

## API Endpoints

### User Management
- `POST /register` - Create user account

### Authentication
- `POST /auth/login` - Login and receive JWT access token
- `POST /auth/google` - Login with Google credential and receive JWT access token

### User URLs
- `GET /users/me/urls` - Get current user's URLs (requires Bearer token)

### Core URL Functionality
- `POST /shorten` - Create short URL (guest supported; ownership set when logged in)
- `GET /{short_code}` - Redirect to original URL
- `GET /{short_code}/info` - Get URL information
- `PUT /{short_code}` - Update URL (owner only, requires Bearer token)
- `DELETE /{short_code}` - Delete URL (owner only, requires Bearer token)
- `GET /{short_code}/stats` - Get analytics (owner only, requires Bearer token)

### System Monitoring
- `GET /health` - Service health check
- `GET /` - Welcome message and version info

## Usage Examples

### Create a User Account
```bash
curl -X POST "http://localhost:8000/register" \
     -H "Content-Type: application/json" \
     -d '{
       "email": "user@example.com",
       "password": "securepassword123"
     }'
```

### Create a Short URL
```bash
curl -X POST "http://localhost:8000/shorten" \
     -H "Content-Type: application/json" \
     -d '{
       "original_url": "https://example.com/very/long/url/path",
       "custom_code": "mylink",
       "expires_in_days": 30
     }'
```

### Login and Get Access Token
```bash
curl -X POST "http://localhost:8000/auth/login" \
     -H "Content-Type: application/json" \
     -d '{
       "email": "user@example.com",
       "password": "securepassword123"
     }'
```

### Login with Google Credential
```bash
curl -X POST "http://localhost:8000/auth/google" \
     -H "Content-Type: application/json" \
     -d '{
       "credential": "<google_id_token_credential>"
     }'
```

### Get URL Statistics (Owner Only)
```bash
curl "http://localhost:8000/mylink/stats" \
     -H "Authorization: Bearer <access_token>"
```

### Get User's URLs
```bash
curl "http://localhost:8000/users/me/urls?limit=10" \
     -H "Authorization: Bearer <access_token>"
```

## Services

- **FastAPI App** (Port 8000): Main application
- **PostgreSQL 16** (Port 5432): Primary database
- **Redis 7** (Port 6379): Caching layer
- **Apache Kafka** (Port 9092): Message queue for analytics
- **Click Consumer Worker**: Processes click events asynchronously

## Development

### Local Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Start individual services
uvicorn main:app --reload --port 8000
python -m app.worker.click_consumer
```

### Database Migration
The application automatically creates tables on startup. For production, consider using Alembic for migrations.

### Environment Variables
See `.env.example` for all configuration options.

Google login requires setting `GOOGLE_CLIENT_ID` to your OAuth client id.

## Production Considerations

1. **Security**: Change default SECRET_KEY
2. **CORS**: Configure allowed origins
3. **Database**: Use managed PostgreSQL service
4. **Monitoring**: Add logging and metrics
5. **SSL**: Enable HTTPS in production
6. **Scaling**: Use Kubernetes or container orchestration

## License

MIT License - see LICENSE file for details.

```bash
Frontend                    Backend                     Google
   |                           |                           |
   |── POST /api/auth/google ──>|                           |
   |   { credential: "..." }   |── verify_oauth2_token() ──>|
   |                           |<── { sub, email, name } ───|
   |                           |                           |
   |                           |── SELECT user WHERE       |
   |                           |   google_id = sub         |
   |                           |── INSERT/UPDATE user       |
   |                           |── CREATE JWT (app token)  |
   |<── { access_token, user } ─|                           |
   |                           |                           |
   |── GET /api/auth/me ───────>|                           |
   |   Authorization: Bearer   |── verify JWT              |
   |                           |── SELECT user WHERE id=sub|
   |<── { user } ───────────── |                           |
```
