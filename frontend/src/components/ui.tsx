import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes,
  TextareaHTMLAttributes } from "react";
import { useEffect } from "react";
import { twMerge } from "tailwind-merge";

/** Joins class names; when two Tailwind classes conflict, the later one wins. */
export function cx(...classes: (string | false | null | undefined)[]) {
  return twMerge(classes.filter(Boolean).join(" "));
}

type Variant = "primary" | "secondary" | "danger" | "ghost";

const variants: Record<Variant, string> = {
  primary: "bg-brand-600 text-white shadow-sm shadow-brand-900/20 hover:bg-brand-700 active:bg-brand-800 disabled:bg-brand-600/50 disabled:shadow-none",
  secondary: "bg-white text-slate-700 border border-slate-300 shadow-xs hover:border-slate-400 hover:bg-slate-50 disabled:opacity-50",
  danger: "bg-red-600 text-white shadow-sm shadow-red-900/20 hover:bg-red-700 disabled:bg-red-600/50",
  ghost: "text-slate-600 hover:bg-slate-100 disabled:opacity-50",
};

export function Button({ variant = "primary", className, ...props }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant }) {
  return (
    <button
      {...props}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium",
        "transition focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed",
        variants[variant],
        className,
      )}
    />
  );
}

const fieldClass =
  "block w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm shadow-xs transition " +
  "placeholder:text-slate-400 hover:border-slate-400 focus:border-brand-500 focus:outline-none focus:ring-4 focus:ring-brand-500/15";

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} className={cx(fieldClass, props.className)} />;
}

export function Select(props: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select {...props} className={cx(fieldClass, props.className)} />;
}

/** A labelled form field. Use `group` when the field holds several controls (e.g. a person
 *  picker's search box and result buttons): a <label> would name every button after itself. */
export function Field({ label, hint, children, group }: { label: string; hint?: string; children: ReactNode; group?: boolean }) {
  if (group) {
    return (
      <div role="group" aria-label={label} className="block">
        <span className="mb-1 block text-sm font-medium text-slate-700">{label}</span>
        {children}
        {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
      </div>
    );
  }
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-slate-700">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

export function Card({ title, actions, children, className }:
  { title?: string; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("rounded-xl border border-slate-200/80 bg-white shadow-sm shadow-slate-900/[0.03]", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-5 py-3.5">
          {title && <h2 className="text-[15px] font-semibold text-slate-900">{title}</h2>}
          {actions}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }:
  { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-7 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

const badgeTones = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  amber: "bg-amber-50 text-amber-800 ring-amber-600/20",
  red: "bg-red-50 text-red-700 ring-red-600/20",
  slate: "bg-slate-100 text-slate-600 ring-slate-500/20",
  blue: "bg-brand-50 text-brand-700 ring-brand-600/20",
  violet: "bg-violet-50 text-violet-700 ring-violet-600/20",
};
export type BadgeTone = keyof typeof badgeTones;

export function Badge({ tone = "slate", children }: { tone?: BadgeTone; children: ReactNode }) {
  return (
    <span className={cx("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset", badgeTones[tone])}>
      {children}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const [label, tone] = ({
    active: ["active", "green"], invited: ["not signed in yet", "blue"], suspended: ["suspended", "amber"],
    deactivated: ["deactivated", "red"], proposed: ["waiting for approval", "amber"], rejected: ["not approved", "red"],
  } as const)[status as "active"] ?? ([status, "slate"] as const);
  return <Badge tone={tone}>{label}</Badge>;
}

export function Alert({ tone = "red", children }: { tone?: "red" | "green" | "amber"; children: ReactNode }) {
  const styles = {
    red: "border-red-200 bg-red-50 text-red-800",
    green: "border-emerald-200 bg-emerald-50 text-emerald-800",
    amber: "border-amber-200 bg-amber-50 text-amber-900",
  };
  return <div role="alert" className={cx("rounded-lg border px-3.5 py-2.5 text-sm", styles[tone])}>{children}</div>;
}

export function Modal({ title, open, onClose, children }:
  { title: string; open: boolean; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-brand-950/40 p-4 backdrop-blur-sm sm:items-center"
         onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title}
           className="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl shadow-brand-950/20" onMouseDown={(e) => e.stopPropagation()}>
        <div className="h-1 bg-gradient-to-r from-brand-600 to-brand-400" />
        <header className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <h2 className="text-lg font-semibold text-slate-900">{title}</h2>
          <button onClick={onClose} className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                  aria-label="Close">✕</button>
        </header>
        <div className="p-6">{children}</div>
      </div>
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="rounded-lg border border-dashed border-slate-200 bg-slate-50/60 py-8 text-center text-sm text-slate-500">{children}</p>;
}

export function Spinner() {
  return (
    <div role="status" className="flex items-center justify-center gap-3 py-12 text-sm text-slate-500">
      <span className="size-5 animate-spin rounded-full border-2 border-brand-200 border-t-brand-600" />
      Loading…
    </div>
  );
}

/** Tabs kept in the URL (?tab=…) so a page can be linked and survives a reload. */
export function Tabs<T extends string>({ tabs, value, onChange }: {
  tabs: readonly (readonly [T, string])[]; value: T; onChange: (tab: T) => void;
}) {
  return (
    <div className="mb-4 flex gap-1 overflow-x-auto border-b border-slate-200">
      {tabs.map(([key, label]) => (
        <button key={key} onClick={() => onChange(key)}
                className={cx("-mb-px whitespace-nowrap border-b-2 px-4 py-2 text-sm font-medium",
                  value === key ? "border-brand-600 text-brand-700" : "border-transparent text-slate-500 hover:text-slate-700")}>
          {label}
        </button>
      ))}
    </div>
  );
}

export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea rows={3} {...props} className={cx(fieldClass, props.className)} />;
}

/** ISO timestamp → value for <input type="datetime-local"> in the viewer's time zone. */
export function toInputDateTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  const local = new Date(d.getTime() - d.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

/** <input type="datetime-local"> value (local time) → ISO timestamp with time zone, or null. */
export function fromInputDateTime(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

/** "in 3 days", "2 hours ago": for due dates and activity. */
export function relativeTime(iso: string): string {
  const diff = new Date(iso).getTime() - Date.now();
  const units: [Intl.RelativeTimeFormatUnit, number][] = [["day", 86_400_000], ["hour", 3_600_000], ["minute", 60_000]];
  const fmt = new Intl.RelativeTimeFormat("en-IN", { numeric: "auto" });
  for (const [unit, ms] of units) {
    if (Math.abs(diff) >= ms || unit === "minute") return fmt.format(Math.round(diff / ms), unit);
  }
  return "";
}

export function formatDate(value: string | null | undefined, withTime = true): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}
