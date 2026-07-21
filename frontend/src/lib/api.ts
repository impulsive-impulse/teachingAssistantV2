/** Typed browser client. Server state remains authoritative at all times. */

export type ComponentState = "ready" | "unavailable" | "setup_required" | "error";

export interface ComponentStatus {
  state: ComponentState;
  detail: string;
}

export interface SystemStatus {
  application: ComponentStatus;
  database: ComponentStatus;
  storage: ComponentStatus;
  frozen_configs: ComponentStatus;
  embedding_model: ComponentStatus;
  online_provider: ComponentStatus;
  offline_provider: ComponentStatus;
  cpu: string;
  memory: string;
  profiles: {
    retrieval: string;
    online_model: string;
    online_max_output_tokens: number;
    offline_model: string;
    offline_max_output_tokens: number;
  };
}

export type BookStatus = "validating" | "processing" | "indexing" | "ready" | "failed" | "deleting";

export interface Book {
  id: string;
  book_id: string;
  sha256: string;
  original_filename: string;
  title: string;
  status: BookStatus;
  status_reason: string | null;
  page_count: number | null;
  searchable_page_count: number | null;
  chapter_count: number | null;
  ingestion_policy_version: string;
  runtime_profile_version: string;
  created_at: string;
  indexed_at: string | null;
  last_opened_at: string | null;
  current_job: IngestionJob | null;
}

export interface IngestionJob {
  id: string;
  checksum: string;
  book_id: string | null;
  stage: string;
  stage_progress: number;
  overall_progress: number;
  state: string;
  error_code: string | null;
  user_message: string | null;
  updated_at: string;
}

export interface UploadResult {
  disposition: "created" | "duplicate_ready" | "duplicate_active";
  book: Book;
  job: IngestionJob | null;
}

export interface ModelSetupJob {
  id: string;
  component: string;
  state: string;
  stage: string;
  progress: number;
  downloaded_bytes: number;
  total_bytes: number | null;
  error_code: string | null;
  user_message: string | null;
}

export interface OfflineRuntimeStatus {
  state: "loaded" | "unloaded";
  artifacts_ready: boolean;
  compatible: boolean;
  detail: string;
}

export type Backend = "online" | "offline";

export interface Chat {
  id: string;
  book_id: string;
  title: string;
  default_backend: Backend;
  created_at: string;
  updated_at: string;
}

export interface GroundedOutput {
  status: "answered" | "insufficient_evidence";
  answer: string;
  selected_evidence_ids: string[];
  citations: Array<{ evidence_id: string; pdf_page: number; textbook_page: number }>;
  missing_information: string[];
}

export interface Attempt {
  id: string;
  message_id: string;
  retrieval_snapshot_id: string | null;
  backend: Backend;
  state: string;
  prompt_checksum: string | null;
  output?: GroundedOutput | null;
  provider_identity: string | null;
  usage?: Record<string, number> | null;
  timing?: Record<string, number | null> | null;
  validation?: { valid: boolean; errors: string[] } | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface UserMessage {
  id: string;
  chat_id: string;
  question: string;
  created_at: string;
  attempts: Attempt[];
}

export interface Transcript { chat: Chat; messages: UserMessage[] }

export interface SourceItem {
  evidence_id: string;
  pdf_page: number;
  textbook_page: number;
  pdf_pages: number[];
  textbook_pages: number[];
  text: string;
  retrieval_rank: number;
  source_chunk_id: string;
}

class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
    throw new ApiError(response.status, payload?.detail ?? "The local application request failed.");
  }
  return response.json() as Promise<T>;
}

export const api = {
  systemStatus: () => request<SystemStatus>("/api/system/status"),
  systemDiagnostics: () => request<Record<string, unknown>>("/api/system/diagnostics"),
  setupEmbeddingModel: () => request<ModelSetupJob>("/api/system/embedding/setup", { method: "POST" }),
  setupOfflineProvider: () => request<ModelSetupJob>("/api/system/offline/setup", { method: "POST" }),
  offlineRuntime: () => request<OfflineRuntimeStatus>("/api/system/offline/runtime"),
  loadOffline: () => request<{ state: string; load_seconds?: number }>("/api/system/offline/load", { method: "POST" }),
  unloadOffline: () => request<{ state: string }>("/api/system/offline/unload", { method: "POST" }),
  books: () => request<Book[]>("/api/books"),
  uploadBook: (file: File) => {
    const body = new FormData();
    body.append("upload", file);
    return request<UploadResult>("/api/books/upload", { method: "POST", body });
  },
  deleteBook: (bookId: string) => request<{ id: string; deleted: boolean }>(`/api/books/${bookId}`, { method: "DELETE" }),
  chats: (bookId: string) => request<Chat[]>(`/api/books/${bookId}/chats`),
  createChat: (bookId: string, backend: Backend = "online") => request<Chat>(`/api/books/${bookId}/chats`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "New chat", default_backend: backend }),
  }),
  transcript: (chatId: string) => request<Transcript>(`/api/chats/${chatId}`),
  updateChatBackend: (chatId: string, backend: Backend) => request<Chat>(`/api/chats/${chatId}`, {
    method: "PATCH", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ default_backend: backend }),
  }),
  deleteChat: (chatId: string) => request<{ id: string; deleted: boolean }>(`/api/chats/${chatId}`, { method: "DELETE" }),
  sendMessage: (chatId: string, question: string, backend: Backend | null, acknowledged: boolean) =>
    request<{ message: UserMessage; attempt: Attempt }>(`/api/chats/${chatId}/messages`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, backend, online_disclosure_acknowledged: acknowledged }),
    }),
  cancelAttempt: (attemptId: string) => request<Attempt>(`/api/attempts/${attemptId}/cancel`, { method: "POST" }),
  regenerate: (messageId: string, backend: Backend, acknowledged: boolean) => request<Attempt>(`/api/messages/${messageId}/regenerate`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ backend, online_disclosure_acknowledged: acknowledged }),
  }),
  sources: (attemptId: string) => request<{ attempt_id: string; snapshot_checksum: string; sources: SourceItem[] }>(`/api/attempts/${attemptId}/sources`),
};
