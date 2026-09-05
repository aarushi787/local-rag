import { FormEvent, KeyboardEvent, lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowUp,
  ArrowCounterClockwise,
  Books,
  ChatCircle,
  ChartLineUp,
  Check,
  CheckCircle,
  CircleNotch,
  Copy,
  Database,
  DownloadSimple,
  FileArrowUp,
  FileText,
  Gear,
  Gauge,
  List,
  MagnifyingGlass,
  Moon,
  Plus,
  PencilSimple,
  ArrowsClockwise,
  ShieldCheck,
  SidebarSimple,
  SignIn,
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
  rotateUserKey,
  CurrentUser,
  deleteConversation,
  deleteDocument,
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
  renameConversation,
  EvaluationRun,
  IngestionJob,
  Source,
  displayApiUrl,
  storedApiUrl,
  storedApiKey,
  storeApiUrl,
  storeApiKey,
  startEvaluation,
  setDocumentPermission,
  setConversationTrainingApproval,
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

const makeId = () =>
  globalThis.crypto?.randomUUID?.() ??
  `${Date.now()}-${Math.random().toString(16).slice(2)}-${Math.random()
    .toString(16)
    .slice(2)}`;
const lastUserIndex = (items: UiMessage[]) => {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    if (items[index].role === "user") return index;
  }
  return -1;
};
const ingestionPhaseLabel = (phase: string) => ({
  queued: "Queued",
  extracting: "OCR / extraction",
  preparing: "Chunking",
  chunking: "Chunking",
  embedding: "Embedding",
  saving: "Saving",
  ready: "Completed",
  duplicate: "Completed · already indexed",
  failed: "Failed",
  interrupted: "Interrupted"
}[phase] || phase);
const MarkdownContent = lazy(() => import("./MarkdownContent"));

function App() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = localStorage.getItem("local-rag-theme");
    if (saved === "light" || saved === "dark") return saved;
    return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  const [health, setHealth] = useState<Health | null>(null);
  const [healthChecked, setHealthChecked] = useState(false);
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
  const [generationStage, setGenerationStage] = useState("");
  const [activeRequestId, setActiveRequestId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(!storedApiKey());
  const [documentsOpen, setDocumentsOpen] = useState(false);
  const [evaluationOpen, setEvaluationOpen] = useState(false);
  const [securityOpen, setSecurityOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [apiKeyInput, setApiKeyInput] = useState(storedApiKey());
  const [apiUrlInput, setApiUrlInput] = useState(displayApiUrl());
  const [connecting, setConnecting] = useState(false);
  const [copiedMessage, setCopiedMessage] = useState<string | null>(null);
  const [conversationSearch, setConversationSearch] = useState("");
  const [documentSearch, setDocumentSearch] = useState("");
  const [documentFilter, setDocumentFilter] = useState("all");
  const [dragActive, setDragActive] = useState(false);
  const [editingLastTurn, setEditingLastTurn] = useState(false);
  const [expandedSource, setExpandedSource] = useState<number | null>(null);
  const [renameTarget, setRenameTarget] = useState<ConversationSummary | null>(null);
  const [renameTitle, setRenameTitle] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ type: "conversation" | "document"; id: string; name: string } | null>(null);
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
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const copyTimerRef = useRef<number | null>(null);

  const isHealthy = health?.status === "healthy";
  const connectedServer = storedApiUrl() || window.location.origin;
  const serverHost = (() => {
    try {
      return new URL(connectedServer).host;
    } catch {
      return connectedServer;
    }
  })();
  const latestMetrics = useMemo(
    () => [...messages].reverse().find((message) => message.role === "assistant")?.metrics,
    [messages]
  );
  const latestSources = useMemo(
    () => [...messages].reverse().find((message) => message.role === "assistant" && message.sources.length)?.sources || [],
    [messages]
  );
  const visibleSourceCount = activeSources.length || latestSources.length;
  const filteredConversations = useMemo(() => {
    const query = conversationSearch.trim().toLowerCase();
    return query
      ? conversations.filter((item) => item.title.toLowerCase().includes(query))
      : conversations;
  }, [conversationSearch, conversations]);
  const filteredDocuments = useMemo(() => {
    const query = documentSearch.trim().toLowerCase();
    return documents.filter((item) => {
      const matchesQuery = !query || `${item.source} ${item.filename}`.toLowerCase().includes(query);
      const matchesFilter = documentFilter === "all" || item.status === documentFilter;
      return matchesQuery && matchesFilter;
    });
  }, [documentFilter, documentSearch, documents]);

  useEffect(() => {
    localStorage.setItem("local-rag-theme", theme);
  }, [theme]);

  useEffect(() => () => {
    if (copyTimerRef.current) window.clearTimeout(copyTimerRef.current);
  }, []);

  useEffect(() => {
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        composerRef.current?.focus();
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "n") {
        event.preventDefault();
        startNewChat();
      }
      if (event.key === "Escape" && generating) void stopGeneration();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  });

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
    } finally {
      setHealthChecked(true);
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

  const saveConnection = async () => {
    const address = apiUrlInput.trim().replace(/\/$/, "");
    if (address && !/^https?:\/\//i.test(address)) {
      setError("Server address must start with http:// or https://.");
      return;
    }
    storeApiUrl(address === window.location.origin ? "" : address);
    storeApiKey(apiKeyInput.trim());
    setConnecting(true);
    setError("");
    try {
      const status = await getHealth();
      await getCurrentUser();
      setHealth(status);
      await refreshWorkspace();
      setSettingsOpen(false);
    } catch (caught) {
      handleApiError(caught);
    } finally {
      setConnecting(false);
    }
  };

  const copyAnswer = async (message: UiMessage) => {
    await navigator.clipboard.writeText(message.content);
    setCopiedMessage(message.id);
    if (copyTimerRef.current) window.clearTimeout(copyTimerRef.current);
    copyTimerRef.current = window.setTimeout(() => setCopiedMessage(null), 1800);
  };

  const startNewChat = () => {
    setConversationId(null);
    setMessages([]);
    setActiveSources([]);
    setError("");
    setEditingLastTurn(false);
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

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      if (deleteTarget.type === "conversation") {
        await deleteConversation(deleteTarget.id);
        if (conversationId === deleteTarget.id) startNewChat();
      } else {
        await deleteDocument(deleteTarget.id);
        if (selectedDocument === deleteTarget.id) setSelectedDocument("all");
      }
      setDeleteTarget(null);
      await refreshWorkspace();
    } catch (caught) {
      handleApiError(caught);
    }
  };

  const saveConversationTitle = async (event: FormEvent) => {
    event.preventDefault();
    if (!renameTarget || !renameTitle.trim()) return;
    try {
      await renameConversation(renameTarget.id, renameTitle.trim());
      setRenameTarget(null);
      await refreshWorkspace();
    } catch (caught) {
      handleApiError(caught);
    }
  };

  const exportConversation = async (id: string) => {
    try {
      const conversation = await getConversation(id);
      const safeTitle = conversation.title.replace(/[^a-z0-9_-]+/gi, "-").replace(/^-|-$/g, "") || "conversation";
      const body = conversation.messages.map((message) => {
        const citations = message.sources?.map((source) =>
          `- ${source.filename}, page ${source.page_number || 1}`
        ).join("\n");
        return `## ${message.role === "user" ? "You" : "Gemma"}\n\n${message.content}${citations ? `\n\nSources:\n${citations}` : ""}`;
      }).join("\n\n");
      const blob = new Blob([`# ${conversation.title}\n\n${body}\n`], { type: "text/markdown;charset=utf-8" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `${safeTitle}.md`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (caught) {
      handleApiError(caught);
    }
  };

  const toggleTrainingApproval = async (conversation: ConversationSummary) => {
    try {
      await setConversationTrainingApproval(conversation.id, !conversation.training_approved);
      await refreshWorkspace();
    } catch (caught) {
      handleApiError(caught);
    }
  };

  const sendPrompt = async (
    textOverride?: string,
    baseMessages?: UiMessage[],
    replaceLast = editingLastTurn
  ) => {
    const text = (textOverride ?? prompt).trim();
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
    const base = baseMessages ?? (replaceLast
      ? messages.slice(0, Math.max(0, lastUserIndex(messages)))
      : messages);
    const requestMessages = [...base, userMessage].map(({ role, content }) => ({ role, content }));
    setMessages([
      ...base,
      userMessage,
      { id: assistantId, role: "assistant", content: "", sources: [], metrics: {} }
    ]);
    setPrompt("");
    setEditingLastTurn(false);
    setGenerating(true);
    setQueuePosition(0);
    setGenerationStage("Preparing request");
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
          max_tokens: 220,
          replace_last: replaceLast
        },
        {
          onQueue: (requestId, position) => {
            setActiveRequestId(requestId);
            setQueuePosition(position);
          },
          onStatus: (_stage, message) => setGenerationStage(message),
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
            setGenerationStage("");
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
      setGenerationStage("");
      setActiveRequestId(null);
      abortRef.current = null;
    }
  };

  const regenerateLastResponse = () => {
    if (generating) return;
    const userIndex = lastUserIndex(messages);
    if (userIndex < 0) return;
    const previous = messages[userIndex];
    void sendPrompt(previous.content, messages.slice(0, userIndex), true);
  };

  const editLastPrompt = () => {
    const userIndex = lastUserIndex(messages);
    if (userIndex < 0 || generating) return;
    setPrompt(messages[userIndex].content);
    setEditingLastTurn(true);
    window.setTimeout(() => composerRef.current?.focus(), 0);
  };

  const stopGeneration = async () => {
    if (activeRequestId) void cancelChat(activeRequestId).catch(() => undefined);
    abortRef.current?.abort();
    setGenerating(false);
  };

  const handleComposerKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      event.currentTarget.form?.requestSubmit();
    }
  };

  const submitPrompt = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    void sendPrompt();
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

  const runEvaluation = async (pipeline: "baseline" | "upgraded", includeGeneration: boolean) => {
    try {
      const run = await startEvaluation(pipeline, includeGeneration);
      setEvaluations((current) => [{
        id: run.id, status: "running", total: 0, completed: 0, top1_rate: 0,
        top3_rate: 0, top5_rate: 0, evidence_rate: 0, mrr: 0, average_retrieval_ms: 0,
        dataset_version: "v1", pipeline, include_generation: includeGeneration,
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

  const rotateKey = async (user: UserRecord) => {
    try {
      const rotated = await rotateUserKey(user.id);
      setCreatedApiKey(rotated.api_key);
      setError("");
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
      <a className="skip-link" href="#main-workspace">Skip to chat</a>
      <div className="app-shell">
        <button
          className={`mobile-scrim ${sidebarOpen ? "visible" : ""}`}
          aria-label="Close navigation"
          onClick={() => setSidebarOpen(false)}
        />

        <aside className={`sidebar ${sidebarOpen ? "open" : ""}`}>
          <div className="brand-row">
            <div className="brand-mark" aria-hidden="true"><Books weight="fill" /></div>
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
            <label className="compact-search">
              <MagnifyingGlass aria-hidden="true" />
              <input value={conversationSearch} onChange={(event) => setConversationSearch(event.target.value)} placeholder="Search conversations" aria-label="Search conversations" />
            </label>
            {conversations.length === 0 ? (
              <div className="sidebar-empty">Your saved chats will appear here.</div>
            ) : filteredConversations.length === 0 ? (
              <div className="sidebar-empty">No conversations match that search.</div>
            ) : (
              filteredConversations.map((conversation) => (
                <div
                  key={conversation.id}
                  className={`conversation-item ${conversation.id === conversationId ? "active" : ""}`}
                >
                  <button
                    className="conversation-open"
                    onClick={() => void openConversation(conversation.id)}
                    aria-current={conversation.id === conversationId ? "page" : undefined}
                  >
                    <ChatCircle aria-hidden="true" />
                    <span>
                      <strong>{conversation.title}</strong>
                      <small>{conversation.message_count} messages</small>
                    </span>
                  </button>
                  <div className="conversation-actions">
                    {currentUser?.role === "admin" ? (
                      <button aria-label={`${conversation.training_approved ? "Remove" : "Approve"} ${conversation.title} for training export`} title={conversation.training_approved ? "Remove training approval" : "Approve for training export"} onClick={() => void toggleTrainingApproval(conversation)}><CheckCircle weight={conversation.training_approved ? "fill" : "regular"} /></button>
                    ) : null}
                    <button aria-label={`Rename ${conversation.title}`} title="Rename" onClick={() => { setRenameTarget(conversation); setRenameTitle(conversation.title); }}><PencilSimple /></button>
                    <button aria-label={`Export ${conversation.title}`} title="Export" onClick={() => void exportConversation(conversation.id)}><DownloadSimple /></button>
                    <button aria-label={`Delete ${conversation.title}`} title="Delete" onClick={() => setDeleteTarget({ type: "conversation", id: conversation.id, name: conversation.title })}><Trash /></button>
                  </div>
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
              <span className={`status-dot ${!healthChecked ? "waiting" : isHealthy ? "online" : "offline"}`} />
              <span>
                <strong>{!healthChecked ? "Checking server" : health?.warmup?.status === "warming" ? "Loading models" : isHealthy ? "Server ready" : "Server unavailable"}</strong>
                <small title={connectedServer}>{serverHost}</small>
              </span>
              {health?.queue.waiting ? <Badge color="amber">{health.queue.waiting} queued</Badge> : null}
            </div>
          </div>
        </aside>

        <main className="workspace" id="main-workspace">
          <header className="topbar">
            <IconButton className="mobile-menu" variant="ghost" onClick={() => setSidebarOpen(true)} aria-label="Open navigation">
              <List />
            </IconButton>
            <div className="topbar-control mode-control">
              <Gauge aria-hidden="true" />
              <span className="control-label">Response</span>
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
              <span className="control-label">Scope</span>
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
            <Tooltip content={visibleSourceCount ? `${visibleSourceCount} sources` : "Sources appear with grounded answers"}>
              <IconButton
                className="sources-toggle"
                variant="ghost"
                disabled={!visibleSourceCount}
                onClick={() => setActiveSources(activeSources.length ? [] : latestSources)}
                aria-label={visibleSourceCount ? `Toggle ${visibleSourceCount} sources` : "No sources available"}
              >
                <SidebarSimple />
                {visibleSourceCount ? <span className="source-count" aria-hidden="true">{visibleSourceCount}</span> : null}
              </IconButton>
            </Tooltip>
          </header>

          <div className="component-statuses" aria-label="Service status">
            <strong>{!healthChecked ? "Checking systems" : health?.warmup?.status === "warming" ? "Models loading" : isHealthy ? "Systems ready" : "Needs attention"}</strong>
            <span><i className={`status-dot ${!healthChecked ? "waiting" : isHealthy ? "online" : "offline"}`} />Server</span>
            <span><i className={`status-dot ${!healthChecked ? "waiting" : health?.ollama?.status === "connected" ? "online" : "offline"}`} />Ollama</span>
            <span><i className={`status-dot ${!healthChecked ? "waiting" : health?.database?.status === "connected" ? "online" : "offline"}`} />Database</span>
            <span><i className={`status-dot ${!healthChecked ? "waiting" : health?.warmup?.status === "ready" ? "online" : health?.warmup?.status === "warming" ? "waiting" : "offline"}`} />Model</span>
          </div>

          <section className="chat-region" aria-live="polite" aria-busy={generating}>
            {messages.length === 0 ? (
              <div className="empty-chat">
                <div className="welcome-layout">
                  <div className="workspace-intro">
                    <div className="privacy-kicker"><ShieldCheck weight="fill" /> Private server, cited answers</div>
                    <h1>Ask your private knowledge.</h1>
                    <p>Gemma searches the documents on this server, builds a grounded answer, and keeps the evidence within reach.</p>
                    <div className="starter-prompts">
                      <span>Start with a useful question</span>
                      <div className="suggestions">
                        {["Summarize my latest document", "Find records about export opportunities", "Compare the models in this archive", "Show the evidence for PG2473"].map((suggestion) => (
                          <button key={suggestion} onClick={() => { setPrompt(suggestion); composerRef.current?.focus(); }}><ChatCircle /><span>{suggestion}</span><ArrowUp weight="bold" /></button>
                        ))}
                      </div>
                    </div>
                  </div>
                  <aside className="workspace-summary" aria-label="Workspace status">
                    <div className="workspace-summary-head">
                      <span className={`status-dot ${!healthChecked ? "waiting" : isHealthy ? "online" : "offline"}`} />
                      <div><strong>{!healthChecked ? "Checking workspace" : isHealthy ? "Workspace ready" : "Workspace offline"}</strong><small>Live status from this server</small></div>
                    </div>
                    <div className="workspace-overview">
                      <div><Books /><span>Documents<strong>{health?.database?.stored_documents ?? documents.length}</strong></span></div>
                      <div><Database /><span>Search chunks<strong>{health?.database?.stored_chunks ?? 0}</strong></span></div>
                      <div><Gauge /><span>Response mode<strong>{profiles.find((item) => item.id === profile)?.label || "Auto"}</strong></span></div>
                      <div><FileText /><span>Search scope<strong>{selectedDocument === "all" ? "All documents" : documents.find((item) => item.id === selectedDocument)?.source || "Selected document"}</strong></span></div>
                    </div>
                    <div className="active-model"><span>Active model</span><strong title={model}>{model}</strong><small>Processing stays on your hardware</small></div>
                  </aside>
                </div>
              </div>
            ) : (
              <div className="message-list">
                {messages.map((message, messageIndex) => (
                  <article
                    key={message.id}
                    className={`message ${message.role}`}
                    onClick={() => message.sources.length && setActiveSources(message.sources)}
                  >
                    <div className="message-author">{message.role === "user" ? "You" : "Gemma"}</div>
                    <div className="message-content">
                      {message.content ? (
                        <Suspense fallback={<span className="message-plain">{message.content}</span>}>
                          <MarkdownContent>{message.content}</MarkdownContent>
                        </Suspense>
                      ) : generating && message.role === "assistant" ? (
                        <span className="thinking"><CircleNotch className="spin" /> Preparing context</span>
                      ) : null}
                    </div>
                    {message.role === "user" && messageIndex === lastUserIndex(messages) && !generating ? (
                      <div className="message-actions">
                        <button onClick={editLastPrompt}><PencilSimple /> Edit and resend</button>
                      </div>
                    ) : null}
                    {message.role === "assistant" && message.content ? (
                      <div className="message-actions">
                        <button onClick={() => void copyAnswer(message)} aria-label="Copy answer">
                          {copiedMessage === message.id ? <Check /> : <Copy />}
                          {copiedMessage === message.id ? "Copied" : "Copy"}
                        </button>
                        {messageIndex === messages.length - 1 && !generating ? (
                          <button onClick={regenerateLastResponse}><ArrowCounterClockwise /> Regenerate</button>
                        ) : null}
                        {message.metrics.cache_hit ? <span>Cached response</span> : null}
                        {message.metrics.generation_tokens_per_second ? <span>{message.metrics.generation_tokens_per_second} tokens/sec</span> : null}
                        {message.metrics.first_token_ms ? <span>{Math.round(message.metrics.first_token_ms)} ms first token</span> : null}
                        {message.metrics.total_ms ? <span>{(message.metrics.total_ms / 1000).toFixed(1)} sec total</span> : null}
                        {currentUser?.role === "admin" && message.metrics.retrieval_ms ? <span>{Math.round(message.metrics.retrieval_ms)} ms retrieval</span> : null}
                      </div>
                    ) : null}
                    {message.sources.length ? (
                      <div className="citation-row">
                        {message.sources.slice(0, 4).map((source) => (
                          <button key={source.id} onClick={() => setActiveSources(message.sources)}>
                            {source.index} <span>{source.filename} · p.{source.page_number || 1} · {Math.round(source.rerank_score * 100)}%</span>
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
            {generating && queuePosition === 0 && generationStage ? <div className="queue-banner">{generationStage}</div> : null}
            {editingLastTurn ? <div className="edit-banner"><span>Editing your latest prompt</span><button onClick={() => { setEditingLastTurn(false); setPrompt(""); }}>Cancel</button></div> : null}
            <form className="composer" onSubmit={submitPrompt}>
              <textarea
                ref={composerRef}
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
                <IconButton className="send-button" type="submit" disabled={!prompt.trim()} aria-label="Send message">
                  <ArrowUp weight="bold" />
                </IconButton>
              )}
            </form>
            <div className="composer-footnote">
              <span>Verify important answers against cited sources.</span>
              <span className="shortcut-hint"><kbd>Ctrl</kbd> + <kbd>K</kbd> focus · <kbd>Ctrl</kbd> + <kbd>N</kbd> new chat</span>
            </div>
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
                  <button className="source-summary" onClick={() => setExpandedSource(expandedSource === source.id ? null : source.id)} aria-expanded={expandedSource === source.id}>
                    <span>{source.index}</span>
                    <div><strong>{source.filename}</strong><small>Page {source.page_number || 1}{source.section_title ? ` · ${source.section_title}` : ""} · chunk {source.chunk_index || source.index}</small></div>
                    <b>{Math.round(source.rerank_score * 100)}%</b>
                  </button>
                  {expandedSource === source.id ? (
                    <div className="source-detail"><p>{source.quote}</p><div className="source-score">Relevance {Math.round(source.rerank_score * 100)}%</div></div>
                  ) : null}
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
            Use the secure address of your secondary laptop and its Local RAG API key.
          </Dialog.Description>
          <label className="field-label" htmlFor="api-url">Server address</label>
          <TextField.Root id="api-url" type="url" value={apiUrlInput} onChange={(event) => setApiUrlInput(event.target.value)} placeholder="https://your-server.tailnet.ts.net" />
          <p className="field-help">Leave this device's address here when the frontend is served by FastAPI.</p>
          <label className="field-label" htmlFor="api-key">API key</label>
          <TextField.Root id="api-key" type="password" value={apiKeyInput} onChange={(event) => setApiKeyInput(event.target.value)} placeholder="Paste API key" />
          <div className="dialog-actions">
            {storedApiKey() ? <Button variant="soft" color="gray" onClick={() => setSettingsOpen(false)}>Cancel</Button> : null}
            <Button onClick={() => void saveConnection()} disabled={connecting || !apiKeyInput.trim()}>
              {connecting ? <CircleNotch className="spin" /> : <SignIn />}
              {connecting ? "Testing" : "Connect"}
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Root>

      <Dialog.Root open={documentsOpen} onOpenChange={setDocumentsOpen}>
        <Dialog.Content maxWidth="680px">
          <Dialog.Title>Knowledge documents</Dialog.Title>
          <Dialog.Description size="2" mb="4">Upload a supported file to extract, embed, and index it.</Dialog.Description>
          <form className="upload-form" onSubmit={submitUpload}>
            <label
              className={`file-drop ${dragActive ? "drag-active" : ""}`}
              htmlFor="document-file"
              onDragOver={(event) => { event.preventDefault(); setDragActive(true); }}
              onDragLeave={() => setDragActive(false)}
              onDrop={(event) => {
                event.preventDefault();
                setDragActive(false);
                const file = event.dataTransfer.files?.[0];
                if (file) setUploadFile(file);
              }}
            >
              <FileArrowUp />
              <strong>{uploadFile?.name || "Drop a document here or choose a file"}</strong>
              <span>PDF, DOCX, XLSX, TXT, PNG or JPG up to 25 MB</span>
              <input id="document-file" type="file" accept=".pdf,.docx,.xlsx,.txt,.md,.csv,.json,.png,.jpg,.jpeg" onChange={(event) => setUploadFile(event.target.files?.[0] || null)} />
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
                    <small>{job.status === "failed" ? job.error : `${ingestionPhaseLabel(job.phase)}, ${job.progress}%`}</small>
                  </div>
                  <progress max="100" value={job.progress} aria-label={`${job.source} ingestion progress`} />
                </div>
              ))}
            </div>
          ) : null}
          <div className="document-tools">
            <label className="compact-search">
              <MagnifyingGlass aria-hidden="true" />
              <input value={documentSearch} onChange={(event) => setDocumentSearch(event.target.value)} placeholder="Search documents" aria-label="Search documents" />
            </label>
            <Select.Root value={documentFilter} onValueChange={setDocumentFilter}>
              <Select.Trigger aria-label="Filter document status" />
              <Select.Content>
                <Select.Item value="all">All statuses</Select.Item>
                <Select.Item value="ready">Ready</Select.Item>
                <Select.Item value="processing">Processing</Select.Item>
                <Select.Item value="failed">Failed</Select.Item>
              </Select.Content>
            </Select.Root>
          </div>
          <div className="document-list">
            {filteredDocuments.length ? filteredDocuments.map((document) => (
              <div key={document.id}>
                <div className="document-icon"><Check weight="bold" /></div>
                <span><strong>{document.source}</strong><small>{document.filename} · {document.pages} pages · {document.chunks} chunks</small></span>
                <Badge color={document.status === "ready" ? "jade" : "amber"}>{document.status}</Badge>
                <IconButton variant="ghost" color="red" aria-label={`Delete ${document.source}`} onClick={() => setDeleteTarget({ type: "document", id: document.id, name: document.source })}><Trash /></IconButton>
              </div>
            )) : <div className="documents-empty">No documents match the current filters.</div>}
          </div>
        </Dialog.Content>
      </Dialog.Root>

      <Dialog.Root open={Boolean(renameTarget)} onOpenChange={(open) => !open && setRenameTarget(null)}>
        <Dialog.Content maxWidth="420px">
          <Dialog.Title>Rename conversation</Dialog.Title>
          <form onSubmit={saveConversationTitle} className="rename-form">
            <TextField.Root value={renameTitle} onChange={(event) => setRenameTitle(event.target.value)} aria-label="Conversation title" autoFocus />
            <div className="dialog-actions">
              <Button type="button" variant="soft" color="gray" onClick={() => setRenameTarget(null)}>Cancel</Button>
              <Button type="submit" disabled={!renameTitle.trim()}>Save name</Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Root>

      <Dialog.Root open={Boolean(deleteTarget)} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <Dialog.Content maxWidth="440px">
          <Dialog.Title>Delete {deleteTarget?.type}</Dialog.Title>
          <Dialog.Description size="2">
            This will permanently delete “{deleteTarget?.name}”{deleteTarget?.type === "document" ? " and its indexed chunks" : ""}.
          </Dialog.Description>
          <div className="dialog-actions">
            <Button variant="soft" color="gray" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button color="red" onClick={() => void confirmDelete()}><Trash /> Delete</Button>
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
            <div className="evaluation-actions">
              <Button variant="soft" onClick={() => void runEvaluation("baseline", false)} disabled={evaluations.some((run) => run.status === "running")}>
                Baseline retrieval
              </Button>
              <Button onClick={() => void runEvaluation("upgraded", true)} disabled={evaluations.some((run) => run.status === "running")}>
                <ChartLineUp /> Full upgraded test
              </Button>
            </div>
          </div>
          {evaluations.length ? evaluations.map((run) => (
            <section className="evaluation-run" key={run.id}>
              <div className="evaluation-meta">
                <strong>{run.status === "running" ? `Testing ${run.completed} of ${run.total || "..."}` : `${run.pipeline} · dataset ${run.dataset_version}`}</strong>
                <Badge color={run.status === "ready" ? "jade" : run.status === "failed" ? "red" : "amber"}>{run.status}</Badge>
              </div>
              <div className="metric-grid">
                <div><span>Top 1</span><strong>{Math.round(run.top1_rate * 100)}%</strong></div>
                <div><span>Top 3</span><strong>{Math.round(run.top3_rate * 100)}%</strong></div>
                <div><span>Top 5</span><strong>{Math.round(run.top5_rate * 100)}%</strong></div>
                <div><span>Evidence</span><strong>{Math.round(run.evidence_rate * 100)}%</strong></div>
                <div><span>MRR</span><strong>{run.mrr.toFixed(2)}</strong></div>
                <div><span>Retrieval</span><strong>{Math.round(run.average_retrieval_ms)} ms</strong></div>
                {run.include_generation ? <>
                  <div><span>Citations</span><strong>{Math.round((run.citation_correctness || 0) * 100)}%</strong></div>
                  <div><span>Grounded</span><strong>{Math.round((run.grounded_answer_rate || 0) * 100)}%</strong></div>
                  <div><span>Unsupported</span><strong>{Math.round((run.unsupported_claim_rate || 0) * 100)}%</strong></div>
                  <div><span>Refusals</span><strong>{Math.round((run.refusal_correctness || 0) * 100)}%</strong></div>
                  <div><span>First token</span><strong>{Math.round(run.average_first_token_ms || 0)} ms</strong></div>
                  <div><span>Total</span><strong>{((run.average_total_latency_ms || 0) / 1000).toFixed(1)} s</strong></div>
                  <div><span>Generation</span><strong>{(run.average_generation_tps || 0).toFixed(1)} tok/s</strong></div>
                  <div><span>Cache hits</span><strong>{Math.round((run.cache_hit_rate || 0) * 100)}%</strong></div>
                </> : null}
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
                {user.active && user.id !== currentUser?.id ? (
                  <IconButton variant="ghost" onClick={() => void rotateKey(user)} aria-label={`Rotate API key for ${user.name}`} title="Rotate API key"><ArrowsClockwise /></IconButton>
                ) : null}
              </div>
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Root>
    </Theme>
  );
}

export default App;
