from datetime import datetime
from pydantic import BaseModel


class HealthCheck(BaseModel):
    status: str
    timestamp: datetime
    version: str
    services: dict

