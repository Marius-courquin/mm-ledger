from pydantic import BaseModel, Field

class ConnectorCreate(BaseModel):
    id: str | None = None  # Auto-generated from label if not provided
    type: str
    label: str
    credentials: dict = Field(default_factory=dict, repr=False)
    config: dict = Field(default_factory=dict)

class ConnectorUpdate(BaseModel):
    label: str | None = None
    credentials: dict | None = Field(default=None, repr=False)
    config: dict | None = None

class WorkerInfo(BaseModel):
    state: str = "disconnected"
    pid: int | None = None
    uptime_seconds: float | None = None
    last_error: str | None = None
    last_fetch: str | None = None
    accounts_count: int | None = None
    accounts: list[str] | None = None
    detail: str | None = None

class ConnectorResponse(BaseModel):
    id: str
    type: str
    label: str
    config: dict = Field(default_factory=dict)
    worker: WorkerInfo | None = None

class TwoFARequest(BaseModel):
    code: str = Field(..., min_length=1)
