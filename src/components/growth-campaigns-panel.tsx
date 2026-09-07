"use client";

import {
  Building2,
  CirclePause,
  ContactRound,
  Loader2,
  MailCheck,
  Megaphone,
  Play,
  ShieldCheck,
  UserRoundX,
  type LucideIcon,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
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
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { requestJson } from "@/lib/api";
import type { GrowthState, Lead, LeadCampaign, LeadCampaignStatus } from "@/lib/app-types";
import { cn } from "@/lib/utils";

const emptyGrowth: GrowthState = {
  companies: [],
  contacts: [],
  campaigns: [],
  summary: { companies: 0, contacts: 0, campaigns: 0, activeCampaigns: 0 },
};

const statusStyle: Record<LeadCampaignStatus, string> = {
  draft: "border-zinc-700 bg-zinc-900 text-zinc-300",
  active: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
  paused: "border-amber-500/30 bg-amber-500/10 text-amber-300",
  archived: "border-zinc-800 bg-black text-zinc-500",
};

export function GrowthCampaignsPanel({ leads }: { leads: Lead[] }) {
  const [growth, setGrowth] = useState<GrowthState>(emptyGrowth);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("First-touch campaign");
  const [objective, setObjective] = useState("Start a useful, relevant conversation");
  const [tone, setTone] = useState("Clear, relevant, and respectful");
  const [subject, setSubject] = useState("A practical idea for {{business_name}}");
  const [body, setBody] = useState("Hello,\n\nI noticed {{business_name}} and wanted to share one relevant idea.\n\nBest regards");
  const [followUp, setFollowUp] = useState(false);
  const [followUpDays, setFollowUpDays] = useState("4");
  const [followUpBody, setFollowUpBody] = useState("Hello,\n\nFollowing up in case this is useful for {{business_name}}.\n\nBest regards");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const loadGrowth = useCallback(async () => {
    setLoading(true);
    try {
      setGrowth(await requestJson<GrowthState>("/api/growth", { cache: "no-store" }));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not load the growth workspace.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadGrowth(), 0);
    return () => window.clearTimeout(timer);
  }, [loadGrowth, leads]);

  const readyLeads = useMemo(() => leads.filter((lead) => lead.outreachReady && !lead.suppressed), [leads]);
  const metricCards: Array<{ label: string; value: number; icon: LucideIcon }> = [
    { label: "Companies", value: growth.summary.companies, icon: Building2 },
    { label: "Contacts", value: growth.summary.contacts, icon: ContactRound },
    { label: "Campaigns", value: growth.summary.campaigns, icon: Megaphone },
    { label: "Active", value: growth.summary.activeCampaigns, icon: Play },
  ];

  function toggleLead(id: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    if (selected.size === 0) return;
    setBusy("create");
    try {
      const steps = [{ waitDays: 0, subjectTemplate: subject, bodyTemplate: body }];
      if (followUp) {
        steps.push({
          waitDays: Number(followUpDays),
          subjectTemplate: `Re: ${subject}`,
          bodyTemplate: followUpBody,
        });
      }
      await requestJson("/api/growth/campaigns", {
        method: "POST",
        body: JSON.stringify({
          name,
          objective,
          tone,
          leadIds: [...selected],
          steps,
          stopOnReply: true,
          stopOnConsentChange: true,
        }),
      });
      setCreateOpen(false);
      setSelected(new Set());
      await loadGrowth();
      toast.success("Campaign saved as a draft", { description: "Nothing was sent. Activate it when you are ready to prepare approval drafts." });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not create the campaign.");
    } finally {
      setBusy(null);
    }
  }

  async function setStatus(campaign: LeadCampaign, status: Exclude<LeadCampaignStatus, "draft">) {
    setBusy(`${status}-${campaign.id}`);
    try {
      await requestJson(`/api/growth/campaigns/${campaign.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      await loadGrowth();
      toast.success(status === "active" ? "Approval drafts prepared" : `Campaign ${status}`, {
        description: status === "active" ? "Review each draft before any delivery." : undefined,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update the campaign.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card>
      <CardHeader className="border-b border-zinc-900">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle aria-level={2} className="flex items-center gap-2 text-base" role="heading"><Megaphone className="size-4 text-rose-400" />Growth workspace</CardTitle>
            <CardDescription className="mt-1 text-sm">Companies, people, and permission-aware campaigns stored locally.</CardDescription>
          </div>
          <Button disabled={readyLeads.length === 0} onClick={() => setCreateOpen(true)}><Megaphone />New campaign</Button>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2 lg:grid-cols-4">
          {metricCards.map(({ label, value, icon: Icon }) => (
            <div className="rounded-lg border border-zinc-800 bg-black p-3" key={label}>
              <div className="flex items-center justify-between text-zinc-500"><span className="text-sm">{label}</span><Icon className="size-4" /></div>
              <p className="mt-2 text-xl font-semibold text-zinc-100 tabular-nums">{value}</p>
            </div>
          ))}
        </div>
      </CardHeader>
      <CardContent className="p-4 sm:p-5">
        {loading ? <div className="grid min-h-32 place-items-center"><Loader2 className="size-5 animate-spin text-zinc-500" /></div> : (
          <Tabs defaultValue="campaigns">
            <TabsList className="h-10 w-full justify-start overflow-x-auto border border-zinc-800 bg-black p-1 sm:w-fit">
              <TabsTrigger className="px-4" value="campaigns">Campaigns</TabsTrigger>
              <TabsTrigger className="px-4" value="companies">Companies</TabsTrigger>
              <TabsTrigger className="px-4" value="contacts">Contacts</TabsTrigger>
            </TabsList>

            <TabsContent className="mt-4 space-y-3" value="campaigns">
              {growth.campaigns.length === 0 ? (
                <Empty icon={Megaphone} title="No campaigns yet" detail="Select compliant contacts and create a review-gated sequence." />
              ) : growth.campaigns.map((campaign) => (
                <div className="rounded-lg border border-zinc-800 bg-black p-4" key={campaign.id}>
                  <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="font-medium text-zinc-100">{campaign.name}</p>
                        <Badge className={cn("capitalize", statusStyle[campaign.status])} variant="outline">{campaign.status}</Badge>
                        <Badge className="border-emerald-500/25 bg-emerald-500/8 text-emerald-300" variant="outline"><ShieldCheck className="size-3" />Approval required</Badge>
                      </div>
                      <p className="mt-2 text-sm leading-6 text-zinc-400">{campaign.objective}</p>
                      <p className="mt-2 text-sm text-zinc-500">{campaign.members.length} contacts · {campaign.steps.length} step{campaign.steps.length === 1 ? "" : "s"} · stops on reply</p>
                    </div>
                    <div className="flex gap-2">
                      {campaign.status !== "active" && campaign.status !== "archived" ? <Button disabled={Boolean(busy)} onClick={() => void setStatus(campaign, "active")} size="sm"><Play />Prepare drafts</Button> : null}
                      {campaign.status === "active" ? <Button disabled={Boolean(busy)} onClick={() => void setStatus(campaign, "paused")} size="sm" variant="outline"><CirclePause />Pause</Button> : null}
                    </div>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    {Object.entries(campaign.memberCounts).map(([status, count]) => <Badge className="capitalize" key={status} variant="outline">{status.replace("_", " ")}: {count}</Badge>)}
                  </div>
                </div>
              ))}
            </TabsContent>

            <TabsContent className="mt-4" value="companies">
              {growth.companies.length === 0 ? <Empty icon={Building2} title="No companies yet" detail="Import leads to build normalized company records." /> : (
                <Table>
                  <TableHeader><TableRow><TableHead>Company</TableHead><TableHead>Domain</TableHead><TableHead>Location</TableHead><TableHead className="text-right">Contacts</TableHead></TableRow></TableHeader>
                  <TableBody>{growth.companies.map((company) => <TableRow key={company.id}><TableCell className="font-medium text-zinc-200">{company.name || "Unnamed company"}</TableCell><TableCell>{company.domain || "—"}</TableCell><TableCell>{company.location || "—"}</TableCell><TableCell className="text-right tabular-nums">{company.contactCount}</TableCell></TableRow>)}</TableBody>
                </Table>
              )}
            </TabsContent>

            <TabsContent className="mt-4" value="contacts">
              {growth.contacts.length === 0 ? <Empty icon={ContactRound} title="No contacts yet" detail="Lead imports become normalized contacts automatically." /> : (
                <Table>
                  <TableHeader><TableRow><TableHead>Contact</TableHead><TableHead>Company</TableHead><TableHead>Consent</TableHead><TableHead>Status</TableHead></TableRow></TableHeader>
                  <TableBody>{growth.contacts.map((contact) => <TableRow key={contact.id}><TableCell><p className="font-medium text-zinc-200">{contact.fullName || contact.email || "Unnamed contact"}</p>{contact.email && contact.fullName ? <p className="text-sm text-zinc-500">{contact.email}</p> : null}</TableCell><TableCell>{contact.companyName || "—"}</TableCell><TableCell className="capitalize">{contact.consentStatus.replace("_", " ")}</TableCell><TableCell>{contact.suppressed ? <Badge className="border-red-500/25 text-red-300" variant="outline"><UserRoundX className="size-3" />Suppressed</Badge> : <Badge className="capitalize" variant="outline">{contact.status}</Badge>}</TableCell></TableRow>)}</TableBody>
                </Table>
              )}
            </TabsContent>
          </Tabs>
        )}
      </CardContent>

      <Dialog onOpenChange={setCreateOpen} open={createOpen}>
        <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl">
          <form onSubmit={create}>
            <DialogHeader><DialogTitle>Create lead campaign</DialogTitle><DialogDescription>Build a local sequence. Activation only prepares drafts for human review; it never sends automatically.</DialogDescription></DialogHeader>
            <div className="my-5 space-y-5">
              <div className="grid gap-4 sm:grid-cols-2"><Field htmlFor="campaign-name" label="Campaign name"><Input id="campaign-name" maxLength={160} onChange={(event) => setName(event.target.value)} required value={name} /></Field><Field htmlFor="campaign-tone" label="Tone"><Input id="campaign-tone" maxLength={160} onChange={(event) => setTone(event.target.value)} required value={tone} /></Field></div>
              <Field htmlFor="campaign-objective" label="Objective"><Input id="campaign-objective" maxLength={500} onChange={(event) => setObjective(event.target.value)} required value={objective} /></Field>
              <div className="space-y-2"><Label>Eligible contacts</Label><div className="max-h-44 divide-y divide-zinc-900 overflow-y-auto rounded-lg border border-zinc-800 bg-black">{readyLeads.map((lead) => <label className="flex min-h-12 cursor-pointer items-center gap-3 px-3 py-2 text-sm hover:bg-zinc-950" key={lead.id}><input checked={selected.has(lead.id)} className="size-4 accent-rose-500" onChange={() => toggleLead(lead.id)} type="checkbox" /><span className="min-w-0"><span className="block truncate text-zinc-200">{lead.businessName || lead.email}</span><span className="block truncate text-zinc-500">{lead.email}</span></span></label>)}</div><p className="text-sm text-zinc-500">Only contacts that currently pass consent, legal-basis, suppression, and retention checks appear here.</p></div>
              <div className="rounded-lg border border-zinc-800 bg-[#070707] p-4"><p className="mb-4 font-medium text-zinc-200">Step 1 · First email</p><div className="space-y-4"><Field htmlFor="campaign-subject" label="Subject"><Input id="campaign-subject" maxLength={200} onChange={(event) => setSubject(event.target.value)} required value={subject} /></Field><Field htmlFor="campaign-message" label="Message"><Textarea className="min-h-32" id="campaign-message" maxLength={12000} onChange={(event) => setBody(event.target.value)} required value={body} /></Field></div></div>
              <div className="rounded-lg border border-zinc-800 bg-[#070707] p-4"><div className="flex items-center justify-between gap-4"><div><p className="font-medium text-zinc-200">Add one follow-up</p><p className="mt-1 text-sm text-zinc-500">It will stop automatically if Gmail receives a reply.</p></div><Switch aria-label="Add one follow-up" checked={followUp} onCheckedChange={setFollowUp} /></div>{followUp ? <div className="mt-4 grid gap-4 sm:grid-cols-[120px_1fr]"><Field htmlFor="campaign-follow-up-days" label="Wait days"><Input id="campaign-follow-up-days" max={365} min={1} onChange={(event) => setFollowUpDays(event.target.value)} required type="number" value={followUpDays} /></Field><Field htmlFor="campaign-follow-up-message" label="Follow-up message"><Textarea className="min-h-28" id="campaign-follow-up-message" maxLength={12000} onChange={(event) => setFollowUpBody(event.target.value)} required value={followUpBody} /></Field></div> : null}</div>
              <div className="flex gap-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4 text-sm leading-6 text-emerald-200"><MailCheck className="mt-1 size-4 shrink-0" /><p>Every prepared message remains a draft until you approve its exact revision. Consent changes, suppression, retention expiry, and Gmail replies stop delivery.</p></div>
            </div>
            <DialogFooter><Button onClick={() => setCreateOpen(false)} type="button" variant="outline">Cancel</Button><Button disabled={selected.size === 0 || busy === "create"} type="submit">{busy === "create" ? <Loader2 className="animate-spin" /> : <Megaphone />}Create draft campaign</Button></DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function Field({ htmlFor, label, children }: { htmlFor: string; label: string; children: React.ReactNode }) {
  return <div className="space-y-2"><Label htmlFor={htmlFor}>{label}</Label>{children}</div>;
}

function Empty({ icon: Icon, title, detail }: { icon: LucideIcon; title: string; detail: string }) {
  return <div className="grid min-h-40 place-items-center rounded-lg border border-dashed border-zinc-800 bg-black p-6 text-center"><div><Icon className="mx-auto size-5 text-zinc-600" /><p className="mt-3 font-medium text-zinc-300">{title}</p><p className="mt-1 text-sm text-zinc-500">{detail}</p></div></div>;
}
