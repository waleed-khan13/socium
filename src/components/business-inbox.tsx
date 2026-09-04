"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowUpRight, CheckCircle2, Inbox, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { requestJson } from "@/lib/api";
import type { BusinessInboxItem } from "@/lib/app-types";
import { cn } from "@/lib/utils";

type InboxResponse = { ok: boolean; items: BusinessInboxItem[] };

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function BusinessInbox({ onNavigate }: { onNavigate: (view: string) => void }) {
  const query = useQuery({
    queryKey: ["business-inbox"],
    queryFn: () => requestJson<InboxResponse>("/api/inbox"),
    refetchInterval: 20_000,
  });

  return (
    <Card className="business-panel overflow-hidden">
      <CardHeader className="border-b border-white/7">
        <div className="flex items-start gap-3">
          <div className="flex size-11 items-center justify-center rounded-xl border border-fuchsia-400/20 bg-fuchsia-400/8 text-fuchsia-300"><Inbox className="size-5" /></div>
          <div><CardTitle>What needs attention</CardTitle><CardDescription>Approvals, failures, missed schedules and knowledge review in one local inbox.</CardDescription></div>
        </div>
      </CardHeader>
      <CardContent className="p-3 md:p-4">
        {query.isPending ? <div className="flex min-h-64 items-center justify-center text-sm text-zinc-400"><Loader2 className="mr-2 size-4 animate-spin" />Loading inbox…</div> : query.isError ? <div className="flex min-h-64 flex-col items-center justify-center text-center"><AlertTriangle className="mb-3 size-6 text-red-300" /><p className="text-sm text-red-200">{query.error instanceof Error ? query.error.message : "Inbox could not be loaded."}</p><Button className="mt-4" onClick={() => void query.refetch()} variant="outline">Try again</Button></div> : query.data?.items.length ? (
          <div className="space-y-2">
            {query.data.items.map((item) => (
              <button className="flex min-h-20 w-full items-start gap-4 rounded-xl border border-white/7 bg-white/[0.02] p-4 text-left transition-colors hover:bg-white/[0.045] focus-visible:ring-2 focus-visible:ring-fuchsia-300" key={item.id} onClick={() => onNavigate(item.actionUrl?.includes("calendar") ? "calendar" : item.entityType === "post" || item.kind === "approval" ? "queue" : "activity")} type="button">
                <span className={cn("mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg", item.priority === "high" || item.priority === "urgent" ? "bg-orange-400/10 text-orange-300" : "bg-fuchsia-400/10 text-fuchsia-300")}>{item.priority === "high" || item.priority === "urgent" ? <AlertTriangle className="size-4" /> : <Inbox className="size-4" />}</span>
                <span className="min-w-0 flex-1"><span className="flex flex-wrap items-center gap-2"><span className="font-medium text-zinc-100">{item.title}</span><Badge className="capitalize" variant="outline">{item.kind.replaceAll("_", " ")}</Badge></span><span className="mt-1 block text-sm leading-6 text-zinc-400">{item.body}</span><time className="mt-2 block text-xs text-zinc-600" dateTime={item.createdAt}>{formatDate(item.createdAt)}</time></span>
                <ArrowUpRight className="mt-2 size-4 shrink-0 text-zinc-500" />
              </button>
            ))}
          </div>
        ) : <div className="flex min-h-72 flex-col items-center justify-center text-center"><span className="flex size-12 items-center justify-center rounded-full border border-emerald-400/20 bg-emerald-400/8 text-emerald-300"><CheckCircle2 className="size-6" /></span><h3 className="mt-4 text-base font-semibold text-zinc-100">You&apos;re all caught up</h3><p className="mt-2 max-w-sm text-sm leading-6 text-zinc-500">Socium will place approvals, workflow failures and knowledge changes here when they need you.</p></div>}
      </CardContent>
    </Card>
  );
}
