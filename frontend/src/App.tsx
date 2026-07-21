import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { BookMarked, Bug, Library, MessageSquareText, Settings, X } from "lucide-react";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import { ChatPage } from "./features/chat/ChatPage";
import { LibraryPage } from "./features/library/LibraryPage";
import { ReadinessStrip } from "./features/system/ReadinessStrip";
import { api, type ModelSetupJob } from "./lib/api";

export default function App() {
  const queryClient = useQueryClient();
  const [setupJob, setSetupJob] = useState<ModelSetupJob | null>(null);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const location = useLocation();
  const status = useQuery({ queryKey: ["system-status"], queryFn: api.systemStatus, refetchInterval: 30_000 });
  const diagnostics = useQuery({ queryKey: ["system-diagnostics"], queryFn: api.systemDiagnostics, enabled: showDiagnostics });
  const offlineRuntime = useQuery({ queryKey: ["offline-runtime"], queryFn: api.offlineRuntime, enabled: showSettings, refetchInterval: showSettings ? 5_000 : false });
  const loadOffline = useMutation({ mutationFn: api.loadOffline, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["offline-runtime"] }) });
  const unloadOffline = useMutation({ mutationFn: api.unloadOffline, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["offline-runtime"] }) });
  const embeddingSetup = useMutation({
    mutationFn: api.setupEmbeddingModel,
    onSuccess: (job) => {
      setSetupJob(job);
      const stream = new EventSource(`/api/system/embedding/setup/${job.id}/events`);
      stream.addEventListener("progress", (event) => {
        const update = JSON.parse((event as MessageEvent).data) as ModelSetupJob;
        setSetupJob(update);
        if (["completed", "failed", "cancelled"].includes(update.state)) {
          stream.close();
          void queryClient.invalidateQueries({ queryKey: ["system-status"] });
        }
      });
    },
  });
  const offlineSetup = useMutation({
    mutationFn: api.setupOfflineProvider,
    onSuccess: (job) => {
      setSetupJob(job);
      const stream = new EventSource(`/api/system/offline/setup/${job.id}/events`);
      stream.addEventListener("progress", (event) => {
        const update = JSON.parse((event as MessageEvent).data) as ModelSetupJob;
        setSetupJob(update);
        if (["completed", "failed", "cancelled"].includes(update.state)) {
          stream.close();
          void queryClient.invalidateQueries({ queryKey: ["system-status"] });
        }
      });
    },
  });
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand__mark"><BookMarked size={21} /></span><span>Marginalia</span></div>
        <nav aria-label="Primary navigation">
          <Link className={`nav-link ${location.pathname === "/" ? "nav-link--active" : ""}`} to="/"><Library size={18} /> Library</Link>
          <button className="nav-link" disabled><MessageSquareText size={18} /> Recent chats</button>
        </nav>
        <div className="sidebar__bottom">
          <button className="nav-link" onClick={() => setShowDiagnostics(true)}><Bug size={18} /> Diagnostics</button>
          <button className="nav-link" onClick={() => setShowSettings(true)}><Settings size={18} /> Settings</button>
          <p>Local only · Baseline v1</p>
        </div>
      </aside>
      <div className="workspace">
        {status.data ? (
          <ReadinessStrip
            status={status.data}
            setupBusy={embeddingSetup.isPending || Boolean(setupJob?.component === "embedding_model" && ["queued", "running"].includes(setupJob.state))}
            onSetupEmbedding={() => embeddingSetup.mutate()}
            offlineSetupBusy={offlineSetup.isPending || Boolean(setupJob?.component === "offline_provider" && ["queued", "running"].includes(setupJob.state))}
            onSetupOffline={() => offlineSetup.mutate()}
          />
        ) : <div className="readiness readiness--loading">Checking local system readiness…</div>}
        <Routes>
          <Route path="/" element={<LibraryPage />} />
          <Route path="/books/:bookId" element={<ChatPage />} />
        </Routes>
      </div>
      {showDiagnostics && <div className="modal-backdrop" role="presentation"><section className="diagnostics-panel" role="dialog" aria-modal="true" aria-labelledby="diagnostics-title"><button className="icon-button diagnostics-panel__close" aria-label="Close diagnostics" onClick={() => setShowDiagnostics(false)}><X size={19} /></button><p className="eyebrow">Local developer view</p><h2 id="diagnostics-title">System diagnostics</h2><p className="subtle">No API key values or textbook content are included.</p>{diagnostics.isLoading ? <p>Collecting local status…</p> : diagnostics.isError ? <p className="inline-error">Diagnostics are unavailable.</p> : <pre>{JSON.stringify(diagnostics.data, null, 2)}</pre>}</section></div>}
      {showSettings && <div className="modal-backdrop" role="presentation"><section className="diagnostics-panel settings-panel" role="dialog" aria-modal="true" aria-labelledby="settings-title"><button className="icon-button diagnostics-panel__close" aria-label="Close settings" onClick={() => setShowSettings(false)}><X size={19} /></button><p className="eyebrow">Frozen local provider</p><h2 id="settings-title">Offline model</h2><p className="subtle">Qwen3-8B Q4_K_M · llama.cpp b10046 · CPU only</p><div className="settings-card"><div><strong>{offlineRuntime.data?.state === "loaded" ? "Loaded in memory" : offlineRuntime.data?.artifacts_ready ? "Ready to load" : "Setup required"}</strong><p>{offlineRuntime.data?.detail ?? "Checking the local runtime…"}</p>{setupJob?.component === "offline_provider" && ["queued", "running"].includes(setupJob.state) && <div className="progress-track"><span style={{ width: `${Math.max(3, setupJob.progress * 100)}%` }} /></div>}</div><div className="settings-card__actions">{!offlineRuntime.data?.artifacts_ready ? <button className="button button--secondary" disabled={offlineSetup.isPending} onClick={() => offlineSetup.mutate()}>Set up exact artifacts</button> : offlineRuntime.data.state === "loaded" ? <button className="button button--quiet" disabled={unloadOffline.isPending} onClick={() => unloadOffline.mutate()}>Unload model</button> : <button className="button button--primary" disabled={loadOffline.isPending} onClick={() => loadOffline.mutate()}>Load model</button>}</div></div>{(loadOffline.isError || unloadOffline.isError || offlineSetup.isError) && <p className="inline-error">{(loadOffline.error ?? unloadOffline.error ?? offlineSetup.error)?.message}</p>}</section></div>}
    </div>
  );
}
