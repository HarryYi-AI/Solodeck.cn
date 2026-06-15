export async function onRequest(context) {
  const apiOrigin = context.env.SOLODECK_API_ORIGIN;
  if (!apiOrigin) {
    return new Response("SOLODECK_API_ORIGIN is not configured.", { status: 500 });
  }

  const incomingUrl = new URL(context.request.url);
  const targetUrl = new URL(incomingUrl.pathname + incomingUrl.search, apiOrigin);
  const headers = new Headers(context.request.headers);
  headers.delete("host");

  const init = {
    method: context.request.method,
    headers,
    redirect: "manual",
  };

  if (!["GET", "HEAD"].includes(context.request.method)) {
    init.body = context.request.body;
  }

  return fetch(new Request(targetUrl.toString(), init));
}
