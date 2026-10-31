import type { ReactNode } from "react";
import { BrandLogo, TriangleMotif } from "../components/Brand";

export function AuthLayout({ title, subtitle, children }: { title: string; subtitle?: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen bg-white">
      <aside className="relative hidden w-[44%] max-w-xl overflow-hidden bg-gradient-to-br from-brand-700 via-brand-800 to-brand-950 text-white lg:flex lg:flex-col lg:justify-between lg:p-12">
        <TriangleMotif className="pointer-events-none absolute -right-24 -bottom-16 w-[28rem] text-white/10" />
        <TriangleMotif className="pointer-events-none absolute -top-10 -left-16 w-56 rotate-180 text-white/5" />
        <div className="relative text-sm font-medium tracking-[0.2em] text-brand-200 uppercase">#ESTD 2026</div>
        <div className="relative">
          <h2 className="text-4xl leading-tight font-bold">IETE Student Forum<br />Management Portal</h2>
          <p className="mt-4 max-w-sm text-brand-100/80">
            One place for the forum's team, departments, roles and records at Chandigarh University.
          </p>
        </div>
        <p className="relative text-lg text-brand-100/90" lang="sa">सह वीर्यं करवावहै</p>
      </aside>

      <main className="flex flex-1 flex-col items-center justify-center bg-gradient-to-b from-brand-50/60 to-white px-4 py-10 sm:px-8">
        <div className="w-full max-w-sm">
          <BrandLogo className="mx-auto mb-8 w-72" />
          <div className="rounded-2xl border border-slate-200/80 bg-white p-7 shadow-xl shadow-brand-900/5">
            <h1 className="text-xl font-semibold text-slate-900">{title}</h1>
            {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
            <div className="mt-6">{children}</div>
          </div>
          <p className="mt-8 text-center text-xs text-slate-400">© {new Date().getFullYear()} IETE Student Forum · Chandigarh University</p>
        </div>
      </main>
    </div>
  );
}
