import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router";
import { api, errorMessage } from "../../api/client";
import type { DocumentStatus, DocumentSummary } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { Alert, Card, Field, Input, PageHeader, Select, Spinner, Tabs } from "../../components/ui";
import { DOCUMENT_STATUS, DocumentModal } from "./DocumentModal";
import { DocumentList, FolderBrowser } from "./FolderBrowser";

const TABS = [["all", "All documents"], ["forum", "Forum folders"]] as const;
type Tab = (typeof TABS)[number][0];

export function DocumentsPage() {
  const { me } = useAuth();
  const [params, setParams] = useSearchParams();
  // The forum's own folders need access across the whole forum, not just one department.
  const forumFolders = !!me && (me.all_permissions || me.permissions.some((p) => p.code === "documents.view" && p.scope_type === "global"));
  const tab: Tab = forumFolders && params.get("tab") === "forum" ? "forum" : "all";
  const opened = Number(params.get("open")) || null;
  const close = () => setParams((p) => { p.delete("open"); return p; });

  return (
    <>
      <PageHeader title="Documents" subtitle="Event records and forum files. Every version is kept." />
      {forumFolders && <Tabs tabs={TABS} value={tab} onChange={(t) => setParams({ tab: t })} />}
      {tab === "forum" ? <FolderBrowser /> : <AllDocuments onOpen={(id) => setParams((p) => { p.set("open", String(id)); return p; })} />}
      {opened && <DocumentModal id={opened} onClose={close} />}
    </>
  );
}

function AllDocuments({ onOpen }: { onOpen: (id: number) => void }) {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [status, setStatus] = useState("");
  const search = new URLSearchParams(Object.entries({ q: q.trim(), category: category.trim(), status }).filter(([, v]) => v));
  const docs = useQuery({ queryKey: ["documents", "search", search.toString()],
                          queryFn: () => api<DocumentSummary[]>(`/documents?${search}`) });
  return (
    <Card>
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Field label="Search"><Input value={q} placeholder="Title or description" onChange={(e) => setQ(e.target.value)} /></Field>
        <Field label="Category"><Input value={category} onChange={(e) => setCategory(e.target.value)} /></Field>
        <Field label="Status">
          <Select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Any</option>
            {(Object.keys(DOCUMENT_STATUS) as DocumentStatus[]).map((s) => <option key={s} value={s}>{DOCUMENT_STATUS[s][0]}</option>)}
          </Select>
        </Field>
      </div>
      {docs.error ? <Alert>{errorMessage(docs.error)}</Alert> : docs.isLoading ? <Spinner />
        : <DocumentList documents={docs.data ?? []} onOpen={onOpen} showHome
                        empty={search.size ? "No documents match." : "No documents yet. Open an event and use its Documents tab to upload."} />}
    </Card>
  );
}
