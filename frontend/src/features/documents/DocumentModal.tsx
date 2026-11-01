import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { DocumentDetail, DocumentStatus, DocumentVersion } from "../../api/types";
import { Alert, Badge, Button, Field, formatDate, Input, Modal, Spinner, Textarea } from "../../components/ui";
import { ReasonModal } from "../org/modals";

export const DOCUMENT_STATUS: Record<DocumentStatus, [string, "slate" | "blue" | "green" | "amber" | "red"]> = {
  draft: ["Draft", "slate"], submitted: ["Waiting for review", "amber"], approved: ["Approved", "green"],
  rejected: ["Rejected", "red"], final: ["Final", "blue"], archived: ["Archived", "slate"],
};
const REVIEW_LABELS: Record<string, [string, "primary" | "secondary" | "danger"]> = {
  submitted: ["Submit for review", "primary"], approved: ["Approve", "primary"], rejected: ["Reject", "danger"],
  final: ["Mark as final", "primary"], archived: ["Archive", "secondary"],
};
const PREVIEWABLE = ["application/pdf", "image/jpeg", "image/png"];

export function DocumentStatusBadge({ status }: { status: DocumentStatus }) {
  const [label, tone] = DOCUMENT_STATUS[status];
  return <Badge tone={tone}>{label}</Badge>;
}

export function fileSize(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function uploadForm(file: File, fields: Record<string, string> = {}) {
  const form = new FormData();
  Object.entries(fields).forEach(([k, v]) => form.append(k, v));
  form.append("file", file);
  return form;
}

/** Opens a short-lived file link. The tab opens first, or the browser would block it as a pop-up. */
async function openFile(documentId: number, version: DocumentVersion, inline: boolean) {
  const tab = window.open("", "_blank");
  try {
    const { url } = await api<{ url: string }>(`/documents/${documentId}/download?version_id=${version.id}&inline=${inline}`);
    if (tab) tab.location.href = url;
    else window.location.href = url;
  } catch (err) {
    tab?.close();
    throw err;
  }
}

export function DocumentModal({ id, onClose }: { id: number; onClose: () => void }) {
  const qc = useQueryClient();
  const doc = useQuery({ queryKey: ["document", id], queryFn: () => api<DocumentDetail>(`/documents/${id}`) });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);

  async function run(action: () => Promise<DocumentDetail | void>) {
    setBusy(true);
    setError(null);
    try {
      const updated = await action();
      if (updated) qc.setQueryData(["document", id], updated);
      qc.invalidateQueries({ queryKey: ["documents"] });
      return true;
    } catch (err) {
      setError(errorMessage(err));
      return false;
    } finally {
      setBusy(false);
    }
  }

  const review = (to_status: string, remarks?: string) =>
    run(() => api<DocumentDetail>(`/documents/${id}/review`, { method: "POST", body: { to_status, remarks } }));

  if (!doc.data) {
    return (
      <Modal title="Document" open onClose={onClose}>
        {doc.error ? <Alert>{errorMessage(doc.error)}</Alert> : <Spinner />}
      </Modal>
    );
  }
  const d = doc.data;
  const open = (v: DocumentVersion, inline: boolean) => openFile(id, v, inline).catch((err) => setError(errorMessage(err)));

  return (
    <Modal title={d.title} open onClose={onClose}>
      <div className="space-y-5 text-sm">
        {error && <Alert>{error}</Alert>}
        <div className="flex flex-wrap items-center gap-2">
          <DocumentStatusBadge status={d.status} />
          <span className="text-slate-500">
            {d.event && <><Link to={`/app/events/${d.event.id}?tab=documents`} className="text-brand-700 hover:underline">{d.event.name}</Link> · </>}
            {d.folder.name}{d.category && ` · ${d.category}`}
          </span>
        </div>
        {d.description && <p className="whitespace-pre-line text-slate-700">{d.description}</p>}

        <div className="flex flex-wrap gap-2">
          {PREVIEWABLE.includes(d.current_version.mime_type) && (
            <Button variant="secondary" onClick={() => open(d.current_version, true)}>Preview</Button>
          )}
          <Button variant="secondary" onClick={() => open(d.current_version, false)}>Download</Button>
          {d.can_upload_version && (
            <>
              <Button variant="secondary" disabled={busy} onClick={() => fileInput.current?.click()}>Upload new version</Button>
              <input ref={fileInput} type="file" hidden aria-label="New version file" accept={ACCEPT}
                     onChange={(e) => {
                       const file = e.target.files?.[0];
                       e.target.value = "";
                       if (file) run(() => api<DocumentDetail>(`/documents/${id}/versions`, { method: "POST", body: uploadForm(file) }));
                     }} />
            </>
          )}
          {d.allowed_reviews.map((s) => (
            <Button key={s} variant={REVIEW_LABELS[s][1]} disabled={busy}
                    onClick={() => s === "rejected" ? setRejecting(true) : review(s)}>{REVIEW_LABELS[s][0]}</Button>
          ))}
          {d.can_delete && <Button variant="ghost" className="text-red-700" disabled={busy} onClick={() => setDeleting(true)}>Delete</Button>}
        </div>

        <section>
          <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Versions</h3>
          <ul className="divide-y divide-slate-100">
            {d.versions.map((v) => (
              <li key={v.id} className="flex items-center justify-between gap-3 py-2">
                <div className="min-w-0">
                  <div className="truncate font-medium text-slate-800">v{v.version_no} · {v.original_filename}</div>
                  <div className="text-xs text-slate-500">{fileSize(v.size_bytes)} · {v.uploaded_by.full_name} · {formatDate(v.uploaded_at)}</div>
                </div>
                <button onClick={() => open(v, false)} className="shrink-0 text-brand-700 hover:underline">Download</button>
              </li>
            ))}
          </ul>
        </section>

        {d.reviews.length > 0 && (
          <section>
            <h3 className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">History</h3>
            <ul className="space-y-1.5 text-slate-600">
              {d.reviews.map((r, i) => (
                <li key={i}>
                  <span className="font-medium text-slate-800">{DOCUMENT_STATUS[r.to_status as DocumentStatus]?.[0] ?? r.to_status}</span>
                  {" "}by {r.reviewer.full_name} · <span className="text-xs">{formatDate(r.created_at)}</span>
                  {r.remarks && <div className="text-xs text-slate-500">“{r.remarks}”</div>}
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
      {rejecting && (
        <ReasonModal title={`Reject ${d.title}`} label="Reason (the uploader will see it)" submitLabel="Reject" danger
                     onClose={() => setRejecting(false)} onSubmit={async (remarks) => { await review("rejected", remarks); }} />
      )}
      {deleting && (
        <Modal title={`Delete ${d.title}?`} open onClose={() => setDeleting(false)}>
          <p className="text-sm text-slate-600">It disappears from the portal. The files and the record of who deleted it are kept.</p>
          <div className="mt-6 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setDeleting(false)}>Cancel</Button>
            <Button variant="danger" disabled={busy} onClick={async () => {
              if (await run(() => api(`/documents/${id}`, { method: "DELETE" }))) onClose();
              else setDeleting(false);
            }}>Delete</Button>
          </div>
        </Modal>
      )}
    </Modal>
  );
}

export const ACCEPT = ".pdf,.docx,.xlsx,.pptx,.jpg,.jpeg,.png,.zip";

export function UploadModal({ folderId, folderName, onClose, onDone }: {
  folderId: number; folderName: string; onClose: () => void; onDone: (id: number) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api<DocumentDetail>("/documents", {
        method: "POST",
        body: uploadForm(file, { folder_id: String(folderId), title, category, description }),
      });
      onDone(created.id);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title={`Upload to ${folderName}`} open onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <Field label="File" hint="PDF, DOCX, XLSX, PPTX or ZIP up to 15 MB. JPG or PNG up to 5 MB.">
          <Input type="file" required accept={ACCEPT} onChange={(e) => {
            const picked = e.target.files?.[0] ?? null;
            setFile(picked);
            if (picked && !title) setTitle(picked.name.replace(/\.[^.]+$/, ""));
          }} />
        </Field>
        <Field label="Title"><Input required maxLength={200} value={title} onChange={(e) => setTitle(e.target.value)} /></Field>
        <Field label="Category" hint="Optional. For example: Notice, Budget, Report.">
          <Input maxLength={80} value={category} onChange={(e) => setCategory(e.target.value)} />
        </Field>
        <Field label="Description" hint="Optional.">
          <Textarea maxLength={2000} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" disabled={busy || !file}>{busy ? "Uploading…" : "Upload"}</Button>
        </div>
      </form>
    </Modal>
  );
}
