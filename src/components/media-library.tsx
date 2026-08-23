"use client";

import {
  AlertTriangle,
  Check,
  Crop,
  FileImage,
  HardDrive,
  ImageIcon,
  KeyRound,
  Loader2,
  Pencil,
  PlugZap,
  Plus,
  RefreshCw,
  RotateCcw,
  Send,
  ShieldCheck,
  Trash2,
  Upload,
  WandSparkles,
  X,
} from "lucide-react";
import Image from "next/image";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { CredentialHelp } from "@/components/credential-help";
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
import { Separator } from "@/components/ui/separator";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import type {
  ImageProviderKind,
  MediaAsset,
  MediaGenerationJob,
  MediaLibraryResponse,
  ProviderConnectionResult,
  PublicAppState,
  PublicImageProviderSettings,
} from "@/lib/app-types";
import { requestJson } from "@/lib/api";
import { cn } from "@/lib/utils";

type TransformPreset = "square" | "portrait" | "landscape";

type Props = {
  imageProvider: PublicImageProviderSettings;
  initialGenerationBrief?: {
    id: string;
    prompt: string;
    negativePrompt: string;
    altText: string;
  } | null;
  onStateChange: (state: PublicAppState) => void;
  onUseInDraft: (asset: MediaAsset) => void;
};

const transformLabels: Record<TransformPreset, string> = {
  square: "Square 1080",
  portrait: "Portrait 4:5",
  landscape: "Landscape",
};

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(value),
  );
}

async function uploadAsset(file: File) {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/api/media", { method: "POST", body });
  const payload = await response.json().catch(() => ({})) as {
    asset?: MediaAsset;
    deduplicated?: boolean;
    error?: string;
  };
  if (!response.ok || !payload.asset) {
    throw new Error(payload.error || `Upload failed (${response.status}).`);
  }
  return { asset: payload.asset, deduplicated: Boolean(payload.deduplicated) };
}

export function MediaLibrary({ imageProvider, initialGenerationBrief, onStateChange, onUseInDraft }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const generationActiveRef = useRef(false);
  const [library, setLibrary] = useState<MediaLibraryResponse | null>(null);
  const [generationJobs, setGenerationJobs] = useState<MediaGenerationJob[]>([]);
  const [pollGenerations, setPollGenerations] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [editAsset, setEditAsset] = useState<MediaAsset | null>(null);
  const [editForm, setEditForm] = useState({ altText: "", publicSourceUrl: "" });
  const [deleteAsset, setDeleteAsset] = useState<MediaAsset | null>(null);
  const [imageProviderForm, setImageProviderForm] = useState({
    kind: imageProvider.kind,
    baseUrl: imageProvider.baseUrl,
    model: imageProvider.model,
    apiKey: "",
    workflowJson: "",
  });
  const [generateForm, setGenerateForm] = useState({
    prompt: initialGenerationBrief?.prompt ?? "",
    negativePrompt: initialGenerationBrief?.negativePrompt ?? "",
    altText: initialGenerationBrief?.altText ?? "",
    preset: "square" as TransformPreset,
    quality: "auto" as "low" | "medium" | "high" | "auto",
    steps: 28,
    guidanceScale: 7,
    seed: -1,
  });

  const loadLibrary = useCallback(async () => {
    setLoading(true);
    try {
      setLibrary(await requestJson<MediaLibraryResponse>("/api/media", { cache: "no-store" }));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not load the media library.");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadGenerationJobs = useCallback(async () => {
    const response = await requestJson<{ items: MediaGenerationJob[] }>(
      "/api/media/generations?limit=20",
      { cache: "no-store" },
    );
    setGenerationJobs(response.items);
    return response.items;
  }, []);

  useEffect(() => {
    let cancelled = false;
    void requestJson<MediaLibraryResponse>("/api/media", { cache: "no-store" })
      .then((response) => {
        if (!cancelled) setLibrary(response);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          toast.error(error instanceof Error ? error.message : "Could not load the media library.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    void requestJson<{ items: MediaGenerationJob[] }>("/api/media/generations?limit=20", {
      cache: "no-store",
    })
      .then((response) => {
        if (cancelled) return;
        setGenerationJobs(response.items);
        const items = response.items;
        const active = items.some((job) => ["queued", "retrying", "running"].includes(job.status));
        generationActiveRef.current = active;
        setPollGenerations(active);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          toast.error(error instanceof Error ? error.message : "Could not load image generation jobs.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [loadGenerationJobs]);

  useEffect(() => {
    if (!pollGenerations) return;
    let cancelled = false;
    const poll = async () => {
      try {
        const items = await loadGenerationJobs();
        const active = items.some((job) => ["queued", "retrying", "running"].includes(job.status));
        if (!cancelled && generationActiveRef.current && !active) {
          await loadLibrary();
          generationActiveRef.current = false;
          setPollGenerations(false);
        }
      } catch {
        // A later poll retries transient localhost startup or navigation races.
      }
    };
    void poll();
    const timer = setInterval(() => void poll(), 1500);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [loadGenerationJobs, loadLibrary, pollGenerations]);

  async function submitUpload(event: FormEvent) {
    event.preventDefault();
    if (!uploadFile) return;
    setBusy("upload");
    try {
      const result = await uploadAsset(uploadFile);
      setUploadFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      await loadLibrary();
      toast.success(result.deduplicated ? "Existing asset reused" : "Image stored locally", {
        description: result.deduplicated
          ? "The same image was already in your library."
          : `${result.asset.width}×${result.asset.height} · ${formatBytes(result.asset.byteSize)}`,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Image upload failed.");
    } finally {
      setBusy(null);
    }
  }

  function changeProviderKind(kind: ImageProviderKind) {
    setImageProviderForm({
      kind,
      baseUrl: kind === "automatic1111" ? "http://127.0.0.1:7860" : kind === "comfyui" ? "http://127.0.0.1:8188" : "https://api.openai.com/v1",
      model: kind === "openai-images" ? "gpt-image-2" : "",
      apiKey: "",
      workflowJson: "",
    });
  }

  async function saveImageProvider(verify: boolean) {
    setBusy(verify ? "image-provider-test" : "image-provider-save");
    try {
      const response = await requestJson<{ ok: boolean; state: PublicAppState }>(
        "/api/settings/image-provider",
        { method: "PUT", body: JSON.stringify(imageProviderForm) },
      );
      onStateChange(response.state);
      if (verify) {
        const result = await requestJson<ProviderConnectionResult>("/api/image-providers/test", {
          method: "POST",
        });
        toast.success("Image provider connected", { description: result.message });
      } else {
        toast.success("Image provider settings saved");
      }
      setImageProviderForm((current) => ({ ...current, apiKey: "", workflowJson: "" }));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save the image provider.");
    } finally {
      setBusy(null);
    }
  }

  async function generateAsset(event: FormEvent) {
    event.preventDefault();
    setBusy("generate-image");
    try {
      const response = await requestJson<{
        ok: boolean;
        job: MediaGenerationJob;
      }>("/api/media/generations", {
        method: "POST",
        body: JSON.stringify(generateForm),
      });
      generationActiveRef.current = true;
      setPollGenerations(true);
      setGenerationJobs((current) => [response.job, ...current.filter((job) => job.id !== response.job.id)]);
      void loadGenerationJobs();
      toast.success("Image generation queued", {
        description: "You can leave this screen; the restart-safe local worker will continue.",
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Image generation failed.");
    } finally {
      setBusy(null);
    }
  }

  async function updateGenerationJob(job: MediaGenerationJob, action: "cancel" | "retry") {
    setBusy(`${action}-generation-${job.id}`);
    try {
      const response = await requestJson<{ job: MediaGenerationJob }>(
        `/api/media/generations/${job.id}/${action}`,
        { method: "POST" },
      );
      setGenerationJobs((current) => current.map((item) => item.id === job.id ? response.job : item));
      if (action === "retry") {
        generationActiveRef.current = true;
        setPollGenerations(true);
        void loadGenerationJobs();
      }
      toast.success(action === "cancel" ? "Cancellation requested" : "Image generation queued again");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : `Could not ${action} this generation.`);
    } finally {
      setBusy(null);
    }
  }

  function openEdit(asset: MediaAsset) {
    setEditAsset(asset);
    setEditForm({ altText: asset.altText, publicSourceUrl: asset.publicSourceUrl ?? "" });
  }

  async function saveMetadata(event: FormEvent) {
    event.preventDefault();
    if (!editAsset) return;
    setBusy(`edit-${editAsset.id}`);
    try {
      const response = await requestJson<{ ok: boolean; asset: MediaAsset }>(`/api/media/${editAsset.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          altText: editForm.altText,
          publicSourceUrl: editForm.publicSourceUrl || null,
        }),
      });
      setLibrary((current) => current ? {
        ...current,
        items: current.items.map((item) => item.id === response.asset.id ? response.asset : item),
      } : current);
      setEditAsset(null);
      toast.success("Media metadata saved");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save media metadata.");
    } finally {
      setBusy(null);
    }
  }

  async function transformAsset(asset: MediaAsset, preset: TransformPreset) {
    setBusy(`transform-${asset.id}-${preset}`);
    try {
      const response = await requestJson<{ ok: boolean; asset: MediaAsset; deduplicated: boolean }>(
        `/api/media/${asset.id}/transform`,
        { method: "POST", body: JSON.stringify({ preset }) },
      );
      await loadLibrary();
      toast.success(response.deduplicated ? "Existing transform reused" : `${transformLabels[preset]} created`, {
        description: response.asset.originalName,
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Image transform failed.");
    } finally {
      setBusy(null);
    }
  }

  async function confirmDelete() {
    if (!deleteAsset) return;
    setBusy(`delete-${deleteAsset.id}`);
    try {
      await requestJson<{ ok: boolean; message: string }>(`/api/media/${deleteAsset.id}`, {
        method: "DELETE",
      });
      setLibrary((current) => current ? {
        ...current,
        items: current.items.filter((item) => item.id !== deleteAsset.id),
        total: Math.max(0, current.total - 1),
      } : current);
      toast.success("Media asset deleted from this computer");
      setDeleteAsset(null);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not delete the media asset.");
    } finally {
      setBusy(null);
    }
  }

  const maximum = library?.maxUploadBytes ?? 10 * 1024 * 1024;

  return (
    <div className="space-y-5">
      <Card className="overflow-hidden border-violet-500/20 bg-[#050505] shadow-[0_0_70px_-36px_rgba(139,92,246,0.55)]">
        <CardHeader className="border-b border-zinc-900 bg-[radial-gradient(circle_at_top_left,rgba(139,92,246,0.18),transparent_34%),radial-gradient(circle_at_top_right,rgba(34,211,238,0.08),transparent_28%)]">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="grid size-11 place-items-center rounded-lg border border-violet-400/25 bg-violet-500/10 text-violet-200 shadow-[inset_0_0_18px_rgba(139,92,246,0.08)]">
                <WandSparkles className="size-5" />
              </div>
              <div>
                <CardTitle>AI image studio</CardTitle>
                <CardDescription>Generate one campaign visual, inspect it locally, then decide where it belongs.</CardDescription>
              </div>
            </div>
            <Badge className={cn(
              "border-zinc-800 bg-black/70",
              imageProvider.configured ? "text-emerald-300" : "text-amber-300",
            )} variant="outline">
              <span className={cn("mr-1.5 size-1.5 rounded-full", imageProvider.configured ? "bg-emerald-400" : "bg-amber-400")} />
              {imageProvider.configured ? "Provider saved" : "Setup required"}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="grid gap-6 p-0 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.65fr)]">
          <form className="space-y-4 p-5 sm:p-6" onSubmit={generateAsset}>
            <div className="space-y-2">
              <Label htmlFor="image-prompt">Campaign image prompt</Label>
              <Textarea
                id="image-prompt"
                maxLength={4000}
                onChange={(event) => setGenerateForm((current) => ({ ...current, prompt: event.target.value }))}
                placeholder="A premium editorial product scene for a local coffee brand, deep charcoal background, warm rim light, no text..."
                required
                rows={5}
                value={generateForm.prompt}
              />
              <div className="flex justify-between text-[10px] text-zinc-600"><span>Be specific about subject, setting, lighting, and exclusions.</span><span>{generateForm.prompt.length}/4000</span></div>
            </div>
            {imageProvider.kind !== "openai-images" ? (
              <div className="space-y-2">
                <Label htmlFor="image-negative-prompt">Negative prompt</Label>
                <Textarea id="image-negative-prompt" maxLength={2000} onChange={(event) => setGenerateForm((current) => ({ ...current, negativePrompt: event.target.value }))} placeholder="blurry, watermark, distorted text" rows={2} value={generateForm.negativePrompt} />
              </div>
            ) : null}
            <div className="space-y-2">
              <Label htmlFor="image-alt-text">Planned alt text</Label>
              <Textarea id="image-alt-text" maxLength={500} onChange={(event) => setGenerateForm((current) => ({ ...current, altText: event.target.value }))} placeholder="Concise description for people who cannot see the final visual" rows={2} value={generateForm.altText} />
              <p className="text-[10px] leading-4 text-zinc-600">Saved with the generated asset and editable before publishing.</p>
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="image-preset">Aspect</Label>
                <Select onValueChange={(value) => setGenerateForm((current) => ({ ...current, preset: value as TransformPreset }))} value={generateForm.preset}>
                  <SelectTrigger className="w-full bg-black" id="image-preset"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="square">Square 1:1</SelectItem><SelectItem value="portrait">Portrait 4:5</SelectItem><SelectItem value="landscape">Landscape</SelectItem></SelectContent>
                </Select>
              </div>
              {imageProvider.kind === "openai-images" ? (
                <div className="space-y-2 sm:col-span-2">
                  <Label htmlFor="image-quality">Quality</Label>
                  <Select onValueChange={(value) => setGenerateForm((current) => ({ ...current, quality: value as "low" | "medium" | "high" | "auto" }))} value={generateForm.quality}>
                    <SelectTrigger className="w-full bg-black" id="image-quality"><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="auto">Auto</SelectItem><SelectItem value="low">Low</SelectItem><SelectItem value="medium">Medium</SelectItem><SelectItem value="high">High</SelectItem></SelectContent>
                  </Select>
                </div>
              ) : (
                <>
                  <div className="space-y-2"><Label htmlFor="image-steps">Steps</Label><Input id="image-steps" max={80} min={1} onChange={(event) => setGenerateForm((current) => ({ ...current, steps: Number(event.target.value) }))} type="number" value={generateForm.steps} /></div>
                  <div className="space-y-2"><Label htmlFor="image-guidance">Guidance</Label><Input id="image-guidance" max={20} min={1} onChange={(event) => setGenerateForm((current) => ({ ...current, guidanceScale: Number(event.target.value) }))} step={0.5} type="number" value={generateForm.guidanceScale} /></div>
                </>
              )}
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-900 pt-4">
              <p className="max-w-md text-[11px] leading-5 text-zinc-600"><ShieldCheck className="mr-1.5 inline size-3.5 text-emerald-400" />Generated bytes are validated and saved privately. This action never creates or publishes a post.</p>
              <Button disabled={!imageProvider.configured || !generateForm.prompt.trim() || busy === "generate-image"} size="lg" type="submit">
                {busy === "generate-image" ? <Loader2 className="animate-spin" /> : <WandSparkles />} Generate image
              </Button>
            </div>
          </form>

          <div className="border-t border-zinc-900 bg-[#030303] p-5 xl:border-t-0 xl:border-l sm:p-6">
            <div className="mb-4 flex items-center gap-2"><KeyRound className="size-4 text-cyan-300" /><h2 className="text-sm font-semibold text-zinc-200">Image provider</h2></div>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="image-provider-kind">Adapter</Label>
                <Select onValueChange={(value) => changeProviderKind(value as ImageProviderKind)} value={imageProviderForm.kind}>
                  <SelectTrigger className="w-full bg-black" id="image-provider-kind"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="comfyui">ComfyUI workflow</SelectItem><SelectItem value="automatic1111">Automatic1111 / Forge</SelectItem><SelectItem value="openai-images">OpenAI-compatible Images API</SelectItem></SelectContent>
                </Select>
              </div>
              <div className="space-y-2"><Label htmlFor="image-provider-url">Base URL</Label><Input id="image-provider-url" onChange={(event) => setImageProviderForm((current) => ({ ...current, baseUrl: event.target.value }))} required type="url" value={imageProviderForm.baseUrl} /><p className="text-[10px] text-zinc-600">{imageProviderForm.kind === "automatic1111" ? "Start WebUI with --api. Forge uses the same endpoint." : imageProviderForm.kind === "comfyui" ? "Default local ComfyUI server: http://127.0.0.1:8188" : "Use an API root or a URL ending in /v1."}</p></div>
              <div className="space-y-2"><Label htmlFor="image-provider-model">Model {imageProviderForm.kind !== "openai-images" ? "(optional label/checkpoint)" : ""}</Label><Input id="image-provider-model" onChange={(event) => setImageProviderForm((current) => ({ ...current, model: event.target.value }))} placeholder={imageProviderForm.kind === "automatic1111" ? "Use active checkpoint" : imageProviderForm.kind === "comfyui" ? "Workflow model" : "gpt-image-2"} required={imageProviderForm.kind === "openai-images"} value={imageProviderForm.model} /></div>
              {imageProviderForm.kind === "comfyui" ? <div className="space-y-2"><Label htmlFor="comfy-workflow">Workflow (API format JSON)</Label><Textarea className="min-h-32 font-mono text-[11px]" id="comfy-workflow" maxLength={200000} onChange={(event) => setImageProviderForm((current) => ({ ...current, workflowJson: event.target.value }))} placeholder={imageProvider.hasWorkflow ? "Stored workflow — leave blank to keep it" : "Paste ComfyUI's Save (API Format) JSON. Replace values with {{prompt}}, {{negative_prompt}}, {{seed}}, {{width}}, {{height}}, {{steps}}, or {{guidance_scale}}."} value={imageProviderForm.workflowJson} /><p className="text-[10px] leading-4 text-zinc-600">The workflow stays on this computer. Socium injects only declared placeholders and reads the first image output.</p></div> : null}
              <div className="space-y-2">
                <Label htmlFor="image-provider-key">API key</Label>
                <Input autoComplete="off" id="image-provider-key" onChange={(event) => setImageProviderForm((current) => ({ ...current, apiKey: event.target.value }))} placeholder={imageProvider.hasApiKey ? "Stored — blank keeps current key" : "Optional for local; required by most hosted APIs"} type="password" value={imageProviderForm.apiKey} />
                {imageProviderForm.kind === "openai-images" ? (
                  <CredentialHelp
                    description="For this field: create an OpenAI Platform API key and paste it above. A ChatGPT subscription does not include API credits."
                    primary={{ href: "https://platform.openai.com/api-keys", label: "Get Images API key" }}
                    secondary={{ href: "https://platform.openai.com/docs/guides/images", label: "Images guide" }}
                  />
                ) : (
                  <CredentialHelp
                    description={imageProviderForm.kind === "automatic1111" ? "This field is only for optional local --api-auth. Enter username:password; there is no provider token." : "Normal local ComfyUI has no token for this field. Leave it blank unless your own proxy requires one."}
                    primary={{ href: imageProviderForm.kind === "automatic1111" ? "https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/API" : "https://docs.comfy.org/development/core-concepts/api-server", label: "Local setup guide" }}
                  />
                )}
              </div>
              <div className="grid grid-cols-2 gap-2 pt-1">
                <Button disabled={busy === "image-provider-save" || busy === "image-provider-test"} onClick={() => void saveImageProvider(false)} type="button" variant="outline">{busy === "image-provider-save" ? <Loader2 className="animate-spin" /> : <Check />} Save</Button>
                <Button disabled={busy === "image-provider-save" || busy === "image-provider-test"} onClick={() => void saveImageProvider(true)} type="button">{busy === "image-provider-test" ? <Loader2 className="animate-spin" /> : <PlugZap />} Save & test</Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {generationJobs.length ? (
        <Card className="overflow-hidden border-cyan-500/15 bg-[#050505]">
          <CardHeader className="border-b border-zinc-900">
            <div className="flex items-center justify-between gap-3"><div><CardTitle>Generation queue</CardTitle><CardDescription>Durable local jobs continue across navigation and restart safely after interruption.</CardDescription></div><Badge className="border-cyan-500/20 bg-cyan-500/5 text-cyan-300" variant="outline">{generationJobs.filter((job) => ["queued", "retrying", "running"].includes(job.status)).length} active</Badge></div>
          </CardHeader>
          <CardContent className="space-y-3 p-4 sm:p-5">
            {generationJobs.slice(0, 6).map((job) => (
              <div className="rounded-lg border border-zinc-900 bg-black p-4" key={job.id}>
                <div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><Badge className={cn("border-zinc-800 bg-zinc-950", job.status === "completed" ? "text-emerald-300" : job.status === "failed" ? "text-red-300" : job.status === "cancelled" ? "text-zinc-500" : "text-cyan-300")} variant="outline">{job.status}</Badge><span className="font-mono text-[10px] text-zinc-700">{job.payload.provider.kind}</span></div><p className="mt-2 line-clamp-2 text-xs leading-5 text-zinc-400">{job.payload.request.prompt}</p></div><div className="flex gap-2">{["queued", "retrying", "running"].includes(job.status) ? <Button disabled={busy === `cancel-generation-${job.id}` || job.cancelRequested} onClick={() => void updateGenerationJob(job, "cancel")} size="sm" type="button" variant="ghost">{busy === `cancel-generation-${job.id}` ? <Loader2 className="animate-spin" /> : <X />}Cancel</Button> : null}{["failed", "cancelled", "missed"].includes(job.status) ? <Button disabled={busy === `retry-generation-${job.id}`} onClick={() => void updateGenerationJob(job, "retry")} size="sm" type="button" variant="outline">{busy === `retry-generation-${job.id}` ? <Loader2 className="animate-spin" /> : <RotateCcw />}Retry</Button> : null}</div></div>
                <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-zinc-900"><div className={cn("h-full rounded-full transition-[width] duration-500", job.status === "failed" ? "bg-red-500" : job.status === "cancelled" ? "bg-zinc-700" : "bg-gradient-to-r from-violet-500 to-cyan-400")} style={{ width: `${job.progressPercent}%` }} /></div>
                <div className="mt-2 flex flex-wrap justify-between gap-2 text-[10px] text-zinc-600"><span>{job.progressMessage ?? "Waiting for status."}</span><span>{job.progressPercent}% · attempt {job.attempts}/{job.maxAttempts}</span></div>
                {job.lastError ? <p className="mt-2 text-xs leading-5 text-red-300">{job.lastError}</p> : null}
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        <Card className="overflow-hidden border-zinc-800 bg-[#060606]">
          <CardHeader className="border-b border-zinc-900 bg-[radial-gradient(circle_at_top_left,rgba(168,85,247,0.12),transparent_38%)]">
            <div className="flex items-center gap-3">
              <div className="grid size-10 place-items-center rounded-md border border-violet-500/20 bg-violet-500/5 text-violet-300">
                <Upload className="size-4" />
              </div>
              <div>
                <CardTitle>Import a local image</CardTitle>
                <CardDescription>Verified raster files are stored under the private Socium data directory.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={submitUpload}>
              <div className="rounded-lg border border-dashed border-zinc-700 bg-black p-5">
                <Label className="sr-only" htmlFor="media-upload">Choose local image file</Label>
                <input
                  accept="image/jpeg,image/png,image/webp"
                  className="sr-only"
                  id="media-upload"
                  onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                  ref={fileInputRef}
                  type="file"
                />
                <div className="flex flex-col items-center gap-3 text-center sm:flex-row sm:text-left">
                  <div className="grid size-12 shrink-0 place-items-center rounded-lg border border-zinc-800 bg-zinc-950 text-zinc-500">
                    <FileImage className="size-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-zinc-200">
                      {uploadFile?.name ?? "JPEG, PNG, or WebP"}
                    </p>
                    <p className="mt-1 text-xs text-zinc-600">
                      {uploadFile ? formatBytes(uploadFile.size) : `Maximum ${formatBytes(maximum)} · decoded content is verified`}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <Button onClick={() => fileInputRef.current?.click()} type="button" variant="outline">
                      <Plus /> Choose image
                    </Button>
                    <Button disabled={!uploadFile || busy === "upload"} type="submit">
                      {busy === "upload" ? <Loader2 className="animate-spin" /> : <Upload />}
                      Store locally
                    </Button>
                  </div>
                </div>
              </div>
            </form>
          </CardContent>
        </Card>

        <Card className="border-zinc-800 bg-[#050505]">
          <CardHeader>
            <div className="flex items-center justify-between gap-3">
              <div>
                <CardTitle>Storage boundary</CardTitle>
                <CardDescription>Private by default, explicit when external.</CardDescription>
              </div>
              <HardDrive className="size-4 text-violet-400" />
            </div>
          </CardHeader>
          <CardContent className="space-y-3 text-xs leading-5 text-zinc-500">
            <div className="flex gap-2"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-emerald-400" /><span>Originals and previews stay on this computer with random storage names.</span></div>
            <Separator className="bg-zinc-900" />
            <div className="flex gap-2"><AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-400" /><span>Instagram cannot fetch a localhost file. Add an HTTPS source only when the same asset is publicly hosted.</span></div>
          </CardContent>
        </Card>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold tracking-[0.16em] text-zinc-600 uppercase">Local assets</p>
          <h2 className="mt-1 text-lg font-semibold text-zinc-100">{library?.total ?? 0} stored image{library?.total === 1 ? "" : "s"}</h2>
        </div>
        <Button disabled={loading} onClick={() => void loadLibrary()} type="button" variant="outline">
          <RefreshCw className={cn(loading && "animate-spin")} /> Refresh
        </Button>
      </div>

      {loading && !library ? (
        <div className="grid min-h-60 place-items-center rounded-lg border border-zinc-900 bg-[#050505] text-zinc-600">
          <Loader2 className="size-5 animate-spin" />
        </div>
      ) : library?.items.length ? (
        <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {library.items.map((asset) => (
            <Card className="group overflow-hidden border-zinc-800 bg-[#060606]" key={asset.id}>
              <div className="relative aspect-[16/10] overflow-hidden border-b border-zinc-900 bg-black">
                <Image
                  alt={asset.altText || `Preview of ${asset.originalName}`}
                  className="object-contain transition-transform duration-300 group-hover:scale-[1.02]"
                  fill
                  sizes="(min-width: 1536px) 30vw, (min-width: 768px) 45vw, 100vw"
                  src={asset.previewUrl}
                  unoptimized
                />
                <div className="absolute top-3 left-3 flex gap-2">
                  <Badge className="border-black/50 bg-black/80 text-zinc-300" variant="outline">{asset.source.replace("transform:", "")}</Badge>
                  {asset.instagramReady ? <Badge className="border-emerald-500/30 bg-black/80 text-emerald-300" variant="outline">HTTPS ready</Badge> : null}
                </div>
              </div>
              <CardContent className="space-y-4 p-4">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-zinc-200" title={asset.originalName}>{asset.originalName}</p>
                  <p className="mt-1 font-mono text-[10px] text-zinc-600">{asset.width}×{asset.height} · {formatBytes(asset.byteSize)} · {asset.mimeType.replace("image/", "")}</p>
                </div>
                {asset.generationPrompt ? (
                  <div className="rounded-md border border-violet-500/15 bg-violet-500/[0.04] p-3">
                    <div className="mb-1.5 flex items-center gap-2 text-[10px] font-semibold tracking-[0.12em] text-violet-300 uppercase"><WandSparkles className="size-3" /> AI provenance</div>
                    <p className="line-clamp-3 text-xs leading-5 text-zinc-400" title={asset.generationPrompt}>{asset.generationPrompt}</p>
                    <p className="mt-2 truncate font-mono text-[10px] text-zinc-600">{asset.generationProvider} · {asset.generationModel}</p>
                  </div>
                ) : null}
                <div className="grid grid-cols-3 gap-2">
                  {(Object.keys(transformLabels) as TransformPreset[]).map((preset) => (
                    <Button
                      aria-label={`Create ${transformLabels[preset]} transform of ${asset.originalName}`}
                      disabled={busy?.startsWith(`transform-${asset.id}`)}
                      key={preset}
                      onClick={() => void transformAsset(asset, preset)}
                      size="sm"
                      type="button"
                      variant="outline"
                    >
                      {busy === `transform-${asset.id}-${preset}` ? <Loader2 className="animate-spin" /> : <Crop />}
                      <span className="hidden xl:inline">{preset}</span>
                    </Button>
                  ))}
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 border-t border-zinc-900 pt-3">
                  <div className="flex gap-1">
                    <Button aria-label={`Edit ${asset.originalName}`} onClick={() => openEdit(asset)} size="icon-sm" type="button" variant="ghost"><Pencil /></Button>
                    <Button aria-label={`Delete ${asset.originalName}`} onClick={() => setDeleteAsset(asset)} size="icon-sm" type="button" variant="ghost"><Trash2 /></Button>
                  </div>
                  <Button
                    disabled={!asset.instagramReady}
                    onClick={() => onUseInDraft(asset)}
                    size="sm"
                    title={asset.instagramReady ? "Use the public HTTPS source in an Instagram draft" : "Add a public HTTPS source first"}
                    type="button"
                  >
                    <Send /> Use in draft
                  </Button>
                </div>
                <p className="text-[10px] text-zinc-700">Stored {formatDate(asset.createdAt)}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : (
        <div className="grid min-h-64 place-items-center rounded-lg border border-zinc-900 bg-[#050505] px-6 text-center">
          <div>
            <div className="mx-auto grid size-12 place-items-center rounded-lg border border-zinc-800 bg-black text-zinc-600"><ImageIcon className="size-5" /></div>
            <h2 className="mt-4 text-sm font-medium text-zinc-200">No media stored yet</h2>
            <p className="mt-2 max-w-md text-xs leading-5 text-zinc-600">Upload the first campaign image. Socium will verify, fingerprint, preview, and store it locally.</p>
          </div>
        </div>
      )}

      <Dialog onOpenChange={(open) => !open && setEditAsset(null)} open={Boolean(editAsset)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Edit media metadata</DialogTitle>
            <DialogDescription>Alt text stays local. The optional HTTPS source must point to this same image.</DialogDescription>
          </DialogHeader>
          <form className="space-y-4" id="media-metadata-form" onSubmit={saveMetadata}>
            <div className="space-y-2">
              <Label htmlFor="media-alt-text">Alt text</Label>
              <Textarea id="media-alt-text" maxLength={500} onChange={(event) => setEditForm((current) => ({ ...current, altText: event.target.value }))} placeholder="Describe the image for accessibility" rows={3} value={editForm.altText} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="media-public-source">Public HTTPS source</Label>
              <Input id="media-public-source" onChange={(event) => setEditForm((current) => ({ ...current, publicSourceUrl: event.target.value }))} pattern="https://.+" placeholder="https://cdn.example.com/campaign.webp" type="url" value={editForm.publicSourceUrl} />
              <p className="text-[11px] leading-5 text-zinc-600">Required only when Meta must fetch the asset for Instagram publishing.</p>
            </div>
          </form>
          <DialogFooter className="border-zinc-800 bg-[#090909]">
            <Button onClick={() => setEditAsset(null)} type="button" variant="ghost"><X /> Cancel</Button>
            <Button disabled={Boolean(editAsset && busy === `edit-${editAsset.id}`)} form="media-metadata-form" type="submit">
              {editAsset && busy === `edit-${editAsset.id}` ? <Loader2 className="animate-spin" /> : <Check />} Save metadata
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog onOpenChange={(open) => !open && setDeleteAsset(null)} open={Boolean(deleteAsset)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete {deleteAsset?.originalName}?</DialogTitle>
            <DialogDescription>The original and generated preview will be removed from this computer.</DialogDescription>
          </DialogHeader>
          <div className="flex gap-2 rounded-md border border-red-500/20 bg-red-500/5 p-3 text-xs leading-5 text-red-200">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" /> This deletion cannot be undone. Existing remote copies are not affected.
          </div>
          <DialogFooter className="border-zinc-800 bg-[#090909]">
            <Button disabled={Boolean(deleteAsset && busy === `delete-${deleteAsset.id}`)} onClick={() => setDeleteAsset(null)} type="button" variant="ghost">Cancel</Button>
            <Button disabled={Boolean(deleteAsset && busy === `delete-${deleteAsset.id}`)} onClick={() => void confirmDelete()} type="button" variant="destructive">
              {deleteAsset && busy === `delete-${deleteAsset.id}` ? <Loader2 className="animate-spin" /> : <Trash2 />} Delete local files
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
