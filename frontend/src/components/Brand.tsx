import { cx } from "./ui";

/** Logo files live in public/brand/. Replace them there to rebrand; no code change needed. */
export const LOGO_FULL = "/brand/logo-full.png";

export function BrandLogo({ className }: { className?: string }) {
  return <img src={LOGO_FULL} alt="IETE Student Forum, Chandigarh University" className={cx("h-auto select-none", className)} />;
}

/** Decorative outline of the IETE triangle, used as a background motif on brand panels. */
export function TriangleMotif({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 200 180" fill="none" aria-hidden="true" className={className}>
      <path d="M100 6 194 174H6Z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M100 30 172 160H28Z" stroke="currentColor" strokeWidth="1" strokeLinejoin="round" opacity=".6" />
      <circle cx="100" cy="112" r="30" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}
