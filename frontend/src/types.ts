// Mirrors backend ConversionResult + /status response shapes.

export type TemplateChoice = "article" | "ieee" | "acm" | "springer" | "beamer";

export interface ConvertResponse {
  job_id: string;
  status: "queued" | "finished";
  message: string;
  /** Set when the backend returned a cached conversion instead of enqueueing. */
  cached?: boolean;
  /** Present when cached=true: the conversion's history ID. */
  conversion_id?: string;
}

export interface ResultSummary {
  has_images: boolean;
  warning_count: number;
  citation_count: number;
  compile_ok: boolean;
  compile_error: string | null;
  compile_error_line: number | null;
  template: TemplateChoice;
  warnings: string[];
}

export type JobStatus = "queued" | "started" | "deferred" | "finished" | "failed" | "not_found";

export interface StatusResponse {
  job_id: string;
  status: JobStatus;
  result_summary?: ResultSummary;
  error_message?: string;
}

// ── Auth + history ────────────────────────────────────────────────────

export interface User {
  id: string;
  email: string;
  display_name: string | null;
  providers: string[];
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  user: User;
}

export interface AuthProviders {
  email: boolean;
  google: boolean;
  github: boolean;
}

export interface ConversionSummary {
  id: string;
  filename: string;
  template: TemplateChoice;
  has_images: boolean;
  citation_count: number;
  warning_count: number;
  compile_ok: boolean;
  created_at: string;
}

export interface ConversionDetail extends ConversionSummary {
  latex_source: string;
  warnings: string[];
  compile_error: string | null;
  compile_error_line: number | null;
  figure_filenames: string[];
}

export interface HistoryPage {
  items: ConversionSummary[];
  total: number;
  limit: number;
  offset: number;
}
