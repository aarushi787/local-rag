import { FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUp,
  Books,
  ChatCircle,
  ChartLineUp,
  Check,
  CircleNotch,
  Copy,
  FileArrowUp,
  FileText,
  Gear,
  Gauge,
  List,
  Moon,
  Plus,
  ShieldCheck,
  SidebarSimple,
  SignIn,
  Sparkle,
  Square,
  Sun,
  Trash,
  X
} from "@phosphor-icons/react";
import {
  Badge,
  Button,
  Dialog,
  IconButton,
  Select,
  TextField,
  Theme,
  Tooltip
} from "@radix-ui/themes";
import {
  ApiError,
  cancelChat,
  createUser,
  CurrentUser,
  deleteConversation,
  DocumentRecord,
  getConversation,
  getConversations,
  getDocuments,
  getEvaluations,
  getHealth,
  getIngestionJobs,
  getModels,
  getProfiles,
  getCurrentUser,
  getUsers,
  Health,
  Metrics,
  ResponseProfile,
  EvaluationRun,
  IngestionJob,
  Source,
  storedApiKey,
  storeApiKey,
  startEvaluation,
  setDocumentPermission,
  streamChat,
  uploadDocument,
  ConversationSummary,
  UserRecord
} from "./api";

type UiMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  metrics: Metrics;
};

const makeId = () => crypto.randomUUID();

function App() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = localStorage.getItem("local-rag-theme");
    if (saved === "light" || saved === "dark") return saved;
    return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  const [health, setHealth] = useState<Health | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState("gemma4:e2b-it-qat");
  const [profiles, setProfiles] = useState<ResponseProfile[]>([]);
  const [profile, setProfile] = useState<ResponseProfile["id"]>("auto");
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [prompt, setPrompt] = useState("");
  const [activeSources, setActiveSources] = useState<Source[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [ingestionJobs, setIngestionJobs] = useState<IngestionJob[]>([]);
  const [evaluations, setEvaluations] = useState<EvaluationRun[]>([]);
  const [users, setUsers] = useState<UserRecord[]>([]);
  const [selectedDocument, setSelectedDocument] = useState("all");
  const [generating, setGenerating] = useState(false);
  const [queuePosition, setQueuePosition] = useState(0);
  const [activeRequestId, setActiveRequestId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(!storedApiKey());
  const [documentsOpen, setDocumentsOpen] = useState(false);
  const [evaluationOpen, setEvaluationOpen] = useState(false);
  const [securityOpen, setSecurityOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [apiKeyInput, setApiKeyInput] = useState(storedApiKey());
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadSource, setUploadSource] = useState("");
  const [uploading, setUploading] = useState(false);
  const [newUserName, setNewUserName] = useState("");
  const [newUserRole, setNewUserRole] = useState<"admin" | "user">("user");
  const [createdApiKey, setCreatedApiKey] = useState("");
  const [permissionUser, setPermissionUser] = useState("");
  const [permissionDocument, setPermissionDocument] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const isHealthy = health?.status === "healthy";
  const latestMetrics = useMemo(
    () => [...messages].reverse().find((message) => message.role === "assistant")?.metrics,
    [messages]
  );

  useEffect(() => {
    localStorage.setItem("local-rag-theme", theme);
  }, [theme]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: generating ? "auto" : "smooth" });
  }, [messages, generating]);

  const handleApiError = (caught: unknown) => {
    const message = caught instanceof Error ? caught.message : "The server could not complete the request.";
    setError(message);
    if (caught instanceof ApiError && caught.status === 401) setSettingsOpen(true);
  };

  const refreshHealth = async () => {
    try {
      setHealth(await getHealth());
    } catch {
      setHealth(null);
    }
  };

  const refreshWorkspace = async () => {
    try {
      const me = await getCurrentUser();
      const [availableModels, responseProfiles, savedConversations, indexedDocuments, jobs] = await Promise.all([
        getModels(),
        getProfiles(),
        getConversations(),
        getDocuments(),
        getIngestionJobs()
      ]);
      setCurrentUser(me);
      setModels(availableModels);
      setProfiles(responseProfiles);
      setConversations(savedConversations);
      setDocuments(indexedDocuments);
      setIngestionJobs(jobs);
      if (me.role === "admin") {
        const [runs, team] = await Promise.all([getEvaluations(), getUsers()]);
        setEvaluations(runs);
        setUsers(team);
      }
      if (availableModels.length && !availableModels.includes(model)) {
        setModel(availableModels[0]);
      }
    } catch (caught) {
      handleApiError(caught);
    }
  };

  useEffect(() => {
    void refreshHealth();
    const timer = window.setInterval(() => void refreshHealth(), 15_000);
    if (storedApiKey()) void refreshWorkspace();
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const activeWork = ingestionJobs.some((job) => job.status === "queued" || job.status === "running")
      || evaluations.some((run) => run.status === "running");
    if (!activeWork || !storedApiKey()) return;
    const timer = window.setInterval(() => void refreshWorkspace(), 2_500);
    return () => window.clearInterval(timer);
  }, [ingestionJobs, evaluations]);

  const saveKey = () => {
    storeApiKey(apiKeyInput.trim());
    setSettingsOpen(false);
    setError("");
    void refreshWorkspace();
  };

  const startNewChat = () => {
    setConversationId(null);
    setMessages([]);
    setActiveSources([]);
    setError("");
    setSidebarOpen(false);
  };

  const openConversation = async (id: string) => {
    if (generating) return;
    try {
      const conversation = await getConversation(id);
      setConversationId(id);
      setModel(conversation.model);
      const matchingProfile = profiles.find((item) => item.model === conversation.model);
      if (matchingProfile) setProfile(matchingProfile.id);
      setMessages(
        conversation.messages.map((message) => ({
          id: message.id,
          role: message.role,
          content: message.content,
          sources: message.sources || [],
          metrics: message.metrics || {}
        }))
      );
      setActiveSources(
        [...conversation.messages].reverse().find((message) => message.sources?.length)?.sources || []
      );
      setSidebarOpen(false);
      setError("");
    } catch (caught) {
      handleApiError(caught);
    }
  };

  const removeConversation = async (id: string) => {
    try {
      await deleteConversation(id);
      if (conversationId === id) startNewChat();
      await refreshWorkspace();
    } catch (caught) {
      handleApiError(caught);
    }
  };

  const sendPrompt = async () => {
    const text = prompt.trim();
    if (!text || generating) return;
    if (!storedApiKey()) {
      setSettingsOpen(true);
      return;
    }

    const userMessage: UiMessage = {
      id: makeId(),
      role: "user",
      content: text,
      sources: [],
      metrics: {}
    };
    const assistantId = makeId();
    const requestMessages = [...messages, userMessage].map(({ role, content }) => ({ role, content }));
    setMessages((current) => [
      ...current,
      userMessage,
      { id: assistantId, role: "assistant", content: "", sources: [], metrics: {} }
    ]);
    setPrompt("");
    setGenerating(true);
    setQueuePosition(0);
    setError("");
    setActiveSources([]);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      await streamChat(
        {
          model,
          messages: requestMessages,
          conversation_id: conversationId || undefined,
          document_id: selectedDocument === "all" ? undefined : selectedDocument,
          profile,
          stream: true,
          max_tokens: 220
        },
        {
          onQueue: (requestId, position) => {
            setActiveRequestId(requestId);
            setQueuePosition(position);
          },
          onStart: (newConversationId, sources, routedModel) => {
            if (newConversationId) setConversationId(newConversationId);
            if (routedModel) setModel(routedModel);
            setActiveSources(sources);
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId ? { ...message, sources } : message
              )
            );
          },
          onToken: (token) => {
            setQueuePosition(0);
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? { ...message, content: message.content + token }
                  : message
              )
            );
          },
          onComplete: (sources, metrics) => {
            setActiveSources(sources);
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId ? { ...message, sources, metrics } : message
              )
            );
          }
        },
        controller.signal
      );
      void refreshWorkspace();
      void refreshHealth();
    } catch (caught) {
      if (!(caught instanceof DOMException && caught.name === "AbortError")) {
        handleApiError(caught);
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantId && !message.content
              ? { ...message, content: "I could not complete this response. Check the server status and try again." }
              : message
          )
        );
      }
    } finally {
      setGenerating(false);
      setQueuePosition(0);
      setActiveRequestId(null);
      abortRef.current = null;
    }
  };

  const stopGeneration = async () => {
    if (activeRequestId) void cancelChat(activeRequestId).catch(() => undefined);
    abortRef.current?.abort();
    setGenerating(false);
  };

  const handleComposerKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendPrompt();
    }
  };

  const openDocuments = async () => {
    setDocumentsOpen(true);
    try {
      setDocuments(await getDocuments());
    } catch (caught) {
      handleApiError(caught);
    }
  };

  const changeProfile = (value: ResponseProfile["id"]) => {
    setProfile(value);
    const selected = profiles.find((item) => item.id === value);
    if (selected) setModel(selected.model);
  };

  const submitUpload = async (event: FormEvent) => {
    event.preventDefault();
    if (!uploadFile) return;
    setUploading(true);
    setError("");
    try {
      const job = await uploadDocument(uploadFile, uploadSource);
      setIngestionJobs((current) => [job, ...current]);
      setUploadFile(null);
      setUploadSource("");
    } catch (caught) {
      handleApiError(caught);
    } finally {
      setUploading(false);
    }
  };

  const openEvaluations = async () => {
    setEvaluationOpen(true);
    try {
      setEvaluations(await getEvaluations());
    } catch (caught) {
      handleApiError(caught);
    }
  };

  const runEvaluation = async () => {
    try {
      const run = await startEvaluation();
      setEvaluations((current) => [{
        id: run.id, status: "running", total: 0, completed: 0, top1_rate: 0,
        top3_rate: 0, evidence_rate: 0, mrr: 0, average_retrieval_ms: 0,
        created_at: new Date().toISOString()
      }, ...current]);
    } catch (caught) {
      handleApiError(caught);
    }
  };

  const openSecurity = async () => {
    setSecurityOpen(true);
    try {
      setUsers(await getUsers());
    } catch (caught) {
      handleApiError(caught);
    }
  };

  const addUser = async (event: FormEvent) => {
    event.preventDefault();
    if (!newUserName.trim()) return;
    try {
      const created = await createUser(newUserName.trim(), newUserRole);
      setCreatedApiKey(created.api_key);
      setNewUserName("");
      setUsers(await getUsers());
    } catch (caught) {
      handleApiError(caught);
    }
  };

  const grantDocumentAccess = async () => {
    if (!permissionUser || !permissionDocument) return;
    try {
      await setDocumentPermission(permissionDocument, permissionUser);
      setError("");
    } catch (caught) {
      handleApiError(caught);
    }
  };

  return (
    <Theme appearance={theme} accentColor="jade" grayColor="sage" radius="medium">
      <div className="app-shell">
        <button
          className={`mobile-scrim ${sidebarOpen ? "visible" : ""}`}
          aria-label="Close navigation"
          onClick={() => setSidebarOpen(false)}
        />

        <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
          <div className="brand-row">
            <div className="brand-mark" aria-hidden="true"><Sparkle weight="fill" /></div>
            <div>
              <strong>Local RAG</strong>
              <span>Private AI workspace</span>
            </div>
            <IconButton className="mobile-close" variant="ghost" onClick={() => setSidebarOpen(false)} aria-label="Close navigation">
              <X />
            </IconButton>
          </div>

          <Button className="new-chat" size="3" onClick={startNewChat}>
            <Plus weight="bold" /> New chat
          </Button>

          <nav className="conversation-list" aria-label="Saved conversations">
            <p className="section-label">Conversations</p>
            {conversations.length === 0 ? (
              <div className="sidebar-empty">Your saved chats will appear here.</div>
            ) : (
              conversations.map((conversation) => (
                <div
                  key={conversation.id}
                  className={`conversation-item ${conversation.id === conversationId ? "active" : ""}`}
                >
                  <button
                    className="conversation-open"
                    onClick={() => void openConversation(conversation.id)}
                  >
                    <ChatCircle aria-hidden="true" />
                    <span>
                      <strong>{conversation.title}</strong>
                      <small>{conversation.message_count} messages</small>
                    </span>
                  </button>
                  <button
                    className="delete-chat"
                    aria-label={`Delete ${conversation.title}`}
                    onClick={() => void removeConversation(conversation.id)}
                  >
                    <Trash />
                  </button>
                </div>
              ))
            )}
          </nav>

          <div className="sidebar-actions">
            <button onClick={() => void openDocuments()}><Books /> Documents</button>
            {currentUser?.role === "admin" ? <button onClick={() => void openEvaluations()}><ChartLineUp /> Evaluations</button> : null}
            {currentUser?.role === "admin" ? <button onClick={() => void openSecurity()}><ShieldCheck /> Access</button> : null}
            <button onClick={() => setSettingsOpen(true)}><Gear /> Connection</button>
            <div className="server-state">
              <span className={`status-dot ${isHealthy ? "online" : "offline"}`} />
              <span>{health?.warmup?.status === "warming" ? "Loading models" : isHealthy ? "Server ready" : "Server unavailable"}</span>
              {health?.queue.waiting ? <Badge color="amber">{health.queue.waiting} queued</Badge> : null}
            </div>
          </div>
        </aside>

        <main className="workspace">
          <header className="topbar">
            <IconButton className="mobile-menu" variant="ghost" onClick={() => setSidebarOpen(true)} aria-label="Open navigation">
              <List />
            </IconButton>
            <div className="topbar-control mode-control">
              <Gauge aria-hidden="true" />
              <Select.Root value={profile} onValueChange={(value) => changeProfile(value as ResponseProfile["id"])} disabled={generating}>
                <Select.Trigger aria-label="Response mode" />
                <Select.Content>
                  {(profiles.length ? profiles : [
                    { id: "auto", label: "Auto", available: true },
                    { id: "fast", label: "Fast", available: true },
                    { id: "balanced", label: "Balanced", available: true },
                    { id: "quality", label: "Quality", available: true }
                  ]).map((item) => (
                    <Select.Item value={item.id} key={item.id} disabled={!item.available}>{item.label}</Select.Item>
                  ))}
                </Select.Content>
              </Select.Root>
            </div>
            <div className="topbar-control document-control">
              <FileText aria-hidden="true" />
              <Select.Root value={selectedDocument} onValueChange={setSelectedDocument} disabled={generating}>
                <Select.Trigger aria-label="Search scope" />
                <Select.Content>
                  <Select.Item value="all">All documents</Select.Item>
                  {documents.filter((item) => item.status === "ready").map((item) => (
                    <Select.Item value={item.id} key={item.id}>{item.source}</Select.Item>
                  ))}
                </Select.Content>
              </Select.Root>
            </div>
            <div className="model-control raw-model-control" title={model}>
              <span>Model</span>
              <strong>{model}</strong>
            </div>
            <div className="topbar-spacer" />
            {latestMetrics?.cache_hit ? (
              <span className="speed-readout">Cached</span>
            ) : latestMetrics?.generation_tokens_per_second ? (
              <span className="speed-readout">{latestMetrics.generation_tokens_per_second} tok/s</span>
            ) : null}
            <Tooltip content={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>
              <IconButton
                variant="ghost"
                onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
                aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
              >
                {theme === "dark" ? <Sun /> : <Moon />}
              </IconButton>
            </Tooltip>
            <Tooltip content="Toggle sources">
              <IconButton variant="ghost" onClick={() => setActiveSources(activeSources.length ? [] : messages.at(-1)?.sources || [])} aria-label="Toggle sources">
                <SidebarSimple />
              </IconButton>
            </Tooltip>
          </header>

          <section className="chat-region" aria-live="polite">
            {messages.length === 0 ? (
              <div className="empty-chat">
                <div className="empty-symbol"><Sparkle weight="fill" /></div>
                <h1>Ask your private knowledge.</h1>
                <p>Your documents stay grounded in citations while Gemma runs on your own hardware.</p>
                <div className="suggestions">
                  {["Summarize my most recently uploaded document", "Which models are in the RAG workflow?", "Explain the cited architecture"].map((suggestion) => (
                    <button key={suggestion} onClick={() => setPrompt(suggestion)}>{suggestion}</button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="message-list">
                {messages.map((message) => (
                  <article
                    key={message.id}
                    className={`message ${message.role}`}
                    onClick={() => message.sources.length && setActiveSources(message.sources)}
                  >
                    <div className="message-author">{message.role === "user" ? "You" : "Gemma"}</div>
                    <div className="message-content">
                      {message.content || (generating && message.role === "assistant" ? (
                        <span className="thinking"><CircleNotch className="spin" /> Preparing context</span>
                      ) : null)}
                    </div>
                    {message.sources.length ? (
                      <div className="citation-row">
                        {message.sources.slice(0, 4).map((source) => (
                          <button key={source.id} onClick={() => setActiveSources(message.sources)}>
                            {source.index} <span>{source.filename}</span>
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </article>
                ))}
                <div ref={endRef} />
              </div>
            )}
          </section>

          {error ? (
            <div className="error-banner" role="alert">
              <span>{error}</span>
              <button onClick={() => setError("")} aria-label="Dismiss error"><X /></button>
            </div>
          ) : null}

          <footer className="composer-wrap">
            {queuePosition > 0 ? <div className="queue-banner">Waiting in position {queuePosition}</div> : null}
            <div className="composer">
              <textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                onKeyDown={handleComposerKey}
                placeholder="Ask about your documents"
                aria-label="Message"
                rows={1}
                disabled={generating}
              />
              {generating ? (
                <IconButton className="send-button stop" onClick={() => void stopGeneration()} aria-label="Stop generation">
                  <Square weight="fill" />
                </IconButton>
              ) : (
                <IconButton className="send-button" onClick={() => void sendPrompt()} disabled={!prompt.trim()} aria-label="Send message">
                  <ArrowUp weight="bold" />
                </IconButton>
              )}
            </div>
            <p>Gemma can make mistakes. Check the cited source.</p>
          </footer>
        </main>

        {activeSources.length ? (
          <aside className="sources-panel">
            <div className="sources-header">
              <div><strong>Sources</strong><span>{activeSources.length} retrieved chunks</span></div>
              <IconButton variant="ghost" onClick={() => setActiveSources([])} aria-label="Close sources"><X /></IconButton>
            </div>
            <div className="sources-list">
              {activeSources.map((source) => (
                <article key={source.id}>
                  <div className="source-title">
                    <span>{source.index}</span>
                    <div><strong>{source.filename}</strong><small>Page {source.page_number || 1}, chunk {source.chunk_index || source.index}</small></div>
                  </div>
                  <p>{source.quote}</p>
                  <div className="source-score">Relevance {Math.round(source.rerank_score * 100)}%</div>
                </article>
              ))}
            </div>
          </aside>
        ) : null}
      </div>

      <Dialog.Root open={settingsOpen} onOpenChange={setSettingsOpen}>
        <Dialog.Content maxWidth="440px">
          <Dialog.Title>Connect to your server</Dialog.Title>
          <Dialog.Description size="2" mb="4">
            Enter the API key configured on the secondary laptop. It is kept only for this browser session.
          </Dialog.Description>
          <label className="field-label" htmlFor="api-key">API key</label>
          <TextField.Root id="api-key" type="password" value={apiKeyInput} onChange={(event) => setApiKeyInput(event.target.value)} placeholder="Paste API key" />
          <div className="dialog-actions">
            {storedApiKey() ? <Button variant="soft" color="gray" onClick={() => setSettingsOpen(false)}>Cancel</Button> : null}
            <Button onClick={saveKey}><SignIn /> Connect</Button>
          </div>
        </Dialog.Content>
      </Dialog.Root>

      <Dialog.Root open={documentsOpen} onOpenChange={setDocumentsOpen}>
        <Dialog.Content maxWidth="680px">
          <Dialog.Title>Knowledge documents</Dialog.Title>
          <Dialog.Description size="2" mb="4">Upload a supported file to extract, embed, and index it.</Dialog.Description>
          <form className="upload-form" onSubmit={submitUpload}>
            <label className="file-drop" htmlFor="document-file">
              <FileArrowUp />
              <strong>{uploadFile?.name || "Choose a document"}</strong>
              <span>PDF, DOCX, TXT, PNG or JPG up to 25 MB</span>
              <input id="document-file" type="file" accept=".pdf,.docx,.txt,.md,.csv,.json,.png,.jpg,.jpeg" onChange={(event) => setUploadFile(event.target.files?.[0] || null)} />
            </label>
            <div>
              <label className="field-label" htmlFor="source-name">Source name</label>
              <TextField.Root id="source-name" value={uploadSource} onChange={(event) => setUploadSource(event.target.value)} placeholder="Defaults to filename" />
            </div>
            <Button type="submit" disabled={!uploadFile || uploading}>
              {uploading ? <CircleNotch className="spin" /> : <FileArrowUp />}
              {uploading ? "Processing" : "Upload"}
            </Button>
          </form>
          {ingestionJobs.length ? (
            <div className="job-list" aria-live="polite">
              {ingestionJobs.slice(0, 4).map((job) => (
                <div className="job-row" key={job.id}>
                  <div>
                    <strong>{job.source}</strong>
                    <small>{job.status === "failed" ? job.error : `${job.phase}, ${job.progress}%`}</small>
                  </div>
                  <progress max="100" value={job.progress} aria-label={`${job.source} ingestion progress`} />
                </div>
              ))}
            </div>
          ) : null}
          <div className="document-list">
            {documents.length ? documents.map((document) => (
              <div key={document.id}>
                <div className="document-icon"><Check weight="bold" /></div>
                <span><strong>{document.source}</strong><small>{document.pages} pages, {document.chunks} chunks</small></span>
                <Badge color={document.status === "ready" ? "jade" : "amber"}>{document.status}</Badge>
              </div>
            )) : <div className="documents-empty">No indexed documents yet.</div>}
          </div>
        </Dialog.Content>
      </Dialog.Root>

      <Dialog.Root open={evaluationOpen} onOpenChange={setEvaluationOpen}>
        <Dialog.Content maxWidth="760px">
          <div className="dialog-heading-row">
            <div>
              <Dialog.Title>Retrieval quality</Dialog.Title>
              <Dialog.Description size="2">Measure whether known questions retrieve the expected evidence.</Dialog.Description>
            </div>
            <Button onClick={() => void runEvaluation()} disabled={evaluations.some((run) => run.status === "running")}>
              <ChartLineUp /> Run evaluation
            </Button>
          </div>
          {evaluations.length ? evaluations.map((run) => (
            <section className="evaluation-run" key={run.id}>
              <div className="evaluation-meta">
                <strong>{run.status === "running" ? `Testing ${run.completed} of ${run.total || "..."}` : "Completed evaluation"}</strong>
                <Badge color={run.status === "ready" ? "jade" : run.status === "failed" ? "red" : "amber"}>{run.status}</Badge>
              </div>
              <div className="metric-grid">
                <div><span>Top 1</span><strong>{Math.round(run.top1_rate * 100)}%</strong></div>
                <div><span>Top 3</span><strong>{Math.round(run.top3_rate * 100)}%</strong></div>
                <div><span>Evidence</span><strong>{Math.round(run.evidence_rate * 100)}%</strong></div>
                <div><span>MRR</span><strong>{run.mrr.toFixed(2)}</strong></div>
                <div><span>Retrieval</span><strong>{Math.round(run.average_retrieval_ms)} ms</strong></div>
              </div>
              {run.status === "running" && run.total ? <progress max={run.total} value={run.completed} aria-label="Evaluation progress" /> : null}
              {run.error ? <p className="inline-error">{run.error}</p> : null}
            </section>
          )) : <div className="documents-empty">No evaluation runs yet.</div>}
        </Dialog.Content>
      </Dialog.Root>

      <Dialog.Root open={securityOpen} onOpenChange={setSecurityOpen}>
        <Dialog.Content maxWidth="640px">
          <Dialog.Title>Team access</Dialog.Title>
          <Dialog.Description size="2" mb="4">Create separate keys so each person sees only permitted conversations and documents.</Dialog.Description>
          <form className="user-form" onSubmit={addUser}>
            <TextField.Root value={newUserName} onChange={(event) => setNewUserName(event.target.value)} placeholder="User name" aria-label="User name" />
            <Select.Root value={newUserRole} onValueChange={(value) => setNewUserRole(value as "admin" | "user")}>
              <Select.Trigger aria-label="User role" />
              <Select.Content>
                <Select.Item value="user">User</Select.Item>
                <Select.Item value="admin">Administrator</Select.Item>
              </Select.Content>
            </Select.Root>
            <Button type="submit" disabled={!newUserName.trim()}>Create key</Button>
          </form>
          {createdApiKey ? (
            <div className="created-key" role="status">
              <div><strong>Copy this key now</strong><small>It cannot be retrieved again.</small></div>
              <code>{createdApiKey}</code>
              <IconButton variant="soft" onClick={() => void navigator.clipboard.writeText(createdApiKey)} aria-label="Copy new API key"><Copy /></IconButton>
            </div>
          ) : null}
          <div className="permission-form">
            <div>
              <strong>Document access</strong>
              <small>Grant read-only access to one indexed document.</small>
            </div>
            <Select.Root value={permissionUser} onValueChange={setPermissionUser}>
              <Select.Trigger placeholder="Select user" aria-label="Permission user" />
              <Select.Content>
                {users.filter((user) => user.active && user.role === "user").map((user) => (
                  <Select.Item value={user.id} key={user.id}>{user.name}</Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
            <Select.Root value={permissionDocument} onValueChange={setPermissionDocument}>
              <Select.Trigger placeholder="Select document" aria-label="Permission document" />
              <Select.Content>
                {documents.filter((document) => document.status === "ready").map((document) => (
                  <Select.Item value={document.id} key={document.id}>{document.source}</Select.Item>
                ))}
              </Select.Content>
            </Select.Root>
            <Button variant="soft" onClick={() => void grantDocumentAccess()} disabled={!permissionUser || !permissionDocument}>Grant access</Button>
          </div>
          <div className="user-list">
            {users.map((user) => (
              <div key={user.id}>
                <span><strong>{user.name}</strong><small>{user.role}</small></span>
                <Badge color={user.active ? "jade" : "gray"}>{user.active ? "active" : "disabled"}</Badge>
              </div>
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Root>
    </Theme>
  );
}

export default App;
