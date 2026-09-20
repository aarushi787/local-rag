from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class ChatMessage(BaseModel):
    role: Literal['system', 'user', 'assistant']
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = DEFAULT_CHAT_MODEL
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int | None = Field(default=250, ge=1, le=2048)
    max_completion_tokens: int | None = Field(default=None, ge=1, le=2048)
    top_p: float | None = Field(default=None, gt=0, le=1)
    conversation_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    profile: Literal['auto', 'fast', 'balanced', 'quality'] | None = None
    assistant_mode: Literal['company_knowledge', 'general', 'business_analytics'] = 'company_knowledge'
    save: bool = True
    use_cache: bool = True
    replace_last: bool = False

class DocumentRequest(BaseModel):
    source: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=5000000)
    page_number: int | None = Field(default=None, ge=1)
    chunk_size: int = Field(default=900, ge=200, le=4000)
    overlap: int = Field(default=120, ge=0, le=1000)
    replace: bool = False

class ConversationRequest(BaseModel):
    title: str = Field(default='New conversation', min_length=1, max_length=160)
    model: str = Field(default=DEFAULT_CHAT_MODEL, min_length=1, max_length=160)

class ConversationUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)

class ConversationTrainingRequest(BaseModel):
    approved: bool

class UserRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: Literal['admin', 'user'] = 'user'
    requests_per_minute: int = Field(default=30, ge=1, le=600)
    max_concurrent_requests: int = Field(default=1, ge=1, le=4)
    allowed_models: list[str] = Field(default_factory=list, max_length=10)
    expires_at: datetime | None = None

class UserLimitsRequest(BaseModel):
    requests_per_minute: int = Field(ge=1, le=600)
    max_concurrent_requests: int = Field(ge=1, le=4)
    allowed_models: list[str] = Field(default_factory=list, max_length=10)
    expires_at: datetime | None = None
    active: bool = True

class PermissionRequest(BaseModel):
    user_id: uuid.UUID
    can_read: bool = True
    can_write: bool = False

class DocumentLifecycleRequest(BaseModel):
    lifecycle_status: Literal['active', 'superseded', 'archived']
    supersedes_id: uuid.UUID | None = None

class EvaluationRequest(BaseModel):
    pipeline: Literal['baseline', 'upgraded'] = 'upgraded'
    include_generation: bool = False

