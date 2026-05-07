export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export type TaskState = "PENDING" | "STARTED" | "RETRY" | "SUCCESS" | "FAILURE";

export interface HealthResponse {
  status: string;
}

export interface Book {
  id: string;
  title: string;
  source_type: string;
  status: string;
  skill_checkpoint_chapter?: number;
  created_at: string;
}

export interface UploadResponse {
  task_id: string;
  book_id: string;
  status: string;
}

export interface TaskResult {
  book_id?: string;
  status?: string;
  chapter_count?: number;
  checkpoint_chapter?: number;
}

export interface TaskStatusResponse {
  task_id: string;
  status: TaskState;
  result?: TaskResult | string;
}

export interface ChapterSummary {
  id: string;
  chapter_index: number;
  title: string;
}

export interface ChapterDetail {
  id: string;
  book_id: string;
  chapter_index: number;
  title: string;
  raw_text: string;
}

export interface CharacterSummary {
  id: string;
  canonical_name: string;
  first_chapter_index?: number | null;
  mention_count: number;
  confidence: number;
  is_verified: boolean;
  aliases: string[];
  card_preview?: string | null;
}

export interface CharacterCard {
  identity_summary: string;
  personality_summary: string;
  speaking_style: string;
  values_and_taboo: string;
}

export interface CharacterState {
  chapter_index: number;
  emotional_state: string;
  stance: string;
  current_goal: string;
  relation_snapshot: string;
}

export interface CharacterEvidence {
  chapter_index: number;
  excerpt: string;
  evidence_type: string;
}

export interface CharacterDetail {
  id: string;
  canonical_name: string;
  first_chapter_index?: number | null;
  mention_count: number;
  confidence: number;
  is_verified: boolean;
  aliases: string[];
  card?: CharacterCard | null;
  latest_state?: CharacterState | null;
  evidences: CharacterEvidence[];
}

export interface RelationshipEdge {
  id: string;
  source_character_id: string;
  source_name: string;
  target_character_id: string;
  target_name: string;
  relation_type: string;
  strength: number;
  first_chapter_index?: number | null;
  last_chapter_index?: number | null;
  evidence_excerpt: string;
}

export interface RelationshipGraphNodeMetric {
  character_id: string;
  canonical_name: string;
  degree: number;
  in_degree: number;
  out_degree: number;
  weighted_degree: number;
  relation_diversity: number;
  last_chapter_index?: number | null;
}

export interface CharacterPortrait {
  id: string;
  character_id: string;
  canonical_name: string;
  unlocked_chapter_index: number;
  status: string;
  style_prompt: string;
  image_url: string;
  generator: string;
}

export interface ChatRequest {
  book_id: string;
  role_name: string;
  message: string;
  chapter_index?: number | null;
  session_id?: string | null;
}

export interface Citation {
  chapter_index: number;
  chapter_title: string;
  chunk_id: string;
  chunk_index: number;
  score: number;
  preview: string;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  spoiler_risk: string;
  llm_used: boolean;
  llm_model: string;
  llm_error: string;
  guard_applied: boolean;
  session_id?: string | null;
}

export interface VisualJobCreateResponse {
  task_id: string;
  job_id: string;
  book_id: string;
  status: string;
}

export interface VisualJobCreateRequest {
  asset_type: "portrait" | "character_card" | "scene";
  character_id?: string;
  chapter_index?: number;
  style_prompt?: string;
  priority?: number;
}

export interface VisualJobStatusResponse {
  job_id: string;
  book_id: string;
  asset_type: string;
  status: string;
  task_id: string;
  result_asset_id?: string | null;
  error_message: string;
}

export interface MediaAsset {
  id: string;
  book_id: string;
  character_id?: string | null;
  asset_type: string;
  chapter_index?: number | null;
  status: string;
  style_prompt: string;
  storage_url: string;
  generator: string;
  version: number;
}

interface ApiErrorPayload {
  detail?: string;
  message?: string;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    cache: "no-store"
  });

  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`;
    try {
      const payload = (await res.json()) as ApiErrorPayload;
      detail = payload.detail || payload.message || detail;
    } catch {
      // Keep fallback detail.
    }
    throw new Error(detail);
  }

  return res.json() as Promise<T>;
}

export function fetchHealth(): Promise<HealthResponse> {
  return requestJson<HealthResponse>("/api/healthz", { method: "GET" });
}

export function listBooks(): Promise<Book[]> {
  return requestJson<Book[]>("/api/books", { method: "GET" });
}

export async function uploadBookTxt(file: File, title?: string): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append("file", file);
  if (title?.trim()) {
    formData.append("title", title.trim());
  }

  const res = await fetch(`${API_BASE_URL}/api/books/upload`, {
    method: "POST",
    body: formData
  });
  if (!res.ok) {
    let detail = `Upload failed with status ${res.status}`;
    try {
      const payload = (await res.json()) as ApiErrorPayload;
      detail = payload.detail || payload.message || detail;
    } catch {
      // Keep fallback detail.
    }
    throw new Error(detail);
  }

  return res.json() as Promise<UploadResponse>;
}

export function getTaskStatus(taskId: string): Promise<TaskStatusResponse> {
  return requestJson<TaskStatusResponse>(`/api/books/tasks/${taskId}`, {
    method: "GET"
  });
}

export function listChapters(bookId: string): Promise<ChapterSummary[]> {
  return requestJson<ChapterSummary[]>(
    `/api/books/${encodeURIComponent(bookId)}/chapters`,
    {
      method: "GET"
    }
  );
}

export function getChapter(bookId: string, chapterIndex: number): Promise<ChapterDetail> {
  return requestJson<ChapterDetail>(
    `/api/books/${encodeURIComponent(bookId)}/chapters/${chapterIndex}`,
    { method: "GET" }
  );
}

export function listCharacters(
  bookId: string,
  includeUnverified = false
): Promise<CharacterSummary[]> {
  const query = includeUnverified ? "?include_unverified=true" : "";
  return requestJson<CharacterSummary[]>(
    `/api/books/${encodeURIComponent(bookId)}/characters${query}`,
    { method: "GET" }
  );
}

export function getCharacterDetail(
  bookId: string,
  characterId: string
): Promise<CharacterDetail> {
  return requestJson<CharacterDetail>(
    `/api/books/${encodeURIComponent(bookId)}/characters/${encodeURIComponent(characterId)}`,
    { method: "GET" }
  );
}

export function getRelationshipGraph(bookId: string): Promise<RelationshipEdge[]> {
  return requestJson<RelationshipEdge[]>(
    `/api/books/${encodeURIComponent(bookId)}/graph`,
    { method: "GET" }
  );
}

export function getRelationshipGraphNodes(
  bookId: string
): Promise<RelationshipGraphNodeMetric[]> {
  return requestJson<RelationshipGraphNodeMetric[]>(
    `/api/books/${encodeURIComponent(bookId)}/graph/nodes`,
    { method: "GET" }
  );
}

export function listCharacterPortraits(
  bookId: string,
  status?: string,
  characterId?: string
): Promise<CharacterPortrait[]> {
  const params = new URLSearchParams();
  if (status) {
    params.set("status", status);
  }
  if (characterId) {
    params.set("character_id", characterId);
  }
  const query = params.toString() ? `?${params.toString()}` : "";
  return requestJson<CharacterPortrait[]>(
    `/api/books/${encodeURIComponent(bookId)}/portraits${query}`,
    { method: "GET" }
  );
}

export function postRoleChat(payload: ChatRequest): Promise<ChatResponse> {
  return requestJson<ChatResponse>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
}

export function runBookSkills(
  bookId: string,
  chapterIndex: number,
  incremental = true
): Promise<UploadResponse> {
  return requestJson<UploadResponse>(`/api/books/${encodeURIComponent(bookId)}/skills/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      chapter_index: chapterIndex,
      incremental
    })
  });
}

export function triggerCharacterPortraitGenerate(
  bookId: string,
  characterId: string
): Promise<UploadResponse> {
  return requestJson<UploadResponse>(
    `/api/books/${encodeURIComponent(bookId)}/characters/${encodeURIComponent(characterId)}/portrait/generate`,
    {
      method: "POST"
    }
  );
}

export function enqueueVisualPortraitJob(
  bookId: string,
  characterId: string,
  chapterIndex?: number | null
): Promise<VisualJobCreateResponse> {
  const query = chapterIndex ? `?chapter_index=${chapterIndex}` : "";
  return requestJson<VisualJobCreateResponse>(
    `/api/books/${encodeURIComponent(bookId)}/visual/portrait/jobs/${encodeURIComponent(characterId)}${query}`,
    { method: "POST" }
  );
}

export function getVisualJobStatus(
  bookId: string,
  jobId: string
): Promise<VisualJobStatusResponse> {
  return requestJson<VisualJobStatusResponse>(
    `/api/books/${encodeURIComponent(bookId)}/visual/jobs/${encodeURIComponent(jobId)}`,
    { method: "GET" }
  );
}

export function listMediaAssets(
  bookId: string,
  assetType?: string,
  characterId?: string
): Promise<MediaAsset[]> {
  const params = new URLSearchParams();
  if (assetType) params.set("asset_type", assetType);
  if (characterId) params.set("character_id", characterId);
  const query = params.toString() ? `?${params.toString()}` : "";
  return requestJson<MediaAsset[]>(
    `/api/books/${encodeURIComponent(bookId)}/visual/assets${query}`,
    { method: "GET" }
  );
}

export function enqueueVisualJob(
  bookId: string,
  payload: VisualJobCreateRequest
): Promise<VisualJobCreateResponse> {
  return requestJson<VisualJobCreateResponse>(
    `/api/books/${encodeURIComponent(bookId)}/visual/jobs`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }
  );
}
