import type { ConvertResponse, StatusResponse, TemplateChoice } from "./types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

function join(path: string): string {
  if (!BASE) return path;
  return BASE.replace(/\/+$/, "") + path;
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

export async function uploadDocx(
  file: File,
  template: TemplateChoice
): Promise<ConvertResponse> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(join(`/convert?template=${encodeURIComponent(template)}`), {
    method: "POST",
    body: fd,
  });
  if (!res.ok) throw new ApiError(res.status, await readDetail(res));
  return res.json();
}

export async function fetchStatus(jobId: string): Promise<StatusResponse> {
  const res = await fetch(join(`/status/${encodeURIComponent(jobId)}`));
  if (!res.ok) throw new ApiError(res.status, await readDetail(res));
  return res.json();
}

export interface DownloadResult {
  blob: Blob;
  filename: string;
  contentType: string;
  overleafTempUrl: string | null;
  text: string | null; // populated for .tex responses; null for zip
}

export async function downloadResult(jobId: string): Promise<DownloadResult> {
  const res = await fetch(join(`/download/${encodeURIComponent(jobId)}`));
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
