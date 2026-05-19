import type {
  AuthProviders,
  ConversionDetail,
  ConvertResponse,
  HistoryPage,
  StatusResponse,
  TemplateChoice,
  TokenResponse,
  User,
} from "./types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";
const TOKEN_KEY = "coretex_token";

function join(path: string): string {
  if (!BASE) return path;
  return BASE.replace(/\/+$/, "") + path;
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly detail: string) {
    super(`API ${status}: ${detail}`);
  }
}

async function readDetail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
  } catch {
    return res.statusText;
  }
}

// ── Conversion ─────────────────────────────────────────────────────────

export async function uploadDocx(
  file: File,
  template: TemplateChoice
): Promise<ConvertResponse & { cached?: boolean; conversion_id?: string }> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(join(`/convert?template=${encodeURIComponent(template)}`), {
    method: "POST",
    body: fd,
    headers: authHeaders(),
  });
  if (!res.ok) throw new ApiError(res.status, await readDetail(res));
  return res.json();
}

export async function fetchStatus(jobId: string): Promise<StatusResponse> {
  const res = await fetch(join(`/status/${encodeURIComponent(jobId)}`), {
    headers: authHeaders(),
  });
  if (!res.ok) throw new ApiError(res.status, await readDetail(res));
  return res.json();
}

export interface DownloadResult {
  blob: Blob;
  filename: string;
  contentType: string;
  overleafTempUrl: string | null;
  text: string | null;
}

export async function downloadResult(jobId: string): Promise<DownloadResult> {
  const res = await fetch(join(`/download/${encodeURIComponent(jobId)}`), {
    headers: authHeaders(),
  });
  if (!res.ok) throw new ApiError(res.status, await readDetail(res));
  const contentType = res.headers.get("content-type") ?? "application/octet-stream";
  const overleafTempUrl = res.headers.get("x-overleaf-temp-url");
  const blob = await res.blob();
  const isZip = contentType.includes("zip");
  const filename = isZip ? "output.zip" : "output.tex";
  const text = isZip ? null : await blob.text();
  return { blob, filename, contentType, overleafTempUrl, text };
}

export function tempUrl(path: string): string {
  return join(path);
}

// ── Auth ───────────────────────────────────────────────────────────────

export async function fetchProviders(): Promise<AuthProviders> {
  const res = await fetch(join("/auth/providers"));
  if (!res.ok) throw new ApiError(res.status, await readDetail(res));
  return res.json();
}

export async function signup(
  email: string,
  password: string,
  display_name?: string
): Promise<TokenResponse> {
  const res = await fetch(join("/auth/signup"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password, display_name }),
  });
  if (!res.ok) throw new ApiError(res.status, await readDetail(res));
  return res.json();
}

export async function login(email: string, password: string): Promise<TokenResponse> {
  const res = await fetch(join("/auth/login"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new ApiError(res.status, await readDetail(res));
  return res.json();
}

export async function fetchMe(): Promise<User> {
  const res = await fetch(join("/auth/me"), { headers: authHeaders() });
  if (!res.ok) throw new ApiError(res.status, await readDetail(res));
  return res.json();
}

export function oauthStartUrl(provider: "google" | "github"): string {
  return join(`/auth/${provider}/start`);
}

// ── History ────────────────────────────────────────────────────────────

export async function fetchHistory(limit = 50, offset = 0): Promise<HistoryPage> {
  const res = await fetch(join(`/history?limit=${limit}&offset=${offset}`), {
    headers: authHeaders(),
  });
  if (!res.ok) throw new ApiError(res.status, await readDetail(res));
  return res.json();
}

export async function fetchHistoryDetail(id: string): Promise<ConversionDetail> {
  const res = await fetch(join(`/history/${encodeURIComponent(id)}`), {
    headers: authHeaders(),
  });
  if (!res.ok) throw new ApiError(res.status, await readDetail(res));
  return res.json();
}

export async function downloadHistoryItem(id: string): Promise<DownloadResult> {
  const res = await fetch(join(`/history/${encodeURIComponent(id)}/download`), {
    headers: authHeaders(),
  });
  if (!res.ok) throw new ApiError(res.status, await readDetail(res));
  const contentType = res.headers.get("content-type") ?? "application/octet-stream";
  const blob = await res.blob();
  const isZip = contentType.includes("zip");
  const filename = isZip ? "output.zip" : "output.tex";
  const text = isZip ? null : await blob.text();
  return { blob, filename, contentType, overleafTempUrl: null, text };
}

export async function deleteHistoryItem(id: string): Promise<void> {
  const res = await fetch(join(`/history/${encodeURIComponent(id)}`), {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok && res.status !== 204) throw new ApiError(res.status, await readDetail(res));
}
