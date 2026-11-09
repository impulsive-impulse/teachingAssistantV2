import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, collectionApi, type Backend, type ClaimCitation } from "../../lib/api";

export function CollectionPage() {
  const client = useQueryClient();
  const sources = useQuery({ queryKey: ["collection-sources"], queryFn: collectionApi.sources });
  const collections = useQuery({ queryKey: ["collections"], queryFn: collectionApi.collections });
  const books = useQuery({ queryKey: ["books"], queryFn: api.books });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [documentIds, setDocumentIds] = useState<string[]>([]);
  const [title, setTitle] = useState("My collection");
  const [question, setQuestion] = useState("");
  const [backend, setBackend] = useState<Backend>("offline");
  const [authorizedIndexing, setAuthorizedIndexing] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [citation, setCitation] = useState<ClaimCitation | null>(null);
  const active = collections.data?.find((item) => item.id === selectedId) ?? collections.data?.[0];
  const ask = useMutation({
    mutationFn: () => collectionApi.ask(active!.id, question.trim(), backend, acknowledged),
    onSuccess: () => setQuestion(""),
    onSettled: () => client.invalidateQueries({ queryKey: ["collection-queries"] }),
  });
  const history = useQuery({
    queryKey: ["collection-queries", active?.id],
    queryFn: () => collectionApi.history(active!.id),
    enabled: Boolean(active),
    refetchInterval: (query) => ask.isPending || query.state.data?.some(
      (item) => item.state === "retrieving" || item.state === "generating",
    ) ? 2000 : false,
  });
  const importBook = useMutation({
    mutationFn: collectionApi.fromBook,
    onSuccess: () => client.invalidateQueries({ queryKey: ["collection-sources"] }),
  });
  const create = useMutation({
    mutationFn: () => collectionApi.create(title.trim(), documentIds),
    onSuccess: (created) => {
      setSelectedId(created.id);
      setDocumentIds([]);
      void client.invalidateQueries({ queryKey: ["collections"] });
    },
  });
  const error = sources.error ?? collections.error ?? history.error ?? books.error ?? importBook.error ?? create.error ?? ask.error;
  return (
    <main className="collection-page">
      <header><p className="eyebrow">Versioned context layer</p><h1>Ask across documents</h1>
        <p>Each question is independent. Claims link to original source units; printed page labels are not guessed.</p>
        <p className="subtle">PDF answers select literal source clauses. This profile is separate from the benchmark generator.</p></header>
      {error && <p className="inline-error" role="alert">{error.message}</p>}
      <div className="collection-grid">
        <section className="collection-card" aria-label="Collection and source selection">
          <h2>Collections</h2>
          {collections.data?.map((item) => <button key={item.id} className="button button--secondary" disabled={ask.isPending}
            onClick={() => { setSelectedId(item.id); setCitation(null); }}>{item.title} ({item.document_ids.length})</button>)}
          <h2>Create a collection</h2>
          <label>Title<input value={title} maxLength={120} onChange={(event) => setTitle(event.target.value)} /></label>
          {sources.data?.map((source) => <label className="collection-check" key={source.id}>
            <input type="checkbox" checked={documentIds.includes(source.id)} onChange={(event) => setDocumentIds(
              event.target.checked ? [...documentIds, source.id] : documentIds.filter((id) => id !== source.id),
            )} />{source.title} ({source.unit_count} units)
          </label>)}
          <button className="button button--primary" disabled={!title.trim() || !documentIds.length || create.isPending}
            onClick={() => create.mutate()}>Create collection</button>
          <h2>Add ready library books</h2>
          <p>Upload PDFs in Library first. Collection imports retain independent verified source copies.</p>
          <label className="collection-check"><input type="checkbox" checked={authorizedIndexing}
            onChange={(event) => setAuthorizedIndexing(event.target.checked)} />I have permission for local indexing.</label>
          {books.data?.filter((book) => book.status === "ready").map((book) => <button className="button button--quiet" key={book.id}
            disabled={!authorizedIndexing || importBook.isPending} onClick={() => importBook.mutate(book.id)}>Import {book.title}</button>)}
        </section>
        <section className="collection-card" aria-label="Collection questions">
          <h2>{active?.title ?? "Create or select a collection"}</h2>
          <p>{active?.documents.map((source) => source.title).join(" + ")}</p>
          {history.data?.map((query) => <article className="collection-answer" key={query.id}>
            <h3>{query.question}</h3><p className="subtle">{query.backend} · {query.state}{
              query.execution_mode === "cached_pdf_adapter_replay" ? " · cached adapter replay (no new call)" : ""
            }</p>
            {query.error_code && <p className="inline-error">{query.error_code}: {query.validation_errors.join("; ")}</p>}
            {query.output && <>
              <strong>{query.output.short_answer || "Insufficient evidence"}</strong>
              {query.output.claims.map((claim, index) => <div key={index}><p>{claim.text}</p>
                {claim.citations.map((source, number) => <button className="button button--quiet" key={number}
                  onClick={() => setCitation(source)}>{source.source.document_title} · {
                    source.source.pdf_page !== null ? `PDF page ${source.source.pdf_page}` : `sentence ${source.source.sentence_index}`
                  }</button>)}</div>)}
              {query.output.missing_information.map((item, index) => <p key={index}>{item}</p>)}
              <p className="subtle">Quoted address/lexical checks passed; semantic support still needs source review.</p>
            </>}
          </article>)}
          <form onSubmit={(event) => { event.preventDefault(); ask.mutate(); }}>
            <label>Question<textarea value={question} maxLength={2000} onChange={(event) => setQuestion(event.target.value)} /></label>
            <label>Backend<select value={backend} onChange={(event) => { setBackend(event.target.value === "online" ? "online" : "offline"); setAcknowledged(false); }}>
              <option value="offline">Offline Qwen (local)</option><option value="online">Online GPT-4o (paid)</option>
            </select></label>
            {backend === "online" && <label className="collection-check"><input type="checkbox" checked={acknowledged}
              onChange={(event) => setAcknowledged(event.target.checked)} />
              I authorize sending this question and retrieved excerpts to OpenAI, have the required source permissions,
              and accept a paid call from the shared assessment contingency budget.
            </label>}
            <button className="button button--primary" disabled={!active || !question.trim() || ask.isPending || (backend === "online" && !acknowledged)}>
              {ask.isPending ? "Retrieving and checking claims..." : "Ask collection"}
            </button>
          </form>
          {citation && <aside className="collection-citation" aria-label="Selected citation">
            <h3>{citation.source.document_title}</h3><p>Original {citation.unit_id}; character ranges {JSON.stringify(citation.source.char_ranges)}</p>
            <blockquote>{citation.quote}</blockquote>
            {citation.source.pdf_page !== null && <a className="button button--secondary" target="_blank" rel="noreferrer"
              href={`/api/sources/${encodeURIComponent(citation.source.document_id)}/file#page=${citation.source.pdf_page}`}>
              Open original PDF page {citation.source.pdf_page}
            </a>}
          </aside>}
        </section>
      </div>
    </main>
  );
}
