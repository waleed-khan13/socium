"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import {
  BookOpenCheck,
  Check,
  ExternalLink,
  Globe2,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { requestJson } from "@/lib/api";
import type { KnowledgeItem, KnowledgeState } from "@/lib/app-types";
import { cn } from "@/lib/utils";

type KnowledgeResponse = { ok: boolean } & KnowledgeState;

function readableValue(value: string) {
  try {
    const parsed = JSON.parse(value) as unknown;
    if (Array.isArray(parsed)) return parsed.join(", ");
    if (typeof parsed === "object" && parsed) return JSON.stringify(parsed);
    return String(parsed);
  } catch {
    return value;
  }
}

export function KnowledgeWorkspace() {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState("");
  const [search, setSearch] = useState("");
  const [sourceToDelete, setSourceToDelete] = useState<{ id: string; label: string } | null>(null);
  const query = useQuery({
    queryKey: ["knowledge", search],
    queryFn: () => requestJson<KnowledgeResponse>(`/api/workspaces/1/knowledge${search.trim() ? `?query=${encodeURIComponent(search.trim())}` : ""}`),
  });
  const analyze = useMutation({
    mutationFn: () => requestJson<{ ok: boolean; knowledge: KnowledgeState }>("/api/workspaces/1/knowledge/analyze", {
      method: "POST",
      body: JSON.stringify({ url, workspaceId: 1 }),
    }),
    onSuccess: async () => {
      toast.success("Website facts are ready for review.");
      await queryClient.invalidateQueries({ queryKey: ["knowledge"] });
      await queryClient.invalidateQueries({ queryKey: ["business-os-dashboard"] });
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Website analysis failed."),
  });
  const review = useMutation({
    mutationFn: ({ id, status }: { id: string; status: "confirmed" | "rejected" }) => requestJson(`/api/workspaces/1/knowledge/items/${id}`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
    onSuccess: async (_, variables) => {
      toast.success(variables.status === "confirmed" ? "Fact added to trusted business context." : "Suggestion rejected.");
      await queryClient.invalidateQueries({ queryKey: ["knowledge"] });
      await queryClient.invalidateQueries({ queryKey: ["business-os-dashboard"] });
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not review that fact."),
  });
  const removeSource = useMutation({
    mutationFn: (id: string) => requestJson(`/api/workspaces/1/knowledge/sources/${id}`, { method: "DELETE" }),
    onSuccess: async () => {
      setSourceToDelete(null);
      toast.success("Knowledge source removed.");
      await queryClient.invalidateQueries({ queryKey: ["knowledge"] });
    },
    onError: (error) => toast.error(error instanceof Error ? error.message : "Could not remove source."),
  });

  const columns = useMemo<ColumnDef<KnowledgeItem>[]>(
    () => [
      {
        accessorKey: "factKey",
        header: "Business fact",
        cell: ({ row }) => <span className="font-medium text-zinc-100">{row.original.factKey.replace(/([A-Z])/g, " $1").trim()}</span>,
      },
      {
        accessorKey: "value",
        header: "Extracted value",
        cell: ({ row }) => <p className="max-w-xl whitespace-normal text-sm leading-6 text-zinc-300">{readableValue(row.original.value)}</p>,
      },
      {
        accessorKey: "confidence",
        header: "Confidence",
        cell: ({ row }) => <span className="tabular-nums text-zinc-300">{row.original.confidence}%</span>,
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ row }) => (
          <Badge className={cn(
            "capitalize",
            row.original.status === "confirmed" && "border-emerald-400/20 text-emerald-300",
            row.original.status === "proposed" && "border-amber-400/20 text-amber-300",
            row.original.status === "stale" && "border-orange-400/20 text-orange-300",
            row.original.status === "rejected" && "border-zinc-700 text-zinc-400",
          )} variant="outline">{row.original.status}</Badge>
        ),
      },
      {
        id: "actions",
        header: "Review",
        cell: ({ row }) => row.original.status === "confirmed" || row.original.status === "rejected" ? null : (
          <div className="flex items-center gap-1">
            <Button aria-label={`Confirm ${row.original.factKey}`} disabled={review.isPending} onClick={() => review.mutate({ id: row.original.id, status: "confirmed" })} size="icon-sm" title="Confirm fact" variant="outline"><Check /></Button>
            <Button aria-label={`Reject ${row.original.factKey}`} disabled={review.isPending} onClick={() => review.mutate({ id: row.original.id, status: "rejected" })} size="icon-sm" title="Reject suggestion" variant="ghost"><X /></Button>
          </div>
        ),
      },
    ],
    [review],
  );
  // TanStack Table intentionally returns mutable table helpers; React Compiler skips this hook.
  // eslint-disable-next-line react-hooks/incompatible-library
  const table = useReactTable({ data: query.data?.items ?? [], columns, getCoreRowModel: getCoreRowModel() });

  return (
    <div className="space-y-4">
      <Card className="business-panel overflow-hidden">
        <CardHeader className="border-b border-white/7">
          <div className="flex items-start gap-3">
            <div className="flex size-11 items-center justify-center rounded-xl border border-fuchsia-400/20 bg-fuchsia-400/8 text-fuchsia-300"><BookOpenCheck className="size-5" /></div>
            <div><CardTitle>Understand my business</CardTitle><CardDescription>Socium extracts proposals; only facts you confirm become trusted AI context.</CardDescription></div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4 p-4 md:p-5">
          <div className="grid gap-3 lg:grid-cols-[1fr_auto] lg:items-end">
            <div className="space-y-2">
              <Label htmlFor="knowledge-url">Business website</Label>
              <div className="relative"><Globe2 className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-zinc-500" /><Input id="knowledge-url" onChange={(event) => setUrl(event.target.value)} placeholder="https://your-business.com" type="url" value={url} className="pl-10" /></div>
            </div>
            <Button className="socium-gradient-button min-h-11" disabled={analyze.isPending || !url.trim()} onClick={() => analyze.mutate()}>
              {analyze.isPending ? <Loader2 className="animate-spin" /> : <RefreshCw />} {analyze.isPending ? "Analyzing…" : "Analyze website"}
            </Button>
          </div>
          <div className="flex items-start gap-3 rounded-xl border border-emerald-400/15 bg-emerald-400/[0.04] p-3 text-sm leading-6 text-emerald-100">
            <ShieldCheck className="mt-0.5 size-4 shrink-0 text-emerald-300" />
            Public pages are crawled safely. Website content remains untrusted until you review each extracted fact.
          </div>
        </CardContent>
      </Card>

      <section className="grid gap-3 sm:grid-cols-3" aria-label="Knowledge summary">
        {[{ label: "Sources", value: query.data?.sources.length ?? 0 }, { label: "Confirmed facts", value: query.data?.summary.confirmed ?? 0 }, { label: "Needs review", value: query.data?.summary.needsReview ?? 0 }].map((item) => <Card className="business-metric-card" key={item.label}><CardContent className="p-4"><p className="text-sm text-zinc-400">{item.label}</p><p className="mt-2 text-2xl font-semibold tabular-nums text-white">{item.value}</p></CardContent></Card>)}
      </section>

      <Card className="business-panel">
        <CardHeader className="flex-row items-center justify-between gap-4 border-b border-white/7">
          <div><CardTitle>Knowledge sources</CardTitle><CardDescription>Trace every fact back to where it came from.</CardDescription></div>
        </CardHeader>
        <CardContent className="p-3">
          {query.data?.sources.length ? <div className="space-y-2">{query.data.sources.map((source) => <div className="flex min-h-14 items-center gap-3 rounded-xl border border-white/6 bg-white/[0.02] p-3" key={source.id}><Globe2 className="size-4 shrink-0 text-fuchsia-300" /><div className="min-w-0 flex-1"><p className="truncate text-sm font-medium text-zinc-100">{source.title || source.locator}</p><a className="mt-1 flex items-center gap-1 truncate text-xs text-zinc-500 hover:text-zinc-300" href={source.locator} rel="noreferrer" target="_blank">{source.locator}<ExternalLink className="size-3" /></a></div><Badge variant="outline">{source.status}</Badge><Button aria-label={`Delete ${source.title || source.locator}`} disabled={removeSource.isPending} onClick={() => setSourceToDelete({ id: source.id, label: source.title || source.locator })} size="icon-sm" title="Delete source" variant="ghost"><Trash2 /></Button></div>)}</div> : <p className="p-8 text-center text-sm text-zinc-500">No knowledge sources yet. Analyze your business website above.</p>}
        </CardContent>
      </Card>

      <Card className="business-panel overflow-hidden">
        <CardHeader className="gap-4 border-b border-white/7 md:flex-row md:items-center md:justify-between">
          <div><CardTitle>Business facts</CardTitle><CardDescription>Review suggestions before Socium can use them.</CardDescription></div>
          <div className="relative w-full md:max-w-xs"><Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-zinc-500" /><Input aria-label="Search business facts" onChange={(event) => setSearch(event.target.value)} placeholder="Search facts" value={search} className="pl-10" /></div>
        </CardHeader>
        <CardContent className="p-0">
          {query.isPending ? <div className="flex min-h-48 items-center justify-center text-sm text-zinc-400"><Loader2 className="mr-2 size-4 animate-spin" />Loading knowledge…</div> : query.isError ? <div className="p-8 text-center text-sm text-red-300">{query.error instanceof Error ? query.error.message : "Knowledge could not be loaded."}</div> : query.data?.items.length ? (
            <div className="overflow-x-auto"><Table><TableHeader>{table.getHeaderGroups().map((headerGroup) => <TableRow key={headerGroup.id}>{headerGroup.headers.map((header) => <TableHead key={header.id}>{header.isPlaceholder ? null : flexRender(header.column.columnDef.header, header.getContext())}</TableHead>)}</TableRow>)}</TableHeader><TableBody>{table.getRowModel().rows.map((row) => <TableRow key={row.id}>{row.getVisibleCells().map((cell) => <TableCell key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</TableCell>)}</TableRow>)}</TableBody></Table></div>
          ) : <p className="p-10 text-center text-sm text-zinc-500">No facts match this view.</p>}
        </CardContent>
      </Card>

      <Dialog onOpenChange={(open) => { if (!open) setSourceToDelete(null); }} open={Boolean(sourceToDelete)}>
        <DialogContent>
          <DialogHeader><DialogTitle>Remove knowledge source?</DialogTitle><DialogDescription>This removes {sourceToDelete?.label} and its extracted facts from Socium. This cannot be undone.</DialogDescription></DialogHeader>
          <DialogFooter><Button disabled={removeSource.isPending} onClick={() => setSourceToDelete(null)} variant="outline">Cancel</Button><Button disabled={removeSource.isPending || !sourceToDelete} onClick={() => sourceToDelete && removeSource.mutate(sourceToDelete.id)} variant="destructive">{removeSource.isPending ? <Loader2 className="animate-spin" /> : <Trash2 />} Remove source</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
