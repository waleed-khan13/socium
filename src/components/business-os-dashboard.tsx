"use client";

import { useQuery } from "@tanstack/react-query";
import Image from "next/image";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Bot,
  CalendarDays,
  CheckCircle2,
  Clock3,
  Cloud,
  FileCheck2,
  Inbox,
  Loader2,
  Megaphone,
  Plus,
  RadioTower,
  Sparkles,
  Target,
  UsersRound,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { requestJson } from "@/lib/api";
import type { DashboardSummary } from "@/lib/app-types";
import { cn } from "@/lib/utils";

type DashboardResponse = { ok: boolean; summary: DashboardSummary };

type BusinessDashboardProps = {
  onNavigate: (view: string) => void;
};

const metricDefinitions = [
  { key: "postsPublished", label: "Posts published", icon: Megaphone },
  { key: "postsScheduled", label: "Posts scheduled", icon: CalendarDays },
  { key: "approvalsPending", label: "Pending approvals", icon: FileCheck2 },
  { key: "leadsCaptured", label: "Leads captured", icon: UsersRound },
] as const;

const channelLogos: Record<string, string> = {
  instagram: "/social/instagram.svg",
  linkedin: "/social/linkedin.svg",
  "linkedin-company": "/social/linkedin.svg",
  slack: "/social/slack.svg",
  telegram: "/social/telegram.svg",
  facebook: "/social/facebook.svg",
};

function formatShortDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(
    new Date(`${value}T00:00:00Z`),
  );
}

function formatDateTime(value: string | null) {
  if (!value) return "Schedule pending";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

function LoadingDashboard() {
  return (
    <div className="flex min-h-[480px] items-center justify-center rounded-2xl border border-white/8 bg-[#0d0b10]">
      <div className="flex items-center gap-3 text-sm text-zinc-300">
        <Loader2 aria-hidden="true" className="size-5 animate-spin text-fuchsia-400" />
        Loading your local business operations…
      </div>
    </div>
  );
}

function EmptyPanel({
  description,
  action,
  onAction,
}: {
  description: string;
  action?: string;
  onAction?: () => void;
}) {
  return (
    <div className="flex min-h-44 flex-col items-center justify-center px-6 text-center">
      <Activity aria-hidden="true" className="mb-3 size-6 text-zinc-600" />
      <p className="max-w-sm text-sm leading-6 text-zinc-400">{description}</p>
      {action && onAction ? (
        <Button className="mt-4" onClick={onAction} size="sm" variant="outline">
          {action}
        </Button>
      ) : null}
    </div>
  );
}

export function BusinessOsDashboard({ onNavigate }: BusinessDashboardProps) {
  const query = useQuery({
    queryKey: ["business-os-dashboard"],
    queryFn: () => requestJson<DashboardResponse>("/api/dashboard/summary"),
    refetchInterval: 30_000,
  });

  if (query.isPending) return <LoadingDashboard />;
  if (query.isError || !query.data) {
    return (
      <Card className="border-red-500/20 bg-red-500/[0.04]">
        <CardContent className="flex min-h-64 flex-col items-center justify-center text-center">
          <AlertTriangle aria-hidden="true" className="mb-3 size-7 text-red-300" />
          <h2 className="text-base font-semibold text-zinc-100">Dashboard data is unavailable</h2>
          <p className="mt-2 max-w-md text-sm text-zinc-400">
            {query.error instanceof Error ? query.error.message : "The local API did not return a dashboard summary."}
          </p>
          <Button className="mt-5" onClick={() => void query.refetch()} variant="outline">
            Try again
          </Button>
        </CardContent>
      </Card>
    );
  }

  const summary = query.data.summary;
  const hasPublishingData = summary.publishingTrend.some((point) => point.value > 0);
  const businessName = summary.workspace.businessName || summary.workspace.name || "your business";
  const currentMonth = new Intl.DateTimeFormat(undefined, { month: "long", year: "numeric" }).format(
    new Date(),
  );
  const today = new Date();
  const firstWeekday = new Date(today.getFullYear(), today.getMonth(), 1).getDay();
  const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
  const calendarCells = Array.from(
    { length: Math.ceil((firstWeekday + daysInMonth) / 7) * 7 },
    (_, index) => index - firstWeekday + 1,
  );

  return (
    <div className="space-y-5">
      <section className="flex flex-col gap-5 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold tracking-[0.16em] text-fuchsia-300 uppercase">
            <span className="size-1.5 rounded-full bg-fuchsia-400 shadow-[0_0_16px_#f472b6]" />
            Local-first AI Business OS
          </div>
          <h2 className="text-balance text-2xl font-semibold tracking-tight text-white md:text-3xl">
            Good day, {businessName}
          </h2>
          <p className="mt-2 text-sm text-zinc-400">Here&apos;s what needs attention across your business today.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-white/10 bg-[#100d13] p-2 shadow-[0_20px_70px_rgba(0,0,0,0.28)]">
          <div className="flex min-h-11 items-center gap-2 rounded-xl border border-white/8 bg-black/30 px-3">
            {summary.ai.local ? <Bot className="size-4 text-fuchsia-300" /> : <Cloud className="size-4 text-orange-300" />}
            <div>
              <p className="text-xs font-medium text-zinc-100">{summary.ai.local ? "Local AI" : "Cloud AI"}</p>
              <p className={cn("text-[11px]", summary.ai.configured ? "text-emerald-300" : "text-amber-300")}>
                {summary.ai.configured ? "Connected" : "Setup required"}
              </p>
            </div>
          </div>
          <Button className="socium-gradient-button min-h-11 px-5" onClick={() => onNavigate("create")}>
            <Plus aria-hidden="true" /> Create
          </Button>
        </div>
      </section>

      {summary.attention.total > 0 ? (
        <button
          className="flex min-h-12 w-full items-center justify-between gap-4 rounded-xl border border-orange-400/20 bg-orange-400/[0.06] px-4 py-3 text-left transition-colors hover:bg-orange-400/[0.09] focus-visible:ring-2 focus-visible:ring-orange-300"
          onClick={() => onNavigate("inbox")}
          type="button"
        >
          <span className="flex items-center gap-3 text-sm text-orange-100">
            <Target aria-hidden="true" className="size-5 text-orange-300" />
            <span><strong>{summary.attention.total} items</strong> need your attention</span>
          </span>
          <ArrowUpRight aria-hidden="true" className="size-4" />
        </button>
      ) : (
        <div className="flex min-h-12 items-center gap-3 rounded-xl border border-emerald-400/20 bg-emerald-400/[0.05] px-4 text-sm text-emerald-100">
          <CheckCircle2 aria-hidden="true" className="size-5 text-emerald-300" />
          Nothing urgent—your local workflows are clear.
        </div>
      )}

      <section aria-label="Business metrics" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {metricDefinitions.map((definition) => {
          const Icon = definition.icon;
          return (
            <Card className="business-metric-card overflow-hidden" key={definition.key}>
              <CardContent className="flex items-center gap-4 p-4 md:p-5">
                <div className="flex size-12 shrink-0 items-center justify-center rounded-full border border-fuchsia-400/25 bg-fuchsia-500/8 text-fuchsia-300 shadow-[inset_0_0_18px_rgba(236,72,153,0.08)]">
                  <Icon aria-hidden="true" className="size-5" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm text-zinc-400">{definition.label}</p>
                  <p className="mt-1 text-2xl font-semibold tabular-nums text-white">
                    {summary.metrics[definition.key].toLocaleString()}
                  </p>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </section>

      <section className="grid gap-4 xl:grid-cols-[1.35fr_0.65fr_0.9fr]">
        <Card className="business-panel min-w-0">
          <CardHeader className="flex-row items-center justify-between border-b border-white/7">
            <div>
              <CardTitle>Publishing over time</CardTitle>
              <p className="mt-1 text-sm text-zinc-500">Real posts published during the last 30 days.</p>
            </div>
            <Badge className="border-white/10 bg-white/[0.03] text-zinc-300" variant="outline">30 days</Badge>
          </CardHeader>
          <CardContent className="p-3 md:p-5">
            {hasPublishingData ? (
              <div className="h-64 w-full" role="img" aria-label="Posts published during the last 30 days">
                <ResponsiveContainer height="100%" width="100%">
                  <AreaChart data={summary.publishingTrend} margin={{ left: -20, right: 8, top: 8 }}>
                    <defs>
                      <linearGradient id="publishingFill" x1="0" x2="0" y1="0" y2="1">
                        <stop offset="0%" stopColor="#f43f8f" stopOpacity={0.42} />
                        <stop offset="100%" stopColor="#f43f8f" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid stroke="#27222b" strokeDasharray="3 5" vertical={false} />
                    <XAxis dataKey="date" minTickGap={34} stroke="#807886" tickFormatter={formatShortDate} tickLine={false} />
                    <YAxis allowDecimals={false} stroke="#807886" tickLine={false} width={40} />
                    <ChartTooltip
                      contentStyle={{ background: "#121015", border: "1px solid #3b3440", borderRadius: 10 }}
                      labelFormatter={(label) => formatShortDate(String(label))}
                    />
                    <Area dataKey="value" fill="url(#publishingFill)" stroke="#fb3f91" strokeWidth={2.5} type="monotone" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <EmptyPanel
                action="Create first post"
                description="No posts were published in the last 30 days. Socium will chart real activity after your first publication."
                onAction={() => onNavigate("create")}
              />
            )}
          </CardContent>
        </Card>

        <Card className="business-panel">
          <CardHeader className="flex-row items-center justify-between border-b border-white/7">
            <CardTitle>Connected channels</CardTitle>
            <Button onClick={() => onNavigate("integrations")} size="sm" variant="ghost">Manage</Button>
          </CardHeader>
          <CardContent className="p-3">
            {summary.channels.length ? (
              <div className="space-y-1">
                {summary.channels.slice(0, 6).map((channel) => (
                  <div className="flex min-h-12 items-center gap-3 rounded-xl px-2.5 py-2 hover:bg-white/[0.03]" key={channel.id}>
                    <span className="flex size-8 items-center justify-center overflow-hidden rounded-lg border border-white/8 bg-white/[0.04] p-1.5">
                      {channelLogos[channel.adapterId] ? <Image alt="" className="size-full object-contain" height={24} src={channelLogos[channel.adapterId]} width={24} /> : <span className="text-xs font-bold text-zinc-200">{channel.name.slice(0, 1).toUpperCase()}</span>}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-zinc-100">{channel.name}</p>
                      <p className="text-[11px] text-zinc-500">{channel.adapterId}</p>
                    </div>
                    <span className={cn("size-2 rounded-full", channel.connected ? "bg-emerald-400" : "bg-amber-400")} title={channel.status} />
                  </div>
                ))}
              </div>
            ) : (
              <EmptyPanel action="Connect a channel" description="No publishing channel is connected yet." onAction={() => onNavigate("integrations")} />
            )}
          </CardContent>
        </Card>

        <Card className="business-panel">
          <CardHeader className="flex-row items-center justify-between border-b border-white/7">
            <CardTitle>Upcoming posts</CardTitle>
            <Button onClick={() => onNavigate("calendar")} size="sm" variant="ghost">View calendar</Button>
          </CardHeader>
          <CardContent className="p-3">
            {summary.upcoming.length ? (
              <div className="space-y-2">
                {summary.upcoming.map((post) => (
                  <button className="flex min-h-14 w-full items-center gap-3 rounded-xl border border-white/6 bg-white/[0.025] p-2.5 text-left transition-colors hover:bg-white/[0.05]" key={post.id} onClick={() => onNavigate("calendar")} type="button">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-fuchsia-500/10 text-fuchsia-300"><Clock3 className="size-4" /></span>
                    <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium text-zinc-100">{post.title}</span><span className="mt-1 block text-[11px] text-zinc-500">{formatDateTime(post.publishAt)}</span></span>
                    <span className="text-[11px] text-zinc-400">{post.channel}</span>
                  </button>
                ))}
              </div>
            ) : (
              <EmptyPanel action="Open automations" description="No upcoming posts are scheduled." onAction={() => onNavigate("automations")} />
            )}
          </CardContent>
        </Card>
      </section>

      <section className="grid gap-4 xl:grid-cols-[0.85fr_1.15fr_0.8fr]">
        <Card className="business-panel">
          <CardHeader className="flex-row items-center justify-between border-b border-white/7">
            <CardTitle>Approvals pending</CardTitle>
            <Button onClick={() => onNavigate("queue")} size="sm" variant="ghost">View all</Button>
          </CardHeader>
          <CardContent className="p-4">
            {summary.metrics.approvalsPending ? (
              <button className="flex min-h-24 w-full items-center justify-between rounded-xl border border-fuchsia-400/15 bg-fuchsia-400/[0.05] p-4 text-left" onClick={() => onNavigate("queue")} type="button">
                <span><span className="block text-3xl font-semibold tabular-nums text-white">{summary.metrics.approvalsPending}</span><span className="mt-1 block text-sm text-zinc-400">content items awaiting review</span></span>
                <Inbox className="size-6 text-fuchsia-300" />
              </button>
            ) : (
              <EmptyPanel description="Every current content revision has been reviewed." />
            )}
          </CardContent>
        </Card>

        <Card className="business-panel">
          <CardHeader className="flex-row items-center justify-between border-b border-white/7">
            <div><CardTitle>Content calendar</CardTitle><p className="mt-1 text-sm text-zinc-500">{currentMonth}</p></div>
            <Button onClick={() => onNavigate("calendar")} size="sm" variant="ghost">Open calendar</Button>
          </CardHeader>
          <CardContent className="grid grid-cols-7 gap-1 p-4 text-center">
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((day) => <div className="py-1 text-[11px] font-medium text-zinc-600" key={day}>{day}</div>)}
            {calendarCells.map((day, index) => {
              const active = day === today.getDate();
              return <div className={cn("flex aspect-square items-center justify-center rounded-lg text-xs tabular-nums", day > 0 && day <= daysInMonth ? "text-zinc-300" : "text-zinc-800", active && "border border-fuchsia-400 bg-fuchsia-400/10 text-fuchsia-100")} key={index}>{day > 0 && day <= daysInMonth ? day : ""}</div>;
            })}
          </CardContent>
        </Card>

        <Card className="business-panel">
          <CardHeader className="border-b border-white/7"><CardTitle>AI status</CardTitle></CardHeader>
          <CardContent className="space-y-3 p-4">
            <div className="rounded-xl border border-white/8 bg-white/[0.025] p-4">
              <div className="flex items-center justify-between gap-3"><span className="flex items-center gap-2 text-sm font-medium text-zinc-100">{summary.ai.local ? <Bot className="size-4 text-fuchsia-300" /> : <Cloud className="size-4 text-orange-300" />}{summary.ai.local ? "Local AI" : "Cloud AI"}</span><Badge className={summary.ai.configured ? "border-emerald-400/20 text-emerald-300" : "border-amber-400/20 text-amber-300"} variant="outline">{summary.ai.configured ? "Online" : "Setup"}</Badge></div>
              <p className="mt-3 truncate text-xs text-zinc-400" title={summary.ai.model}>{summary.ai.model || "No model selected"}</p>
              <p className="mt-2 text-[11px] leading-5 text-zinc-600">Usage telemetry appears only when the provider reports real values.</p>
            </div>
            <Button className="w-full" onClick={() => onNavigate("ai-settings")} variant="outline"><Sparkles /> AI settings</Button>
          </CardContent>
        </Card>
      </section>

      <Card className="business-panel">
        <CardHeader className="flex-row items-center justify-between border-b border-white/7">
          <CardTitle>Recent activity</CardTitle>
          <Button onClick={() => onNavigate("activity")} size="sm" variant="ghost">View all activity</Button>
        </CardHeader>
        <CardContent className="grid gap-2 p-3 md:grid-cols-2 xl:grid-cols-4">
          {summary.recentActivity.length ? summary.recentActivity.slice(0, 4).map((event) => (
            <button className="min-h-24 rounded-xl border border-white/6 bg-white/[0.02] p-3 text-left transition-colors hover:bg-white/[0.045]" key={event.id} onClick={() => onNavigate("activity")} type="button">
              <RadioTower className="mb-3 size-4 text-fuchsia-300" />
              <span className="line-clamp-2 block text-sm leading-5 text-zinc-200">{event.summary}</span>
              <time className="mt-2 block text-[11px] text-zinc-600" dateTime={event.createdAt}>{formatDateTime(event.createdAt)}</time>
            </button>
          )) : <div className="md:col-span-2 xl:col-span-4"><EmptyPanel description="Configuration and workflow activity will be recorded locally." /></div>}
        </CardContent>
      </Card>
    </div>
  );
}
