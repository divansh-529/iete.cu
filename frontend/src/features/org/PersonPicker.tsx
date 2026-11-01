import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/client";
import type { PersonRef } from "../../api/types";
import { cx, Input } from "../../components/ui";

/** Search team members by name or email and pick one. */
export function PersonPicker({ value, onChange, exclude = [], autoFocus = true }: {
  value: PersonRef | null; onChange: (p: PersonRef | null) => void; exclude?: number[]; autoFocus?: boolean;
}) {
  const [q, setQ] = useState("");
  const results = useQuery({
    queryKey: ["org-people", q],
    queryFn: () => api<PersonRef[]>(`/org/people?limit=8&q=${encodeURIComponent(q)}`),
    enabled: !value,
  });

  if (value) {
    return (
      <div className="flex items-center justify-between rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-sm">
        <span><span className="font-medium">{value.full_name}</span> <span className="text-slate-500">{value.email}</span></span>
        <button type="button" className="text-xs text-brand-600 hover:underline" onClick={() => onChange(null)}>Change</button>
      </div>
    );
  }
  const options = (results.data ?? []).filter((p) => !exclude.includes(p.id));
  return (
    <div>
      <Input placeholder="Search by name or email…" value={q} onChange={(e) => setQ(e.target.value)} autoFocus={autoFocus} />
      <ul className="mt-1 max-h-48 overflow-y-auto rounded-md border border-slate-200">
        {options.length === 0 && <li className="px-3 py-2 text-sm text-slate-500">No matching team members.</li>}
        {options.map((p, i) => (
          <li key={p.id}>
            <button type="button" onClick={() => onChange(p)}
                    className={cx("block w-full px-3 py-2 text-left text-sm hover:bg-brand-50", i > 0 && "border-t border-slate-100")}>
              <span className="font-medium">{p.full_name}</span> <span className="text-slate-500">{p.email}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
