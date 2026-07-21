import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, BookOpen, ChevronDown, ChevronUp, LoaderCircle, Plus, Send, Square, Trash2, Wifi, WifiOff } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { api, type Attempt, type Backend, type SourceItem } from "../../lib/api";

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

export function ChatPage() {
  const { bookId = "" } = useParams();
  const queryClient = useQueryClient();
  const books = useQuery({ queryKey: ["books"], queryFn: api.books });
  const chats = useQuery({ queryKey: ["chats", bookId], queryFn: () => api.chats(bookId), enabled: Boolean(bookId) });
  const [chatId, setChatId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [override, setOverride] = useState<"inherit" | Backend>("inherit");
  const [acknowledged, setAcknowledged] = useState(() => sessionStorage.getItem("online-disclosure") === "yes");
  const [live, setLive] = useState<Record<string, string>>({});
  const streams = useRef<Record<string, EventSource>>({});
  const book = books.data?.find((item) => item.id === bookId);
  useEffect(() => {
    if (!chatId && chats.data?.length) setChatId(chats.data[0].id);
  }, [chatId, chats.data]);
  useEffect(() => () => Object.values(streams.current).forEach((stream) => stream.close()), []);
  const transcript = useQuery({
    queryKey: ["transcript", chatId], queryFn: () => api.transcript(chatId!), enabled: Boolean(chatId),
  });
  const currentChat = transcript.data?.chat ?? chats.data?.find((chat) => chat.id === chatId);
  const defaultBackend = currentChat?.default_backend ?? "online";
  const selectedBackend = override === "inherit" ? defaultBackend : override;
  const activeAttempt = useMemo(() => transcript.data?.messages.flatMap((message) => message.attempts)
    .find((attempt) => !TERMINAL.has(attempt.state)), [transcript.data]);

  const createChat = useMutation({
    mutationFn: () => api.createChat(bookId),
    onSuccess: async (chat) => { await queryClient.invalidateQueries({ queryKey: ["chats", bookId] }); setChatId(chat.id); },
  });
  const changeBackend = useMutation({
    mutationFn: (backend: Backend) => api.updateChatBackend(chatId!, backend),
    onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ["transcript", chatId] }); setOverride("inherit"); },
  });
  const removeChat = useMutation({
    mutationFn: () => api.deleteChat(chatId!),
    onSuccess: async () => {
      setChatId(null);
      await queryClient.invalidateQueries({ queryKey: ["chats", bookId] });
      await queryClient.removeQueries({ queryKey: ["transcript", chatId] });
    },
  });

  const watchAttempt = (attempt: Attempt) => {
    const stream = new EventSource(`/api/attempts/${attempt.id}/events`);
    streams.current[attempt.id] = stream;
    stream.addEventListener("answer_delta", (event) => {
      const { delta } = JSON.parse((event as MessageEvent).data) as { delta: string };
      setLive((value) => ({ ...value, [attempt.id]: (value[attempt.id] ?? "") + delta }));
    });
    for (const name of ["completed", "failed", "cancelled"]) stream.addEventListener(name, () => {
      stream.close(); delete streams.current[attempt.id];
      void queryClient.invalidateQueries({ queryKey: ["transcript", chatId] });
    });
    stream.onerror = () => { stream.close(); delete streams.current[attempt.id]; void queryClient.invalidateQueries({ queryKey: ["transcript", chatId] }); };
  };
  const send = useMutation({
    mutationFn: () => api.sendMessage(chatId!, draft.trim(), override === "inherit" ? null : override, acknowledged),
    onSuccess: async ({ attempt }) => { setDraft(""); await queryClient.invalidateQueries({ queryKey: ["transcript", chatId] }); watchAttempt(attempt); },
  });
  const regenerate = useMutation({
    mutationFn: ({ messageId, backend }: { messageId: string; backend: Backend }) => api.regenerate(messageId, backend, acknowledged),
    onSuccess: async (attempt) => { await queryClient.invalidateQueries({ queryKey: ["transcript", chatId] }); watchAttempt(attempt); },
  });
  const acknowledge = (checked: boolean) => { setAcknowledged(checked); if (checked) sessionStorage.setItem("online-disclosure", "yes"); else sessionStorage.removeItem("online-disclosure"); };

  if (!book) return <main className="chat-loading">Loading textbook…</main>;
  return (
    <main className="chat-layout">
      <aside className="chat-list">
        <Link className="text-button" to="/"><ArrowLeft size={15} /> Library</Link>
        <div className="chat-book"><span className="book-cover chat-book__cover">{book.title.slice(0, 1)}</span><div><p className="eyebrow">Selected textbook</p><strong>{book.title}</strong></div></div>
        <button className="button button--secondary" onClick={() => createChat.mutate()} disabled={createChat.isPending}><Plus size={16} /> New chat</button>
        <div className="chat-list__items">{chats.data?.map((chat) => <button key={chat.id} className={chat.id === chatId ? "active" : ""} onClick={() => setChatId(chat.id)}>{chat.title}</button>)}</div>
      </aside>
      <section className="conversation">
        {!chatId ? <div className="conversation-empty"><BookOpen size={32} /><h1>Ask this textbook</h1><p>Each question is answered independently. Include the topic in your question.</p><button className="button button--primary" onClick={() => createChat.mutate()}>Start a chat</button></div> : <>
          <header className="conversation__header"><div><p className="eyebrow">Book-scoped chat</p><h1>{currentChat?.title}</h1></div><div className="conversation__tools"><BackendToggle value={defaultBackend} busy={changeBackend.isPending} onChange={(value) => changeBackend.mutate(value)} /><button className="icon-button" aria-label="Delete this chat" disabled={Boolean(activeAttempt) || removeChat.isPending} onClick={() => { if (window.confirm(`Delete “${currentChat?.title ?? "this chat"}” and its transcript?`)) removeChat.mutate(); }}><Trash2 size={16} /></button></div></header>
          <div className="transcript">
            {transcript.data?.messages.length === 0 && <div className="conversation-empty"><BookOpen size={30} /><h2>Begin with a self-contained question</h2><p>Earlier messages are displayed here, but never added to retrieval or generation.</p></div>}
            {transcript.data?.messages.map((message) => <article className="message-pair" key={message.id}><div className="user-message">{message.question}</div>{message.attempts.map((attempt) => <AnswerCard key={attempt.id} attempt={attempt} liveText={live[attempt.id]} acknowledged={acknowledged} busy={regenerate.isPending || Boolean(activeAttempt)} onRegenerate={(backend) => regenerate.mutate({ messageId: message.id, backend })} />)}</article>)}
          </div>
          <footer className="composer">
            {selectedBackend === "online" && <label className="disclosure"><input type="checkbox" checked={acknowledged} onChange={(event) => acknowledge(event.target.checked)} /> My question and retrieved textbook excerpts may be sent to OpenAI.</label>}
            {send.isError && <p className="inline-error">{send.error.message}</p>}
            <div className="composer__box"><textarea value={draft} onChange={(event) => setDraft(event.target.value)} placeholder="Ask a self-contained question about this textbook…" rows={2} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); if (draft.trim() && !activeAttempt && (selectedBackend !== "online" || acknowledged)) send.mutate(); } }} /><div className="composer__actions"><select value={override} onChange={(event) => setOverride(event.target.value as "inherit" | Backend)}><option value="inherit">Use chat default ({defaultBackend})</option><option value="online">Online · GPT-4o</option><option value="offline">Offline · Qwen</option></select>{activeAttempt ? <button className="button button--quiet" onClick={() => api.cancelAttempt(activeAttempt.id)}><Square size={14} /> Stop</button> : <button className="button button--primary" disabled={!draft.trim() || send.isPending || (selectedBackend === "online" && !acknowledged)} onClick={() => send.mutate()}>{send.isPending ? <LoaderCircle className="spin" size={16} /> : <Send size={16} />} Ask</button>}</div></div>
          </footer>
        </>}
      </section>
    </main>
  );
}

function BackendToggle({ value, busy, onChange }: { value: Backend; busy: boolean; onChange: (value: Backend) => void }) {
  return <div className="backend-toggle" aria-label="Default answer backend"><button className={value === "online" ? "active" : ""} disabled={busy} onClick={() => onChange("online")}><Wifi size={14} /> Online</button><button className={value === "offline" ? "active" : ""} disabled={busy} onClick={() => onChange("offline")}><WifiOff size={14} /> Offline</button></div>;
}

function AnswerCard({ attempt, liveText, acknowledged, busy, onRegenerate }: { attempt: Attempt; liveText?: string; acknowledged: boolean; busy: boolean; onRegenerate: (backend: Backend) => void }) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const sources = useQuery({ queryKey: ["sources", attempt.id], queryFn: () => api.sources(attempt.id), enabled: sourcesOpen && Boolean(attempt.retrieval_snapshot_id) });
  const opposite: Backend = attempt.backend === "online" ? "offline" : "online";
  const answer = attempt.output?.answer ?? liveText;
  return <div className="answer-card"><div className="answer-card__meta"><span className={`provider-badge provider-badge--${attempt.backend}`}>{attempt.backend === "online" ? <Wifi size={13} /> : <WifiOff size={13} />}{attempt.backend}</span><span>{attempt.state.replaceAll("_", " ")}</span></div>{answer ? <p className="answer-text">{answer}</p> : attempt.state === "failed" ? <p className="answer-error">{attempt.error_message}</p> : <p className="answer-pending"><LoaderCircle className="spin" size={15} /> {attempt.state === "retrieving" ? "Finding evidence…" : "Preparing answer…"}</p>}<div className="answer-card__actions"><button className="text-button" disabled={!attempt.retrieval_snapshot_id} onClick={() => setSourcesOpen((value) => !value)}>{sourcesOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />} View sources</button>{attempt.state === "completed" && <button className="text-button" disabled={busy || (opposite === "online" && !acknowledged)} title={opposite === "online" && !acknowledged ? "Acknowledge online sharing below first" : undefined} onClick={() => onRegenerate(opposite)}>Regenerate {opposite}</button>}</div>{sourcesOpen && <SourceList loading={sources.isLoading} sources={sources.data?.sources ?? []} />}</div>;
}

function SourceList({ loading, sources }: { loading: boolean; sources: SourceItem[] }) {
  if (loading) return <p className="source-loading">Loading evidence…</p>;
  return <div className="source-list">{sources.map((source) => <details key={source.evidence_id}><summary><strong>{source.evidence_id}</strong><span>PDF {source.pdf_page} · textbook {source.textbook_page}</span></summary><p>{source.text}</p></details>)}</div>;
}
