export type Source = {
  index: number;
  id: number;
  document_id?: string | null;
  source: string;
  filename: string;
  page_number?: number | null;
  chunk_index?: number | null;
  bbox?: number[] | null;
  similarity: number;
  rerank_score: number;
  quote: string;
};

export type Metrics = {
  retrieval_ms?: number;
  first_token_ms?: number | null;
  generation_tokens_per_second?: number | null;
  prompt_tokens_per_second?: number | null;
  queue_wait_ms?: number;
  total_ms?: number;
  profile?: string | null;
  cache_hit?: boolean;
};

export type ResponseProfile = {
  id: "auto" | "fast" | "balanced" | "quality";
  label: string;
  model: string;
  description: string;
  top_k: number;
  max_tokens: number;
  num_ctx: number;
  available: boolean;
};

export type Health = {
  status: "healthy" | "degraded";
  embedding_model: string;
  chat_model: string;
  reranking: boolean;
  queue: { active: number; waiting: number; capacity: number; active_seconds: number };
  warmup?: { status: string; models: string[]; error?: string | null };
  query_cache?: { entries: number; capacity: number };
  ollama?: { status: string; models?: number; error?: string };
  neon?: { status: string; stored_documents?: number; stored_chunks?: number; error?: string };
};

export type ConversationSummary = {
  id: string;
  title: string;
  model: string;
  created_at: string;
  updated_at: string;
  message_count: number;
};

export type StoredMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  metrics: Metrics;
  created_at: string;
};

export type Conversation = ConversationSummary & { messages: StoredMessage[] };

export type DocumentRecord = {
  id: string;
  source: string;
  filename: string;
  media_type: string;
  status: string;
  pages: number;
  chunks: number;
  checksum_sha256: string;
  error?: string | null;
  created_at: string;
};

export type CurrentUser = { id: string; name: string; role: "admin" | "user" };

export type IngestionJob = {
  id: string;
  filename: string;
  source: string;
  status: "queued" | "running" | "ready" | "failed";
  phase: string;
  progress: number;
  document_id?: string | null;
  error?: string | null;
  created_at: string;
  updated_at: string;
};

export type EvaluationRun = {
  id: string;
  status: "running" | "ready" | "failed";
  total: number;
  completed: number;
  top1_rate: number;
  top3_rate: number;
  evidence_rate: number;
  mrr: number;
  average_retrieval_ms: number;
  error?: string | null;
  created_at: string;
  finished_at?: string | null;
};

export type UserRecord = {
  id: string;
  name: string;
  role: "admin" | "user";
  active: boolean;
  created_at: string;
};

const DEFAULT_API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");
const API_URL_NAME = "local-rag-api-url";
const KEY_NAME = "local-rag-api-key";

export function storedApiUrl(): string {
  return localStorage.getItem(API_URL_NAME) || DEFAULT_API_BASE;
}

export function storeApiUrl(value: string): void {
  const normalized = value.trim().replace(/\/$/, "");
  if (normalized) localStorage.setItem(API_URL_NAME, normalized);
  else localStorage.removeItem(API_URL_NAME);
}

export function displayApiUrl(): string {
  return storedApiUrl() || window.location.origin;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function storedApiKey(): string {
  return sessionStorage.getItem(KEY_NAME) || "";
}

export function storeApiKey(value: string): void {
  if (value) sessionStorage.setItem(KEY_NAME, value);
  else sessionStorage.removeItem(KEY_NAME);
}

function authHeaders(json = false): HeadersInit {
  const headers: Record<string, string> = {};
  const key = storedApiKey();
  if (key) headers["X-API-Key"] = key;
  if (json) headers["Content-Type"] = "application/json";
  return headers;
}

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${storedApiUrl()}${path}`, {
    ...init,
    headers: { ...authHeaders(Boolean(init.body && !(init.body instanceof FormData))), ...init.headers },
    credentials: "same-origin"
  });
  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const payload = await response.json();
      message = payload.detail || message;
    } catch {
      // Keep the status-based message for non-JSON failures.
    }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

export const getHealth = () => requestJson<Health>("/health");

export async function getModels(): Promise<string[]> {
  const payload = await requestJson<{ data: { id: string }[] }>("/v1/models");
  return payload.data.map((model) => model.id);
}

export async function getProfiles(): Promise<ResponseProfile[]> {
  const payload = await requestJson<{ data: ResponseProfile[] }>("/v1/profiles");
  return payload.data;
}

export const getCurrentUser = () => requestJson<CurrentUser>("/v1/me");

export async function getIngestionJobs(): Promise<IngestionJob[]> {
  const payload = await requestJson<{ data: IngestionJob[] }>("/v1/ingestion-jobs");
  return payload.data;
}

export async function getEvaluations(): Promise<EvaluationRun[]> {
  const payload = await requestJson<{ data: EvaluationRun[] }>("/v1/evaluations");
  return payload.data;
}

export const startEvaluation = () =>
  requestJson<{ id: string; status: string }>("/v1/evaluations", { method: "POST" });

export async function getUsers(): Promise<UserRecord[]> {
  const payload = await requestJson<{ data: UserRecord[] }>("/v1/users");
  return payload.data;
}

export const createUser = (name: string, role: "admin" | "user") =>
  requestJson<UserRecord & { api_key: string; notice: string }>("/v1/users", {
    method: "POST",
    body: JSON.stringify({ name, role })
  });

export const setDocumentPermission = (documentId: string, userId: string) =>
  requestJson(`/v1/documents/${documentId}/permissions`, {
    method: "PUT",
    body: JSON.stringify({ user_id: userId, can_read: true, can_write: false })
  });

export async function getConversations(): Promise<ConversationSummary[]> {
  const payload = await requestJson<{ data: ConversationSummary[] }>("/v1/conversations");
  return payload.data;
}

export const getConversation = (id: string) =>
  requestJson<Conversation>(`/v1/conversations/${id}`);

export const deleteConversation = (id: string) =>
  requestJson<{ deleted: boolean }>(`/v1/conversations/${id}`, { method: "DELETE" });

export async function getDocuments(): Promise<DocumentRecord[]> {
  const payload = await requestJson<{ data: DocumentRecord[] }>("/v1/documents");
  return payload.data;
}

export function uploadDocument(file: File, source: string): Promise<IngestionJob> {
  const form = new FormData();
  form.append("file", file);
  if (source.trim()) form.append("source", source.trim());
  return requestJson("/v1/ingestion-jobs", { method: "POST", body: form });
}

export const cancelChat = (requestId: string) =>
  requestJson<{ cancelled: boolean }>(`/v1/chat/cancel/${requestId}`, { method: "POST" });

type StreamCallbacks = {
  onQueue: (requestId: string, position: number) => void;
  onStart: (conversationId: string | null, sources: Source[], model?: string) => void;
  onToken: (token: string) => void;
  onComplete: (sources: Source[], metrics: Metrics, finishReason: string) => void;
};

export async function streamChat(
  payload: {
    model: string;
    messages: { role: "user" | "assistant"; content: string }[];
    conversation_id?: string;
    document_id?: string;
    profile?: "auto" | "fast" | "balanced" | "quality";
    stream: true;
    max_tokens: number;
  },
  callbacks: StreamCallbacks,
  signal: AbortSignal
): Promise<void> {
  const response = await fetch(`${storedApiUrl()}/v1/chat/completions`, {
    method: "POST",
    headers: authHeaders(true),
    credentials: "same-origin",
    body: JSON.stringify(payload),
    signal
  });
  if (!response.ok || !response.body) {
    let message = `Chat failed with status ${response.status}`;
    try {
      const body = await response.json();
      message = body.detail || message;
    } catch {
      // Keep the status-based message.
    }
    throw new ApiError(response.status, message);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() || "";
    for (const frame of frames) {
      const data = frame
        .split(/\r?\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim())
        .join("\n");
      if (!data || data === "[DONE]") continue;
      const event = JSON.parse(data);
      if (event.error) throw new ApiError(500, event.error.message || "Streaming failed");
      if (event.object === "rag.queue") {
        callbacks.onQueue(event.id, event.position || 0);
        continue;
      }
      if (event.sources && event.choices?.[0]?.delta?.role) {
        callbacks.onStart(event.conversation_id || null, event.sources, event.model);
      }
      const token = event.choices?.[0]?.delta?.content;
      if (token) callbacks.onToken(token);
      if (event.choices?.[0]?.finish_reason) {
        callbacks.onComplete(
          event.sources || [],
          event.metrics || {},
          event.choices[0].finish_reason
        );
      }
    }
    if (done) break;
  }
}
