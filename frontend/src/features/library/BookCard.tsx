import { BookOpen, Clock3, FileText, Trash2 } from "lucide-react";
import type { Book } from "../../lib/api";
import { useNavigate } from "react-router-dom";

const STATUS_LABELS: Record<Book["status"], string> = {
  validating: "Validating",
  processing: "Processing",
  indexing: "Indexing",
  ready: "Ready",
  failed: "Needs attention",
  deleting: "Deleting",
};

export function BookCard({ book, deleting, onDelete }: { book: Book; deleting: boolean; onDelete: () => void }) {
  const navigate = useNavigate();
  const progress = Math.round((book.current_job?.overall_progress ?? 0) * 100);
  const stage = book.current_job?.stage.replaceAll("_", " ");
  const metadata = book.status === "ready"
    ? `${book.page_count ?? "—"} pages · ${book.chapter_count ?? "—"} chapters`
    : book.status_reason ?? (stage ? `${stage} · ${progress}%` : "Preparing your textbook for grounded questions");
  return (
    <article className="book-card">
      <div className="book-cover" aria-hidden="true">
        <span>{book.title.slice(0, 1).toUpperCase()}</span>
        <FileText size={18} />
      </div>
      <div className="book-card__body">
        <div className="book-card__topline">
          <span className={`book-status book-status--${book.status}`}>{STATUS_LABELS[book.status]}</span>
          <button className="icon-button" aria-label={`Delete ${book.title}`} disabled={deleting} onClick={onDelete}><Trash2 size={16} /></button>
        </div>
        <h3>{book.title}</h3>
        <p>{metadata}</p>
        {book.status !== "ready" && book.status !== "failed" && (
          <div className="progress-track" aria-label={`${STATUS_LABELS[book.status]} progress`}>
            <span style={{ width: `${Math.max(progress, 3)}%` }} />
          </div>
        )}
        <div className="book-card__footer">
          <span><Clock3 size={14} /> Added {new Date(book.created_at).toLocaleDateString()}</span>
          <button className="text-button" disabled={book.status !== "ready"} onClick={() => navigate(`/books/${book.id}`)}>
            <BookOpen size={15} /> {book.status === "ready" ? "Open" : "View progress"}
          </button>
        </div>
      </div>
    </article>
  );
}
