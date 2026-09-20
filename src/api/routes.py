from fastapi import APIRouter, Depends, HTTPException, Request

router = APIRouter()

def shutdown() -> None:
    global DB_POOL
    if DB_POOL is not None:
        DB_POOL.close()
        DB_POOL = None

@router.get('/')
def root():
    index = FRONTEND_DIST / 'index.html'
    if index.exists():
        return FileResponse(index)
    return {'name': 'Local RAG API', 'docs': '/docs', 'health': '/health', 'models': '/v1/models', 'chat': '/v1/chat/completions', 'documents': '/v1/documents', 'upload': '/v1/documents/upload'}

@router.get('/health')
def health() -> JSONResponse:
    checks: dict[str, object] = {}
    healthy = True
    try:
        tags = ollama_get('/api/tags')
        checks['ollama'] = {'status': 'connected', 'models': len(tags.get('models', [])), 'chat_url': OLLAMA_URL, 'embedding_url': EMBEDDING_OLLAMA_URL, 'separate_embedding_runtime': EMBEDDING_OLLAMA_URL != OLLAMA_URL}
    except Exception as exc:
        healthy = False
        checks['ollama'] = {'status': 'unavailable', 'error': str(exc)}
    try:
        with db_connection() as conn:
            count = conn.execute('SELECT COUNT(*) FROM rag_chunks').fetchone()[0]
            document_count = conn.execute("SELECT COUNT(*) FROM rag_documents WHERE status = 'ready'").fetchone()[0]
        checks['database'] = {'status': 'connected', 'stored_documents': document_count, 'stored_chunks': count}
    except Exception as exc:
        healthy = False
        checks['database'] = {'status': 'unavailable', 'error': error_detail(exc)}
    body = {'status': 'healthy' if healthy else 'degraded', 'embedding_model': EMBEDDING_MODEL, 'chat_model': DEFAULT_CHAT_MODEL, 'auto_model_routing': AUTO_MODEL_ROUTING, 'reranking': RERANK_ENABLED, 'security': {'api_key_configured': bool(API_KEY), 'api_key_required': REQUIRE_API_KEY}, 'queue': MODEL_GATE.snapshot(), 'warmup': dict(WARMUP_STATE), 'query_cache': {'entries': cached_query_embedding.cache_info().currsize, 'capacity': cached_query_embedding.cache_info().maxsize}, 'answer_cache': {'memory_entries': len(MEMORY_ANSWER_CACHE), 'memory_capacity': MEMORY_ANSWER_CACHE_SIZE, 'corpus_version_ttl_seconds': CORPUS_VERSION_CACHE_SECONDS}, 'database_pool': dict(DATABASE_POOL_STATE), 'resource_protection': {**dict(RESOURCE_STATE), 'office_hours_active': office_hours_active(), 'minimum_available_ram_gb': MIN_AVAILABLE_RAM_GB, 'maximum_cpu_percent': MAX_SYSTEM_CPU_PERCENT}, 'cross_encoder': {'configured': bool(CROSS_ENCODER_URL), 'url': CROSS_ENCODER_URL or None}, **checks}
    return JSONResponse(body, status_code=200 if healthy else 503)

@router.get('/health/live')
def liveness() -> dict:
    return {'status': 'alive', 'time': int(time.time())}

@router.get('/health/ready')
def readiness() -> JSONResponse:
    return health()

@router.get('/v1/models', dependencies=[Depends(require_api_key)])
def models() -> dict:
    try:
        tags = ollama_get('/api/tags')
    except Exception as exc:
        raise HTTPException(status_code=502, detail=error_detail(exc)) from exc
    created = int(time.time())
    data = [{'id': item.get('name') or item.get('model'), 'object': 'model', 'created': created, 'owned_by': 'ollama'} for item in tags.get('models', [])]
    return {'object': 'list', 'data': data}

@router.get('/v1/profiles', dependencies=[Depends(require_api_key)])
def profiles() -> dict:
    try:
        installed = {item.get('name') or item.get('model') for item in ollama_get('/api/tags').get('models', [])}
    except Exception:
        installed = set()
    return {'object': 'list', 'data': [{'id': profile_id, **config, 'available': config['model'] in installed} for profile_id, config in PROFILE_CONFIG.items()]}

@router.get('/v1/assistant-modes', dependencies=[Depends(require_api_key)])
def assistant_modes() -> dict:
    """Capability declaration for clients; unavailable modes must not be simulated."""
    return {'object': 'list', 'data': [{'id': mode_id, **config} for mode_id, config in ASSISTANT_MODE_CONFIG.items()]}

@router.get('/v1/me')
def current_user(principal: Principal=Depends(require_api_key)) -> dict:
    return {'id': str(principal.id), 'name': principal.name, 'role': principal.role}

@router.get('/v1/users')
def list_users(principal: Principal=Depends(require_admin)) -> dict:
    with db_connection() as conn:
        rows = conn.execute('SELECT id, name, role, active, created_at, requests_per_minute,\n                      max_concurrent_requests, allowed_models, expires_at, last_used_at\n               FROM rag_users ORDER BY created_at').fetchall()
    return {'object': 'list', 'data': [{'id': str(row[0]), 'name': row[1], 'role': row[2], 'active': row[3], 'created_at': row[4].isoformat(), 'requests_per_minute': row[5], 'max_concurrent_requests': row[6], 'allowed_models': row[7] or [], 'expires_at': row[8].isoformat() if row[8] else None, 'last_used_at': row[9].isoformat() if row[9] else None} for row in rows]}

@router.post('/v1/users', status_code=201)
def create_user(request: UserRequest, principal: Principal=Depends(require_admin)) -> dict:
    user_id = uuid.uuid4()
    raw_key = f'rag_{secrets.token_urlsafe(32)}'
    with db_connection() as conn:
        conn.execute('INSERT INTO rag_users (\n                   id, name, api_key_hash, role, requests_per_minute,\n                   max_concurrent_requests, allowed_models, expires_at\n               ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)', (user_id, request.name.strip(), api_key_hash(raw_key), request.role, request.requests_per_minute, request.max_concurrent_requests, json.dumps(request.allowed_models), request.expires_at))
    return {'id': str(user_id), 'name': request.name.strip(), 'role': request.role, 'api_key': raw_key, 'requests_per_minute': request.requests_per_minute, 'max_concurrent_requests': request.max_concurrent_requests, 'allowed_models': request.allowed_models, 'expires_at': request.expires_at.isoformat() if request.expires_at else None, 'notice': 'Copy this API key now. It cannot be retrieved later.'}

@router.patch('/v1/users/{user_id}/limits')
def update_user_limits(user_id: uuid.UUID, request: UserLimitsRequest, principal: Principal=Depends(require_admin)) -> dict:
    if user_id == MASTER_USER_ID:
        raise HTTPException(status_code=400, detail='Environment administrator limits are configured globally')
    with db_connection() as conn:
        row = conn.execute('UPDATE rag_users\n               SET requests_per_minute = %s, max_concurrent_requests = %s,\n                   allowed_models = %s::jsonb, expires_at = %s, active = %s,\n                   updated_at = NOW()\n               WHERE id = %s RETURNING name', (request.requests_per_minute, request.max_concurrent_requests, json.dumps(request.allowed_models), request.expires_at, request.active, user_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail='user not found')
    return {'id': str(user_id), 'name': row[0], **request.model_dump(mode='json')}

@router.post('/v1/users/{user_id}/rotate-key')
def rotate_user_key(user_id: uuid.UUID, principal: Principal=Depends(require_admin)) -> dict:
    if user_id == MASTER_USER_ID:
        raise HTTPException(status_code=400, detail='The environment administrator key is configured in .env')
    raw_key = f'rag_{secrets.token_urlsafe(32)}'
    with db_connection() as conn:
        row = conn.execute('UPDATE rag_users SET api_key_hash = %s, updated_at = NOW() WHERE id = %s AND active RETURNING name', (api_key_hash(raw_key), user_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail='active user not found')
    return {'id': str(user_id), 'name': row[0], 'api_key': raw_key, 'notice': 'The previous API key is now invalid. Copy this key now; it cannot be retrieved later.'}

@router.delete('/v1/users/{user_id}')
def deactivate_user(user_id: uuid.UUID, principal: Principal=Depends(require_admin)) -> dict:
    if user_id == MASTER_USER_ID:
        raise HTTPException(status_code=400, detail='The environment administrator cannot be disabled')
    with db_connection() as conn:
        row = conn.execute('UPDATE rag_users SET active = FALSE, updated_at = NOW() WHERE id = %s RETURNING name', (user_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail='user not found')
    return {'id': str(user_id), 'name': row[0], 'active': False}

@router.put('/v1/documents/{document_id}/permissions')
def set_document_permission(document_id: uuid.UUID, request: PermissionRequest, principal: Principal=Depends(require_admin)) -> dict:
    with db_connection() as conn:
        exists = conn.execute('SELECT 1 FROM rag_documents WHERE id = %s', (document_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail='document not found')
        conn.execute('\n            INSERT INTO rag_document_permissions (document_id, user_id, can_read, can_write)\n            VALUES (%s, %s, %s, %s)\n            ON CONFLICT (document_id, user_id) DO UPDATE\n            SET can_read = EXCLUDED.can_read, can_write = EXCLUDED.can_write\n            ', (document_id, request.user_id, request.can_read, request.can_write))
    invalidate_local_answer_caches()
    return {'document_id': str(document_id), 'user_id': str(request.user_id), 'can_read': request.can_read, 'can_write': request.can_write}

@router.post('/v1/conversations')
def create_conversation(request: ConversationRequest, principal: Principal=Depends(require_api_key)) -> dict:
    conversation_id = uuid.uuid4()
    try:
        with db_connection() as conn:
            conn.execute('INSERT INTO rag_conversations (id, title, model, owner_user_id) VALUES (%s, %s, %s, %s)', (conversation_id, request.title.strip(), request.model, principal.id))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=error_detail(exc)) from exc
    return {'id': str(conversation_id), 'object': 'rag.conversation', 'title': request.title.strip(), 'model': request.model, 'messages': []}

@router.get('/v1/conversations')
def list_conversations(limit: int=50, offset: int=0, principal: Principal=Depends(require_api_key)) -> dict:
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    try:
        with db_connection() as conn:
            total = conn.execute('SELECT COUNT(*) FROM rag_conversations WHERE %s OR owner_user_id = %s', (principal.is_admin, principal.id)).fetchone()[0]
            rows = conn.execute('\n                SELECT c.id, c.title, c.model, c.created_at, c.updated_at,\n                       COUNT(m.id) AS message_count, c.training_approved\n                FROM rag_conversations c\n                LEFT JOIN rag_messages m ON m.conversation_id = c.id\n                WHERE %s OR c.owner_user_id = %s\n                GROUP BY c.id\n                ORDER BY c.updated_at DESC\n                LIMIT %s OFFSET %s\n                ', (principal.is_admin, principal.id, limit, offset)).fetchall()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=error_detail(exc)) from exc
    return {'object': 'list', 'total': total, 'data': [{'id': str(row[0]), 'title': row[1], 'model': row[2], 'created_at': row[3].isoformat(), 'updated_at': row[4].isoformat(), 'message_count': row[5], 'training_approved': row[6]} for row in rows]}

@router.get('/v1/conversations/{conversation_id}')
def get_conversation(conversation_id: uuid.UUID, principal: Principal=Depends(require_api_key)) -> dict:
    try:
        with db_connection() as conn:
            conversation = conn.execute('\n                SELECT id, title, model, created_at, updated_at, training_approved\n                FROM rag_conversations WHERE id = %s AND (%s OR owner_user_id = %s)\n                ', (conversation_id, principal.is_admin, principal.id)).fetchone()
            if not conversation:
                raise HTTPException(status_code=404, detail='conversation not found')
            messages = conn.execute('\n                SELECT id, role, content, sources, metrics, created_at\n                FROM rag_messages\n                WHERE conversation_id = %s\n                ORDER BY created_at, id\n                ', (conversation_id,)).fetchall()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=error_detail(exc)) from exc
    return {'id': str(conversation[0]), 'object': 'rag.conversation', 'title': conversation[1], 'model': conversation[2], 'created_at': conversation[3].isoformat(), 'updated_at': conversation[4].isoformat(), 'training_approved': conversation[5], 'messages': [{'id': str(row[0]), 'role': row[1], 'content': row[2], 'sources': row[3], 'metrics': row[4], 'created_at': row[5].isoformat()} for row in messages]}

@router.patch('/v1/conversations/{conversation_id}')
def update_conversation(conversation_id: uuid.UUID, request: ConversationUpdateRequest, principal: Principal=Depends(require_api_key)) -> dict:
    title = ' '.join(request.title.split())
    try:
        with db_connection() as conn:
            row = conn.execute('\n                UPDATE rag_conversations\n                SET title = %s, updated_at = NOW()\n                WHERE id = %s AND (%s OR owner_user_id = %s)\n                RETURNING id, title, model, updated_at\n                ', (title, conversation_id, principal.is_admin, principal.id)).fetchone()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=error_detail(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail='conversation not found')
    return {'id': str(row[0]), 'title': row[1], 'model': row[2], 'updated_at': row[3].isoformat()}

@router.put('/v1/conversations/{conversation_id}/training-approval')
def set_conversation_training_approval(conversation_id: uuid.UUID, request: ConversationTrainingRequest, principal: Principal=Depends(require_admin)) -> dict:
    try:
        with db_connection() as conn:
            row = conn.execute('\n                UPDATE rag_conversations\n                SET training_approved = %s,\n                    training_approved_at = CASE WHEN %s THEN NOW() ELSE NULL END,\n                    training_approved_by = CASE WHEN %s THEN %s ELSE NULL END,\n                    updated_at = NOW()\n                WHERE id = %s\n                RETURNING id, title, training_approved\n                ', (request.approved, request.approved, request.approved, principal.id, conversation_id)).fetchone()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=error_detail(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail='conversation not found')
    return {'id': str(row[0]), 'title': row[1], 'training_approved': row[2]}

@router.delete('/v1/conversations/{conversation_id}')
def delete_conversation(conversation_id: uuid.UUID, principal: Principal=Depends(require_api_key)) -> dict:
    try:
        with db_connection() as conn:
            row = conn.execute('DELETE FROM rag_conversations WHERE id = %s AND (%s OR owner_user_id = %s) RETURNING title', (conversation_id, principal.is_admin, principal.id)).fetchone()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=error_detail(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail='conversation not found')
    return {'deleted': True, 'id': str(conversation_id), 'title': row[0]}

@router.get('/v1/documents')
def list_documents(limit: int=50, offset: int=0, principal: Principal=Depends(require_api_key)) -> dict:
    limit = min(max(limit, 1), 200)
    offset = max(offset, 0)
    try:
        with db_connection() as conn:
            total = conn.execute('SELECT COUNT(*) FROM rag_documents d WHERE %s OR EXISTS (\n                    SELECT 1 FROM rag_document_permissions p\n                    WHERE p.document_id = d.id AND p.user_id = %s AND p.can_read\n                )', (principal.is_admin, principal.id)).fetchone()[0]
            rows = conn.execute('\n                SELECT id, source_name, original_filename, media_type, status,\n                       page_count, chunk_count, checksum_sha256, error_message,\n                       created_at, updated_at, lifecycle_status, document_version,\n                       effective_date, department, document_type, ocr_confidence,\n                       supersedes_id, metadata\n                FROM rag_documents\n                WHERE %s OR EXISTS (\n                    SELECT 1 FROM rag_document_permissions p\n                    WHERE p.document_id = rag_documents.id AND p.user_id = %s AND p.can_read\n                )\n                ORDER BY created_at DESC\n                LIMIT %s OFFSET %s\n                ', (principal.is_admin, principal.id, limit, offset)).fetchall()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=error_detail(exc)) from exc
    return {'object': 'list', 'total': total, 'data': [{'id': str(row[0]), 'source': row[1], 'filename': row[2], 'media_type': row[3], 'status': row[4], 'pages': row[5], 'chunks': row[6], 'checksum_sha256': row[7], 'error': row[8], 'created_at': row[9].isoformat(), 'updated_at': row[10].isoformat(), 'lifecycle_status': row[11], 'document_version': row[12], 'effective_date': row[13].isoformat() if row[13] else None, 'department': row[14], 'document_type': row[15], 'ocr_confidence': row[16], 'supersedes_id': str(row[17]) if row[17] else None, 'metadata': row[18] or {}} for row in rows]}

@router.patch('/v1/documents/{document_id}/lifecycle')
def update_document_lifecycle(document_id: uuid.UUID, request: DocumentLifecycleRequest, principal: Principal=Depends(require_admin)) -> dict:
    if request.supersedes_id == document_id:
        raise HTTPException(status_code=422, detail='A document cannot supersede itself')
    try:
        with db_connection() as conn:
            if request.supersedes_id:
                previous = conn.execute('SELECT id FROM rag_documents WHERE id = %s', (request.supersedes_id,)).fetchone()
                if not previous:
                    raise HTTPException(status_code=404, detail='Superseded document not found')
                conn.execute("UPDATE rag_documents SET lifecycle_status = 'superseded', updated_at = NOW() WHERE id = %s", (request.supersedes_id,))
            row = conn.execute('UPDATE rag_documents\n                   SET lifecycle_status = %s, supersedes_id = %s, updated_at = NOW()\n                   WHERE id = %s\n                   RETURNING source_name, lifecycle_status, supersedes_id', (request.lifecycle_status, request.supersedes_id, document_id)).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail='document not found')
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=error_detail(exc)) from exc
    invalidate_local_answer_caches()
    return {'id': str(document_id), 'source': row[0], 'lifecycle_status': row[1], 'supersedes_id': str(row[2]) if row[2] else None}

@router.delete('/v1/documents/{document_id}')
def delete_document(document_id: uuid.UUID, principal: Principal=Depends(require_api_key)) -> dict:
    try:
        with db_connection() as conn:
            row = conn.execute('DELETE FROM rag_documents d WHERE id = %s AND (%s OR owner_user_id = %s OR EXISTS (\n                    SELECT 1 FROM rag_document_permissions p\n                    WHERE p.document_id = d.id AND p.user_id = %s AND p.can_write\n                )) RETURNING source_name, chunk_count', (document_id, principal.is_admin, principal.id, principal.id)).fetchone()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=error_detail(exc)) from exc
    if not row:
        raise HTTPException(status_code=404, detail='document not found')
    invalidate_local_answer_caches()
    return {'deleted': True, 'id': str(document_id), 'source': row[0], 'chunks': row[1]}

@router.post('/v1/documents')
def ingest_document(request: DocumentRequest, principal: Principal=Depends(require_api_key)) -> dict:
    if request.replace and (not principal.is_admin):
        raise HTTPException(403, 'Only administrators can replace a document')
    try:
        page = DocumentPage(number=request.page_number or 1, text=request.text)
        return store_document(filename=request.source, source=request.source, media_type='text/plain', raw_data=request.text.encode('utf-8'), pages=[page], chunk_size=request.chunk_size, overlap=request.overlap, replace=request.replace and principal.is_admin, owner_user_id=principal.id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=error_detail(exc)) from exc

@router.post('/v1/ingestion-jobs', status_code=202)
async def create_ingestion_job(file: UploadFile=File(...), source: str | None=Form(default=None), replace: bool=Form(default=False), chunk_size: int=Form(default=900, ge=200, le=4000), overlap: int=Form(default=120, ge=0, le=1000), principal: Principal=Depends(require_api_key)) -> dict:
    ensure_generation_resources()
    filename = Path(file.filename or 'upload').name
    data = await read_upload_limited(file)
    content_type = file.content_type
    await file.close()
    if not data:
        raise HTTPException(status_code=422, detail='uploaded file is empty')
    if replace and (not principal.is_admin):
        raise HTTPException(status_code=403, detail='Only administrators can replace a document')
    job_id = uuid.uuid4()
    checksum = hashlib.sha256(data).hexdigest()
    with db_connection() as conn:
        pending_jobs = conn.execute("SELECT COUNT(*) FROM rag_ingestion_jobs WHERE status IN ('queued', 'running')").fetchone()[0]
    if pending_jobs >= MAX_PENDING_INGESTION_JOBS:
        raise HTTPException(status_code=429, detail='The ingestion queue is full. Wait for an active document to finish.', headers={'Retry-After': '15'})
    if not replace:
        with db_connection() as conn:
            duplicate = conn.execute("SELECT d.id FROM rag_documents d\n                   WHERE checksum_sha256 = %s AND status = 'ready' AND (%s OR EXISTS (\n                     SELECT 1 FROM rag_document_permissions p WHERE p.document_id = d.id\n                     AND p.user_id = %s AND p.can_read))", (checksum, principal.is_admin, principal.id)).fetchone()
            if duplicate:
                conn.execute('INSERT INTO rag_document_permissions (document_id, user_id, can_read, can_write)\n                       VALUES (%s, %s, TRUE, FALSE)\n                       ON CONFLICT (document_id, user_id) DO UPDATE SET can_read = TRUE', (duplicate[0], principal.id))
                conn.execute("\n                    INSERT INTO rag_ingestion_jobs (\n                        id, owner_user_id, filename, source_name, status, phase,\n                        progress, document_id\n                    ) VALUES (%s, %s, %s, %s, 'ready', 'duplicate', 100, %s)\n                    ", (job_id, principal.id, filename, (source or filename).strip() or filename, duplicate[0]))
                return {'id': str(job_id), 'status': 'ready', 'phase': 'duplicate', 'progress': 100, 'document_id': str(duplicate[0])}
    INGESTION_DIR.mkdir(parents=True, exist_ok=True)
    file_path = INGESTION_DIR / f'{job_id}{Path(filename).suffix.lower()}'
    file_path.write_bytes(data)
    source_name = (source or filename).strip() or filename
    with db_connection() as conn:
        conn.execute("\n            INSERT INTO rag_ingestion_jobs (\n                id, owner_user_id, filename, source_name, status, phase, progress\n            ) VALUES (%s, %s, %s, %s, 'queued', 'queued', 0)\n            ", (job_id, principal.id, filename, source_name))
    threading.Thread(target=run_ingestion_job, args=(job_id, file_path, filename, content_type, source_name, replace, chunk_size, overlap, principal.id), name=f'rag-ingest-{job_id.hex[:8]}', daemon=True).start()
    return {'id': str(job_id), 'status': 'queued', 'phase': 'queued', 'progress': 0}

@router.get('/v1/ingestion-jobs')
def list_ingestion_jobs(principal: Principal=Depends(require_api_key), limit: int=20) -> dict:
    with db_connection() as conn:
        rows = conn.execute('\n            SELECT id, filename, source_name, status, phase, progress, document_id,\n                   error_message, created_at, updated_at\n            FROM rag_ingestion_jobs\n            WHERE %s OR owner_user_id = %s\n            ORDER BY created_at DESC LIMIT %s\n            ', (principal.is_admin, principal.id, min(max(limit, 1), 100))).fetchall()
    return {'object': 'list', 'data': [{'id': str(row[0]), 'filename': row[1], 'source': row[2], 'status': row[3], 'phase': row[4], 'progress': row[5], 'document_id': str(row[6]) if row[6] else None, 'error': row[7], 'created_at': row[8].isoformat(), 'updated_at': row[9].isoformat()} for row in rows]}

@router.post('/v1/evaluations', status_code=202)
def create_evaluation(request: EvaluationRequest, principal: Principal=Depends(require_admin)) -> dict:
    if request.include_generation and request.pipeline != 'upgraded':
        raise HTTPException(status_code=422, detail='Answer generation is available only for the upgraded pipeline')
    run_id = uuid.uuid4()
    with db_connection() as conn:
        conn.execute('INSERT INTO rag_evaluation_runs (\n                   id, owner_user_id, pipeline_version, include_generation\n               ) VALUES (%s, %s, %s, %s)', (run_id, principal.id, request.pipeline, request.include_generation))
    threading.Thread(target=run_retrieval_evaluation, args=(run_id, principal, request.pipeline, request.include_generation), name=f'rag-eval-{run_id.hex[:8]}', daemon=True).start()
    return {'id': str(run_id), 'status': 'running', 'pipeline': request.pipeline}

@router.get('/v1/evaluations')
def list_evaluations(principal: Principal=Depends(require_admin), limit: int=10) -> dict:
    with db_connection() as conn:
        rows = conn.execute('\n            SELECT id, status, total_questions, completed_questions, top1_hits,\n                   top3_hits, top5_hits, evidence_hits, mean_reciprocal_rank,\n                   average_retrieval_ms, dataset_version, pipeline_version,\n                   include_generation, citation_correct_hits, grounded_answer_hits,\n                   unsupported_claim_hits, refusal_correct_hits, generated_questions,\n                   total_first_token_ms, total_latency_ms, total_generation_tps,\n                   cache_hits, error_message, created_at, finished_at\n            FROM rag_evaluation_runs ORDER BY created_at DESC LIMIT %s\n            ', (min(max(limit, 1), 50),)).fetchall()
    return {'object': 'list', 'data': [evaluation_payload(row) for row in rows]}

@router.post('/v1/documents/upload')
async def upload_document(file: UploadFile=File(...), source: str | None=Form(default=None), replace: bool=Form(default=False), chunk_size: int=Form(default=900, ge=200, le=4000), overlap: int=Form(default=120, ge=0, le=1000), principal: Principal=Depends(require_api_key)) -> dict:
    ensure_generation_resources()
    filename = Path(file.filename or 'upload').name
    data = await read_upload_limited(file)
    await file.close()
    if not data:
        raise HTTPException(status_code=422, detail='uploaded file is empty')
    if replace and (not principal.is_admin):
        raise HTTPException(status_code=403, detail='Only administrators can replace a document')
    try:
        return await run_in_threadpool(ingest_uploaded_data, data, filename, file.content_type, (source or filename).strip() or filename, replace, chunk_size, overlap, principal.id)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=error_detail(exc)) from exc

@router.get('/v1/queue', dependencies=[Depends(require_api_key)])
def queue_status() -> dict:
    return MODEL_GATE.snapshot()

@router.get('/v1/metrics/summary')
def metrics_summary(hours: int=24, principal: Principal=Depends(require_admin)) -> dict:
    window = min(max(hours, 1), 24 * 30)
    numeric_fields = ('total_ms', 'first_token_ms', 'retrieval_ms', 'query_embedding_ms', 'hybrid_search_ms', 'context_enrichment_ms', 'load_ms', 'queue_wait_ms', 'generation_ms', 'validation_ms', 'model_first_token_ms', 'first_visible_text_ms')
    with db_connection() as conn:
        row = conn.execute("\n            SELECT COUNT(*),\n                   AVG(CASE WHEN COALESCE((metrics->>'cache_hit')::boolean, FALSE) THEN 1 ELSE 0 END),\n                   percentile_cont(0.5) WITHIN GROUP (ORDER BY (metrics->>'total_ms')::double precision),\n                   percentile_cont(0.95) WITHIN GROUP (ORDER BY (metrics->>'total_ms')::double precision),\n                   AVG((metrics->>'generation_tokens_per_second')::double precision)\n            FROM rag_messages\n            WHERE role = 'assistant' AND metrics ? 'total_ms'\n              AND metrics->>'timing_scope' = 'server_before_persistence_and_transport'\n              AND created_at >= NOW() - (%s * INTERVAL '1 hour')\n            ", (window,)).fetchone()
        component_rows = conn.execute("\n            SELECT key, AVG(value::double precision),\n                   percentile_cont(0.95) WITHIN GROUP (ORDER BY value::double precision)\n            FROM rag_messages, LATERAL jsonb_each_text(metrics) item(key, value)\n            WHERE role = 'assistant' AND key = ANY(%s)\n              AND metrics->>'timing_scope' = 'server_before_persistence_and_transport'\n              AND value ~ '^[0-9]+(?:\\.[0-9]+)?$'\n              AND created_at >= NOW() - (%s * INTERVAL '1 hour')\n            GROUP BY key\n            ", (list(numeric_fields), window)).fetchall()
    return {'window_hours': window, 'samples': int(row[0] or 0), 'timing_scope': 'server_before_persistence_and_transport', 'legacy_samples_excluded': True, 'cache_hit_rate': round(float(row[1]), 4) if row[1] is not None else None, 'total_ms': {'p50': round(float(row[2]), 2) if row[2] is not None else None, 'p95': round(float(row[3]), 2) if row[3] is not None else None}, 'generation_tokens_per_second': round(float(row[4]), 2) if row[4] is not None else None, 'components': {key: {'average_ms': round(float(average or 0), 2), 'p95_ms': round(float(p95 or 0), 2)} for key, average, p95 in component_rows}, 'resource_protection': dict(RESOURCE_STATE)}

@router.post('/v1/chat/cancel/{request_id}')
def cancel_chat(request_id: str, principal: Principal=Depends(require_api_key)) -> dict:
    with CANCEL_EVENTS_LOCK:
        active = CANCEL_EVENTS.get(request_id)
    if not active or active[0] != principal.id:
        raise HTTPException(status_code=404, detail='active request not found')
    active[1].set()
    return {'cancelled': True, 'request_id': request_id}

@router.post('/v1/chat/completions')
def chat_completions(request: ChatCompletionRequest, principal: Principal=Depends(require_api_key)):
    if request.stream:
        validate_assistant_mode_request(request)
        return StreamingResponse(streaming_chat(request, principal), media_type='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})
    started = time.perf_counter()
    question = last_user_question(request.messages)
    assistant_mode = validate_assistant_mode_request(request)
    settings = {**response_settings(request, question), 'assistant_mode': assistant_mode}
    effective_model = str(settings['model'])
    enforce_model_access(principal, effective_model)
    cache_started = time.perf_counter()
    cache_descriptor = cache_identity(request, question, settings, principal)
    cached = get_cached_answer(cache_descriptor[0], principal) if cache_descriptor else None
    cache_lookup_ms = (time.perf_counter() - cache_started) * 1000
    if cached:
        conversation_id = prepare_conversation(request, question, effective_model, principal)
        cached = {**cached, 'metrics': fresh_cache_metrics(cached, started, cache_lookup_ms)}
        save_assistant_message(conversation_id, cached['answer'], cached['sources'], cached['metrics'])
        return {'id': f'chatcmpl-{uuid.uuid4().hex}', 'object': 'chat.completion', 'created': int(time.time()), 'model': effective_model, 'profile': settings['profile'], 'conversation_id': str(conversation_id) if conversation_id else None, 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': cached['answer']}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0}, 'sources': cached['sources'], 'metrics': cached['metrics']}
    try:
        ensure_generation_resources()
        with principal_generation_slot(principal), QueueLease(MODEL_GATE) as lease:
            ensure_generation_resources()
            conversation_id = prepare_conversation(request, question, effective_model, principal)
            retrieval_started = time.perf_counter()
            retrieval_timings: dict[str, object] = {}
            search_question = document_search_query(request.messages) if assistant_mode == 'company_knowledge' else question
            rows, grounded = retrieve_for_assistant_mode(assistant_mode, request.messages, retrieval_depth(question, int(settings['top_k'])), request.document_id, principal, retrieval_timings)
            retrieval_timings['assistant_mode'] = assistant_mode
            packing_started = time.perf_counter()
            rows = pack_context_rows(rows, int(settings['num_ctx']), request.messages, int(settings['max_tokens']))
            record_timing(retrieval_timings, 'context_packing_ms', packing_started)
            confidence = retrieval_confidence(rows, str(retrieval_timings.get('intent', 'factual')))
            retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
            generation_started = time.perf_counter()
            result = ollama_post('/api/chat', {'model': effective_model, 'messages': grounded_messages(request.messages, rows, grounded, summary_mode=is_summary_request(question), principal=principal, confidence=confidence, assistant_mode=assistant_mode), 'think': False, 'stream': False, 'options': ollama_options(request, settings), 'keep_alive': MODEL_KEEP_ALIVE}, timeout=300)
            generation_ms = (time.perf_counter() - generation_started) * 1000
    except HTTPException:
        raise
    except QueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc), headers={'Retry-After': '10'}) from exc
    except QueueTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=error_detail(exc)) from exc
    prompt_tokens = result.get('prompt_eval_count', 0)
    completion_tokens = result.get('eval_count', 0)
    elapsed_ms = (time.perf_counter() - started) * 1000
    sources = source_payload(rows)
    metrics = metrics_from_ollama(result, retrieval_ms, elapsed_ms)
    metrics.update(retrieval_timings)
    metrics['retrieval_confidence'] = confidence
    metrics['cache_lookup_ms'] = round(cache_lookup_ms, 2)
    metrics['queue_wait_ms'] = round(lease.wait_ms, 2)
    metrics['profile'] = settings['profile']
    metrics['prompt_version'] = RAG_PROMPT_VERSION
    metrics['query_rewritten'] = search_question != question
    answer = result.get('message', {}).get('content', '')
    validation_started = time.perf_counter()
    grounding_validation = validate_live_answer(answer, sources, grounded)
    if STRICT_CITATION_GATE and grounded and (not grounding_validation['valid']):
        answer = "I couldn't find that information in the available documents."
        grounding_validation['blocked_original_answer'] = True
    metrics['grounding_validation'] = public_grounding_validation(grounding_validation)
    metrics['generation_ms'] = round(generation_ms, 2)
    metrics['validation_ms'] = round((time.perf_counter() - validation_started) * 1000, 2)
    metrics['total_ms'] = round((time.perf_counter() - started) * 1000, 2)
    metrics['first_token_ms'] = metrics['first_visible_text_ms'] = metrics['total_ms']
    metrics['model_first_token_ms'] = None
    metrics['buffered_for_validation'] = bool(STRICT_CITATION_GATE and grounded)
    metrics['timing_scope'] = 'server_before_persistence_and_transport'
    if cache_descriptor:
        store_cached_answer(cache_descriptor[0], cache_descriptor[1], question, settings, answer, sources, metrics)
    save_assistant_message(conversation_id, answer, sources, metrics)
    return {'id': f'chatcmpl-{uuid.uuid4().hex}', 'object': 'chat.completion', 'created': int(time.time()), 'model': effective_model, 'profile': settings['profile'], 'conversation_id': str(conversation_id) if conversation_id else None, 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': answer}, 'finish_reason': 'stop'}], 'usage': {'prompt_tokens': prompt_tokens, 'completion_tokens': completion_tokens, 'total_tokens': prompt_tokens + completion_tokens}, 'sources': sources, 'metrics': metrics}

@router.get('/{frontend_path:path}', include_in_schema=False)
def frontend_fallback(frontend_path: str):
    if frontend_path.startswith(('v1/', 'health', 'docs', 'redoc', 'openapi.json')):
        raise HTTPException(status_code=404, detail='not found')
    index = FRONTEND_DIST / 'index.html'
    if not index.exists():
        raise HTTPException(status_code=404, detail='frontend is not built')
    return FileResponse(index)

