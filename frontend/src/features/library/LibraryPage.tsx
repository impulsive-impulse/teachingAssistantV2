import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Plus, Search, SlidersHorizontal } from "lucide-react";
import { api } from "../../lib/api";
import { BookCard } from "./BookCard";
import { UploadPanel } from "./UploadPanel";

export function LibraryPage() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [showUpload, setShowUpload] = useState(false);
  const books = useQuery({ queryKey: ["books"], queryFn: api.books, refetchInterval: 5_000 });
  useEffect(() => {
    const activeJobs = (books.data ?? [])
      .map((book) => book.current_job)
      .filter((job) => job && ["queued", "running", "interrupted"].includes(job.state));
    const streams = activeJobs.map((job) => {
      const stream = new EventSource(`/api/ingestion/${job!.id}/events`);
      stream.addEventListener("progress", () => {
        void queryClient.invalidateQueries({ queryKey: ["books"] });
      });
      return stream;
    });
    return () => streams.forEach((stream) => stream.close());
  }, [books.data, queryClient]);
  const upload = useMutation({
    mutationFn: api.uploadBook,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["books"] });
      setShowUpload(false);
    },
  });
  const remove = useMutation({
    mutationFn: api.deleteBook,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["books"] }),
  });
  const visible = useMemo(() => {
    const value = search.trim().toLocaleLowerCase();
    return (books.data ?? []).filter((book) => !value || book.title.toLocaleLowerCase().includes(value));
  }, [books.data, search]);

  return (
    <main className="main-content">
      <header className="page-heading">
        <div>
          <p className="eyebrow">Your reading room</p>
          <h1>Textbook library</h1>
          <p className="subtle">Every answer stays scoped to the one textbook you select.</p>
        </div>
        <button className="button button--primary" onClick={() => setShowUpload(true)}><Plus size={18} /> Add textbook</button>
      </header>

      <div className="library-toolbar">
        <label className="search-field">
          <Search size={18} />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search your library" />
        </label>
        <button className="button button--quiet"><SlidersHorizontal size={17} /> All books</button>
        <span className="book-count">{visible.length} {visible.length === 1 ? "textbook" : "textbooks"}</span>
      </div>

      {books.isLoading && <div className="skeleton-grid" aria-label="Loading library"><span /><span /><span /></div>}
      {books.isError && <div className="empty-state"><h2>Library unavailable</h2><p>The local API could not load your books.</p></div>}
      {!books.isLoading && !books.isError && visible.length === 0 && (
        <section className="empty-state">
          <span className="empty-state__icon"><BookOpen size={28} /></span>
          <h2>{search ? "No matching textbooks" : "Your library is waiting"}</h2>
          <p>{search ? "Try another title or clear your search." : "Add an English textbook PDF to build its private, book-scoped index."}</p>
          {!search && <button className="button button--secondary" onClick={() => setShowUpload(true)}><Plus size={17} /> Add your first textbook</button>}
        </section>
      )}
      {visible.length > 0 && <section className="book-grid">{visible.map((book) => <BookCard key={book.id} book={book} deleting={remove.isPending && remove.variables === book.id} onDelete={() => { if (window.confirm(`Delete “${book.title}”, all of its chats, and local indexes?`)) remove.mutate(book.id); }} />)}</section>}
      {showUpload && (
        <UploadPanel
          busy={upload.isPending}
          error={upload.error instanceof Error ? upload.error.message : null}
          onClose={() => !upload.isPending && setShowUpload(false)}
          onUpload={(file) => upload.mutate(file)}
        />
      )}
    </main>
  );
}
