/**
 * Setup-page API client: upload textbooks, watch ingestion, manage the library.
 *
 * Kept apart from services/api.ts because none of this has a mock path. The
 * mock tutor exists so the chat UI can be developed with no backend; ingestion
 * is meaningless without one, so these calls always go to the real server and
 * say so plainly when it isn't there.
 */

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export interface LibraryDocument {
  id: number;
  filename: string;
  title: string;
  grade: number;
  subject: string;
  pages: number;
  chunk_count: number;
  created_at: string;
}

export interface IngestJob {
  id: string;
  filename: string;
  title: string;
  grade: number;
  subject: string;
  status: "queued" | "extracting" | "embedding" | "done" | "error";
  stage_detail: string;
  pages: number;
  chunks_total: number;
  chunks_done: number;
  progress: number;
  document_id: number | null;
  error: string | null;
  hint: string | null;
  elapsed_seconds: number;
}

export interface LibraryStatus {
  enabled: boolean;
  available: boolean;
  reason?: string;
  hint?: string | null;
  embedding_model?: string;
  dims?: number;
  documents?: number;
  chunks?: number;
  db_path?: string;
  coverage?: Array<{
    grade: number;
    subject: string;
    documents: number;
    chunks: number;
  }>;
}

function unreachable(): Error {
  return new Error(
    `Can't reach the tutor backend at ${API_BASE_URL}. Start it with ` +
      `scripts/start.sh (macOS/Linux) or scripts\\start.ps1 (Windows).`,
  );
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw unreachable();
  }
  if (!res.ok) {
    // FastAPI puts the actionable message in `detail`; surfacing the raw JSON
    // body instead would show the user a serialised object.
    let message = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) message = String(body.detail);
    } catch {
      /* non-JSON error body: keep the status line */
    }
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export function fetchLibraryStatus(): Promise<LibraryStatus> {
  return call<LibraryStatus>("/api/library/status");
}

export async function fetchDocuments(): Promise<LibraryDocument[]> {
  const { documents } = await call<{ documents: LibraryDocument[] }>(
    "/api/library/documents",
  );
  return documents;
}

export async function uploadTextbook(params: {
  file: File;
  grade: number;
  subject: string;
  title?: string;
}): Promise<IngestJob> {
  const form = new FormData();
  form.append("file", params.file);
  form.append("grade", String(params.grade));
  form.append("subject", params.subject);
  if (params.title) form.append("title", params.title);

  // No Content-Type header: the browser has to set it itself so it can add the
  // multipart boundary, and naming it explicitly breaks the upload.
  const { job } = await call<{ job: IngestJob }>("/api/library/documents", {
    method: "POST",
    body: form,
  });
  return job;
}

export async function fetchJob(jobId: string): Promise<IngestJob> {
  const { job } = await call<{ job: IngestJob }>(`/api/library/jobs/${jobId}`);
  return job;
}

export function deleteDocument(id: number): Promise<{ deleted: boolean }> {
  return call<{ deleted: boolean }>(`/api/library/documents/${id}`, {
    method: "DELETE",
  });
}

export interface SearchHit {
  title: string;
  heading: string;
  page_start: number;
  page_end: number;
  grade: number | null;
  subject: string | null;
  distance: number;
}

export function searchLibrary(payload: {
  question: string;
  grade?: number;
  subject?: string;
}): Promise<{ hits: SearchHit[]; excerpts: string[] }> {
  return call("/api/library/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}
