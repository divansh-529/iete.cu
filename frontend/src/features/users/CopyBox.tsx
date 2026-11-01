import { useState } from "react";
import { Button } from "../../components/ui";

export function CopyBox({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="flex items-start gap-2">
      {value.includes("\n") ? (
        <textarea readOnly value={value} rows={value.split("\n").length} onFocus={(e) => e.target.select()}
                  className="min-w-0 flex-1 resize-none rounded-md border border-slate-300 bg-slate-50 px-3 py-2 font-mono text-xs" />
      ) : (
        <input readOnly value={value} onFocus={(e) => e.target.select()}
               className="min-w-0 flex-1 rounded-md border border-slate-300 bg-slate-50 px-3 py-2 font-mono text-xs" />
      )}
      <Button type="button" variant="secondary" onClick={async () => {
        await navigator.clipboard.writeText(value);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      }}>{copied ? "Copied" : "Copy"}</Button>
    </div>
  );
}
