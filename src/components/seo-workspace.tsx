"use client";

import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  Clock3,
  Download,
  ExternalLink,
  FileSearch,
  Gauge,
  Globe2,
  Loader2,
  RefreshCw,
  RotateCcw,
  SearchCheck,
  ShieldCheck,
  TimerReset,
  TrendingDown,
  TrendingUp,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { requestJson } from "@/lib/api";
import type {
  LocalJobStatus,
  SeoAuditCheck,
  SeoAuditJob,
  SeoAuditListResponse,
  SeoAuditSnapshot,
} from "@/lib/app-types";
import { cn } from "@/lib/utils";

type CheckFilter = "issues" | "all" | "failed" | "warning" | "passed";

const jobStatusStyles: Record<LocalJobStatus, string> = {
  queued: "border-sky-500/25 bg-sky-500/8 text-sky-300",
  retrying: "border-amber-500/25 bg-amber-500/8 text-amber-300",
  running: "border-violet-500/25 bg-violet-500/8 text-violet-300",
  completed: "border-emerald-500/25 bg-emerald-500/8 text-emerald-300",
  failed: "border-red-500/25 bg-red-500/8 text-red-300",
  cancelled: "border-zinc-800 bg-zinc-950 text-zinc-500",
  missed: "border-orange-500/25 bg-orange-500/8 text-orange-300",
  skipped: "border-zinc-800 bg-zinc-950 text-zinc-500",
};

const checkStatusStyles = {
  passed: "border-emerald-500/25 bg-emerald-500/8 text-emerald-300",
  warning: "border-amber-500/25 bg-amber-500/8 text-amber-300",
  failed: "border-red-500/25 bg-red-500/8 text-red-300",
};

const checkFilters: Array<{ value: CheckFilter; label: string }> = [
  { value: "issues", label: "Open issues" },
  { value: "all", label: "All checks" },
  { value: "failed", label: "Failed" },
  { value: "warning", label: "Warnings" },
  { value: "passed", label: "Passed" },
];

function formatDate(value: string | null) {
  if (!value) return "Not yet";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

function defaultScheduleAt() {
  const date = new Date(Date.now() + 60 * 60 * 1_000);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function scoreColor(score: number) {
  if (score >= 80) return "text-emerald-300";
  if (score >= 60) return "text-amber-300";
  return "text-red-300";
}

function scoreStroke(score: number) {
  if (score >= 80) return "stroke-emerald-400";
  if (score >= 60) return "stroke-amber-400";
  return "stroke-red-400";
}

function ScoreDial({ score }: { score: number }) {
  return (
    <div className="relative grid size-32 shrink-0 place-items-center">
      <svg aria-label={`SEO score ${score} out of 100`} className="size-32 -rotate-90" role="img" viewBox="0 0 120 120">
        <circle className="stroke-zinc-900" cx="60" cy="60" fill="none" pathLength="100" r="50" strokeWidth="8" />
        <circle
          className={cn("transition-[stroke-dashoffset] duration-300 motion-reduce:transition-none", scoreStroke(score))}
          cx="60"
          cy="60"
          fill="none"
          pathLength="100"
          r="50"
          strokeDasharray="100"
          strokeDashoffset={100 - score}
          strokeLinecap="round"
          strokeWidth="8"
        />
      </svg>
      <div className="absolute text-center">
        <p className={cn("font-mono text-3xl font-semibold", scoreColor(score))}>{score}</p>
        <p className="text-[11px] text-zinc-600">out of 100</p>
      </div>
    </div>
  );
}

function DeltaBadge({ value }: { value: number | null }) {
  if (value === null) return <Badge variant="outline">First snapshot</Badge>;
  if (value === 0) return <Badge variant="outline">No change</Badge>;
  const positive = value > 0;
  return (
    <Badge
      className={positive ? "border-emerald-500/25 bg-emerald-500/8 text-emerald-300" : "border-red-500/25 bg-red-500/8 text-red-300"}
      variant="outline"
    >
      {positive ? <TrendingUp /> : <TrendingDown />}
      {positive ? "+" : ""}{value} since previous
    </Badge>
  );
}

function SummaryCard({ detail, icon: Icon, label, value }: { detail: string; icon: typeof Gauge; label: string; value: number | string }) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <CardDescription>{label}</CardDescription>
          <div className="grid size-8 place-items-center rounded-md border border-zinc-800 bg-black text-zinc-500"><Icon className="size-4" /></div>
        </div>
      </CardHeader>
      <CardContent>
        <p className="font-mono text-2xl font-semibold text-zinc-100">{value}</p>
        <p className="mt-1 text-xs leading-5 text-zinc-600">{detail}</p>
      </CardContent>
    </Card>
  );
}

function CheckIcon({ check }: { check: SeoAuditCheck }) {
  if (check.status === "passed") return <CheckCircle2 className="size-4 text-emerald-400" />;
  if (check.status === "warning") return <AlertTriangle className="size-4 text-amber-400" />;
  return <X className="size-4 text-red-400" />;
}

function downloadAudit(audit: SeoAuditSnapshot) {
  const blob = new Blob([JSON.stringify(audit, null, 2)], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `seo-audit-${audit.hostname}-${audit.id.slice(0, 8)}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function SeoWorkspace({ schedulerPaused }: { schedulerPaused: boolean }) {
  const [data, setData] = useState<SeoAuditListResponse | null>(null);
  const [jobs, setJobs] = useState<SeoAuditJob[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [scheduleAt, setScheduleAt] = useState(defaultScheduleAt);
  const [filter, setFilter] = useState<CheckFilter>("issues");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async (preferredId?: string) => {
    try {
      const [auditData, jobData] = await Promise.all([
        requestJson<SeoAuditListResponse>("/api/seo/audits?limit=100", { cache: "no-store" }),
        requestJson<{ items: SeoAuditJob[] }>("/api/seo/jobs?limit=100", { cache: "no-store" }),
      ]);
      setData(auditData);
      setJobs(jobData.items);
      setSelectedId((current) => {
        const next = preferredId ?? current;
        return auditData.items.some((item) => item.id === next) ? next : auditData.items[0]?.id ?? null;
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not load the SEO lab.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.all([
      requestJson<SeoAuditListResponse>("/api/seo/audits?limit=100", { cache: "no-store" }),
      requestJson<{ items: SeoAuditJob[] }>("/api/seo/jobs?limit=100", { cache: "no-store" }),
    ])
      .then(([auditData, jobData]) => {
        if (!active) return;
        setData(auditData);
        setJobs(jobData.items);
        setSelectedId(auditData.items[0]?.id ?? null);
      })
      .catch((error: unknown) => {
        if (active) toast.error(error instanceof Error ? error.message : "Could not load the SEO lab.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const selected = useMemo(
    () => data?.items.find((item) => item.id === selectedId) ?? data?.items[0] ?? null,
    [data, selectedId],
  );

  const visibleChecks = useMemo(() => {
    if (!selected) return [];
    if (filter === "all") return selected.checks;
    if (filter === "issues") return selected.checks.filter((item) => item.status !== "passed");
    return selected.checks.filter((item) => item.status === filter);
  }, [filter, selected]);

  async function runAudit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("audit");
    try {
      const response = await requestJson<{ audit: SeoAuditSnapshot }>("/api/seo/audits", {
        method: "POST",
        body: JSON.stringify({ url }),
      });
      setUrl(response.audit.finalUrl);
      await load(response.audit.id);
      toast.success("SEO snapshot saved", { description: `${response.audit.hostname} scored ${response.audit.overallScore}/100.` });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not audit this website.");
    } finally {
      setBusy(null);
    }
  }

  async function scheduleAudit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy("schedule");
    try {
      const runAt = new Date(scheduleAt);
      if (Number.isNaN(runAt.getTime())) throw new Error("Choose a valid schedule time.");
      const response = await requestJson<{ job: SeoAuditJob; created: boolean }>("/api/seo/jobs", {
        method: "POST",
        body: JSON.stringify({ url, runAt: runAt.toISOString() }),
      });
      await load();
      setScheduleAt(defaultScheduleAt());
      toast.success(response.created ? "SEO snapshot scheduled" : "Matching schedule already exists", {
        description: formatDate(response.job.runAt),
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not schedule this audit.");
    } finally {
      setBusy(null);
    }
  }

  async function updateJob(job: SeoAuditJob, action: "cancel" | "retry") {
    setBusy(`${action}-${job.id}`);
    try {
      await requestJson(`/api/seo/jobs/${job.id}/${action}`, { method: "POST" });
      await load();
      toast.success(action === "cancel" ? "Scheduled audit cancelled" : "SEO audit queued again");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : `Could not ${action} this audit.`);
    } finally {
      setBusy(null);
    }
  }

  if (loading) {
    return (
      <div aria-label="Loading SEO workspace" className="space-y-4">
        <Skeleton className="h-44 rounded-lg bg-zinc-900" />
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((item) => <Skeleton className="h-32 rounded-lg bg-zinc-900" key={item} />)}</div>
        <Skeleton className="h-[520px] rounded-lg bg-zinc-900" />
      </div>
    );
  }

  const summary = data?.summary ?? { snapshots: 0, sites: 0, averageScore: 0, openFailures: 0, lastAuditAt: null };

  return (
    <div className="min-w-0 space-y-4">
      <Card className="overflow-hidden">
        <CardHeader className="border-b border-zinc-900">
          <div className="flex min-w-0 items-center gap-3">
            <div className="grid size-9 shrink-0 place-items-center rounded-md border border-zinc-800 bg-black text-zinc-400"><SearchCheck className="size-4" /></div>
            <div className="min-w-0"><CardTitle>Run a local SEO audit</CardTitle><CardDescription>Robots-aware, SSRF-protected HTTP analysis with no page HTML retained.</CardDescription></div>
          </div>
          <CardAction>
            <Badge className="border-emerald-500/25 bg-emerald-500/8 text-emerald-300" variant="outline"><ShieldCheck /> Safe crawler</Badge>
          </CardAction>
        </CardHeader>
        <CardContent className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
          <form className="space-y-3" onSubmit={runAudit}>
            <div className="space-y-2"><Label htmlFor="seo-audit-url">Public website URL</Label><Input id="seo-audit-url" maxLength={2048} onChange={(event) => setUrl(event.target.value)} placeholder="https://example.com" required type="url" value={url} /></div>
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs leading-5 text-zinc-600">Checks the initial HTML response. Rendered-page fallback and Lighthouse are shown as planned integrations, never simulated.</p>
              <Button className="min-h-11 shrink-0" disabled={busy === "audit"} type="submit">{busy === "audit" ? <Loader2 className="animate-spin" /> : <FileSearch />}Audit now</Button>
            </div>
          </form>
          <form className="rounded-md border border-zinc-900 bg-black p-4" onSubmit={scheduleAudit}>
            <div className="flex items-start gap-3"><CalendarClock className="mt-0.5 size-4 text-zinc-500" /><div><p className="text-sm font-medium text-zinc-200">Schedule one snapshot</p><p className="mt-1 text-xs leading-5 text-zinc-600">The SQLite job survives an app or computer restart.</p></div></div>
            <div className="mt-4 flex flex-col gap-3 sm:flex-row"><div className="min-w-0 flex-1 space-y-2"><Label htmlFor="seo-schedule-at">Local run time</Label><Input id="seo-schedule-at" onChange={(event) => setScheduleAt(event.target.value)} required type="datetime-local" value={scheduleAt} /></div><Button className="min-h-11 sm:self-end" disabled={!url || busy === "schedule" || schedulerPaused} type="submit" variant="outline">{busy === "schedule" ? <Loader2 className="animate-spin" /> : <Clock3 />}Schedule</Button></div>
            {schedulerPaused ? <p className="mt-3 text-xs text-amber-300">The local job worker is paused. Resume it from Scheduler before scheduling.</p> : null}
          </form>
        </CardContent>
      </Card>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard detail={`${summary.sites} audited site${summary.sites === 1 ? "" : "s"}`} icon={Gauge} label="Latest average" value={summary.averageScore} />
        <SummaryCard detail="Technical and on-page history" icon={FileSearch} label="Saved snapshots" value={summary.snapshots} />
        <SummaryCard detail="Across each site's latest snapshot" icon={AlertTriangle} label="Open failures" value={summary.openFailures} />
        <SummaryCard detail={formatDate(summary.lastAuditAt)} icon={TimerReset} label="Last completed" value={summary.lastAuditAt ? "Saved" : "—"} />
      </div>

      {!selected ? (
        <Card className="min-h-72"><CardContent className="grid min-h-72 place-items-center text-center"><div><Globe2 className="mx-auto size-6 text-zinc-700" /><h2 className="mt-4 text-base font-semibold text-zinc-200">No SEO snapshots yet</h2><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-zinc-600">Enter a public website URL above. The first audit will create a durable baseline without storing the source HTML.</p></div></CardContent></Card>
      ) : (
        <div className="grid min-w-0 gap-4 2xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="min-w-0 space-y-4">
            <Card>
              <CardHeader className="border-b border-zinc-900">
                <div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><CardTitle className="truncate">{selected.hostname}</CardTitle><DeltaBadge value={selected.scoreDelta} /><Badge variant="outline">{selected.trigger}</Badge></div><CardDescription className="mt-2 truncate">{selected.finalUrl}</CardDescription></div>
                <CardAction><a aria-label={`Open ${selected.hostname} in a new tab`} className="grid size-10 place-items-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-900 hover:text-zinc-200 focus-visible:outline-2 focus-visible:outline-offset-2" href={selected.finalUrl} rel="noreferrer" target="_blank"><ExternalLink className="size-4" /></a></CardAction>
              </CardHeader>
              <CardContent className="grid gap-6 lg:grid-cols-[160px_minmax(0,1fr)]">
                <div className="grid place-items-center"><ScoreDial score={selected.overallScore} /><p className="mt-2 text-xs text-zinc-600">HTTP {selected.statusCode} · {selected.durationMs} ms</p></div>
                <div className="grid content-center gap-4 sm:grid-cols-2">
                  {Object.entries({ Technical: selected.scores.technical, "On-page": selected.scores.onPage, Content: selected.scores.content, Social: selected.scores.social }).map(([label, score]) => (
                    <div className="rounded-md border border-zinc-900 bg-black p-3" key={label}><div className="flex items-center justify-between gap-3"><p className="text-xs font-medium text-zinc-400">{label}</p><span className={cn("font-mono text-xs", scoreColor(score))}>{score}</span></div><Progress aria-label={`${label} score ${score}`} className="mt-3" value={score} /></div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <div className="grid gap-4 xl:grid-cols-3">
              <Card><CardHeader><CardDescription>Indexing</CardDescription><CardTitle>{selected.metrics.indexable ? "Indexable" : "Blocked"}</CardTitle></CardHeader><CardContent><p className="text-xs leading-5 text-zinc-600">Canonical: <span className="break-all text-zinc-400">{selected.metrics.canonicalUrl || "missing"}</span></p></CardContent></Card>
              <Card><CardHeader><CardDescription>Page copy</CardDescription><CardTitle>{selected.metrics.wordCount.toLocaleString()} words</CardTitle></CardHeader><CardContent><p className="text-xs text-zinc-600">{selected.metrics.h1Count} H1 · {selected.metrics.h2Count} H2 · {selected.metrics.internalLinks} internal links</p></CardContent></Card>
              <Card><CardHeader><CardDescription>Media & schema</CardDescription><CardTitle>{selected.metrics.imageCount} images</CardTitle></CardHeader><CardContent><p className="text-xs text-zinc-600">{selected.metrics.imagesMissingAlt} missing alt · {selected.metrics.structuredDataTypes.length || 0} schema types</p></CardContent></Card>
            </div>

            <Card>
              <CardHeader className="border-b border-zinc-900">
                <div><CardTitle>Evidence-backed checks</CardTitle><CardDescription>{selected.metrics.failedChecks} failed · {selected.metrics.warningChecks} warning · {selected.metrics.passedChecks} passed</CardDescription></div>
                <CardAction><Button aria-label="Download current SEO audit as JSON" onClick={() => downloadAudit(selected)} size="sm" variant="outline"><Download /> Export JSON</Button></CardAction>
              </CardHeader>
              <CardContent className="p-0">
                <div className="flex max-w-full gap-2 overflow-x-auto border-b border-zinc-900 p-3 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                  {checkFilters.map((item) => <Button aria-pressed={filter === item.value} className="min-h-10 shrink-0" key={item.value} onClick={() => setFilter(item.value)} size="sm" variant={filter === item.value ? "secondary" : "ghost"}>{item.label}</Button>)}
                </div>
                {visibleChecks.length === 0 ? <div className="grid min-h-40 place-items-center px-6 text-center text-sm text-zinc-600">No checks match this filter.</div> : <div className="divide-y divide-zinc-900">{visibleChecks.map((check) => (
                  <div className="grid gap-3 px-4 py-4 sm:grid-cols-[minmax(0,1fr)_auto] sm:px-5" key={check.code}>
                    <div className="flex min-w-0 gap-3"><div className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-md border border-zinc-900 bg-black"><CheckIcon check={check} /></div><div className="min-w-0"><div className="flex flex-wrap items-center gap-2"><p className="text-sm font-medium text-zinc-200">{check.label}</p><Badge className={checkStatusStyles[check.status]} variant="outline">{check.status}</Badge><span className="text-[11px] text-zinc-700">{check.category}</span></div><p className="mt-1 text-xs leading-5 text-zinc-500">{check.evidence}</p>{check.recommendation ? <p className="mt-2 text-xs leading-5 text-zinc-300">{check.recommendation}</p> : null}</div></div>
                    <span className="font-mono text-[11px] text-zinc-700">weight {check.weight}</span>
                  </div>
                ))}</div>}
              </CardContent>
            </Card>
          </div>

          <div className="min-w-0 space-y-4">
            <Card>
              <CardHeader className="border-b border-zinc-900"><div><CardTitle>Snapshot history</CardTitle><CardDescription>Choose a saved result to inspect.</CardDescription></div><CardAction><Button aria-label="Refresh SEO history" disabled={busy === "refresh"} onClick={() => { setBusy("refresh"); void load().finally(() => setBusy(null)); }} size="icon-sm" variant="ghost">{busy === "refresh" ? <Loader2 className="animate-spin" /> : <RefreshCw />}</Button></CardAction></CardHeader>
              <CardContent className="max-h-[420px] space-y-2 overflow-y-auto p-3">
                {data?.items.map((audit) => <button aria-pressed={audit.id === selected.id} className={cn("w-full rounded-md border p-3 text-left transition-colors", audit.id === selected.id ? "border-zinc-600 bg-zinc-900" : "border-zinc-900 bg-black hover:border-zinc-800 hover:bg-zinc-950")} key={audit.id} onClick={() => setSelectedId(audit.id)} type="button"><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate text-xs font-medium text-zinc-300">{audit.hostname}</p><p className="mt-1 text-[11px] text-zinc-600">{formatDate(audit.createdAt)}</p></div><span className={cn("font-mono text-lg", scoreColor(audit.overallScore))}>{audit.overallScore}</span></div></button>)}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="border-b border-zinc-900"><div><CardTitle>Scheduled snapshots</CardTitle><CardDescription>Read-only jobs use the durable local worker.</CardDescription></div></CardHeader>
              <CardContent className="space-y-3 p-3">
                {jobs.length === 0 ? <div className="rounded-md border border-dashed border-zinc-900 px-4 py-8 text-center"><CalendarClock className="mx-auto size-5 text-zinc-700" /><p className="mt-3 text-xs text-zinc-600">No SEO jobs scheduled.</p></div> : jobs.slice(0, 8).map((job) => (
                  <div className="rounded-md border border-zinc-900 bg-black p-3" key={job.id}><div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate text-xs font-medium text-zinc-300">{job.payload.url}</p><p className="mt-1 text-[11px] text-zinc-600">{formatDate(job.runAt)}</p></div><Badge className={jobStatusStyles[job.status]} variant="outline">{job.status}</Badge></div>{job.lastError ? <p className="mt-3 text-xs leading-5 text-red-300">{job.lastError}</p> : null}<div className="mt-3 flex justify-end gap-2">{["queued", "retrying"].includes(job.status) ? <Button className="min-h-10" disabled={busy === `cancel-${job.id}`} onClick={() => void updateJob(job, "cancel")} size="sm" variant="ghost">{busy === `cancel-${job.id}` ? <Loader2 className="animate-spin" /> : <X />}Cancel</Button> : null}{["failed", "missed"].includes(job.status) ? <Button className="min-h-10" disabled={busy === `retry-${job.id}`} onClick={() => void updateJob(job, "retry")} size="sm" variant="outline">{busy === `retry-${job.id}` ? <Loader2 className="animate-spin" /> : <RotateCcw />}Retry</Button> : null}</div></div>
                ))}
              </CardContent>
            </Card>

            <Card className="border-zinc-800 bg-[#070707]"><CardContent className="flex gap-3"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-zinc-500" /><div><p className="text-xs font-medium text-zinc-300">Audit boundary</p><p className="mt-1 text-xs leading-5 text-zinc-600">The core records derived metrics and recommendations only. It does not retain page HTML, bypass robots rules, or claim Lighthouse/Search Console data exists.</p><p className="mt-2 font-mono text-[10px] text-zinc-700">{selected.userAgent}</p></div></CardContent></Card>
          </div>
        </div>
      )}
    </div>
  );
}
