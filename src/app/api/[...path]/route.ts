import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

const LOOPBACK_HOSTS = new Set(["127.0.0.1", "localhost", "[::1]"]);
const API_UPSTREAM_HOSTS = new Set([...LOOPBACK_HOSTS, "api"]);

function isLoopbackHost(hostname: string) {
  return LOOPBACK_HOSTS.has(hostname.toLowerCase());
}

function localApiBase(value: string) {
  const url = new URL(value);
  if (
    url.protocol !== "http:"
    || !API_UPSTREAM_HOSTS.has(url.hostname.toLowerCase())
    || url.username
    || url.password
    || url.search
    || url.hash
  ) {
    throw new Error(
      "SOCIUM_API_URL must target localhost or the bundled Docker API without credentials or query data.",
    );
  }
  return url;
}

function isTrustedLocalRequest(request: Request) {
  const sourceUrl = new URL(request.url);
  const host = request.headers.get("host") || sourceUrl.host;
  let browserOrigin: URL;
  try {
    browserOrigin = new URL(`${sourceUrl.protocol}//${host}`);
  } catch {
    return false;
  }
  if (!isLoopbackHost(browserOrigin.hostname)) return false;

  const fetchSite = request.headers.get("sec-fetch-site");
  if (fetchSite && fetchSite !== "same-origin" && fetchSite !== "none") return false;

  const origin = request.headers.get("origin");
  if (!origin) return true;
  try {
    return new URL(origin).origin === browserOrigin.origin;
  } catch {
    return false;
  }
}

async function proxyRequest(request: Request, context: RouteContext) {
  if (!isTrustedLocalRequest(request)) {
    return NextResponse.json(
      { ok: false, error: "Socium only accepts same-origin requests on localhost." },
      { status: 403 },
    );
  }

  const { path } = await context.params;
  const configuredBase = process.env.SOCIUM_API_URL || "http://127.0.0.1:8000";
  const sourceUrl = new URL(request.url);
  const headers = new Headers(request.headers);

  for (const header of [
    "connection",
    "content-length",
    "cookie",
    "host",
    "origin",
    "proxy-authorization",
    "referer",
    "transfer-encoding",
    "x-forwarded-for",
    "x-forwarded-host",
    "x-forwarded-proto",
  ]) {
    headers.delete(header);
  }
  headers.set("x-socium-proxy", "nextjs");

  try {
    const baseUrl = localApiBase(configuredBase);
    const targetUrl = new URL(
      `/api/${path.map(encodeURIComponent).join("/")}${sourceUrl.search}`,
      baseUrl,
    );
    const isLocalModelPull = path.join("/") === "providers/local/pull";
    const body = ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer();
    const upstream = await fetch(targetUrl, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      redirect: "manual",
      signal: AbortSignal.timeout(isLocalModelPull ? 6 * 60 * 60_000 : 130_000),
    });
    const responseHeaders = new Headers(upstream.headers);
    for (const header of ["content-encoding", "content-length", "transfer-encoding"]) {
      responseHeaders.delete(header);
    }
    responseHeaders.set("Cache-Control", "no-store");
    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json(
      {
        ok: false,
        error: "The local FastAPI service is unavailable. Restart Socium and try again.",
      },
      { status: 503 },
    );
  }
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
export const OPTIONS = proxyRequest;
