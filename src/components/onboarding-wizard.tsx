"use client";

import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  Cloud,
  Copy,
  Cpu,
  Database,
  Download,
  ExternalLink,
  HardDrive,
  Loader2,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { BrandProfileCard } from "@/components/brand-profile-card";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type {
  LocalAiStatus,
  OnboardingStep,
  ProviderConnectionResult,
  ProviderKind,
  PublicAppState,
} from "@/lib/app-types";
import { requestJson } from "@/lib/api";
import { getProviderPreset } from "@/lib/provider-presets";
import { cn } from "@/lib/utils";

type Props = {
  open: boolean;
  state: PublicAppState;
  onOpenAdvancedAi: () => void;
  onOpenChange: (open: boolean) => void;
  onStateChange: (state: PublicAppState) => void;
};

type StateResponse = { ok: boolean; state: PublicAppState };
type AiMode = "local" | "cloud";

const steps: Array<{ id: OnboardingStep; label: string }> = [
  { id: "welcome", label: "Welcome" },
  { id: "storage", label: "Storage" },
  { id: "ai", label: "AI" },
  { id: "brand", label: "Brand" },
  { id: "finish", label: "Ready" },
];

const cloudKinds: ProviderKind[] = [
  "openrouter",
  "nvidia",
  "openai",
  "gemini",
  "anthropic",
  "openai-compatible",
];

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / (1024 ** index)).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function ReadinessRow({ complete, label, detail }: { complete: boolean; label: string; detail: string }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-zinc-800 bg-black/60 p-3">
      <div className={cn("mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border", complete ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" : "border-zinc-800 text-zinc-700")}>
        {complete ? <Check className="size-3.5" /> : <span className="size-1.5 rounded-full bg-current" />}
      </div>
      <div><p className="text-xs font-medium text-zinc-200">{label}</p><p className="mt-1 text-[10px] leading-4 text-zinc-600">{detail}</p></div>
    </div>
  );
}

export function OnboardingWizard({ open, state, onOpenAdvancedAi, onOpenChange, onStateChange }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [acknowledgeWarnings, setAcknowledgeWarnings] = useState(false);
  const [aiMode, setAiMode] = useState<AiMode>(state.provider.kind === "ollama" ? "local" : "cloud");
  const initialCloudKind = state.provider.kind !== "ollama" && cloudKinds.includes(state.provider.kind)
    ? state.provider.kind
    : "openrouter";
  const [cloudKind, setCloudKind] = useState<ProviderKind>(initialCloudKind);
  const initialPreset = getProviderPreset(initialCloudKind);
  const [cloudBaseUrl, setCloudBaseUrl] = useState(
    state.provider.kind === initialCloudKind ? state.provider.baseUrl : initialPreset.baseUrl,
  );
  const [cloudModel, setCloudModel] = useState(
    state.provider.kind === initialCloudKind ? state.provider.model : initialPreset.defaultModel,
  );
  const [cloudApiKey, setCloudApiKey] = useState("");
  const [localAi, setLocalAi] = useState<LocalAiStatus | null>(null);
  const [localModel, setLocalModel] = useState(state.provider.kind === "ollama" ? state.provider.model : "");
  const [localPull, setLocalPull] = useState<{ percentage: number; status: string } | null>(null);

  const currentStep = state.onboarding.currentStep;
  const currentIndex = Math.max(0, steps.findIndex((step) => step.id === currentStep));
  const selectedPreset = getProviderPreset(cloudKind);
  const storedCloudKey = Boolean(
    state.provider.hasApiKey
      && state.provider.kind === cloudKind
      && state.provider.baseUrl === cloudBaseUrl.replace(/\/$/, ""),
  );
  const cloudCanConnect = Boolean(
    cloudBaseUrl.trim()
      && cloudModel.trim()
      && (!selectedPreset.apiKeyRequired || storedCloudKey || cloudApiKey.trim()),
  );

  async function mutateOnboarding(
    action: "start" | "set-step" | "confirm-storage" | "dismiss" | "complete",
    options: { step?: OnboardingStep; acknowledgeWarnings?: boolean } = {},
  ) {
    const response = await requestJson<StateResponse>("/api/onboarding", {
      method: "PUT",
      body: JSON.stringify({ action, ...options }),
    });
    onStateChange(response.state);
    return response.state;
  }

  useEffect(() => {
    if (!open || !["not-started", "dismissed"].includes(state.onboarding.status)) return;
    void mutateOnboarding("start").catch((error: unknown) => {
      toast.error(error instanceof Error ? error.message : "Could not start setup.");
    });
    // The state transition prevents a repeated request after the response arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, state.onboarding.status]);

  async function refreshLocalAi() {
    setBusy("local-status");
    try {
      const status = await requestJson<LocalAiStatus>(
        "/api/providers/local/status?base_url=http%3A%2F%2F127.0.0.1%3A11434",
        { cache: "no-store" },
      );
      setLocalAi(status);
      setLocalModel((current) => {
        if (current && status.models.includes(current)) return current;
        if (status.models.includes(status.selectedRecommendation)) return status.selectedRecommendation;
        return status.models[0] ?? "";
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not inspect local AI.");
    } finally {
      setBusy(null);
    }
  }

  async function goTo(step: OnboardingStep) {
    setBusy(`step-${step}`);
    try {
      await mutateOnboarding("set-step", { step });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save setup progress.");
    } finally {
      setBusy(null);
    }
  }

  async function confirmStorage() {
    setBusy("storage");
    try {
      await mutateOnboarding("confirm-storage", { acknowledgeWarnings });
      toast.success("Storage locations confirmed");
      void refreshLocalAi();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not confirm storage.");
    } finally {
      setBusy(null);
    }
  }

  async function connectProvider(form: { kind: ProviderKind; baseUrl: string; model: string; apiKey: string }) {
    setBusy("provider");
    try {
      const saved = await requestJson<StateResponse>("/api/settings/provider", {
        method: "PUT",
        body: JSON.stringify(form),
      });
      onStateChange(saved.state);
      const result = await requestJson<ProviderConnectionResult>("/api/providers/test", { method: "POST" });
      const next = await requestJson<PublicAppState>("/api/state", { cache: "no-store" });
      onStateChange(next);
      setCloudApiKey("");
      toast.success("AI connection verified", { description: result.message });
      return true;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "AI connection failed.");
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function verifySavedProvider() {
    setBusy("provider");
    try {
      const result = await requestJson<ProviderConnectionResult>("/api/providers/test", { method: "POST" });
      const next = await requestJson<PublicAppState>("/api/state", { cache: "no-store" });
      onStateChange(next);
      toast.success("Saved AI connection verified", { description: result.message });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Saved AI connection could not be verified.");
    } finally {
      setBusy(null);
    }
  }

  async function downloadLocalModel() {
    if (!localAi?.ollamaRunning) return;
    const model = localAi.selectedRecommendation;
    setBusy("local-pull");
    setLocalPull({ percentage: 0, status: `Preparing ${model}` });
    try {
      const response = await fetch("/api/providers/local/pull", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ baseUrl: localAi.baseUrl, model }),
      });
      if (!response.ok || !response.body) {
        const payload = await response.json().catch(() => ({})) as { error?: string };
        throw new Error(payload.error || `Model download failed (${response.status}).`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffered = "";
      let verified = false;
      while (true) {
        const { done, value } = await reader.read();
        buffered += decoder.decode(value, { stream: !done });
        const updates = buffered.split("\n");
        buffered = updates.pop() ?? "";
        for (const line of updates) {
          if (!line.trim()) continue;
          const update = JSON.parse(line) as { ok: boolean; status?: string; percentage?: number; verified?: boolean; error?: string };
          if (!update.ok) throw new Error(update.error || "Model download failed.");
          setLocalPull({ percentage: update.percentage ?? 0, status: update.status || "Downloading model" });
          verified ||= Boolean(update.verified);
        }
        if (done) break;
      }
      if (!verified) throw new Error("The model download ended before verification.");
      setLocalModel(model);
      await connectProvider({ kind: "ollama", baseUrl: localAi.baseUrl, model, apiKey: "" });
      await refreshLocalAi();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not download the local model.");
    } finally {
      setBusy(null);
    }
  }

  async function dismiss() {
    setBusy("dismiss");
    try {
      await mutateOnboarding("dismiss");
      onOpenChange(false);
      toast.message("Setup saved for later", { description: "Resume it from Setup guide at any time." });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save setup progress.");
    } finally {
      setBusy(null);
    }
  }

  async function complete() {
    setBusy("complete");
    try {
      await mutateOnboarding("complete");
      onOpenChange(false);
      toast.success("Socium is ready", { description: "Create a draft whenever you are ready." });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Setup is not complete yet.");
    } finally {
      setBusy(null);
    }
  }

  function renderStepBody() {
    if (currentStep === "welcome") {
      return (
        <div className="grid min-h-[480px] place-items-center p-6 sm:p-10">
          <div className="max-w-2xl text-center">
            <div className="mx-auto grid size-16 place-items-center rounded-2xl border border-amber-500/30 bg-amber-500/8 text-amber-300 shadow-[0_0_50px_rgba(245,158,11,0.08)]"><Sparkles className="size-7" /></div>
            <Badge className="mt-6 border-emerald-500/25 bg-emerald-500/8 text-emerald-300" variant="outline">LOCAL-FIRST · NO SOCIUM ACCOUNT</Badge>
            <h2 className="mt-5 text-2xl font-semibold tracking-[-0.04em] text-white sm:text-4xl">Welcome to Socium</h2>
            <p className="mx-auto mt-4 max-w-xl text-sm leading-6 text-zinc-500">Confirm where your private data lives, connect one AI, and teach Socium your brand. Nothing publishes during setup.</p>
            <div className="mx-auto mt-8 grid max-w-xl gap-3 text-left sm:grid-cols-3">
              <ReadinessRow complete={false} detail="SQLite, media, credentials, and models stay where you choose." label="Private storage" />
              <ReadinessRow complete={false} detail="Local Ollama is recommended; your own cloud key also works." label="One AI" />
              <ReadinessRow complete={false} detail="Only facts you explicitly confirm become generation context." label="Your brand" />
            </div>
            <Button className="mt-8" disabled={busy !== null} onClick={() => void goTo("storage")} size="lg">Start setup <ArrowRight /></Button>
          </div>
        </div>
      );
    }

    if (currentStep === "storage") {
      const locations = state.storage.locations;
      return (
        <div className="space-y-5 p-5 sm:p-7">
          <div><Badge className="border-zinc-700 text-zinc-400" variant="outline">STEP 1 OF 3</Badge><h2 className="mt-3 text-xl font-semibold text-white">Confirm private storage</h2><p className="mt-2 text-xs leading-5 text-zinc-500">The runtime is replaceable. Your database, encryption key, media, and AI models are stored separately and survive normal updates.</p></div>
          <div className="grid gap-3 lg:grid-cols-3">
            {(["runtime", "data", "models"] as const).map((location) => {
              const details = locations[location];
              const volume = location === "runtime" ? null : state.storage.volumes[location];
              return (
                <Card className={cn(location !== "runtime" && "border-emerald-500/15")} key={location}>
                  <CardContent className="p-4"><div className="flex items-center justify-between"><div className="flex items-center gap-2">{location === "runtime" ? <Cpu className="size-4 text-zinc-500" /> : <HardDrive className="size-4 text-emerald-400" />}<p className="text-xs font-semibold capitalize text-zinc-200">{location}</p></div><Badge className="border-zinc-800 text-[9px] text-zinc-500" variant="outline">{details.kind}</Badge></div><p className="mt-4 break-all font-mono text-[10px] leading-4 text-zinc-500">{details.path}</p>{volume ? <div className="mt-4 flex justify-between text-[10px] text-zinc-600"><span>{formatBytes(volume.freeBytes)} free</span><span>{volume.available ? "Available" : "Unavailable"}</span></div> : <p className="mt-4 text-[10px] text-zinc-700">Program files only</p>}</CardContent>
                </Card>
              );
            })}
          </div>
          {state.storage.warnings.length ? <div className="rounded-lg border border-amber-500/25 bg-amber-500/5 p-4"><p className="text-xs font-semibold text-amber-200">Review storage warnings</p>{state.storage.warnings.map((warning) => <p className="mt-2 text-[11px] leading-5 text-amber-200/75" key={warning}>• {warning}</p>)}<label className="mt-4 flex cursor-pointer items-start gap-3 text-[11px] leading-5 text-zinc-400"><input checked={acknowledgeWarnings} className="mt-1 accent-amber-400" onChange={(event) => setAcknowledgeWarnings(event.target.checked)} type="checkbox" />I understand these warnings and want to use the current locations.</label></div> : <div className="flex items-center gap-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4 text-xs text-emerald-200"><CheckCircle2 className="size-4" />Both durable locations are available.</div>}
          <div className="rounded-lg border border-zinc-800 bg-black p-4"><div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"><div><p className="text-xs font-medium text-zinc-300">Want different drives?</p><p className="mt-1 text-[10px] leading-4 text-zinc-600">Stop Socium first, then run this generated command. The old copy is preserved after checksum verification.</p></div><Button onClick={() => void navigator.clipboard.writeText(state.storage.moveCommand).then(() => toast.success("Move command copied"))} size="sm" type="button" variant="outline"><Copy />Copy move command</Button></div><code className="mt-3 block overflow-x-auto rounded bg-[#050505] p-3 font-mono text-[10px] text-amber-300">{state.storage.moveCommand}</code></div>
          <div className="flex flex-col-reverse gap-2 border-t border-zinc-900 pt-5 sm:flex-row sm:justify-between"><Button onClick={() => void goTo("welcome")} variant="ghost"><ArrowLeft />Back</Button><Button disabled={!state.onboarding.storageReady || (state.storage.warnings.length > 0 && !acknowledgeWarnings) || busy === "storage"} onClick={() => void confirmStorage()}>{busy === "storage" ? <Loader2 className="animate-spin" /> : <Database />}Confirm these locations</Button></div>
        </div>
      );
    }

    if (currentStep === "ai") {
      return (
        <div className="space-y-5 p-5 sm:p-7">
          <div><Badge className="border-zinc-700 text-zinc-400" variant="outline">STEP 2 OF 3</Badge><h2 className="mt-3 text-xl font-semibold text-white">Connect one AI</h2><p className="mt-2 text-xs leading-5 text-zinc-500">Local AI keeps brand context on this computer. Cloud AI is optional and sends generation context only when you request a draft.</p></div>
          {state.onboarding.aiVerified ? <div className="flex items-start gap-3 rounded-lg border border-emerald-500/25 bg-emerald-500/5 p-4"><CheckCircle2 className="mt-0.5 size-4 text-emerald-300" /><div><p className="text-xs font-semibold text-emerald-200">AI verified</p><p className="mt-1 font-mono text-[10px] text-emerald-200/65">{state.provider.kind} · {state.provider.model}</p></div></div> : null}
          <div className="grid gap-3 sm:grid-cols-2" role="group" aria-label="Onboarding AI type">
            <button aria-label="Set up local AI" aria-pressed={aiMode === "local"} className={cn("rounded-xl border p-4 text-left", aiMode === "local" ? "border-emerald-500/35 bg-emerald-500/8" : "border-zinc-800 bg-black")} onClick={() => { setAiMode("local"); setLocalAi(null); }} type="button"><div className="flex items-center justify-between"><span className="flex items-center gap-2 text-xs font-semibold text-white"><Cpu className="size-4 text-emerald-400" />Local AI</span><Badge className="border-emerald-500/25 text-[9px] text-emerald-300" variant="outline">RECOMMENDED</Badge></div><p className="mt-2 text-[10px] leading-4 text-zinc-500">Private and no per-post API bill.</p></button>
            <button aria-label="Set up cloud AI" aria-pressed={aiMode === "cloud"} className={cn("rounded-xl border p-4 text-left", aiMode === "cloud" ? "border-sky-500/35 bg-sky-500/8" : "border-zinc-800 bg-black")} onClick={() => setAiMode("cloud")} type="button"><span className="flex items-center gap-2 text-xs font-semibold text-white"><Cloud className="size-4 text-sky-400" />Cloud API</span><p className="mt-2 text-[10px] leading-4 text-zinc-500">Use your own provider account and key.</p></button>
          </div>
          {aiMode === "local" ? (
            <div className="space-y-4 rounded-xl border border-zinc-800 bg-black p-4">
              {busy === "local-status" && !localAi ? <div className="grid min-h-40 place-items-center text-xs text-zinc-600"><Loader2 className="mb-2 animate-spin" />Inspecting this computer…</div> : localAi ? <>
                <div className="grid gap-3 sm:grid-cols-3"><div className="rounded-lg border border-zinc-900 p-3"><p className="text-[10px] text-zinc-600">Memory</p><p className="mt-1 text-xs text-zinc-300">{formatBytes(localAi.memoryBytes)}</p></div><div className="rounded-lg border border-zinc-900 p-3"><p className="text-[10px] text-zinc-600">Ollama</p><p className="mt-1 text-xs text-zinc-300">{localAi.ollamaRunning ? "Running" : localAi.ollamaInstalled ? "Installed, not running" : "Not installed"}</p></div><div className="rounded-lg border border-zinc-900 p-3"><p className="text-[10px] text-zinc-600">Recommended</p><p className="mt-1 truncate text-xs text-zinc-300">{localAi.selectedRecommendation}</p></div></div>
                {!localAi.ollamaInstalled ? <a className={cn(buttonVariants({ variant: "outline" }), "w-full")} href="https://ollama.com/download" rel="noreferrer" target="_blank">Download Ollama <ExternalLink /></a> : !localAi.ollamaRunning ? <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-200">Open Ollama on this computer, then select Check again.</div> : localAi.models.length ? <div className="space-y-2"><Label htmlFor="onboarding-local-model">Installed model</Label><Select onValueChange={(value) => setLocalModel(value ?? "")} value={localModel}><SelectTrigger className="w-full bg-[#080808]" id="onboarding-local-model"><SelectValue /></SelectTrigger><SelectContent>{localAi.models.map((model) => <SelectItem key={model} value={model}>{model}</SelectItem>)}</SelectContent></Select><Button className="w-full" disabled={!localModel || busy === "provider"} onClick={() => void connectProvider({ kind: "ollama", baseUrl: localAi.baseUrl, model: localModel, apiKey: "" })}>{busy === "provider" ? <Loader2 className="animate-spin" /> : <ShieldCheck />}Connect and verify local AI</Button></div> : <Button className="w-full" disabled={busy === "local-pull"} onClick={() => void downloadLocalModel()}>{busy === "local-pull" ? <Loader2 className="animate-spin" /> : <Download />}{busy === "local-pull" ? `Downloading ${localPull?.percentage ?? 0}%` : `Download ${localAi.selectedRecommendation}`}</Button>}
                {localPull ? <div><div className="mb-2 flex justify-between text-[10px] text-zinc-600"><span>{localPull.status}</span><span>{localPull.percentage}%</span></div><Progress aria-label="Local model download" value={localPull.percentage} /></div> : null}
                <Button className="w-full" disabled={busy === "local-status"} onClick={() => { setLocalAi(null); void refreshLocalAi(); }} variant="ghost"><RefreshCw />Check again</Button>
              </> : <Button className="w-full" onClick={() => void refreshLocalAi()} variant="outline"><Cpu />Inspect this computer</Button>}
            </div>
          ) : (
            <div className="space-y-4 rounded-xl border border-zinc-800 bg-black p-4">
              <div className="space-y-2"><Label htmlFor="onboarding-cloud-provider">AI service</Label><Select onValueChange={(value) => { if (!value) return; const kind = value as ProviderKind; const preset = getProviderPreset(kind); setCloudKind(kind); setCloudBaseUrl(preset.baseUrl); setCloudModel(preset.defaultModel); setCloudApiKey(""); }} value={cloudKind}><SelectTrigger className="w-full bg-[#080808]" id="onboarding-cloud-provider"><SelectValue /></SelectTrigger><SelectContent>{cloudKinds.map((kind) => { const preset = getProviderPreset(kind); return <SelectItem key={kind} value={kind}>{preset.label}</SelectItem>; })}</SelectContent></Select></div>
              {cloudKind === "openai-compatible" ? <div className="space-y-2"><Label htmlFor="onboarding-cloud-url">API base URL</Label><Input id="onboarding-cloud-url" onChange={(event) => setCloudBaseUrl(event.target.value)} placeholder="http://127.0.0.1:1234/v1" required type="url" value={cloudBaseUrl} /></div> : null}
              <div className="space-y-2"><Label htmlFor="onboarding-cloud-model">Model</Label><Input id="onboarding-cloud-model" onChange={(event) => setCloudModel(event.target.value)} required value={cloudModel} /></div>
              <div className="space-y-2"><div className="flex justify-between"><Label htmlFor="onboarding-cloud-key">API key</Label><span className="text-[10px] text-zinc-600">{storedCloudKey ? "Stored · blank keeps it" : selectedPreset.apiKeyRequired ? "Required" : "Optional"}</span></div><Input autoComplete="off" id="onboarding-cloud-key" onChange={(event) => setCloudApiKey(event.target.value)} placeholder={storedCloudKey ? "••••••••••••" : selectedPreset.keyPlaceholder} required={selectedPreset.apiKeyRequired && !storedCloudKey} type="password" value={cloudApiKey} /></div>
              <div className="flex flex-col gap-3 rounded-lg border border-zinc-900 bg-[#050505] p-3 sm:flex-row sm:items-center sm:justify-between"><p className="text-[10px] leading-4 text-zinc-600">{selectedPreset.credentialHelp}</p><a className={cn(buttonVariants({ size: "sm", variant: "outline" }), "shrink-0")} href={selectedPreset.credentialUrl} rel="noreferrer" target="_blank">{selectedPreset.credentialLabel}<ExternalLink /></a></div>
              <Button className="w-full" disabled={!cloudCanConnect || busy === "provider"} onClick={() => void connectProvider({ kind: cloudKind, baseUrl: cloudBaseUrl, model: cloudModel, apiKey: cloudApiKey })}>{busy === "provider" ? <Loader2 className="animate-spin" /> : <ShieldCheck />}Connect and verify cloud AI</Button>
              <Button className="w-full text-zinc-500" onClick={onOpenAdvancedAi} variant="ghost">Advanced discovery for an unknown API <ArrowRight /></Button>
            </div>
          )}
          {state.onboarding.aiConfigured && !state.onboarding.aiVerified ? <Button className="w-full" disabled={busy === "provider"} onClick={() => void verifySavedProvider()} variant="outline">{busy === "provider" ? <Loader2 className="animate-spin" /> : <RefreshCw />}Verify saved connection</Button> : null}
          <div className="flex flex-col-reverse gap-2 border-t border-zinc-900 pt-5 sm:flex-row sm:justify-between"><Button onClick={() => void goTo("storage")} variant="ghost"><ArrowLeft />Back</Button><Button disabled={!state.onboarding.aiVerified} onClick={() => void goTo("brand")}>Continue to brand <ArrowRight /></Button></div>
        </div>
      );
    }

    if (currentStep === "brand") {
      return (
        <div className="space-y-5 p-4 sm:p-6"><div><Badge className="border-zinc-700 text-zinc-400" variant="outline">STEP 3 OF 3</Badge><h2 className="mt-3 text-xl font-semibold text-white">Confirm your brand</h2><p className="mt-2 text-xs leading-5 text-zinc-500">These are the facts and guardrails Socium may use. Save creates a numbered, auditable revision.</p></div><BrandProfileCard key={`${state.workspace.profileVersion}-${state.workspace.updatedAt ?? "new"}`} onStateChange={onStateChange} workspace={state.workspace} /><div className="flex flex-col-reverse gap-2 border-t border-zinc-900 pt-5 sm:flex-row sm:justify-between"><Button onClick={() => void goTo("ai")} variant="ghost"><ArrowLeft />Back</Button><Button disabled={!state.onboarding.brandConfirmed} onClick={() => void goTo("finish")}>Review setup <ArrowRight /></Button></div></div>
      );
    }

    return (
      <div className="grid min-h-[500px] place-items-center p-6 sm:p-10"><div className="w-full max-w-2xl"><div className="text-center"><div className="mx-auto grid size-16 place-items-center rounded-full border border-emerald-500/30 bg-emerald-500/10 text-emerald-300"><CheckCircle2 className="size-7" /></div><h2 className="mt-5 text-2xl font-semibold tracking-[-0.04em] text-white">Ready for your first draft</h2><p className="mx-auto mt-3 max-w-lg text-sm leading-6 text-zinc-500">Dashboard approval is already available. Telegram, Slack, and publishing destinations remain optional.</p></div><div className="mt-7 grid gap-3"><ReadinessRow complete={state.onboarding.storageConfirmed} detail={`${state.storage.locations.data.path} · models: ${state.storage.locations.models.path}`} label="Durable storage confirmed" /><ReadinessRow complete={state.onboarding.aiVerified} detail={`${state.provider.kind} · ${state.provider.model}`} label="AI connection verified" /><ReadinessRow complete={state.onboarding.brandConfirmed} detail={`Confirmed brand profile revision ${state.workspace.profileVersion}`} label="Brand context confirmed" /></div><div className="mt-7 flex flex-col-reverse gap-2 sm:flex-row sm:justify-between"><Button onClick={() => void goTo("brand")} variant="ghost"><ArrowLeft />Back</Button><Button disabled={!state.onboarding.ready || busy === "complete"} onClick={() => void complete()} size="lg">{busy === "complete" ? <Loader2 className="animate-spin" /> : <Sparkles />}Finish setup</Button></div></div></div>
    );
  }

  const stepBody = renderStepBody();

  return (
    <Dialog onOpenChange={(next) => { if (next) onOpenChange(true); }} open={open}>
      <DialogContent className="max-h-[calc(100vh-2rem)] max-w-[min(1120px,calc(100vw-2rem))] gap-0 overflow-hidden border-zinc-700 bg-[#070707] p-0" showCloseButton={false}>
        <DialogHeader className="sr-only"><DialogTitle>Socium first-run setup</DialogTitle><DialogDescription>Configure private storage, one AI provider, and a confirmed brand profile.</DialogDescription></DialogHeader>
        <div className="grid min-h-[620px] lg:grid-cols-[220px_minmax(0,1fr)]">
          <aside className="hidden border-r border-zinc-900 bg-black/70 p-5 lg:flex lg:flex-col">
            <div><p className="text-xs font-semibold tracking-[0.16em] text-zinc-200 uppercase">SOCIUM</p><p className="mt-1 font-mono text-[9px] text-zinc-700">LOCAL SETUP · V1</p></div>
            <ol className="mt-8 space-y-2">{steps.map((step, index) => { const active = step.id === currentStep; const complete = index < currentIndex || (step.id === "finish" && state.onboarding.status === "completed"); return <li className={cn("flex items-center gap-3 rounded-lg border px-3 py-2.5", active ? "border-amber-500/25 bg-amber-500/7" : "border-transparent")} key={step.id}><span className={cn("grid size-6 place-items-center rounded-full border font-mono text-[9px]", complete ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" : active ? "border-amber-500/30 text-amber-300" : "border-zinc-800 text-zinc-700")}>{complete ? <Check className="size-3" /> : index + 1}</span><span className={cn("text-xs", active ? "text-zinc-100" : "text-zinc-600")}>{step.label}</span></li>; })}</ol>
            <div className="mt-auto rounded-lg border border-zinc-900 bg-[#050505] p-3"><div className="flex items-center gap-2 text-[10px] text-zinc-500"><LockKeyhole className="size-3.5 text-emerald-400" />No Socium account</div><p className="mt-2 text-[9px] leading-4 text-zinc-700">Progress is stored only in your local SQLite database.</p></div>
          </aside>
          <div className="flex min-w-0 flex-col overflow-hidden">
            <div className="flex items-center justify-between gap-4 border-b border-zinc-900 px-5 py-3"><div className="min-w-0 flex-1"><div className="flex justify-between font-mono text-[9px] text-zinc-600"><span>{steps[currentIndex]?.label ?? "Setup"}</span><span>{Math.round(((currentIndex + 1) / steps.length) * 100)}%</span></div><Progress aria-label="First-run setup progress" className="mt-2 h-1" value={((currentIndex + 1) / steps.length) * 100} /></div><Button disabled={busy === "dismiss"} onClick={() => void dismiss()} size="sm" variant="ghost">Set up later</Button></div>
            <div className="min-h-0 flex-1 overflow-y-auto">{stepBody}</div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
