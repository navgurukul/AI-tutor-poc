import { useCallback, useEffect, useRef, useState } from "react";
import {
  deleteDocument,
  fetchDocuments,
  fetchJob,
  fetchLibraryStatus,
  uploadTextbook,
  type IngestJob,
  type LibraryDocument,
  type LibraryStatus,
} from "../services/library";

const SUBJECTS = [
  "Mathematics",
  "Science",
  "Physics",
  "Chemistry",
  "Biology",
  "English",
  "Social Science",
  "History",
  "Geography",
  "Computer Science",
];

const GRADES = Array.from({ length: 12 }, (_, i) => i + 1);

// Ingestion is minutes-long on the target laptops, so the page polls rather
// than holding a request open. Two seconds is often enough to show a chunk
// counter moving without generating noticeable load of its own.
const POLL_INTERVAL_MS = 2000;

const STATUS_LABEL: Record<IngestJob["status"], string> = {
  queued: "Queued",
  extracting: "Reading PDF",
  embedding: "Embedding",
  done: "Added",
  error: "Failed",
};

interface SetupPageProps {
  onBack: () => void;
}

export function SetupPage({ onBack }: SetupPageProps) {
  const [status, setStatus] = useState<LibraryStatus | null>(null);
  const [documents, setDocuments] = useState<LibraryDocument[]>([]);
  const [job, setJob] = useState<IngestJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [file, setFile] = useState<File | null>(null);
  const [grade, setGrade] = useState(6);
  const [subject, setSubject] = useState(SUBJECTS[0]);
  const [title, setTitle] = useState("");

  const fileInputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchLibraryStatus();
      setStatus(next);
      // Listing documents needs an open store; asking for them when it is
      // unavailable would replace the explanatory banner with a 503.
      setDocuments(next.available ? await fetchDocuments() : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll only while a job is actually running.
  useEffect(() => {
    if (!job || job.status === "done" || job.status === "error") return;
    const timer = window.setInterval(async () => {
      try {
        const next = await fetchJob(job.id);
        setJob(next);
        if (next.status === "done") void refresh();
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [job, refresh]);

  async function handleUpload(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    setError(null);
    setBusy(true);
    try {
      const started = await uploadTextbook({
        file,
        grade,
        subject,
        title: title.trim() || undefined,
      });
      setJob(started);
      setFile(null);
      setTitle("");
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(doc: LibraryDocument) {
    if (!window.confirm(`Remove "${doc.title}" from the library?`)) return;
    setError(null);
    try {
      await deleteDocument(doc.id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  const unavailable = status && !status.available;

  return (
    <div className="setup">
      <header className="setup__bar">
        <button className="setup__back" onClick={onBack} type="button">
          ← Back to tutor
        </button>
        <div>
          <h1 className="setup__title">Textbook library</h1>
          <p className="setup__sub">
            Add the PDFs the tutor should teach from. Each one is cleaned,
            split and indexed on this device.
          </p>
        </div>
      </header>

      {error && (
        <div className="setup__alert setup__alert--error" role="alert">
          {error}
        </div>
      )}

      {unavailable && (
        <div className="setup__alert setup__alert--warn">
          <strong>Retrieval is unavailable.</strong> {status?.reason}
          {status?.hint && <div className="setup__hint">{status.hint}</div>}
        </div>
      )}

      {status?.available && (
        <div className="setup__stats">
          <div>
            <span className="setup__stat">{status.documents ?? 0}</span>
            <span className="setup__statLabel">textbooks</span>
          </div>
          <div>
            <span className="setup__stat">{status.chunks ?? 0}</span>
            <span className="setup__statLabel">passages</span>
          </div>
          <div>
            <span className="setup__stat setup__stat--sm">
              {status.embedding_model}
            </span>
            <span className="setup__statLabel">embedding model</span>
          </div>
        </div>
      )}

      <form className="setup__card" onSubmit={handleUpload}>
        <h2 className="setup__cardTitle">Add a textbook</h2>

        <label className="setup__field">
          <span>PDF file</span>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf,.pdf"
            disabled={!status?.available || busy}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>

        <div className="setup__row">
          <label className="setup__field">
            <span>Class</span>
            <select
              value={grade}
              disabled={!status?.available || busy}
              onChange={(e) => setGrade(Number(e.target.value))}
            >
              {GRADES.map((g) => (
                <option key={g} value={g}>
                  Class {g}
                </option>
              ))}
            </select>
          </label>

          <label className="setup__field">
            <span>Subject</span>
            <select
              value={subject}
              disabled={!status?.available || busy}
              onChange={(e) => setSubject(e.target.value)}
            >
              {SUBJECTS.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label className="setup__field">
          <span>
            Title <em>(optional — defaults to the file name)</em>
          </span>
          <input
            type="text"
            value={title}
            placeholder="e.g. Science — Chapter 6: Tissues"
            disabled={!status?.available || busy}
            onChange={(e) => setTitle(e.target.value)}
          />
        </label>

        <button
          className="setup__submit"
          type="submit"
          disabled={!file || !status?.available || busy}
        >
          {busy ? "Uploading…" : "Add to library"}
        </button>
        <p className="setup__note">
          A chapter takes seconds; a whole textbook can take several minutes on
          an older laptop. You can leave this page — ingestion keeps running.
        </p>
      </form>

      {job && (
        <div
          className={`setup__job setup__job--${job.status === "error" ? "error" : job.status === "done" ? "done" : "active"}`}
        >
          <div className="setup__jobHead">
            <strong>{job.title}</strong>
            <span>{STATUS_LABEL[job.status]}</span>
          </div>
          {job.status !== "error" && (
            <>
              <div className="setup__progress">
                <div
                  className="setup__progressFill"
                  style={{ width: `${Math.round(job.progress * 100)}%` }}
                />
              </div>
              <div className="setup__jobMeta">
                {job.chunks_total > 0
                  ? `${job.chunks_done} / ${job.chunks_total} passages`
                  : job.stage_detail}
                {" · "}
                {job.elapsed_seconds}s
              </div>
            </>
          )}
          {job.error && (
            <div className="setup__jobError">
              {job.error}
              {job.hint && <div className="setup__hint">{job.hint}</div>}
            </div>
          )}
        </div>
      )}

      <section className="setup__card">
        <h2 className="setup__cardTitle">
          In the library{documents.length > 0 && ` (${documents.length})`}
        </h2>
        {documents.length === 0 ? (
          <p className="setup__empty">
            Nothing yet. The tutor answers from the model alone until a
            textbook is added.
          </p>
        ) : (
          <ul className="setup__list">
            {documents.map((doc) => (
              <li key={doc.id} className="setup__item">
                <div>
                  <div className="setup__itemTitle">{doc.title}</div>
                  <div className="setup__itemMeta">
                    Class {doc.grade} · {doc.subject} · {doc.pages} pages ·{" "}
                    {doc.chunk_count} passages
                  </div>
                </div>
                <button
                  className="setup__delete"
                  type="button"
                  onClick={() => handleDelete(doc)}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
