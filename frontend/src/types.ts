// Mirrors backend ConversionResult + /status response shapes.

export type TemplateChoice = "article" | "ieee" | "acm" | "springer";

export interface ConvertResponse {
  job_id: string;
  status: "queued";
  message: string;
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
