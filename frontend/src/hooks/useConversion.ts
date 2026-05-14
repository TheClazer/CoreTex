import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, downloadResult, fetchStatus, uploadDocx } from "../api";
import type { JobStatus, ResultSummary, TemplateChoice } from "../types";

export type Phase = "idle" | "uploading" | "polling" | "downloading" | "done" | "error";

export interface ConversionState {
  phase: Phase;
  jobId: string | null;
  status: JobStatus | null;
  summary: ResultSummary | null;
  texSource: string | null;
  downloadBlob: Blob | null;
  downloadFilename: string | null;
  overleafTempUrl: string | null;
  error: string | null;
  elapsedMs: number;
}

const POLL_MS = 2000;

const INITIAL: ConversionState = {
  phase: "idle",
  jobId: null,
  status: null,
  summary: null,
  texSource: null,
  downloadBlob: null,
  downloadFilename: null,
  overleafTempUrl: null,
  error: null,
  elapsedMs: 0,
};

export function useConversion() {
  const [state, setState] = useState<ConversionState>(INITIAL);
  const pollTimer = useRef<number | null>(null);
  const tickTimer = useRef<number | null>(null);
  const startedAt = useRef<number | null>(null);

  const stopTimers = useCallback(() => {
    if (pollTimer.current !== null) {
      window.clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
    if (tickTimer.current !== null) {
      window.clearInterval(tickTimer.current);
      tickTimer.current = null;
    }
  }, []);

  useEffect(() => () => stopTimers(), [stopTimers]);

  const reset = useCallback(() => {
    stopTimers();
    startedAt.current = null;
    setState(INITIAL);
  }, [stopTimers]);

  const completeWithDownload = useCallback(async (jobId: string, summary: ResultSummary) => {
    setState((s) => ({ ...s, phase: "downloading", summary }));
    try {
      const dl = await downloadResult(jobId);
      setState((s) => ({
        ...s,
        phase: "done",
        texSource: dl.text,
        downloadBlob: dl.blob,
        downloadFilename: dl.filename,
        overleafTempUrl: dl.overleafTempUrl,
      }));
    } catch (e) {
      const msg = e instanceof ApiError ? e.detail : (e as Error).message;
      setState((s) => ({ ...s, phase: "error", error: msg }));
    } finally {
      stopTimers();
    }
  }, [stopTimers]);

  const pollOnce = useCallback(
    async (jobId: string) => {
      try {
        const res = await fetchStatus(jobId);
        setState((s) => ({ ...s, status: res.status, summary: res.result_summary ?? s.summary }));

        if (res.status === "finished" && res.result_summary) {
          await completeWithDownload(jobId, res.result_summary);
          return;
        }
        if (res.status === "failed") {
          setState((s) => ({ ...s, phase: "error", error: res.error_message ?? "Conversion failed" }));
          stopTimers();
          return;
        }
        if (res.status === "not_found") {
          setState((s) => ({ ...s, phase: "error", error: "Job not found" }));
          stopTimers();
          return;
        }

        pollTimer.current = window.setTimeout(() => pollOnce(jobId), POLL_MS);
      } catch (e) {
        const msg = e instanceof ApiError ? e.detail : (e as Error).message;
        setState((s) => ({ ...s, phase: "error", error: msg }));
        stopTimers();
      }
    },
    [completeWithDownload, stopTimers]
  );

  const start = useCallback(
    async (file: File, template: TemplateChoice) => {
      reset();
      setState((s) => ({ ...s, phase: "uploading" }));
      startedAt.current = performance.now();
      tickTimer.current = window.setInterval(() => {
        if (startedAt.current !== null) {
          setState((s) => ({ ...s, elapsedMs: performance.now() - startedAt.current! }));
        }
      }, 100);

      try {
        const { job_id } = await uploadDocx(file, template);
        setState((s) => ({ ...s, jobId: job_id, phase: "polling", status: "queued" }));
        pollTimer.current = window.setTimeout(() => pollOnce(job_id), POLL_MS);
      } catch (e) {
        const msg = e instanceof ApiError ? e.detail : (e as Error).message;
        setState((s) => ({ ...s, phase: "error", error: msg }));
        stopTimers();
      }
    },
    [pollOnce, reset, stopTimers]
  );

  return { state, start, reset };
}
