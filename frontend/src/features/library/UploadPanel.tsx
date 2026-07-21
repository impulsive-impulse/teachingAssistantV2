import { useRef, useState, type DragEvent } from "react";
import { FileText, UploadCloud, X } from "lucide-react";

interface Props {
  busy: boolean;
  error: string | null;
  onClose: () => void;
  onUpload: (file: File) => void;
}

export function UploadPanel({ busy, error, onClose, onUpload }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const choose = (file?: File) => {
    if (file) onUpload(file);
  };

  const drop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    choose(event.dataTransfer.files[0]);
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section className="upload-panel" role="dialog" aria-modal="true" aria-labelledby="upload-title" onMouseDown={(event) => event.stopPropagation()}>
        <button className="icon-button upload-panel__close" onClick={onClose} aria-label="Close upload">
          <X size={20} />
        </button>
        <span className="upload-panel__icon"><FileText size={23} /></span>
        <p className="eyebrow">Add to your library</p>
        <h2 id="upload-title">Choose a textbook</h2>
        <p className="subtle">English, digitally generated textbook PDFs only. Scans and general documents are rejected.</p>
        <div
          className={`drop-zone ${dragging ? "drop-zone--active" : ""}`}
          onDragEnter={() => setDragging(true)}
          onDragLeave={() => setDragging(false)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={drop}
        >
          <UploadCloud size={30} />
          <strong>{busy ? "Uploading locally…" : "Drop one PDF here"}</strong>
          <span>or</span>
          <button className="button button--secondary" disabled={busy} onClick={() => input.current?.click()}>
            Browse files
          </button>
          <input ref={input} type="file" accept="application/pdf,.pdf" hidden onChange={(event) => choose(event.target.files?.[0])} />
        </div>
        {error && <p className="inline-error" role="alert">{error}</p>}
        <p className="upload-note">The PDF stays on this machine while it is validated, processed, and indexed.</p>
      </section>
    </div>
  );
}
