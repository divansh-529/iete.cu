import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { api, errorMessage } from "../../api/client";
import type { DocumentSummary, FolderList } from "../../api/types";
import { Alert, Button, Card, cx, Empty, Field, formatDate, Input, Modal, Spinner } from "../../components/ui";
import { DocumentModal, DocumentStatusBadge, fileSize, UploadModal } from "./DocumentModal";

/** Folders on the left, the chosen folder's documents on the right. No event means the forum's own folders. */
export function FolderBrowser({ eventId }: { eventId?: number }) {
  const qc = useQueryClient();
  const query = eventId ? `?event_id=${eventId}` : "";
  const folders = useQuery({ queryKey: ["documents", "folders", eventId ?? null], queryFn: () => api<FolderList>(`/documents/folders${query}`) });
  const [chosen, setChosen] = useState<number | null>(null);
  const [opened, setOpened] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [naming, setNaming] = useState(false);
  const list = folders.data?.folders ?? [];
  const folder = list.find((f) => f.id === chosen) ?? list[0];
  const docs = useQuery({ queryKey: ["documents", "in-folder", folder?.id], enabled: !!folder,
                          queryFn: () => api<DocumentSummary[]>(`/documents?folder_id=${folder!.id}`) });

  if (folders.isLoading) return <Spinner />;
  if (folders.error) return <Alert>{errorMessage(folders.error)}</Alert>;

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <Card title="Folders" actions={folders.data?.can_manage && <Button variant="ghost" onClick={() => setNaming(true)}>New folder</Button>}>
        {list.length ? (
          <ul className="-mx-2 space-y-0.5 text-sm">
            {list.map((f) => (
              <li key={f.id}>
                <button onClick={() => setChosen(f.id)} aria-current={f.id === folder?.id}
                        className={cx("flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left",
                                      f.id === folder?.id ? "bg-brand-50 font-medium text-brand-700" : "text-slate-700 hover:bg-slate-50")}>
                  <span className="min-w-0 truncate">{f.name}</span>
                  <span className="shrink-0 text-xs tabular-nums text-slate-500">{f.document_count}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : <Empty>No folders yet.</Empty>}
      </Card>
      <Card title={folder?.name ?? "Documents"} className="lg:col-span-2"
            actions={folder && folders.data?.can_upload && <Button onClick={() => setUploading(true)}>Upload</Button>}>
        {!folder ? <Empty>Create a folder to start.</Empty> : docs.isLoading ? <Spinner />
          : <DocumentList documents={docs.data ?? []} onOpen={setOpened} empty="No documents in this folder yet." />}
      </Card>
      {uploading && folder && (
        <UploadModal folderId={folder.id} folderName={folder.name} onClose={() => setUploading(false)}
                     onDone={(id) => {
                       setUploading(false);
                       qc.invalidateQueries({ queryKey: ["documents"] });
                       setOpened(id);
                     }} />
      )}
      {opened && <DocumentModal id={opened} onClose={() => setOpened(null)} />}
      {naming && <NewFolderModal eventId={eventId} onClose={() => setNaming(false)} />}
    </div>
  );
}

export function DocumentList({ documents, onOpen, empty, showHome = false }: {
  documents: DocumentSummary[]; onOpen: (id: number) => void; empty: string; showHome?: boolean;
}) {
  if (!documents.length) return <Empty>{empty}</Empty>;
  return (
    <ul className="divide-y divide-slate-100 text-sm">
      {documents.map((d) => (
        <li key={d.id}>
          <button onClick={() => onOpen(d.id)} className="flex w-full flex-wrap items-center justify-between gap-x-3 gap-y-1 py-2.5 text-left hover:bg-slate-50">
            <span className="min-w-0">
              <span className="block truncate font-medium text-brand-700">{d.title}</span>
              <span className="block text-xs text-slate-500">
                {showHome && `${d.event ? `${d.event.name} · ` : ""}${d.folder.name} · `}
                v{d.current_version.version_no} · {fileSize(d.current_version.size_bytes)} · {d.current_version.uploaded_by.full_name} · {formatDate(d.current_version.uploaded_at, false)}
              </span>
            </span>
            <DocumentStatusBadge status={d.status} />
          </button>
        </li>
      ))}
    </ul>
  );
}

function NewFolderModal({ eventId, onClose }: { eventId?: number; onClose: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      await api("/documents/folders", { method: "POST", body: { name, event_id: eventId ?? null } });
      qc.invalidateQueries({ queryKey: ["documents", "folders"] });
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    }
  }

  return (
    <Modal title="New folder" open onClose={onClose}>
      <form onSubmit={submit} className="space-y-4">
        {error && <Alert>{error}</Alert>}
        <Field label="Name"><Input required autoFocus maxLength={120} value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit">Create</Button>
        </div>
      </form>
    </Modal>
  );
}
