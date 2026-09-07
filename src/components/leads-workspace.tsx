"use client";

import {
  ExternalLink,
  FileSpreadsheet,
  Globe2,
  Gauge,
  Loader2,
  Mail,
  MailCheck,
  MapPin,
  Phone,
  PencilLine,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  Target,
  Upload,
  UsersRound,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { LeadDiscoveryPanel } from "@/components/lead-discovery-panel";
import { LeadOutreachDialog } from "@/components/lead-outreach-dialog";
import { GrowthCampaignsPanel } from "@/components/growth-campaigns-panel";
import { IcpScoringPanel } from "@/components/icp-scoring-panel";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { requestJson } from "@/lib/api";
import type {
  Lead,
  LeadImportResult,
  LeadListResponse,
  LeadSource,
  LeadStatus,
  PublicAppState,
} from "@/lib/app-types";
import { parseLeadCsv } from "@/lib/csv";
import { cn } from "@/lib/utils";

type LeadFilter = "active" | "high-intent" | "outreach-ready" | "retention-expired" | LeadStatus | "suppressed";
type ImportLeadSource = Exclude<LeadSource, "website-crawl">;

const filters: Array<{ value: LeadFilter; label: string }> = [
  { value: "active", label: "All active" },
  { value: "high-intent", label: "High intent (70+)" },
  { value: "outreach-ready", label: "Outreach-ready" },
  { value: "retention-expired", label: "Retention review due" },
  { value: "new", label: "New" },
  { value: "qualified", label: "Qualified" },
  { value: "contacted", label: "Contacted" },
  { value: "archived", label: "Archived" },
  { value: "suppressed", label: "Suppression list" },
];

const sourceLabels: Record<ImportLeadSource, string> = {
  csv: "Generic CSV",
  "linkedin-export": "LinkedIn export",
  "crm-export": "CRM export",
  manual: "Manual CSV",
};

const statusStyles: Record<LeadStatus, string> = {
  new: "border-zinc-700 bg-zinc-900 text-zinc-300",
  qualified: "border-emerald-500/25 bg-emerald-500/8 text-emerald-300",
  contacted: "border-sky-500/25 bg-sky-500/8 text-sky-300",
  archived: "border-zinc-800 bg-black text-zinc-500",
};

function safeHttpUrl(value: string | null | undefined) {
  if (!value) return null;
  try {
    const url = new URL(value.includes("://") ? value : `https://${value}`);
    return ["http:", "https:"].includes(url.protocol) ? url.toString() : null;
  } catch {
    return null;
  }
}

function LeadStatusBadge({ lead }: { lead: Lead }) {
  if (lead.suppressed) {
    return <Badge className="border-red-500/25 bg-red-500/8 text-red-300" variant="outline">Suppressed</Badge>;
  }
  return <Badge className={cn("capitalize", statusStyles[lead.status])} variant="outline">{lead.status}</Badge>;
}

function scoreBand(score: number | null) {
  if (score === null) return { label: "Unscored", style: "border-zinc-800 bg-black text-zinc-600" };
  if (score >= 70) return { label: "High", style: "border-emerald-500/25 bg-emerald-500/8 text-emerald-300" };
  if (score >= 40) return { label: "Review", style: "border-amber-500/25 bg-amber-500/8 text-amber-300" };
  return { label: "Low", style: "border-red-500/25 bg-red-500/8 text-red-300" };
}

function LeadScoreButton({ lead, onClick }: { lead: Lead; onClick: () => void }) {
  const band = scoreBand(lead.effectiveScore);
  return (
    <button
      aria-label={`Review ${lead.businessName || "lead"} score`}
      className="group inline-flex min-h-9 flex-col justify-center rounded-md text-left outline-none focus-visible:ring-2 focus-visible:ring-zinc-500"
      onClick={onClick}
      type="button"
    >
      <Badge className={cn("gap-1.5 font-mono group-hover:border-zinc-500", band.style)} variant="outline">
        <Gauge className="size-3" />
        {lead.effectiveScore ?? "—"}
        <span className="font-sans text-[9px] tracking-wide uppercase">{band.label}</span>
      </Badge>
      {lead.manualScore !== null ? <span className="mt-1 block text-[9px] text-zinc-600">Human corrected</span> : null}
    </button>
  );
}

function SummaryCard({ icon: Icon, label, value, detail }: { icon: typeof UsersRound; label: string; value: number; detail: string }) {
  return (
    <Card className="min-h-0 justify-between gap-3 py-4" size="sm">
      <CardHeader className="flex-row items-center justify-between px-4 pb-0">
        <p className="text-xs font-medium text-zinc-500">{label}</p>
        <div className="grid size-8 place-items-center rounded-md border border-zinc-800 bg-black text-zinc-500"><Icon className="size-3.5" /></div>
      </CardHeader>
      <CardContent className="px-4">
        <p className="text-2xl font-semibold tracking-[-0.04em] text-zinc-50 tabular-nums">{value}</p>
        <p className="mt-1 text-[11px] text-zinc-600">{detail}</p>
      </CardContent>
    </Card>
  );
}

function LeadContact({ lead }: { lead: Lead }) {
  const website = safeHttpUrl(lead.website);
  return (
    <div className="space-y-1.5 text-[11px] text-zinc-500">
      {lead.email ? <a className="flex items-center gap-2 hover:text-zinc-200" href={`mailto:${lead.email}`}><Mail className="size-3" />{lead.email}</a> : null}
      {lead.phone ? <a className="flex items-center gap-2 hover:text-zinc-200" href={`tel:${lead.phone}`}><Phone className="size-3" />{lead.phone}</a> : null}
      {website ? <a className="flex items-center gap-2 hover:text-zinc-200" href={website} rel="noreferrer" target="_blank"><Globe2 className="size-3" />{lead.website}<ExternalLink className="size-2.5" /></a> : null}
      {!lead.email && !lead.phone && !website ? <span className="text-zinc-700">No contact fields</span> : null}
    </div>
  );
}

export function LeadsWorkspace({
  state,
  onStateChange,
}: {
  state: PublicAppState;
  onStateChange: (state: PublicAppState) => void;
}) {
  const [list, setList] = useState<LeadListResponse>({ items: [], total: 0, limit: 200, offset: 0 });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [filter, setFilter] = useState<LeadFilter>("active");
  const [query, setQuery] = useState("");
  const [csvText, setCsvText] = useState("");
  const [fileName, setFileName] = useState("");
  const [source, setSource] = useState<ImportLeadSource>("csv");
  const [suppressionTarget, setSuppressionTarget] = useState<Lead | null>(null);
  const [suppressionReason, setSuppressionReason] = useState("");
  const [scoreTarget, setScoreTarget] = useState<Lead | null>(null);
  const [scoreValue, setScoreValue] = useState("");
  const [scoreReason, setScoreReason] = useState("");
  const [outreachTarget, setOutreachTarget] = useState<Lead | null>(null);
  const preview = useMemo(() => parseLeadCsv(csvText), [csvText]);

  const loadLeads = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ status: filter, limit: "200", offset: "0" });
      if (query.trim()) params.set("query", query.trim());
      setList(await requestJson<LeadListResponse>(`/api/leads?${params.toString()}`, { cache: "no-store" }));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not load the local lead vault.");
    } finally {
      setLoading(false);
    }
  }, [filter, query]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadLeads(), 250);
    return () => window.clearTimeout(timer);
  }, [loadLeads]);

  async function chooseFile(file: File | undefined) {
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      toast.error("CSV must be smaller than 2 MB.");
      return;
    }
    setFileName(file.name);
    setCsvText(await file.text());
  }

  async function importRows(event: FormEvent) {
    event.preventDefault();
    if (preview.rows.length === 0) return;
    setBusy("import");
    try {
      const response = await requestJson<{ ok: boolean; result: LeadImportResult; state: PublicAppState }>("/api/leads/import", {
        method: "POST",
        body: JSON.stringify({ source, rows: preview.rows }),
      });
      onStateChange(response.state);
      setCsvText("");
      setFileName("");
      setFilter("active");
      await loadLeads();
      toast.success(`${response.result.created} leads added`, {
        description: `${response.result.merged} merged · ${response.result.suppressed} blocked by suppression`,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Lead import failed.");
    } finally {
      setBusy(null);
    }
  }

  async function changeStatus(lead: Lead, status: LeadStatus) {
    setBusy(`status-${lead.id}`);
    try {
      const response = await requestJson<{ ok: boolean; lead: Lead; state: PublicAppState }>(`/api/leads/${lead.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      onStateChange(response.state);
      await loadLeads();
      toast.success(`Lead moved to ${status}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update the lead.");
    } finally {
      setBusy(null);
    }
  }

  async function suppress(event: FormEvent) {
    event.preventDefault();
    if (!suppressionTarget) return;
    setBusy(`suppress-${suppressionTarget.id}`);
    try {
      const response = await requestJson<{ ok: boolean; lead: Lead; state: PublicAppState }>(`/api/leads/${suppressionTarget.id}/suppress`, {
        method: "POST",
        body: JSON.stringify({ reason: suppressionReason }),
      });
      onStateChange(response.state);
      setSuppressionTarget(null);
      setSuppressionReason("");
      await loadLeads();
      toast.success("Lead added to the suppression list");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not suppress the lead.");
    } finally {
      setBusy(null);
    }
  }

  async function restore(lead: Lead) {
    setBusy(`restore-${lead.id}`);
    try {
      const response = await requestJson<{ ok: boolean; lead: Lead; state: PublicAppState }>(`/api/leads/${lead.id}/restore`, { method: "POST" });
      onStateChange(response.state);
      await loadLeads();
      toast.success("Lead restored to the active vault");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not restore the lead.");
    } finally {
      setBusy(null);
    }
  }

  function openScoreCorrection(lead: Lead) {
    setScoreTarget(lead);
    setScoreValue(String(lead.effectiveScore ?? 50));
    setScoreReason(lead.manualScoreReason ?? "");
  }

  async function saveScoreCorrection(event: FormEvent) {
    event.preventDefault();
    if (!scoreTarget) return;
    const score = Number(scoreValue);
    if (!Number.isInteger(score) || score < 0 || score > 100) {
      toast.error("Score must be a whole number from 0 to 100.");
      return;
    }
    setBusy(`score-${scoreTarget.id}`);
    try {
      const response = await requestJson<{ ok: boolean; lead: Lead; state: PublicAppState }>(`/api/leads/${scoreTarget.id}/score-override`, {
        method: "PUT",
        body: JSON.stringify({ score, reason: scoreReason }),
      });
      onStateChange(response.state);
      setScoreTarget(null);
      setScoreReason("");
      await loadLeads();
      toast.success("Human score correction saved");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not correct the score.");
    } finally {
      setBusy(null);
    }
  }

  async function clearScoreCorrection() {
    if (!scoreTarget) return;
    setBusy(`score-${scoreTarget.id}`);
    try {
      const response = await requestJson<{ ok: boolean; lead: Lead; state: PublicAppState }>(`/api/leads/${scoreTarget.id}/score-override`, { method: "DELETE" });
      onStateChange(response.state);
      setScoreTarget(null);
      setScoreReason("");
      await loadLeads();
      toast.success("Deterministic ICP score restored");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not clear the correction.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-5">
        <SummaryCard detail="Stored on this computer" icon={UsersRound} label="Total leads" value={state.leadSummary.total} />
        <SummaryCard detail="ICP score of 70 or higher" icon={Target} label="High intent" value={state.leadSummary.highIntent} />
        <SummaryCard detail="Compliance gate completed" icon={MailCheck} label="Outreach-ready" value={state.leadSummary.outreachReady} />
        <SummaryCard detail="Needs retain or delete review" icon={ShieldAlert} label="Retention due" value={state.leadSummary.retentionExpired} />
        <SummaryCard detail="Never reactivated by import" icon={ShieldCheck} label="Suppressed" value={state.leadSummary.suppressed} />
      </div>

      <IcpScoringPanel
        key={`icp-profile-${state.icpProfile.version}`}
        onRescored={loadLeads}
        onStateChange={onStateChange}
        profile={state.icpProfile}
      />

      <LeadDiscoveryPanel
        onImported={async () => {
          setFilter("active");
          await loadLeads();
        }}
        onStateChange={onStateChange}
        state={state}
      />

      <GrowthCampaignsPanel leads={list.items} />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,0.85fr)_minmax(500px,1.15fr)]">
        <Card>
          <CardHeader className="border-b border-zinc-900">
            <div className="flex items-center gap-3">
              <div className="grid size-10 place-items-center rounded-md border border-zinc-700 bg-black text-zinc-200"><FileSpreadsheet className="size-4" /></div>
              <div>
                <CardTitle>Import lead evidence</CardTitle>
                <CardDescription>CSV, CRM, or an export you are allowed to use.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={importRows}>
              <div className="space-y-2">
                <Label className="text-xs text-zinc-300" htmlFor="lead-source">Data source</Label>
                <Select onValueChange={(value) => value && setSource(value as ImportLeadSource)} value={source}>
                  <SelectTrigger className="h-10 w-full rounded-md border-input bg-[#080808]" id="lead-source"><SelectValue>{sourceLabels[source]}</SelectValue></SelectTrigger>
                  <SelectContent className="border border-zinc-700 bg-[#0c0c0c]">
                    {(Object.entries(sourceLabels) as Array<[ImportLeadSource, string]>).map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>

              <div className="rounded-md border border-dashed border-zinc-700 bg-black p-4 text-center">
                <input accept=".csv,text/csv" className="sr-only" id="lead-csv-file" onChange={(event) => void chooseFile(event.target.files?.[0])} type="file" />
                <Upload className="mx-auto size-5 text-zinc-500" />
                <p className="mt-2 text-xs font-medium text-zinc-300">{fileName || "Choose a CSV file"}</p>
                <p className="mt-1 text-[11px] text-zinc-600">Up to 1,000 rows · 2 MB · processed locally</p>
                <label className={cn(buttonVariants({ size: "sm", variant: "outline" }), "mt-3")} htmlFor="lead-csv-file">Browse file</label>
              </div>

              <div className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <Label className="text-xs text-zinc-300" htmlFor="lead-csv-text">Or paste CSV</Label>
                  <span className="text-[10px] text-zinc-600">company, website, email, phone, location</span>
                </div>
                <Textarea
                  className="min-h-32 font-mono text-[11px]"
                  id="lead-csv-text"
                  onChange={(event) => { setCsvText(event.target.value); setFileName(""); }}
                  placeholder={'company,website,email,phone,location\nAcme Studio,acme.example,hello@acme.example,,Karachi'}
                  value={csvText}
                />
              </div>

              {csvText ? (
                <div className="rounded-md border border-zinc-800 bg-black p-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs font-medium text-zinc-300">Import preview</p>
                    <Badge className="border-zinc-700 bg-zinc-900 text-zinc-300" variant="outline">{preview.rows.length} valid</Badge>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {preview.recognizedFields.map((field) => <Badge className="text-zinc-500" key={field} variant="outline">{field}</Badge>)}
                  </div>
                  {preview.errors.length > 0 ? <p className="mt-3 text-[11px] leading-4 text-amber-300">{preview.errors[0]}{preview.errors.length > 1 ? ` +${preview.errors.length - 1} more` : ""}</p> : null}
                </div>
              ) : null}

              <div className="flex items-center justify-between gap-4 border-t border-zinc-900 pt-4">
                <p className="max-w-xs text-[10px] leading-4 text-zinc-600">Duplicates merge by email, domain, phone, or business + location. Existing values are never silently overwritten.</p>
                <Button disabled={preview.rows.length === 0 || busy === "import"} type="submit">
                  {busy === "import" ? <Loader2 className="animate-spin" /> : <Upload />}
                  {busy === "import" ? "Importing…" : "Import leads"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader className="border-b border-zinc-900">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <CardTitle>Local lead vault</CardTitle>
                  <CardDescription>{list.total} {list.total === 1 ? "record" : "records"} in this view.</CardDescription>
                </div>
                <Button aria-label="Refresh leads" disabled={loading} onClick={() => void loadLeads()} size="icon-sm" variant="ghost"><RefreshCw className={cn(loading && "animate-spin")} /></Button>
              </div>
              <div className="mt-3 grid gap-2 sm:grid-cols-[1fr_170px]">
                <div className="relative">
                  <Search className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-zinc-600" />
                  <Input className="pl-9" maxLength={200} onChange={(event) => setQuery(event.target.value)} placeholder="Search company, email, domain…" value={query} />
                </div>
                <Select onValueChange={(value) => value && setFilter(value as LeadFilter)} value={filter}>
                  <SelectTrigger aria-label="Filter leads" className="h-9 w-full rounded-md border-input bg-[#080808]"><SelectValue>{filters.find((item) => item.value === filter)?.label}</SelectValue></SelectTrigger>
                  <SelectContent className="border border-zinc-700 bg-[#0c0c0c]">{filters.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectContent>
                </Select>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {loading && list.items.length === 0 ? (
                <div className="grid min-h-72 place-items-center text-zinc-600"><Loader2 className="size-5 animate-spin" /></div>
              ) : list.items.length === 0 ? (
                <div className="grid min-h-72 place-items-center px-6 text-center">
                  <div><UsersRound className="mx-auto size-5 text-zinc-600" /><p className="mt-3 text-sm font-medium text-zinc-300">No matching leads</p><p className="mt-1 text-xs text-zinc-600">Import an allowed export or change the current filter.</p></div>
                </div>
              ) : (
                <>
                  <div className="hidden md:block">
                    <Table>
                      <TableHeader><TableRow className="border-zinc-900 hover:bg-transparent"><TableHead className="px-5 text-[10px] tracking-wider text-zinc-600 uppercase">Lead</TableHead><TableHead className="text-[10px] tracking-wider text-zinc-600 uppercase">Contact</TableHead><TableHead className="text-[10px] tracking-wider text-zinc-600 uppercase">ICP score</TableHead><TableHead className="text-[10px] tracking-wider text-zinc-600 uppercase">Evidence</TableHead><TableHead className="pr-5 text-right text-[10px] tracking-wider text-zinc-600 uppercase">Control</TableHead></TableRow></TableHeader>
                      <TableBody>
                        {list.items.map((lead) => (
                          <TableRow className="border-zinc-900 hover:bg-zinc-950" key={lead.id}>
                            <TableCell className="max-w-56 px-5 py-4 whitespace-normal">
                              <p className="truncate text-xs font-medium text-zinc-200">{lead.businessName || lead.email || lead.website || "Unnamed lead"}</p>
                              {lead.location ? <p className="mt-1 flex items-center gap-1.5 truncate text-[11px] text-zinc-600"><MapPin className="size-3" />{lead.location}</p> : null}
                              <div className="mt-2 flex flex-wrap gap-1.5"><LeadStatusBadge lead={lead} />{lead.outreachReady ? <Badge className="border-emerald-500/25 bg-emerald-500/8 text-emerald-300" variant="outline"><MailCheck className="size-3" />Ready</Badge> : null}{lead.retentionExpired ? <Badge className="border-red-500/25 bg-red-500/8 text-red-300" variant="outline">Retention due</Badge> : null}</div>
                            </TableCell>
                            <TableCell className="max-w-64 whitespace-normal"><LeadContact lead={lead} /></TableCell>
                            <TableCell><LeadScoreButton lead={lead} onClick={() => openScoreCorrection(lead)} /></TableCell>
                            <TableCell>
                              <Badge className="border-zinc-800 bg-black text-zinc-500" variant="outline">{lead.sourceLabel}</Badge>
                              <p className="mt-1.5 text-[10px] text-zinc-700">{lead.evidence.length} source record{lead.evidence.length === 1 ? "" : "s"}</p>
                            </TableCell>
                            <TableCell className="pr-5 text-right">
                              {lead.suppressed ? (
                                <div className="inline-flex items-center gap-2"><Button aria-label={`Open data controls for ${lead.businessName || "lead"}`} onClick={() => setOutreachTarget(lead)} size="icon-sm" variant="ghost"><MailCheck /></Button><Button disabled={busy === `restore-${lead.id}`} onClick={() => void restore(lead)} size="sm" variant="outline">{busy === `restore-${lead.id}` ? <Loader2 className="animate-spin" /> : <RefreshCw />}Restore</Button></div>
                              ) : (
                                <div className="inline-flex items-center gap-2">
                                  <Button aria-label={`Open reviewed outreach for ${lead.businessName || "lead"}`} onClick={() => setOutreachTarget(lead)} size="icon-sm" variant="ghost"><MailCheck /></Button>
                                  <Select disabled={busy === `status-${lead.id}`} onValueChange={(value) => value && void changeStatus(lead, value as LeadStatus)} value={lead.status}>
                                    <SelectTrigger aria-label={`Change status for ${lead.businessName || lead.email || "lead"}`} className="h-7 w-28 rounded-md border-zinc-800 bg-black text-[11px]"><SelectValue>{lead.status.charAt(0).toUpperCase() + lead.status.slice(1)}</SelectValue></SelectTrigger>
                                    <SelectContent className="border border-zinc-700 bg-[#0c0c0c]"><SelectItem value="new">New</SelectItem><SelectItem value="qualified">Qualified</SelectItem><SelectItem value="contacted">Contacted</SelectItem><SelectItem value="archived">Archived</SelectItem></SelectContent>
                                  </Select>
                                  <Button aria-label={`Suppress ${lead.businessName || "lead"}`} onClick={() => setSuppressionTarget(lead)} size="icon-sm" variant="ghost"><ShieldAlert /></Button>
                                </div>
                              )}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                  <div className="divide-y divide-zinc-900 md:hidden">
                    {list.items.map((lead) => (
                      <div className="space-y-3 p-4" key={lead.id}>
                        <div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="truncate text-xs font-medium text-zinc-200">{lead.businessName || lead.email || lead.website || "Unnamed lead"}</p>{lead.location ? <p className="mt-1 text-[11px] text-zinc-600">{lead.location}</p> : null}</div><div className="flex flex-wrap justify-end gap-1.5"><LeadStatusBadge lead={lead} />{lead.outreachReady ? <Badge className="border-emerald-500/25 bg-emerald-500/8 text-emerald-300" variant="outline"><MailCheck className="size-3" />Ready</Badge> : null}</div></div>
                        <LeadContact lead={lead} />
                        <div className="flex items-center justify-between gap-3"><span className="text-[10px] tracking-wider text-zinc-700 uppercase">ICP fit</span><LeadScoreButton lead={lead} onClick={() => openScoreCorrection(lead)} /></div>
                        <div className="flex items-center justify-between gap-3"><Badge className="border-zinc-800 bg-black text-zinc-500" variant="outline">{lead.sourceLabel}</Badge><span className="text-[10px] text-zinc-700">{lead.evidence.length} source record{lead.evidence.length === 1 ? "" : "s"}</span></div>
                        <div className="flex items-center justify-between gap-3 border-t border-zinc-900 pt-3">
                          {lead.suppressed ? (
                            <span className="text-[11px] text-zinc-600">Blocked from re-import activation</span>
                          ) : (
                            <Select disabled={busy === `status-${lead.id}`} onValueChange={(value) => value && void changeStatus(lead, value as LeadStatus)} value={lead.status}>
                              <SelectTrigger aria-label={`Change status for ${lead.businessName || lead.email || "lead"}`} className="h-7 w-28 rounded-md border-zinc-800 bg-black text-[11px]"><SelectValue>{lead.status.charAt(0).toUpperCase() + lead.status.slice(1)}</SelectValue></SelectTrigger>
                              <SelectContent className="border border-zinc-700 bg-[#0c0c0c]"><SelectItem value="new">New</SelectItem><SelectItem value="qualified">Qualified</SelectItem><SelectItem value="contacted">Contacted</SelectItem><SelectItem value="archived">Archived</SelectItem></SelectContent>
                            </Select>
                          )}
                          <div className="flex flex-wrap justify-end gap-2"><Button onClick={() => setOutreachTarget(lead)} size="sm" variant="outline"><MailCheck />{lead.suppressed ? "Data controls" : "Outreach"}</Button>{lead.suppressed ? <Button onClick={() => void restore(lead)} size="sm" variant="outline"><RefreshCw />Restore</Button> : <Button onClick={() => setSuppressionTarget(lead)} size="sm" variant="ghost"><ShieldAlert />Suppress</Button>}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          <div className="flex items-start gap-3 rounded-lg border border-zinc-900 bg-[#050505] p-4 text-xs leading-5 text-zinc-500">
            <ShieldCheck className="mt-0.5 size-4 shrink-0 text-zinc-400" />
            <p><span className="font-medium text-zinc-300">Permission-aware by design.</span> LinkedIn pages and Google Maps HTML are never scraped. Google Places results stay transient; only fields independently extracted from robots-allowed public websites enter the local vault.</p>
          </div>
        </div>
      </div>

      <LeadOutreachDialog
        key={outreachTarget?.id ?? "closed-outreach"}
        lead={outreachTarget}
        onChanged={async (changedLead, nextState) => {
          onStateChange(nextState);
          setOutreachTarget(changedLead);
          await loadLeads();
        }}
        onOpenChange={(open) => { if (!open) setOutreachTarget(null); }}
        open={Boolean(outreachTarget)}
        providerConfigured={state.provider.configured}
      />

      <Dialog onOpenChange={(open) => { if (!open) { setSuppressionTarget(null); setSuppressionReason(""); } }} open={Boolean(suppressionTarget)}>
        <DialogContent>
          <form onSubmit={suppress}>
            <DialogHeader><DialogTitle>Add to suppression list?</DialogTitle><DialogDescription>This record will stay blocked during future imports until you explicitly restore it.</DialogDescription></DialogHeader>
            <div className="my-5 space-y-2"><Label htmlFor="suppression-reason">Reason</Label><Textarea id="suppression-reason" maxLength={500} onChange={(event) => setSuppressionReason(event.target.value)} placeholder="Example: Contact opted out" required value={suppressionReason} /></div>
            <DialogFooter><Button onClick={() => setSuppressionTarget(null)} type="button" variant="outline">Cancel</Button><Button disabled={!suppressionReason.trim() || busy?.startsWith("suppress-")} type="submit" variant="destructive">{busy?.startsWith("suppress-") ? <Loader2 className="animate-spin" /> : <ShieldAlert />}Suppress lead</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog onOpenChange={(open) => { if (!open) { setScoreTarget(null); setScoreReason(""); } }} open={Boolean(scoreTarget)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
          {scoreTarget ? (
            <form onSubmit={saveScoreCorrection}>
              <DialogHeader>
                <DialogTitle>Review ICP score</DialogTitle>
                <DialogDescription>
                  {scoreTarget.businessName || scoreTarget.email || "This lead"} has an effective score of {scoreTarget.effectiveScore ?? "not scored"}. Deterministic evidence stays visible after a human correction.
                </DialogDescription>
              </DialogHeader>

              <div className="my-5 space-y-4">
                <div className="flex items-center justify-between rounded-md border border-zinc-800 bg-black p-3">
                  <div>
                    <p className="text-[10px] tracking-wider text-zinc-600 uppercase">Deterministic score</p>
                    <p className="mt-1 font-mono text-2xl text-zinc-100">{scoreTarget.icpScore ?? "—"}<span className="text-xs text-zinc-600"> / 100</span></p>
                  </div>
                  {scoreTarget.manualScore !== null ? <Badge className="border-sky-500/25 bg-sky-500/8 text-sky-300" variant="outline"><PencilLine className="size-3" />Human correction: {scoreTarget.manualScore}</Badge> : <Badge className={scoreBand(scoreTarget.icpScore).style} variant="outline">{scoreBand(scoreTarget.icpScore).label}</Badge>}
                </div>

                <div className="space-y-2">
                  <p className="text-[10px] tracking-wider text-zinc-600 uppercase">Point-by-point explanation</p>
                  {scoreTarget.icpReasons.length > 0 ? (
                    <div className="divide-y divide-zinc-900 overflow-hidden rounded-md border border-zinc-800 bg-black">
                      {scoreTarget.icpReasons.map((reason) => (
                        <div className="grid grid-cols-[48px_1fr] gap-3 px-3 py-2.5" key={reason.code}>
                          <span className={cn("font-mono text-xs tabular-nums", reason.points > 0 ? "text-emerald-400" : reason.points < 0 ? "text-red-300" : "text-zinc-500")}>{reason.points > 0 ? "+" : ""}{reason.points}</span>
                          <div><p className="text-xs font-medium text-zinc-300">{reason.label}</p><p className="mt-0.5 text-[10px] leading-4 text-zinc-600">{reason.detail}</p></div>
                        </div>
                      ))}
                    </div>
                  ) : <p className="rounded-md border border-dashed border-zinc-800 bg-black p-4 text-xs text-zinc-600">Activate an ICP profile to generate the deterministic breakdown.</p>}
                </div>

                <div className="grid gap-4 border-t border-zinc-900 pt-4 sm:grid-cols-[120px_1fr]">
                  <div className="space-y-2">
                    <Label htmlFor="lead-score-correction">Corrected score <span aria-hidden="true" className="text-zinc-500">*</span></Label>
                    <Input id="lead-score-correction" inputMode="numeric" max={100} min={0} onChange={(event) => setScoreValue(event.target.value)} required type="number" value={scoreValue} />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="lead-score-reason">Correction reason <span aria-hidden="true" className="text-zinc-500">*</span></Label>
                    <Textarea id="lead-score-reason" maxLength={500} minLength={3} onChange={(event) => setScoreReason(event.target.value)} placeholder="What verified evidence makes the rule-based score inaccurate?" required value={scoreReason} />
                  </div>
                </div>
                <p className="text-[10px] leading-4 text-zinc-600">Corrections are local, auditable, and never erase the original score or its reasons.</p>
              </div>

              <DialogFooter className="sm:justify-between">
                <div>{scoreTarget.manualScore !== null ? <Button disabled={busy === `score-${scoreTarget.id}`} onClick={() => void clearScoreCorrection()} type="button" variant="ghost"><RefreshCw />Restore rule score</Button> : null}</div>
                <div className="flex gap-2"><Button onClick={() => setScoreTarget(null)} type="button" variant="outline">Cancel</Button><Button disabled={scoreReason.trim().length < 3 || busy === `score-${scoreTarget.id}`} type="submit">{busy === `score-${scoreTarget.id}` ? <Loader2 className="animate-spin" /> : <PencilLine />}Save correction</Button></div>
              </DialogFooter>
            </form>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
