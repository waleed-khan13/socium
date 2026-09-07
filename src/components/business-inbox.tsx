"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowUpRight,
  Check,
  CheckCircle2,
  Clock3,
  Inbox,
  Loader2,
  Mail,
  MailCheck,
  RefreshCw,
  Send,
  Sparkles,
} from "lucide-react";
import { useDeferredValue, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { requestJson } from "@/lib/api";
import type {
  BusinessInboxItem,
  ConnectorAccount,
  EmailJob,
  EmailReplyDraft,
  EmailThread,
} from "@/lib/app-types";
import { cn } from "@/lib/utils";

type InboxResponse = { ok: boolean; items: BusinessInboxItem[] };
type ThreadsResponse = { ok: boolean; items: EmailThread[] };
type ThreadResponse = { ok: boolean; thread: EmailThread };

type Props = {
  aiConfigured: boolean;
  gmailAccount: ConnectorAccount | null;
  onNavigate: (view: string) => void;
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function statusTone(status: string) {
  if (status === "sent" || status === "approved") return "border-emerald-500/25 bg-emerald-500/8 text-emerald-300";
  if (status === "failed_uncertain") return "border-red-500/25 bg-red-500/8 text-red-300";
  if (status === "scheduled" || status === "pending") return "border-amber-500/25 bg-amber-500/8 text-amber-200";
  return "border-zinc-800 text-zinc-400";
}

async function waitForEmailJob(jobId: string) {
  for (let attempt = 0; attempt < 120; attempt += 1) {
    const result = await requestJson<{ ok: boolean; job: EmailJob }>(`/api/email/jobs/${jobId}`);
    if (result.job.status === "completed") return result.job;
    if (["failed", "cancelled", "failed_uncertain"].includes(result.job.status)) {
      throw new Error(result.job.lastError || "Email reply generation failed.");
    }
    await new Promise((resolve) => window.setTimeout(resolve, 1_000));
  }
  throw new Error("Reply is still running. It will remain safely queued in Socium.");
}

function DraftEditor({ draft, onChanged }: { draft: EmailReplyDraft; onChanged: () => Promise<void> }) {
  const [subject, setSubject] = useState(draft.subject);
  const [body, setBody] = useState(draft.body);
  const [scheduledFor, setScheduledFor] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  async function save() {
    setBusy("save");
    try {
      await requestJson(`/api/email/reply-drafts/${draft.id}`, {
        method: "PUT",
        body: JSON.stringify({ subject, body }),
      });
      toast.success("A new reply revision is ready for approval.");
      await onChanged();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Reply could not be saved.");
    } finally {
      setBusy(null);
    }
  }

  async function approve() {
    if (!draft.approvalRequestId) return;
    setBusy("approve");
    try {
      await requestJson(`/api/approvals/${draft.approvalRequestId}/decision`, {
        method: "POST",
        body: JSON.stringify({ action: "approve", actor: "Local operator", source: "dashboard" }),
      });
      toast.success("Exact reply revision approved.");
      await onChanged();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Reply could not be approved.");
    } finally {
      setBusy(null);
    }
  }

  async function sendNow() {
    setBusy("send");
    try {
      await requestJson(`/api/email/reply-drafts/${draft.id}/send`, { method: "POST" });
      toast.success("Reply sent through Gmail.");
      await onChanged();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Gmail could not confirm delivery.");
    } finally {
      setBusy(null);
    }
  }

  async function schedule() {
    if (!scheduledFor) return;
    setBusy("schedule");
    try {
      await requestJson(`/api/email/reply-drafts/${draft.id}/schedule`, {
        method: "POST",
        body: JSON.stringify({ runAt: new Date(scheduledFor).toISOString() }),
      });
      toast.success("Approved reply scheduled.");
      await onChanged();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Reply could not be scheduled.");
    } finally {
      setBusy(null);
    }
  }

  const canEdit = draft.status === "pending";
  const canDeliver = draft.status === "approved";

  return (
    <div className="space-y-4 rounded-xl border border-fuchsia-500/15 bg-fuchsia-500/[0.025] p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><p className="text-sm font-semibold text-zinc-100">AI reply draft</p><p className="mt-1 text-xs text-zinc-500">Revision {draft.revision} · {draft.rationale || "Review before approval."}</p></div>
        <Badge className={cn("capitalize", statusTone(draft.status))} variant="outline">{draft.status.replaceAll("_", " ")}</Badge>
      </div>
      <Input aria-label="Reply subject" disabled={!canEdit || Boolean(busy)} onChange={(event) => setSubject(event.target.value)} value={subject} />
      <Textarea aria-label="Reply body" className="min-h-52 leading-7" disabled={!canEdit || Boolean(busy)} onChange={(event) => setBody(event.target.value)} value={body} />
      {draft.lastError ? <p className="rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-xs leading-5 text-red-200">{draft.lastError}</p> : null}
      <div className="flex flex-wrap items-center gap-2">
        {canEdit ? <Button disabled={Boolean(busy)} onClick={() => void save()} type="button" variant="outline">{busy === "save" ? <Loader2 className="animate-spin" /> : <RefreshCw />} Save new revision</Button> : null}
        {canEdit ? <Button disabled={Boolean(busy)} onClick={() => void approve()} type="button">{busy === "approve" ? <Loader2 className="animate-spin" /> : <Check />} Approve exact revision</Button> : null}
        {canDeliver ? <Button disabled={Boolean(busy)} onClick={() => void sendNow()} type="button">{busy === "send" ? <Loader2 className="animate-spin" /> : <Send />} Send now</Button> : null}
      </div>
      {canDeliver ? (
        <div className="grid gap-2 border-t border-white/7 pt-4 sm:grid-cols-[minmax(0,1fr)_auto]">
          <Input aria-label="Scheduled send time" min={new Date().toISOString().slice(0, 16)} onChange={(event) => setScheduledFor(event.target.value)} type="datetime-local" value={scheduledFor} />
          <Button disabled={Boolean(busy) || !scheduledFor} onClick={() => void schedule()} type="button" variant="outline">{busy === "schedule" ? <Loader2 className="animate-spin" /> : <Clock3 />} Schedule</Button>
        </div>
      ) : null}
    </div>
  );
}

function MissedEmailJob({ job, onChanged }: { job: EmailJob; onChanged: () => Promise<void> }) {
  const [rescheduleAt, setRescheduleAt] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  async function recover(decision: "run_now" | "reschedule" | "skip") {
    if (decision === "reschedule" && !rescheduleAt) return;
    setBusy(decision);
    try {
      await requestJson(`/api/jobs/${job.id}/recover`, {
        method: "POST",
        body: JSON.stringify({
          decision,
          runAt: decision === "reschedule" ? new Date(rescheduleAt).toISOString() : null,
        }),
      });
      toast.success(decision === "skip" ? "Missed email skipped." : decision === "run_now" ? "Email queued to send now." : "Email rescheduled.");
      await onChanged();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Missed email could not be recovered.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="grid gap-3 rounded-xl border border-orange-500/20 bg-orange-500/5 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(220px,320px)_auto] lg:items-end">
      <div><p className="text-sm font-medium text-orange-100">A scheduled Gmail reply was missed</p><p className="mt-1 text-xs leading-5 text-orange-100/65">{job.recoveryReason || "Socium was unavailable at the scheduled time and did not send automatically."}</p></div>
      <Input aria-label="New email send time" min={new Date().toISOString().slice(0, 16)} onChange={(event) => setRescheduleAt(event.target.value)} type="datetime-local" value={rescheduleAt} />
      <div className="flex flex-wrap gap-2">
        <Button disabled={Boolean(busy)} onClick={() => void recover("run_now")} size="sm" type="button"><Send /> Run now</Button>
        <Button disabled={Boolean(busy) || !rescheduleAt} onClick={() => void recover("reschedule")} size="sm" type="button" variant="outline"><Clock3 /> Reschedule</Button>
        <Button disabled={Boolean(busy)} onClick={() => void recover("skip")} size="sm" type="button" variant="ghost">Skip</Button>
      </div>
    </div>
  );
}

export function BusinessInbox({ aiConfigured, gmailAccount, onNavigate }: Props) {
  const queryClient = useQueryClient();
  const [selectedThreadId, setSelectedThreadId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const deferredSearch = useDeferredValue(search);
  const connected = gmailAccount?.status === "verified";

  const inboxQuery = useQuery({
    queryKey: ["business-inbox"],
    queryFn: () => requestJson<InboxResponse>("/api/inbox"),
    refetchInterval: 20_000,
  });
  const threadsQuery = useQuery({
    queryKey: ["email-threads", deferredSearch],
    queryFn: () => requestJson<ThreadsResponse>(`/api/email/threads?query=${encodeURIComponent(deferredSearch)}`),
    enabled: connected,
    refetchInterval: 30_000,
  });
  const missedJobsQuery = useQuery({
    queryKey: ["email-jobs", "missed"],
    queryFn: () => requestJson<{ ok: boolean; items: EmailJob[] }>("/api/email/jobs?status=missed"),
    enabled: connected,
    refetchInterval: 30_000,
  });
  const activeThreadId = selectedThreadId ?? threadsQuery.data?.items[0]?.id ?? null;
  const threadQuery = useQuery({
    queryKey: ["email-thread", activeThreadId],
    queryFn: () => requestJson<ThreadResponse>(`/api/email/threads/${activeThreadId}`),
    enabled: Boolean(activeThreadId),
  });
  const operationalItems = useMemo(
    () => (inboxQuery.data?.items ?? []).filter((item) => item.entityType !== "email_thread" && item.entityType !== "email_reply"),
    [inboxQuery.data?.items],
  );

  async function refreshEmailData() {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["email-threads"] }),
      queryClient.invalidateQueries({ queryKey: ["email-thread"] }),
      queryClient.invalidateQueries({ queryKey: ["business-inbox"] }),
      queryClient.invalidateQueries({ queryKey: ["email-jobs"] }),
    ]);
  }

  async function sync() {
    if (!gmailAccount) return;
    setBusy("sync");
    try {
      const result = await requestJson<{ sync: { created: number; updated: number } }>("/api/gmail/sync", {
        method: "POST",
        body: JSON.stringify({ accountId: gmailAccount.id, limit: 25 }),
      });
      toast.success(`Gmail synced: ${result.sync.created} new, ${result.sync.updated} refreshed.`);
      await refreshEmailData();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Gmail sync failed.");
    } finally {
      setBusy(null);
    }
  }

  async function generateReply() {
    if (!activeThreadId) return;
    setBusy("generate");
    try {
      const queued = await requestJson<{ job: EmailJob }>(`/api/email/threads/${activeThreadId}/reply-drafts`, {
        method: "POST",
        body: JSON.stringify({ instruction: "Reply helpfully using only confirmed business facts." }),
      });
      await waitForEmailJob(queued.job.id);
      toast.success("Reply draft is ready for approval.");
      await refreshEmailData();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Reply generation failed.");
      await refreshEmailData();
    } finally {
      setBusy(null);
    }
  }

  if (!connected) {
    return (
      <Card className="business-panel">
        <CardContent className="flex min-h-[440px] flex-col items-center justify-center text-center">
          <span className="grid size-14 place-items-center rounded-2xl border border-red-500/20 bg-red-500/5 text-red-300"><Mail className="size-6" /></span>
          <h2 className="mt-5 text-xl font-semibold text-zinc-100">Connect Gmail to open the Unified Inbox</h2>
          <p className="mt-2 max-w-lg text-sm leading-6 text-zinc-500">One Google consent screen connects real email threads. Credentials stay encrypted on this device and every AI reply needs your approval.</p>
          <Button className="mt-6" onClick={() => onNavigate("integrations")} type="button"><MailCheck /> Open integrations</Button>
        </CardContent>
      </Card>
    );
  }

  const activeThread = threadQuery.data?.thread;
  return (
    <div className="space-y-4">
      {missedJobsQuery.data?.items.map((job) => <MissedEmailJob job={job} key={job.id} onChanged={refreshEmailData} />)}
      <Card className="business-panel overflow-hidden">
        <CardHeader className="border-b border-white/7">
          <div className="flex items-start gap-3">
            <div className="flex size-11 items-center justify-center rounded-xl border border-fuchsia-400/20 bg-fuchsia-400/8 text-fuchsia-300"><Inbox className="size-5" /></div>
            <div><CardTitle>Unified Inbox</CardTitle><CardDescription>Real Gmail threads, local AI drafting, exact-revision approval and deterministic delivery.</CardDescription></div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Badge className="border-emerald-500/25 bg-emerald-500/8 text-emerald-300" variant="outline">{String(gmailAccount.config.email_address || "Gmail connected")}</Badge>
            <Button disabled={busy === "sync"} onClick={() => void sync()} size="sm" type="button" variant="outline">{busy === "sync" ? <Loader2 className="animate-spin" /> : <RefreshCw />} Sync now</Button>
          </div>
        </CardHeader>
        <CardContent className="grid min-h-[620px] p-0 lg:grid-cols-[340px_minmax(0,1fr)]">
          <aside className="border-b border-white/7 lg:border-r lg:border-b-0">
            <div className="border-b border-white/7 p-3"><Input aria-label="Search email threads" onChange={(event) => setSearch(event.target.value)} placeholder="Search email…" value={search} /></div>
            <div className="max-h-[560px] overflow-y-auto p-2">
              {threadsQuery.isPending ? <div className="flex min-h-40 items-center justify-center text-sm text-zinc-500"><Loader2 className="mr-2 size-4 animate-spin" />Loading local inbox…</div> : threadsQuery.isError ? <div className="p-5 text-sm text-red-300">{threadsQuery.error instanceof Error ? threadsQuery.error.message : "Inbox could not be loaded."}</div> : threadsQuery.data?.items.length ? threadsQuery.data.items.map((thread) => (
                <button className={cn("mb-1 w-full rounded-xl border p-3 text-left transition-colors focus-visible:ring-2 focus-visible:ring-fuchsia-300", activeThreadId === thread.id ? "border-fuchsia-400/25 bg-fuchsia-400/[0.07]" : "border-transparent hover:border-white/7 hover:bg-white/[0.03]")} key={thread.id} onClick={() => setSelectedThreadId(thread.id)} type="button">
                  <span className="flex items-center justify-between gap-2"><span className="truncate text-sm font-medium text-zinc-200">{thread.senderName || thread.senderEmail}</span>{thread.unread ? <span className="size-2 shrink-0 rounded-full bg-fuchsia-400" /> : null}</span>
                  <span className="mt-1 block truncate text-sm text-zinc-400">{thread.subject}</span>
                  <span className="mt-1 block truncate text-xs text-zinc-600">{thread.snippet}</span>
                  <span className="mt-2 flex items-center justify-between gap-2"><Badge className="capitalize" variant="outline">{thread.classification.replaceAll("_", " ")}</Badge><time className="text-[10px] text-zinc-600" dateTime={thread.lastMessageAt}>{formatDate(thread.lastMessageAt)}</time></span>
                </button>
              )) : <div className="flex min-h-52 flex-col items-center justify-center px-5 text-center"><MailCheck className="size-6 text-zinc-700" /><p className="mt-3 text-sm font-medium text-zinc-300">No synced email yet</p><p className="mt-1 text-xs leading-5 text-zinc-600">Select Sync now. Socium stores only the bounded set of threads you request.</p></div>}
            </div>
          </aside>
          <section className="min-w-0 p-4 md:p-6">
            {!activeThreadId ? <div className="grid min-h-[480px] place-items-center text-sm text-zinc-600">Select or sync a Gmail thread.</div> : threadQuery.isPending ? <div className="grid min-h-[480px] place-items-center text-zinc-500"><Loader2 className="size-5 animate-spin" /></div> : threadQuery.isError ? <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-4 text-sm text-red-200">{threadQuery.error instanceof Error ? threadQuery.error.message : "Thread could not be loaded."}</div> : activeThread ? (
              <div className="space-y-5">
                <div className="border-b border-white/7 pb-5"><div className="flex flex-wrap items-center gap-2"><Badge variant="outline">{activeThread.messages?.length ?? 0} messages</Badge><Badge className="capitalize" variant="outline">{activeThread.classification.replaceAll("_", " ")}</Badge></div><h2 className="mt-3 text-xl font-semibold text-zinc-100">{activeThread.subject}</h2><p className="mt-1 text-sm text-zinc-500">{activeThread.senderName || activeThread.senderEmail} · {activeThread.senderEmail}</p></div>
                <div className="space-y-3">{activeThread.messages?.map((message) => <article className={cn("rounded-xl border p-4", message.direction === "outbound" ? "ml-6 border-fuchsia-500/15 bg-fuchsia-500/[0.025]" : "mr-6 border-white/7 bg-white/[0.02]")} key={message.id}><div className="flex flex-wrap justify-between gap-2 text-xs text-zinc-500"><span>{message.sender}</span><time dateTime={message.sentAt}>{formatDate(message.sentAt)}</time></div><p className="mt-3 whitespace-pre-wrap text-sm leading-7 text-zinc-300">{message.bodyText || message.snippet}</p></article>)}</div>
                {activeThread.draft ? <DraftEditor draft={activeThread.draft} key={activeThread.draft.id} onChanged={async () => { await refreshEmailData(); await threadQuery.refetch(); }} /> : <div className="rounded-xl border border-dashed border-white/10 p-5"><div className="flex items-start gap-3"><Sparkles className="mt-0.5 size-5 text-fuchsia-300" /><div><p className="font-medium text-zinc-100">Create an approval-ready reply</p><p className="mt-1 text-sm leading-6 text-zinc-500">Socium uses only confirmed business knowledge. Nothing is sent automatically.</p></div></div><Button className="mt-4" disabled={!aiConfigured || busy === "generate"} onClick={() => void generateReply()} type="button">{busy === "generate" ? <Loader2 className="animate-spin" /> : <Sparkles />}{busy === "generate" ? "Drafting safely…" : "Generate reply"}</Button>{!aiConfigured ? <p className="mt-2 text-xs text-amber-300">Connect an AI provider first.</p> : null}</div>}
              </div>
            ) : null}
          </section>
        </CardContent>
      </Card>

      {operationalItems.length ? (
        <Card className="business-panel">
          <CardHeader><CardTitle>Other items needing attention</CardTitle><CardDescription>Workflow failures, publishing approvals and missed schedules.</CardDescription></CardHeader>
          <CardContent className="space-y-2">{operationalItems.map((item) => <button className="flex w-full items-start gap-3 rounded-xl border border-white/7 p-4 text-left hover:bg-white/[0.035]" key={item.id} onClick={() => onNavigate(item.actionUrl?.includes("calendar") ? "calendar" : item.kind === "approval" ? "approvals" : "activity")} type="button"><span className={cn("grid size-9 place-items-center rounded-lg", item.priority === "high" || item.priority === "urgent" ? "bg-orange-400/10 text-orange-300" : "bg-fuchsia-400/10 text-fuchsia-300")}>{item.priority === "high" || item.priority === "urgent" ? <AlertTriangle className="size-4" /> : <Inbox className="size-4" />}</span><span className="min-w-0 flex-1"><span className="font-medium text-zinc-100">{item.title}</span><span className="mt-1 block text-sm leading-6 text-zinc-500">{item.body}</span></span><ArrowUpRight className="mt-2 size-4 text-zinc-600" /></button>)}</CardContent>
        </Card>
      ) : !inboxQuery.isPending ? <div className="flex items-center justify-center gap-2 py-2 text-xs text-zinc-600"><CheckCircle2 className="size-4 text-emerald-400" />No other operational items need attention.</div> : null}
    </div>
  );
}
