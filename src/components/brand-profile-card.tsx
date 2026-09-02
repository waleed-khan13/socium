"use client";

import {
  AlertTriangle,
  Check,
  Cloud,
  ExternalLink,
  Globe2,
  HardDrive,
  ImagePlus,
  Images,
  Loader2,
  Palette,
  ShieldCheck,
  Trash2,
  Upload,
  WandSparkles,
  X,
} from "lucide-react";
import Image from "next/image";
import { FormEvent, useRef, useState } from "react";
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
import { Textarea } from "@/components/ui/textarea";
import type { BrandDiscoveryResponse, MediaAsset, MediaLibraryResponse, PublicAppState, WorkspaceSettings } from "@/lib/app-types";
import { requestJson } from "@/lib/api";
import { cn } from "@/lib/utils";

type Props = {
  workspace: WorkspaceSettings;
  onStateChange: (state: PublicAppState) => void;
};

type StateResponse = { ok: boolean; state: PublicAppState };
type UploadPurpose = "logo" | "reference";
type PreviousBrandSummary = {
  currentBusinessName: string;
  currentProfileVersion: number;
  posts: number;
  publishedPosts: number;
  approvalActions: number;
  scheduledJobs: number;
  auditEvents: number;
  mediaAssets: number;
};

function lines(values: string[]) {
  return values.join("\n");
}

function parseList(value: string) {
  return value
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function Field({
  children,
  htmlFor,
  label,
  hint,
}: {
  children: React.ReactNode;
  htmlFor: string;
  label: string;
  hint?: string;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between gap-3">
        <Label htmlFor={htmlFor}>{label}</Label>
        {hint ? <span className="text-[10px] text-zinc-600">{hint}</span> : null}
      </div>
      {children}
    </div>
  );
}

async function uploadAsset(file: File) {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/api/media", { method: "POST", body });
  const payload = await response.json().catch(() => ({})) as { asset?: MediaAsset; error?: string };
  if (!response.ok || !payload.asset) {
    throw new Error(payload.error || `Upload failed (${response.status}).`);
  }
  return payload.asset;
}

export function BrandProfileCard({ workspace, onStateChange }: Props) {
  const logoInput = useRef<HTMLInputElement>(null);
  const referenceInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [assetDialog, setAssetDialog] = useState(false);
  const [cleanupDialog, setCleanupDialog] = useState(false);
  const [cleanupSummary, setCleanupSummary] = useState<PreviousBrandSummary | null>(null);
  const [library, setLibrary] = useState<MediaLibraryResponse | null>(null);
  const [discovery, setDiscovery] = useState<BrandDiscoveryResponse | null>(null);
  const [form, setForm] = useState({
    name: workspace.name,
    businessName: workspace.businessName,
    description: workspace.description,
    timezone: workspace.timezone,
    website: workspace.website,
    industry: workspace.industry,
    productsServices: workspace.productsServices,
    targetAudience: workspace.targetAudience,
    location: workspace.location,
    goals: lines(workspace.goals),
    callToAction: workspace.callToAction,
    language: workspace.language,
    tone: workspace.tone,
    contentPillars: lines(workspace.contentPillars),
    restrictedClaims: lines(workspace.restrictedClaims),
    brandedHashtags: workspace.brandedHashtags.join(" "),
    logoMediaId: workspace.logoMediaId,
    referenceMediaIds: workspace.referenceMediaIds,
    primaryColor: workspace.primaryColor,
    secondaryColor: workspace.secondaryColor,
    accentColor: workspace.accentColor,
    headingFont: workspace.headingFont,
    bodyFont: workspace.bodyFont,
    visualStyle: workspace.visualStyle,
  });

  const selectedLogo = library?.items.find((asset) => asset.id === form.logoMediaId)
    ?? (workspace.logo?.id === form.logoMediaId ? workspace.logo : null);

  async function openAssetPicker() {
    setAssetDialog(true);
    if (library) return;
    setBusy("assets");
    try {
      setLibrary(await requestJson<MediaLibraryResponse>("/api/media", { cache: "no-store" }));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not load brand images.");
    } finally {
      setBusy(null);
    }
  }

  async function analyzeWebsite() {
    if (!form.website.trim()) {
      toast.error("Enter your business website first.");
      return;
    }
    setBusy("discover");
    try {
      const result = await requestJson<BrandDiscoveryResponse>("/api/settings/brand-profile/discover", {
        method: "POST",
        body: JSON.stringify({ url: form.website }),
      });
      const draft = result.draft;
      setForm((current) => ({
        ...current,
        name: draft.businessName || current.name,
        businessName: draft.businessName || current.businessName,
        website: draft.website || current.website,
        description: draft.description || current.description,
        industry: draft.industry || current.industry,
        productsServices: draft.productsServices || current.productsServices,
        targetAudience: draft.targetAudience || current.targetAudience,
        location: draft.location || current.location,
        goals: draft.goals.length ? lines(draft.goals) : current.goals,
        callToAction: draft.callToAction || current.callToAction,
        language: draft.language || current.language,
        tone: draft.tone || current.tone,
        contentPillars: draft.contentPillars.length ? lines(draft.contentPillars) : current.contentPillars,
        brandedHashtags: draft.brandedHashtags.length ? draft.brandedHashtags.join(" ") : current.brandedHashtags,
        primaryColor: draft.primaryColor || current.primaryColor,
        secondaryColor: draft.secondaryColor || current.secondaryColor,
        accentColor: draft.accentColor || current.accentColor,
        headingFont: draft.headingFont || current.headingFont,
        bodyFont: draft.bodyFont || current.bodyFont,
        visualStyle: draft.visualStyle || current.visualStyle,
        logoMediaId: result.logoAsset?.id ?? current.logoMediaId,
      }));
      if (result.logoAsset) {
        const importedLogo = result.logoAsset;
        setLibrary((current) => current ? {
          ...current,
          items: [importedLogo, ...current.items.filter((item) => item.id !== importedLogo.id)],
          total: current.items.some((item) => item.id === importedLogo.id) ? current.total : current.total + 1,
        } : { items: [importedLogo], total: 1, maxUploadBytes: 10 * 1024 * 1024, storagePolicy: "local-only" });
      }
      setDiscovery(result);
      toast.success("Editable brand draft created. Review it before confirming.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not analyze the website.");
    } finally {
      setBusy(null);
    }
  }

  async function handleUpload(file: File | undefined, purpose: UploadPurpose) {
    if (!file) return;
    setBusy(`upload-${purpose}`);
    try {
      const asset = await uploadAsset(file);
      setLibrary((current) => current ? {
        ...current,
        items: [asset, ...current.items.filter((item) => item.id !== asset.id)],
        total: current.items.some((item) => item.id === asset.id) ? current.total : current.total + 1,
      } : { items: [asset], total: 1, maxUploadBytes: 10 * 1024 * 1024, storagePolicy: "local-only" });
      if (purpose === "logo") {
        setForm((current) => ({ ...current, logoMediaId: asset.id }));
      } else {
        setForm((current) => ({
          ...current,
          referenceMediaIds: current.referenceMediaIds.includes(asset.id)
            ? current.referenceMediaIds
            : [...current.referenceMediaIds, asset.id].slice(0, 12),
        }));
      }
      toast.success(purpose === "logo" ? "Logo uploaded" : "Reference image uploaded");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not upload the image.");
    } finally {
      setBusy(null);
    }
  }

  async function saveProfile(event: FormEvent) {
    event.preventDefault();
    setBusy("save");
    try {
      const response = await requestJson<StateResponse>("/api/settings/brand-profile", {
        method: "PUT",
        body: JSON.stringify({
          ...form,
          goals: parseList(form.goals),
          contentPillars: parseList(form.contentPillars),
          restrictedClaims: parseList(form.restrictedClaims),
          brandedHashtags: parseList(form.brandedHashtags.replaceAll(" ", ",")),
        }),
      });
      onStateChange(response.state);
      toast.success(`Brand profile revision ${response.state.workspace.profileVersion} confirmed`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save the brand profile.");
    } finally {
      setBusy(null);
    }
  }

  async function openPreviousBrandCleanup() {
    setBusy("cleanup-preview");
    try {
      const response = await requestJson<{ ok: boolean; summary: PreviousBrandSummary }>(
        "/api/settings/brand-profile/history",
        { cache: "no-store" },
      );
      setCleanupSummary(response.summary);
      setCleanupDialog(true);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not inspect previous brand data.");
    } finally {
      setBusy(null);
    }
  }

  async function deletePreviousBrandData() {
    setBusy("cleanup-delete");
    try {
      const response = await requestJson<{
        ok: boolean;
        deleted: PreviousBrandSummary;
        state: PublicAppState;
      }>("/api/settings/brand-profile/history", {
        method: "DELETE",
        body: JSON.stringify({ currentBusinessName: workspace.businessName }),
      });
      onStateChange(response.state);
      setCleanupDialog(false);
      setCleanupSummary(null);
      toast.success(
        response.deleted.posts || response.deleted.mediaAssets
          ? `Deleted ${response.deleted.posts} previous-brand post(s) and ${response.deleted.mediaAssets} unused media asset(s).`
          : "No previous brand data remained.",
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not delete previous brand data.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <Card>
        <CardHeader className="border-b border-zinc-900">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-md border border-zinc-700 bg-black text-amber-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
              <Palette className="size-4" />
            </div>
            <div>
              <CardTitle>Brand profile</CardTitle>
              <CardDescription>Confirmed facts, voice, guardrails, and visual preferences used by AI.</CardDescription>
            </div>
          </div>
          <CardAction>
            <Badge className={workspace.profileComplete ? "border-emerald-500/25 bg-emerald-500/8 text-emerald-300" : "border-amber-500/25 bg-amber-500/8 text-amber-300"} variant="outline">
              {workspace.profileComplete ? `CONFIRMED · R${workspace.profileVersion}` : "NEEDS CONFIRMATION"}
            </Badge>
          </CardAction>
        </CardHeader>
        <CardContent>
          <form className="space-y-6" onSubmit={saveProfile}>
            <section className="rounded-lg border border-amber-500/20 bg-[linear-gradient(135deg,rgba(245,158,11,0.08),rgba(0,0,0,0)_55%)] p-4 sm:p-5" aria-labelledby="website-brand-heading">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <div className="flex gap-3">
                  <div className="grid size-9 shrink-0 place-items-center rounded-md border border-amber-500/25 bg-black text-amber-300"><WandSparkles className="size-4" /></div>
                  <div><h3 className="text-sm font-semibold text-zinc-100" id="website-brand-heading">Fill from your website</h3><p className="mt-1 max-w-2xl text-[11px] leading-5 text-zinc-500">Socium reads up to four public pages, then your connected AI prepares an editable draft. Nothing is trusted until you save and confirm it.</p></div>
                </div>
                <Badge className="w-fit border-emerald-500/20 bg-emerald-500/5 text-emerald-300" variant="outline"><ShieldCheck /> SAFE PUBLIC CRAWL</Badge>
              </div>
              <div className="mt-4 flex flex-col gap-2 sm:flex-row">
                <div className="relative min-w-0 flex-1"><Globe2 className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-zinc-600" /><Input aria-label="Business website to analyze" className="pl-9" maxLength={2048} onChange={(event) => setForm((current) => ({ ...current, website: event.target.value }))} placeholder="https://yourbusiness.com" type="url" value={form.website} /></div>
                <Button disabled={busy === "discover"} onClick={() => void analyzeWebsite()} type="button">{busy === "discover" ? <Loader2 className="animate-spin" /> : <WandSparkles />}Analyze & fill</Button>
              </div>
              {discovery ? (
                <div className="mt-4 space-y-3 rounded-md border border-zinc-800 bg-black/70 p-3" aria-live="polite">
                  <div className="flex flex-wrap items-center gap-2 text-[10px]"><Badge className="border-zinc-800 text-zinc-400" variant="outline">{discovery.sources.length} PAGES READ</Badge><Badge className={discovery.provider.local ? "border-emerald-500/20 text-emerald-300" : "border-sky-500/20 text-sky-300"} variant="outline">{discovery.provider.local ? <HardDrive /> : <Cloud />}{discovery.provider.local ? "LOCAL AI" : "CLOUD AI"} · {discovery.provider.model}</Badge>{discovery.logoAsset ? <Badge className="border-amber-500/20 text-amber-300" variant="outline">LOGO IMPORTED</Badge> : null}</div>
                  <p className="text-[11px] leading-5 text-zinc-500">Review every filled field below. Website facts and AI suggestions can both be edited or removed before confirmation.</p>
                  {discovery.sources.length ? <div className="flex flex-wrap gap-x-4 gap-y-2">{discovery.sources.map((source) => <a className="inline-flex max-w-full items-center gap-1 truncate text-[10px] text-zinc-500 hover:text-amber-300" href={source.url} key={source.url} rel="noreferrer" target="_blank"><ExternalLink className="size-3 shrink-0" />{source.title || source.url}</a>)}</div> : null}
                  {discovery.warnings.map((warning) => <p className="flex items-start gap-2 text-[10px] leading-4 text-amber-200" key={warning}><AlertTriangle className="mt-0.5 size-3 shrink-0" />{warning}</p>)}
                </div>
              ) : null}
            </section>

            <section className="space-y-4" aria-labelledby="brand-identity-heading">
              <div>
                <h3 className="text-sm font-semibold text-zinc-100" id="brand-identity-heading">Business identity</h3>
                <p className="mt-1 text-[11px] text-zinc-600">Only facts you confirm here become trusted brand context.</p>
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <Field htmlFor="brand-workspace-name" label="Workspace name"><Input id="brand-workspace-name" maxLength={80} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} required value={form.name} /></Field>
                <Field htmlFor="brand-business-name" label="Business name"><Input id="brand-business-name" maxLength={120} onChange={(event) => setForm((current) => ({ ...current, businessName: event.target.value }))} placeholder="Acme Services" required value={form.businessName} /></Field>
                <Field htmlFor="brand-industry" label="Industry" hint="Optional"><Input id="brand-industry" maxLength={160} onChange={(event) => setForm((current) => ({ ...current, industry: event.target.value }))} placeholder="Home services, SaaS, retail…" value={form.industry} /></Field>
                <Field htmlFor="brand-location" label="Primary location" hint="Optional"><Input id="brand-location" maxLength={240} onChange={(event) => setForm((current) => ({ ...current, location: event.target.value }))} placeholder="Lahore, Pakistan or Global" value={form.location} /></Field>
                <Field htmlFor="brand-timezone" label="Timezone"><Input id="brand-timezone" maxLength={80} onChange={(event) => setForm((current) => ({ ...current, timezone: event.target.value }))} required value={form.timezone} /></Field>
                <div className="lg:col-span-2"><Field htmlFor="brand-description" label="What the business does" hint="Facts only"><Textarea id="brand-description" maxLength={2000} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} placeholder="A short factual business overview." required rows={3} value={form.description} /></Field></div>
                <div className="lg:col-span-2"><Field htmlFor="brand-offer" label="Products or services"><Textarea id="brand-offer" maxLength={4000} onChange={(event) => setForm((current) => ({ ...current, productsServices: event.target.value }))} placeholder="What you sell, deliver, or help customers accomplish." required rows={3} value={form.productsServices} /></Field></div>
                <div className="lg:col-span-2"><Field htmlFor="brand-audience" label="Target audience"><Textarea id="brand-audience" maxLength={3000} onChange={(event) => setForm((current) => ({ ...current, targetAudience: event.target.value }))} placeholder="Who they are, what they need, and where they are." required rows={3} value={form.targetAudience} /></Field></div>
              </div>
            </section>

            <section className="space-y-4 border-t border-zinc-900 pt-6" aria-labelledby="brand-content-heading">
              <div><h3 className="text-sm font-semibold text-zinc-100" id="brand-content-heading">Content preferences</h3><p className="mt-1 text-[11px] text-zinc-600">One item per line keeps goals, pillars, and guardrails precise.</p></div>
              <div className="grid gap-4 lg:grid-cols-2">
                <Field htmlFor="brand-language" label="Preferred language"><Input id="brand-language" list="brand-language-options" maxLength={80} onChange={(event) => setForm((current) => ({ ...current, language: event.target.value }))} placeholder="English, Urdu, Roman Urdu…" required value={form.language} /><datalist id="brand-language-options"><option value="English" /><option value="Urdu" /><option value="Roman Urdu" /><option value="English and Roman Urdu" /></datalist></Field>
                <Field htmlFor="brand-tone" label="Brand voice"><Input id="brand-tone" maxLength={240} onChange={(event) => setForm((current) => ({ ...current, tone: event.target.value }))} placeholder="Clear, practical, and calm" required value={form.tone} /></Field>
                <Field htmlFor="brand-goals" label="Marketing goals" hint="One per line"><Textarea id="brand-goals" maxLength={3000} onChange={(event) => setForm((current) => ({ ...current, goals: event.target.value }))} placeholder={"Build useful awareness\nEarn qualified conversations"} required rows={4} value={form.goals} /></Field>
                <Field htmlFor="brand-pillars" label="Content pillars" hint="One per line"><Textarea id="brand-pillars" maxLength={3000} onChange={(event) => setForm((current) => ({ ...current, contentPillars: event.target.value }))} placeholder={"Practical education\nCustomer questions\nBehind the scenes"} required rows={4} value={form.contentPillars} /></Field>
                <div className="lg:col-span-2"><Field htmlFor="brand-cta" label="Default call to action"><Input id="brand-cta" maxLength={500} onChange={(event) => setForm((current) => ({ ...current, callToAction: event.target.value }))} placeholder="Book a practical workflow review." required value={form.callToAction} /></Field></div>
                <Field htmlFor="brand-restrictions" label="Restricted claims or topics" hint="Optional"><Textarea id="brand-restrictions" maxLength={4800} onChange={(event) => setForm((current) => ({ ...current, restrictedClaims: event.target.value }))} placeholder={"Guaranteed results\nUnverified customer numbers"} rows={4} value={form.restrictedClaims} /></Field>
                <Field htmlFor="brand-hashtags" label="Branded hashtags" hint="Optional"><Textarea id="brand-hashtags" maxLength={1600} onChange={(event) => setForm((current) => ({ ...current, brandedHashtags: event.target.value }))} placeholder="#YourBrand #YourCampaign" rows={4} value={form.brandedHashtags} /></Field>
              </div>
            </section>

            <section className="space-y-4 border-t border-zinc-900 pt-6" aria-labelledby="brand-visual-heading">
              <div><h3 className="text-sm font-semibold text-zinc-100" id="brand-visual-heading">Visual direction</h3><p className="mt-1 text-[11px] text-zinc-600">Colors and references prepare image generation without publishing anything.</p></div>
              <div className="grid gap-4 lg:grid-cols-3">
                {(["primaryColor", "secondaryColor", "accentColor"] as const).map((key) => {
                  const label = key === "primaryColor" ? "Primary color" : key === "secondaryColor" ? "Secondary color" : "Accent color";
                  return <Field htmlFor={`brand-${key}`} key={key} label={label}><div className="flex gap-2"><input aria-label={`${label} picker`} className="h-10 w-12 cursor-pointer rounded-md border border-zinc-800 bg-black p-1" onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))} type="color" value={form[key]} /><Input id={`brand-${key}`} maxLength={7} onChange={(event) => setForm((current) => ({ ...current, [key]: event.target.value }))} pattern="#[0-9a-fA-F]{6}" required value={form[key]} /></div></Field>;
                })}
                <Field htmlFor="brand-heading-font" label="Heading font" hint="Optional"><Input id="brand-heading-font" maxLength={160} onChange={(event) => setForm((current) => ({ ...current, headingFont: event.target.value }))} placeholder="Inter, Sora, Poppins…" value={form.headingFont} /></Field>
                <Field htmlFor="brand-body-font" label="Body font" hint="Optional"><Input id="brand-body-font" maxLength={160} onChange={(event) => setForm((current) => ({ ...current, bodyFont: event.target.value }))} placeholder="Inter, Roboto, system-ui…" value={form.bodyFont} /></Field>
                <div className="lg:col-span-3"><Field htmlFor="brand-visual-style" label="Preferred visual style" hint="Optional"><Textarea id="brand-visual-style" maxLength={2000} onChange={(event) => setForm((current) => ({ ...current, visualStyle: event.target.value }))} placeholder="Dark editorial layouts, authentic product photography, no generic stock-office scenes." rows={3} value={form.visualStyle} /></Field></div>
              </div>

              <div className="grid gap-3 lg:grid-cols-[180px_1fr]">
                <div className="rounded-lg border border-zinc-800 bg-black p-3">
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-zinc-600">Brand logo</p>
                  <div className="mt-3 grid aspect-square place-items-center overflow-hidden rounded-md border border-zinc-800 bg-[#080808]">
                    {selectedLogo ? <Image alt={selectedLogo.altText || "Selected brand logo"} className="size-full object-contain p-3" height={180} src={selectedLogo.previewUrl} width={180} /> : <ImagePlus className="size-7 text-zinc-700" />}
                  </div>
                  {form.logoMediaId ? <Button className="mt-2 w-full" onClick={() => setForm((current) => ({ ...current, logoMediaId: null }))} size="sm" type="button" variant="ghost"><X />Remove logo</Button> : null}
                </div>
                <div className="rounded-lg border border-zinc-800 bg-black p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-medium text-zinc-200">Logo and reference media</p><p className="mt-1 text-[10px] leading-4 text-zinc-600">Files stay in the verified local Media Library. Up to 12 references can guide later image prompts.</p></div><Badge className="border-zinc-800 text-zinc-500" variant="outline">{form.referenceMediaIds.length} REFERENCES</Badge></div>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <Button disabled={busy === "upload-logo"} onClick={() => logoInput.current?.click()} size="sm" type="button" variant="outline">{busy === "upload-logo" ? <Loader2 className="animate-spin" /> : <Upload />}Upload logo</Button>
                    <Button disabled={busy === "upload-reference" || form.referenceMediaIds.length >= 12} onClick={() => referenceInput.current?.click()} size="sm" type="button" variant="outline">{busy === "upload-reference" ? <Loader2 className="animate-spin" /> : <Images />}Upload reference</Button>
                    <Button onClick={() => void openAssetPicker()} size="sm" type="button" variant="ghost"><ImagePlus />Choose from library</Button>
                  </div>
                  <input accept="image/jpeg,image/png,image/webp" aria-label="Upload brand logo" className="sr-only" onChange={(event) => { void handleUpload(event.target.files?.[0], "logo"); event.target.value = ""; }} ref={logoInput} type="file" />
                  <input accept="image/jpeg,image/png,image/webp" aria-label="Upload brand reference image" className="sr-only" onChange={(event) => { void handleUpload(event.target.files?.[0], "reference"); event.target.value = ""; }} ref={referenceInput} type="file" />
                </div>
              </div>
            </section>

            <div className="flex flex-col gap-3 border-t border-zinc-900 pt-5 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex max-w-2xl items-start gap-2 text-[10px] leading-4 text-zinc-500"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-emerald-400" /><span>Saving confirms this exact revision as trusted brand context. AI receives it only when you request generation through the selected provider.</span></div>
              <Button disabled={busy === "save"} type="submit">{busy === "save" ? <Loader2 className="animate-spin" /> : <Check />}{workspace.profileComplete ? "Save new revision" : "Save & confirm profile"}</Button>
            </div>

            <section className="flex flex-col gap-4 rounded-lg border border-red-500/20 bg-red-500/[0.035] p-4 sm:flex-row sm:items-center sm:justify-between" aria-labelledby="previous-brand-data-heading">
              <div className="max-w-2xl">
                <h3 className="text-sm font-semibold text-zinc-100" id="previous-brand-data-heading">Previous brand data</h3>
                <p className="mt-1 text-xs leading-5 text-zinc-400">Delete drafts, approval records, scheduled jobs, audit history, and unused website-imported media from profile revisions before R{workspace.profileVersion}. The active {workspace.businessName} profile and integrations stay connected.</p>
              </div>
              <Button disabled={busy === "cleanup-preview"} onClick={() => void openPreviousBrandCleanup()} type="button" variant="outline">
                {busy === "cleanup-preview" ? <Loader2 className="animate-spin" /> : <Trash2 />}
                Review & delete
              </Button>
            </section>
          </form>
        </CardContent>
      </Card>

      <Dialog onOpenChange={setAssetDialog} open={assetDialog}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-4xl">
          <DialogHeader><DialogTitle>Choose brand images</DialogTitle><DialogDescription>Select one logo and up to 12 visual references from the private local library.</DialogDescription></DialogHeader>
          {busy === "assets" ? <div className="grid min-h-48 place-items-center"><Loader2 className="animate-spin text-zinc-500" /></div> : library?.items.length ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {library.items.map((asset) => {
                const isLogo = form.logoMediaId === asset.id;
                const isReference = form.referenceMediaIds.includes(asset.id);
                return (
                  <div className={cn("overflow-hidden rounded-lg border bg-black", (isLogo || isReference) ? "border-amber-500/40" : "border-zinc-800")} key={asset.id}>
                    <div className="aspect-video bg-[#080808]"><Image alt={asset.altText || asset.originalName} className="size-full object-contain" height={180} src={asset.previewUrl} width={320} /></div>
                    <div className="space-y-3 p-3"><p className="truncate text-[10px] text-zinc-400" title={asset.originalName}>{asset.originalName}</p><div className="grid grid-cols-2 gap-2"><Button aria-pressed={isLogo} onClick={() => setForm((current) => ({ ...current, logoMediaId: isLogo ? null : asset.id }))} size="sm" type="button" variant={isLogo ? "default" : "outline"}>{isLogo ? <Check /> : null}Logo</Button><Button aria-pressed={isReference} disabled={!isReference && form.referenceMediaIds.length >= 12} onClick={() => setForm((current) => ({ ...current, referenceMediaIds: isReference ? current.referenceMediaIds.filter((id) => id !== asset.id) : [...current.referenceMediaIds, asset.id] }))} size="sm" type="button" variant={isReference ? "default" : "outline"}>{isReference ? <Check /> : null}Reference</Button></div></div>
                  </div>
                );
              })}
            </div>
          ) : <div className="grid min-h-48 place-items-center rounded-lg border border-dashed border-zinc-800 text-xs text-zinc-600">No images in the Media Library yet.</div>}
          <DialogFooter showCloseButton />
        </DialogContent>
      </Dialog>

      <Dialog onOpenChange={setCleanupDialog} open={cleanupDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete previous brand data?</DialogTitle>
            <DialogDescription>This permanently removes local content from revisions before R{workspace.profileVersion}. It does not delete posts already published on LinkedIn or another external platform.</DialogDescription>
          </DialogHeader>
          {cleanupSummary ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {[
                ["Posts", cleanupSummary.posts],
                ["Approvals", cleanupSummary.approvalActions],
                ["Scheduled jobs", cleanupSummary.scheduledJobs],
                ["Audit events", cleanupSummary.auditEvents],
                ["Unused media", cleanupSummary.mediaAssets],
                ["Published records", cleanupSummary.publishedPosts],
              ].map(([label, value]) => (
                <div className="rounded-md border border-zinc-800 bg-black p-3" key={String(label)}>
                  <p className="text-lg font-semibold text-zinc-100">{value}</p>
                  <p className="mt-1 text-xs text-zinc-500">{label}</p>
                </div>
              ))}
            </div>
          ) : null}
          <div className="rounded-md border border-emerald-500/20 bg-emerald-500/5 p-3 text-xs leading-5 text-emerald-200">Protected: active {workspace.businessName} profile, AI provider, storage, LinkedIn, Slack, Telegram, scheduler, and current-revision content.</div>
          <DialogFooter>
            <Button disabled={busy === "cleanup-delete"} onClick={() => setCleanupDialog(false)} variant="ghost">Cancel</Button>
            <Button className="bg-red-500 text-white hover:bg-red-400" disabled={busy === "cleanup-delete" || !cleanupSummary} onClick={() => void deletePreviousBrandData()}>
              {busy === "cleanup-delete" ? <Loader2 className="animate-spin" /> : <Trash2 />}
              Delete previous data
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
