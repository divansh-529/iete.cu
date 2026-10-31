// Cloudflare Worker for the portal. Static files (dist/) are served by Workers Static Assets;
// only /api/* reaches this script (run_worker_first in wrangler.jsonc). It forwards those
// requests to the backend so the browser only ever talks to one origin, and session cookies
// stay SameSite=Lax (docs/08-free-tier-hosting.md). Set BACKEND_URL and PROXY_SECRET in the
// Worker's Settings → Variables and Secrets.
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS.fetch(request);

    // Misconfiguration shows up as a readable error instead of a bare 500.
    let target;
    try {
      target = new URL(url.pathname + url.search, env.BACKEND_URL);
    } catch {
      return proxyError("BACKEND_URL is not set (or not a full https:// address) in the Worker's runtime Variables and Secrets.");
    }
    if (!env.PROXY_SECRET) {
      return proxyError("PROXY_SECRET is not set in the Worker's runtime Variables and Secrets.");
    }
    const headers = new Headers(request.headers);
    headers.delete("host");
    headers.set("x-proxy-secret", env.PROXY_SECRET);
    // Overwrite anything the visitor sent: the backend trusts this for login rate limiting.
    headers.set("x-real-client-ip", request.headers.get("cf-connecting-ip") ?? "");

    const hasBody = !["GET", "HEAD"].includes(request.method);
    try {
      return await fetch(target, {
        method: request.method,
        headers,
        body: hasBody ? request.body : undefined,
        redirect: "manual",
      });
    } catch (e) {
      return proxyError(`Could not reach the backend at ${target.origin}: ${e}`, 502);
    }
  },
};

function proxyError(message, status = 500) {
  return Response.json({ error: { code: "PROXY_ERROR", message } }, { status });
}
