"use client";

import {
  CalendarClock,
  Clock3,
  Copy,
  Loader2,
  Pencil,
  Play,
  Plus,
  ShieldCheck,
  Trash2,
  Zap,
} from "lucide-react";
import { FormEvent, useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { AutomationRule, ContentChannel, PublicAppState } from "@/lib/app-types";
import { requestJson } from "@/lib/api";
import { cn } from "@/lib/utils";

type Props = {
  state: PublicAppState;
  onStateChange: (state: PublicAppState) => void;
  onOpenIntegrations: () => void;
};

type AutomationForm = {
  name: string;
  enabled: boolean;
  channel: ContentChannel;
  topic: string;
  tone: string;
  objective: string;
  timezone: string;
  daysOfWeek: number[];
  publishTime: string;
  approvalChannels: Array<"telegram" | "slack">;
  generateAheadMinutes: number;
  publishAfterApproval: boolean;
};

type StateResponse = { ok: boolean; state: PublicAppState; automation?: AutomationRule };

const dayOptions = [
  { value: 0, label: "Mon" },
  { value: 1, label: "Tue" },
  { value: 2, label: "Wed" },
  { value: 3, label: "Thu" },
  { value: 4, label: "Fri" },
  { value: 5, label: "Sat" },
  { value: 6, label: "Sun" },
];

const frequencyPresets = [
  { label: "Daily", days: [0, 1, 2, 3, 4, 5, 6] },
  { label: "Weekdays", days: [0, 1, 2, 3, 4] },
  { label: "3 per week", days: [0, 2, 4] },
  { label: "Weekly", days: [0] },
];

const channelLabels: Record<ContentChannel, string> = {
  linkedin: "LinkedIn profile",
  "linkedin-company": "LinkedIn company",
  instagram: "Instagram",
  facebook: "Facebook",
  x: "X",
  telegram: "Telegram channel",
  blog: "WordPress",
};

const automationChannels: ContentChannel[] = [
  "linkedin",
  "linkedin-company",
  "facebook",
  "telegram",
  "blog",
];

function isPublishingDestinationReady(state: PublicAppState, channel: ContentChannel) {
  if (channel === "telegram") return state.telegram.configured;
  const adapterId = channel === "linkedin"
    ? "linkedin"
    : channel === "linkedin-company"
      ? "linkedin-organization"
      : channel === "facebook"
        ? "meta"
        : channel === "blog"
          ? "wordpress"
          : null;
  if (!adapterId) return false;
  return state.connectors.accounts.some(
    (account) => account.adapterId === adapterId
      && account.enabled
      && account.status === "verified"
      && account.capabilities.includes("publish"),
  );
}

function formatWhen(value: string | null) {
  if (!value) return "Not scheduled";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function initialForm(state: PublicAppState): AutomationForm {
  const slackReady = state.connectors.accounts.some(
    (account) => account.adapterId === "slack" && account.enabled && account.status === "verified",
  );
  const channel = automationChannels.find((candidate) => isPublishingDestinationReady(state, candidate)) ?? "linkedin";
  return {
    name: "Weekly social posts",
    enabled: isPublishingDestinationReady(state, channel) && !state.scheduler.paused,
    channel,
    topic: "Share useful, factual insights about our business and customer problems.",
    tone: state.workspace.tone || "Clear and confident",
    objective: "Build useful awareness",
    timezone: state.workspace.timezone || "Asia/Karachi",
    daysOfWeek: [0, 2, 4],
    publishTime: "10:00",
    approvalChannels: slackReady ? ["slack"] : state.telegram.configured ? ["telegram"] : [],
    generateAheadMinutes: 60,
    publishAfterApproval: true,
  };
}

function sameDays(left: number[], right: number[]) {
  return left.length === right.length && left.every((day, index) => day === right[index]);
}

function formFromRule(rule: AutomationRule): AutomationForm {
  return {
    name: rule.name,
    enabled: rule.enabled,
    channel: rule.channel,
    topic: rule.topic,
    tone: rule.tone,
    objective: rule.objective,
    timezone: rule.timezone,
    daysOfWeek: rule.daysOfWeek,
    publishTime: rule.publishTime,
    approvalChannels: rule.approvalChannels,
    generateAheadMinutes: rule.generateAheadMinutes,
    publishAfterApproval: rule.publishAfterApproval,
  };
}

export function AutomationsWorkspace({ state, onStateChange, onOpenIntegrations }: Props) {
  const [editing, setEditing] = useState<AutomationRule | "new" | null>(null);
  const [deleting, setDeleting] = useState<AutomationRule | null>(null);
  const [form, setForm] = useState<AutomationForm>(() => initialForm(state));
  const [busy, setBusy] = useState<string | null>(null);

  const slackReady = useMemo(
    () => state.connectors.accounts.some(
      (account) => account.adapterId === "slack" && account.enabled && account.status === "verified",
    ),
    [state.connectors.accounts],
  );
  const destinationReady = useMemo(
    () => isPublishingDestinationReady(state, form.channel),
    [form.channel, state],
  );

  function openCreate() {
    setForm(initialForm(state));
    setEditing("new");
  }

  function openEdit(rule: AutomationRule) {
    setForm(formFromRule(rule));
    setEditing(rule);
  }

  function toggleDay(day: number) {
    setForm((current) => ({
      ...current,
      daysOfWeek: current.daysOfWeek.includes(day)
        ? current.daysOfWeek.filter((value) => value !== day)
        : [...current.daysOfWeek, day].sort(),
    }));
  }

  function toggleApproval(channel: "telegram" | "slack") {
    setForm((current) => ({
      ...current,
      approvalChannels: current.approvalChannels.includes(channel)
        ? current.approvalChannels.filter((value) => value !== channel)
        : [...current.approvalChannels, channel],
    }));
  }

  async function saveAutomation(event: FormEvent) {
    event.preventDefault();
    if (form.daysOfWeek.length === 0) {
      toast.error("Choose at least one posting day.");
      return;
    }
    if (form.enabled && !destinationReady) {
      toast.error("Connect the selected publishing destination, or save this automation paused.");
      return;
    }
    if (form.approvalChannels.includes("telegram") && !state.telegram.configured) {
      toast.error("Connect Telegram before using it for approvals.");
      return;
    }
    if (form.approvalChannels.includes("slack") && !slackReady) {
      toast.error("Connect Slack before using it for approvals.");
      return;
    }
    const id = editing === "new" ? "new" : editing?.id;
    if (!id) return;
    setBusy(`save-${id}`);
    try {
      const response = await requestJson<StateResponse>(
        editing === "new" ? "/api/automations" : `/api/automations/${id}`,
        { method: editing === "new" ? "POST" : "PUT", body: JSON.stringify(form) },
      );
      onStateChange(response.state);
      setEditing(null);
      toast.success(editing === "new" ? "Automation created" : "Automation updated", {
        description: `${form.daysOfWeek.length} post${form.daysOfWeek.length === 1 ? "" : "s"} per week`,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save automation.");
    } finally {
      setBusy(null);
    }
  }

  async function setEnabled(rule: AutomationRule, enabled: boolean) {
    if (enabled && state.scheduler.paused) {
      toast.error("Resume the local scheduler before enabling an automation.");
      return;
    }
    setBusy(`toggle-${rule.id}`);
    try {
      const response = await requestJson<StateResponse>(`/api/automations/${rule.id}`, {
        method: "PUT",
        body: JSON.stringify({ ...formFromRule(rule), enabled }),
      });
      onStateChange(response.state);
      toast.success(enabled ? "Automation resumed" : "Automation paused");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update automation.");
    } finally {
      setBusy(null);
    }
  }

  async function resumeScheduler() {
    setBusy("scheduler-resume");
    try {
      const response = await requestJson<StateResponse>("/api/scheduler", {
        method: "PUT",
        body: JSON.stringify({ paused: false }),
      });
      onStateChange(response.state);
      toast.success("Local scheduler resumed", {
        description: "Enabled automations will wake only for their next due task.",
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not resume the scheduler.");
    } finally {
      setBusy(null);
    }
  }

  async function duplicate(rule: AutomationRule) {
    setBusy(`duplicate-${rule.id}`);
    try {
      const response = await requestJson<StateResponse>(`/api/automations/${rule.id}/duplicate`, { method: "POST" });
      onStateChange(response.state);
      toast.success("Automation duplicated", { description: "The copy is paused until you review it." });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not duplicate automation.");
    } finally {
      setBusy(null);
    }
  }

  async function removeAutomation() {
    if (!deleting) return;
    setBusy(`delete-${deleting.id}`);
    try {
      const response = await requestJson<StateResponse>(`/api/automations/${deleting.id}`, { method: "DELETE" });
      onStateChange(response.state);
      setDeleting(null);
      toast.success("Automation deleted", { description: "Existing drafts and publishing history were kept." });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not delete automation.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-5">
      {state.scheduler.paused ? (
        <Card className="border-amber-400/30 bg-amber-400/[0.06]">
          <CardContent className="flex flex-col gap-4 p-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-base font-semibold text-amber-100">Automation engine is paused</p>
              <p className="mt-1 text-base leading-6 text-zinc-300">
                Existing plans are safe, but no draft will be generated until the local scheduler resumes.
              </p>
            </div>
            <Button disabled={busy === "scheduler-resume"} onClick={() => void resumeScheduler()}>
              {busy === "scheduler-resume" ? <Loader2 className="animate-spin" /> : <Play />}
              Resume scheduler
            </Button>
          </CardContent>
        </Card>
      ) : null}
      <Card className="overflow-hidden border-zinc-800 bg-[#0b0b0c]">
        <CardHeader className="border-b border-zinc-800 bg-[#0e0e10]">
          <div className="flex items-start gap-3">
            <div className="rounded-lg border border-amber-400/25 bg-amber-400/10 p-2 text-amber-300"><Zap className="size-5" /></div>
            <div>
              <CardTitle className="text-lg">Recurring content automations</CardTitle>
              <CardDescription className="mt-1 max-w-2xl text-base leading-7 text-zinc-300">
                Choose the exact posting days. Socium creates a fresh draft before each slot, waits for approval, then publishes the approved revision at the planned time.
              </CardDescription>
            </div>
          </div>
          <Button onClick={openCreate}><Plus /> New automation</Button>
        </CardHeader>
        <CardContent className="grid gap-3 p-4 sm:grid-cols-3">
          <div className="rounded-lg border border-zinc-800 bg-black/40 p-4">
            <p className="text-sm font-medium text-zinc-100">{state.automations.filter((item) => item.enabled).length} active</p>
            <p className="mt-1 text-base leading-6 text-zinc-300">Paused automations use no worker time.</p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-black/40 p-4">
            <p className="text-sm font-medium text-zinc-100">{state.automations.reduce((sum, item) => sum + (item.enabled ? item.postsPerWeek : 0), 0)} posts/week</p>
            <p className="mt-1 text-base leading-6 text-zinc-300">Across every active automation.</p>
          </div>
          <div className="rounded-lg border border-zinc-800 bg-black/40 p-4">
            <p className="text-sm font-medium text-zinc-100">Approval-first</p>
            <p className="mt-1 text-base leading-6 text-zinc-300">Nothing publishes until its exact revision is approved.</p>
          </div>
        </CardContent>
      </Card>

      {state.automations.length === 0 ? (
        <Card className="border-dashed border-zinc-700 bg-[#09090a]">
          <CardContent className="flex min-h-72 flex-col items-center justify-center px-6 text-center">
            <CalendarClock className="size-7 text-zinc-400" />
            <h3 className="mt-4 text-lg font-semibold text-zinc-100">No automations yet</h3>
            <p className="mt-2 max-w-lg text-sm leading-6 text-zinc-400">Create a weekly plan once. You can edit, pause, duplicate, or delete it at any time.</p>
            <Button className="mt-5" onClick={openCreate}><Plus /> Create first automation</Button>
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 xl:grid-cols-2">
          {state.automations.map((rule) => (
            <Card className="border-zinc-800 bg-[#0a0a0b]" key={rule.id}>
              <CardHeader className="border-b border-zinc-800">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge className={rule.enabled ? "border-emerald-400/25 bg-emerald-400/10 text-emerald-300" : "border-zinc-700 bg-zinc-900 text-zinc-300"} variant="outline">{rule.enabled ? "Active" : "Paused"}</Badge>
                    <Badge className="border-zinc-700 bg-black text-zinc-300" variant="outline">{rule.postsPerWeek} / week</Badge>
                    <Badge className="border-zinc-700 bg-black text-zinc-300" variant="outline">{channelLabels[rule.channel]}</Badge>
                  </div>
                  <CardTitle className="mt-3 text-base">{rule.name}</CardTitle>
                  <CardDescription className="mt-1 line-clamp-2 text-sm leading-5 text-zinc-400">{rule.topic}</CardDescription>
                </div>
                <Switch aria-label={`${rule.enabled ? "Pause" : "Resume"} ${rule.name}`} checked={rule.enabled} disabled={busy === `toggle-${rule.id}` || (!rule.enabled && state.scheduler.paused)} onCheckedChange={(enabled) => void setEnabled(rule, enabled)} />
              </CardHeader>
              <CardContent className="space-y-4 p-4">
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-lg border border-zinc-800 bg-black/40 p-3"><p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Next draft</p><p className="mt-2 text-sm text-zinc-200">{formatWhen(rule.nextRunAt)}</p></div>
                  <div className="rounded-lg border border-zinc-800 bg-black/40 p-3"><p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Target publish</p><p className="mt-2 text-sm text-zinc-200">{formatWhen(rule.nextPublishAt)}</p></div>
                </div>
                <div className="flex flex-wrap gap-2">
                  {rule.daysOfWeek.map((day) => <span className="rounded-md border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-xs font-medium text-zinc-200" key={day}>{dayOptions[day]?.label}</span>)}
                  <span className="rounded-md border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-xs font-medium text-zinc-200">{rule.publishTime} · {rule.timezone}</span>
                </div>
                {rule.lastError ? <p className="rounded-lg border border-red-400/25 bg-red-400/10 p-3 text-sm leading-5 text-red-200">{rule.lastError}</p> : null}
                <div className="flex flex-wrap justify-end gap-2 border-t border-zinc-800 pt-4">
                  <Button aria-label={`Duplicate ${rule.name}`} disabled={busy === `duplicate-${rule.id}`} onClick={() => void duplicate(rule)} size="sm" variant="ghost">{busy === `duplicate-${rule.id}` ? <Loader2 className="animate-spin" /> : <Copy />} Duplicate</Button>
                  <Button onClick={() => openEdit(rule)} size="sm" variant="outline"><Pencil /> Edit</Button>
                  <Button className="text-red-300 hover:text-red-200" onClick={() => setDeleting(rule)} size="sm" variant="ghost"><Trash2 /> Delete</Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog onOpenChange={(open) => !open && setEditing(null)} open={editing !== null}>
        <DialogContent className="max-h-[calc(100dvh-1rem)] grid-rows-[auto_minmax(0,1fr)_auto] gap-0 overflow-hidden border-zinc-700 bg-[#0b0b0c] p-0 sm:max-h-[min(860px,calc(100dvh-2rem))] sm:max-w-4xl">
          <DialogHeader>
            <div className="border-b border-zinc-800 px-5 py-5 pr-14 sm:px-6">
              <DialogTitle className="text-lg">{editing === "new" ? "Create automation" : "Edit automation"}</DialogTitle>
              <DialogDescription className="mt-2 max-w-2xl text-base leading-6 text-zinc-300">Choose a simple frequency preset or select exact days. One selected day creates one fresh post each week.</DialogDescription>
            </div>
          </DialogHeader>
          <form className="min-h-0 space-y-5 overflow-y-auto px-5 py-5 sm:px-6" id="automation-form" onSubmit={(event) => void saveAutomation(event)}>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2"><Label className="text-sm" htmlFor="automation-name">Name</Label><Input id="automation-name" maxLength={120} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} required value={form.name} /></div>
              <div className="space-y-2"><Label className="text-sm" htmlFor="automation-channel">Publish to</Label><Select onValueChange={(channel) => channel && setForm((current) => ({ ...current, channel: channel as ContentChannel, enabled: isPublishingDestinationReady(state, channel as ContentChannel) ? current.enabled : false }))} value={form.channel}><SelectTrigger className="w-full" id="automation-channel"><SelectValue /></SelectTrigger><SelectContent>{automationChannels.map((value) => <SelectItem key={value} value={value}>{channelLabels[value]}</SelectItem>)}</SelectContent></Select></div>
            </div>
            <div className={cn("flex items-start justify-between gap-4 rounded-lg border p-4", destinationReady ? "border-emerald-400/20 bg-emerald-400/5" : "border-amber-400/25 bg-amber-400/5")}>
              <div>
                <p className="text-sm font-semibold text-zinc-100">Start this automation immediately</p>
                <p className="mt-1 text-base leading-6 text-zinc-300">{state.scheduler.paused ? "Resume the local scheduler first, or save this automation paused." : destinationReady ? "The publishing destination is connected. You can pause this automation at any time." : "This destination is not connected yet. Save it paused, then connect the destination before resuming."}</p>
                {!destinationReady ? <Button className="mt-2 px-0" onClick={onOpenIntegrations} type="button" variant="link">Connect publishing destination</Button> : null}
              </div>
              <Switch aria-label="Start this automation immediately" checked={form.enabled} disabled={!destinationReady || state.scheduler.paused} onCheckedChange={(enabled) => setForm((current) => ({ ...current, enabled }))} />
            </div>
            <div className="space-y-2"><Label className="text-sm" htmlFor="automation-topic">What should Socium post about?</Label><Textarea className="min-h-24 text-sm leading-6" id="automation-topic" maxLength={1000} onChange={(event) => setForm((current) => ({ ...current, topic: event.target.value }))} required value={form.topic} /></div>
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2"><Label className="text-sm" htmlFor="automation-tone">Tone</Label><Input id="automation-tone" onChange={(event) => setForm((current) => ({ ...current, tone: event.target.value }))} required value={form.tone} /></div>
              <div className="space-y-2"><Label className="text-sm" htmlFor="automation-objective">Objective</Label><Input id="automation-objective" onChange={(event) => setForm((current) => ({ ...current, objective: event.target.value }))} required value={form.objective} /></div>
            </div>
            <div className="space-y-3 rounded-lg border border-zinc-700 bg-black/40 p-4">
              <div className="flex flex-wrap items-center justify-between gap-2"><div><p className="text-sm font-semibold text-zinc-100">Posting days</p><p className="mt-1 text-sm text-zinc-400">{form.daysOfWeek.length} post{form.daysOfWeek.length === 1 ? "" : "s"} every week</p></div><Badge variant="outline">{form.daysOfWeek.length}/week</Badge></div>
              <div aria-label="Posting frequency presets" className="flex flex-wrap gap-2">
                {frequencyPresets.map((preset) => (
                  <Button
                    aria-pressed={sameDays(form.daysOfWeek, preset.days)}
                    className={cn(sameDays(form.daysOfWeek, preset.days) && "border-amber-400/40 bg-amber-400/10 text-amber-100")}
                    key={preset.label}
                    onClick={() => setForm((current) => ({ ...current, daysOfWeek: preset.days }))}
                    size="sm"
                    type="button"
                    variant="outline"
                  >
                    {preset.label}
                  </Button>
                ))}
              </div>
              <div className="grid grid-cols-4 gap-2 sm:grid-cols-7">{dayOptions.map((day) => <Button aria-pressed={form.daysOfWeek.includes(day.value)} className={cn("min-h-11", form.daysOfWeek.includes(day.value) && "border-amber-400/40 bg-amber-400/10 text-amber-200")} key={day.value} onClick={() => toggleDay(day.value)} type="button" variant="outline">{day.label}</Button>)}</div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2"><Label className="text-sm" htmlFor="automation-time">Publish time</Label><Input id="automation-time" onChange={(event) => setForm((current) => ({ ...current, publishTime: event.target.value }))} required type="time" value={form.publishTime} /></div>
                <div className="space-y-2"><Label className="text-sm" htmlFor="automation-timezone">Timezone</Label><Input id="automation-timezone" onChange={(event) => setForm((current) => ({ ...current, timezone: event.target.value }))} required value={form.timezone} /></div>
              </div>
              <div className="space-y-2"><Label className="text-sm" htmlFor="automation-lead">Create draft before publish time</Label><Select onValueChange={(value) => value && setForm((current) => ({ ...current, generateAheadMinutes: Number(value) }))} value={String(form.generateAheadMinutes)}><SelectTrigger className="w-full" id="automation-lead"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="15">15 minutes before</SelectItem><SelectItem value="30">30 minutes before</SelectItem><SelectItem value="60">1 hour before</SelectItem><SelectItem value="120">2 hours before</SelectItem><SelectItem value="1440">1 day before</SelectItem></SelectContent></Select></div>
            </div>
            <div className="space-y-3 rounded-lg border border-zinc-700 bg-black/40 p-4">
              <div><p className="text-sm font-semibold text-zinc-100">Approval route</p><p className="mt-1 text-sm leading-5 text-zinc-400">Dashboard approval is always available. External approval channels are optional.</p></div>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className={cn("flex min-h-16 items-center justify-between gap-3 rounded-lg border border-zinc-700 p-3", !state.telegram.configured && "opacity-60")}><span><span className="block text-sm font-medium text-zinc-100">Telegram</span><span className="mt-1 block text-xs text-zinc-400">{state.telegram.configured ? "Connected" : "Connect first"}</span></span><Switch aria-label="Send approvals to Telegram" checked={form.approvalChannels.includes("telegram")} disabled={!state.telegram.configured} onCheckedChange={() => toggleApproval("telegram")} /></label>
                <label className={cn("flex min-h-16 items-center justify-between gap-3 rounded-lg border border-zinc-700 p-3", !slackReady && "opacity-60")}><span><span className="block text-sm font-medium text-zinc-100">Slack</span><span className="mt-1 block text-xs text-zinc-400">{slackReady ? "Connected" : "Connect first"}</span></span><Switch aria-label="Send approvals to Slack" checked={form.approvalChannels.includes("slack")} disabled={!slackReady} onCheckedChange={() => toggleApproval("slack")} /></label>
              </div>
              {(!state.telegram.configured || !slackReady) ? <Button onClick={onOpenIntegrations} type="button" variant="ghost">Open integrations</Button> : null}
              <label className="flex items-start justify-between gap-4 rounded-lg border border-emerald-400/20 bg-emerald-400/5 p-3"><span className="flex gap-3"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-emerald-300" /><span><span className="block text-sm font-medium text-zinc-100">Publish after approval</span><span className="mt-1 block text-sm leading-5 text-zinc-400">The approved revision waits until its target time. Late approvals publish as soon as the local worker wakes.</span></span></span><Switch aria-label="Publish automatically after approval" checked={form.publishAfterApproval} onCheckedChange={(publishAfterApproval) => setForm((current) => ({ ...current, publishAfterApproval }))} /></label>
            </div>
          </form>
          <DialogFooter className="m-0 shrink-0 rounded-none border-zinc-800 bg-[#0e0e10] px-5 py-4 sm:px-6">
            <Button onClick={() => setEditing(null)} type="button" variant="ghost">Cancel</Button>
            <Button disabled={Boolean(busy?.startsWith("save-"))} form="automation-form" type="submit">{busy?.startsWith("save-") ? <Loader2 className="animate-spin" /> : <Clock3 />} Save automation</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog onOpenChange={(open) => !open && setDeleting(null)} open={deleting !== null}>
        <DialogContent className="border-zinc-700 bg-[#0b0b0c]">
          <DialogHeader><DialogTitle>Delete automation?</DialogTitle><DialogDescription className="text-sm leading-6 text-zinc-400">{deleting?.name} will stop creating future drafts. Existing drafts and publishing history will remain.</DialogDescription></DialogHeader>
          <DialogFooter><Button onClick={() => setDeleting(null)} variant="ghost">Cancel</Button><Button className="bg-red-500 text-white hover:bg-red-400" disabled={Boolean(deleting && busy === `delete-${deleting.id}`)} onClick={() => void removeAutomation()}>{deleting && busy === `delete-${deleting.id}` ? <Loader2 className="animate-spin" /> : <Trash2 />} Delete automation</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
