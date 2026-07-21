import { Cpu } from "lucide-react";
import type { SystemStatus } from "../../lib/api";

interface Props {
  status: SystemStatus;
  setupBusy: boolean;
  onSetupEmbedding: () => void;
  offlineSetupBusy: boolean;
  onSetupOffline: () => void;
}

function ReadinessItem({ ready, label, detail }: { ready: boolean; label: string; detail: string }) {
  return (
    <div className="readiness-item" title={detail}>
      <span className={ready ? "status-dot status-dot--ready" : "status-dot status-dot--muted"} />
      <span>{label}</span>
    </div>
  );
}

export function ReadinessStrip({ status, setupBusy, onSetupEmbedding, offlineSetupBusy, onSetupOffline }: Props) {
  return (
    <section className="readiness" aria-label="System readiness">
      <div className="readiness__summary">
        <span className="eyebrow">System readiness</span>
        <strong>Local workspace ready</strong>
      </div>
      <div className="readiness__items">
        <ReadinessItem ready={status.database.state === "ready"} label="Library" detail={status.database.detail} />
        <div className="readiness-action">
          <ReadinessItem ready={status.embedding_model.state === "ready"} label="Retrieval" detail={status.embedding_model.detail} />
          {status.embedding_model.state === "setup_required" && (
            <button onClick={onSetupEmbedding} disabled={setupBusy}>
              {setupBusy ? "Setting up…" : "Set up"}
            </button>
          )}
        </div>
        <ReadinessItem ready={status.online_provider.state === "ready"} label="GPT-4o" detail={status.online_provider.detail} />
        <div className="readiness-action">
          <ReadinessItem ready={status.offline_provider.state === "ready"} label="Qwen offline" detail={status.offline_provider.detail} />
          {status.offline_provider.state === "setup_required" && (
            <button onClick={onSetupOffline} disabled={offlineSetupBusy}>
              {offlineSetupBusy ? "Setting up…" : "Set up"}
            </button>
          )}
        </div>
      </div>
      <div className="readiness__hardware" title={`${status.cpu} · ${status.memory}`}>
        <Cpu size={16} />
        <span>CPU only</span>
      </div>
    </section>
  );
}
