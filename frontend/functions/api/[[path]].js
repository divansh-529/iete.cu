// Cloudflare Pages Function: forwards /api/* on the portal's own domain to the backend.
// The browser only ever talks to one origin, so session cookies stay SameSite=Lax
// (docs/08-free-tier-hosting.md). Set BACKEND_URL and PROXY_SECRET in the Pages project.
export async function onRequest({ request, env }) {
  const url = new URL(request.url);
  const target = new URL(url.pathname + url.search, env.BACKEND_URL);

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.set("x-proxy-secret", env.PROXY_SECRET);
  // Overwrite anything the visitor sent: the backend trusts this for login rate limiting.
  headers.set("x-real-client-ip", request.headers.get("cf-connecting-ip") ?? "");

  const hasBody = !["GET", "HEAD"].includes(request.method);
  return fetch(target, {
    method: request.method,
    headers,
    body: hasBody ? request.body : undefined,
    redirect: "manual",
  });
}
