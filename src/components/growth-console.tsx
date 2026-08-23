"use client";

import Image from "next/image";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BookOpenCheck,
  Bot,
  Check,
  ChevronRight,
  CircleDot,
  Cloud,
  Clock3,
  Cpu,
  Database,
  Download,
  FilePenLine,
  Inbox,
  Images,
  LayoutDashboard,
  Loader2,
  LockKeyhole,
  Menu,
  MessageCircle,
  Pencil,
  Pause,
  Play,
  PlugZap,
  Plus,
  RefreshCw,
  Rocket,
  Send,
  SearchCheck,
  Settings2,
  ShieldCheck,
  Sparkles,
  SquareArrowOutUpRight,
  UsersRound,
  RadioTower,
  X,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { LeadsWorkspace } from "@/components/leads-workspace";
import { BrandProfileCard } from "@/components/brand-profile-card";
import { MediaLibrary } from "@/components/media-library";
import { OnboardingWizard } from "@/components/onboarding-wizard";
import { CredentialHelp } from "@/components/credential-help";
import {
  InstagramConnectorCard,
  type InstagramConnectorForm,
} from "@/components/instagram-connector-card";
import {
  LinkedInConnectorCard,
  type LinkedInConnectorForm,
} from "@/components/linkedin-connector-card";
import {
  LinkedInOrganizationConnectorCard,
  type LinkedInOrganizationConnectorForm,
} from "@/components/linkedin-organization-connector-card";
import {
  MetaConnectorCard,
  type MetaConnectorForm,
} from "@/components/meta-connector-card";
import { SeoWorkspace } from "@/components/seo-workspace";
import { SetupGuide } from "@/components/setup-guide";

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
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type {
  ConnectorAccount,
  ContentChannel,
  GeneratedPost,
  LocalJob,
  LocalJobStatus,
  LocalAiStatus,
  PostStatus,
  ProviderConnectionResult,
  ProviderDiscoveryResult,
  ProviderKind,
  ProviderProtocolHint,
  PublicAppState,
} from "@/lib/app-types";
import { requestJson } from "@/lib/api";
import { getProviderPreset, PROVIDER_PRESETS } from "@/lib/provider-presets";
import { cn } from "@/lib/utils";
import {
  WordPressConnectorCard,
  type WordPressConnectorForm,
} from "@/components/wordpress-connector-card";

type ViewId = "command" | "guide" | "create" | "queue" | "media" | "leads" | "seo" | "scheduler" | "integrations" | "activity";
type QueueFilter = "all" | PostStatus;

type StateResponse = {
  ok: boolean;
  state: PublicAppState;
};

type NavItem = {
  id: ViewId;
  label: string;
  icon: LucideIcon;
  preview?: boolean;
};

const navigation: NavItem[] = [
  { id: "command", label: "Command", icon: LayoutDashboard },
  { id: "guide", label: "Setup guide", icon: BookOpenCheck },
  { id: "create", label: "Create content", icon: Sparkles },
  { id: "queue", label: "Approval queue", icon: Inbox },
  { id: "media", label: "Media library", icon: Images },
  { id: "leads", label: "Lead intelligence", icon: UsersRound, preview: true },
  { id: "seo", label: "Local SEO lab", icon: SearchCheck, preview: true },
  { id: "scheduler", label: "Scheduler", icon: Clock3 },
  { id: "integrations", label: "Integrations", icon: PlugZap },
  { id: "activity", label: "Activity", icon: Activity },
];

const pageMeta: Record<ViewId, { eyebrow: string; title: string; description: string }> = {
  command: {
    eyebrow: "Personal social manager",
    title: "Growth command",
    description: "Live status for your AI content and human approval workflow.",
  },
  guide: {
    eyebrow: "Guided local setup",
    title: "Setup guide",
    description: "Connect the minimum required services and complete a safe first publishing workflow.",
  },
  create: {
    eyebrow: "AI content engine",
    title: "Create a draft",
    description: "Generate with your own provider. Nothing publishes without approval.",
  },
  queue: {
    eyebrow: "Human in the loop",
    title: "Approval queue",
    description: "Review the exact content version before it can leave this machine.",
  },
  media: {
    eyebrow: "Local creative vault",
    title: "Media library",
    description: "Verify, store, transform, and reuse campaign images without uploading them to Socium cloud.",
  },
  leads: {
    eyebrow: "Permission-aware intelligence",
    title: "Lead intelligence",
    description: "Import, deduplicate, qualify, and suppress business leads in your local database.",
  },
  seo: {
    eyebrow: "Evidence-backed optimization",
    title: "Local SEO lab",
    description: "Audit public pages, inspect weighted findings, and keep restart-safe local snapshots.",
  },
  scheduler: {
    eyebrow: "Durable local jobs",
    title: "Scheduler",
    description: "Restart-safe publishing with explicit missed-work recovery and duplicate protection.",
  },
  integrations: {
    eyebrow: "Bring your own stack",
    title: "Connections",
    description: "Connect local or hosted AI and outbound-only approval channels.",
  },
  activity: {
    eyebrow: "Local audit trail",
    title: "Activity",
    description: "A durable record of settings, approvals, and publishing actions.",
  },
};

const channelLabels: Record<ContentChannel, string> = {
  linkedin: "LinkedIn",
  "linkedin-company": "LinkedIn Company Page",
  instagram: "Instagram",
  facebook: "Facebook",
  x: "X / Twitter",
  telegram: "Telegram",
  blog: "Blog",
};

const channels = Object.entries(channelLabels) as [ContentChannel, string][];

function publisherDisplayName(channel: ContentChannel) {
  if (channel === "blog") return "WordPress";
  if (channel === "facebook") return "Facebook";
  if (channel === "instagram") return "Instagram";
  if (channel === "telegram") return "Telegram";
  return channelLabels[channel];
}

const statusStyles: Record<PostStatus, string> = {
  pending: "border-amber-500/25 bg-amber-500/8 text-amber-300",
  approved: "border-sky-500/25 bg-sky-500/8 text-sky-300",
  rejected: "border-zinc-700 bg-zinc-900 text-zinc-400",
  skipped: "border-zinc-700 bg-zinc-900 text-zinc-400",
  publishing: "border-violet-500/25 bg-violet-500/8 text-violet-300",
  published: "border-emerald-500/25 bg-emerald-500/8 text-emerald-300",
  failed: "border-red-500/25 bg-red-500/8 text-red-300",
};

const jobStatusStyles: Record<LocalJobStatus, string> = {
  queued: "border-sky-500/25 bg-sky-500/8 text-sky-300",
  retrying: "border-amber-500/25 bg-amber-500/8 text-amber-300",
  running: "border-violet-500/25 bg-violet-500/8 text-violet-300",
  completed: "border-emerald-500/25 bg-emerald-500/8 text-emerald-300",
  failed: "border-red-500/25 bg-red-500/8 text-red-300",
  cancelled: "border-zinc-800 bg-zinc-950 text-zinc-500",
  missed: "border-orange-500/25 bg-orange-500/8 text-orange-300",
  skipped: "border-zinc-800 bg-zinc-950 text-zinc-500",
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatCompactDate(value: string) {
  return new Intl.RelativeTimeFormat(undefined, { numeric: "auto" }).format(
    Math.round((new Date(value).getTime() - Date.now()) / 60_000),
    "minute",
  );
}

function formatBytes(value: number) {
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const unit = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  return `${(value / 1024 ** unit).toFixed(unit > 1 ? 1 : 0)} ${units[unit]}`;
}

function defaultScheduleAt() {
  const date = new Date(Date.now() + 60 * 60 * 1_000);
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function Brand() {
  return (
    <div className="flex items-center">
      <Image
        alt="Socium — Personal Social Manager"
        className="h-10 w-auto"
        height={356}
        priority
        src="/brand/socium-logo-horizontal-dark.svg"
        width={1076}
      />
    </div>
  );
}

function RuntimeBadge({ state }: { state: PublicAppState | null }) {
  return (
    <div className="inline-flex items-center gap-2 rounded-full border border-zinc-800 bg-zinc-950 px-2.5 py-1 text-[11px] font-medium text-zinc-400">
      <span className="relative flex size-1.5">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-50" />
        <span className="relative inline-flex size-1.5 rounded-full bg-emerald-400" />
      </span>
      SOCIUM LOCAL · {state ? `v${state.runtime.version}` : "CONNECTING"}
    </div>
  );
}

function SidebarContent({
  active,
  state,
  onNavigate,
}: {
  active: ViewId;
  state: PublicAppState | null;
  onNavigate: (id: ViewId) => void;
}) {
  const pending = state?.posts.filter((post) => post.status === "pending").length ?? 0;
  const visibleNavigation = navigation.filter((item) => !item.preview || state?.features.labsEnabled);
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-[72px] items-center border-b border-zinc-900 px-5">
        <Brand />
      </div>
      <nav aria-label="Primary" className="flex-1 space-y-1 px-3 py-5">
        <p className="mb-3 px-2 text-[10px] font-semibold tracking-[0.18em] text-zinc-700 uppercase">
          Workspace
        </p>
        {visibleNavigation.map((item) => {
          const Icon = item.icon;
          const selected = active === item.id;
          return (
            <button
              aria-current={selected ? "page" : undefined}
              className={cn(
                "group flex h-10 w-full items-center gap-3 rounded-md border px-3 text-left text-[13px] font-medium transition-colors",
                selected
                  ? "border-zinc-700 bg-zinc-900 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.035)]"
                  : "border-transparent text-zinc-500 hover:bg-zinc-950 hover:text-zinc-200",
              )}
              key={item.id}
              onClick={() => onNavigate(item.id)}
              type="button"
            >
              <Icon className={cn("size-4", selected ? "text-white" : "text-zinc-600 group-hover:text-zinc-300")} />
              <span>{item.label}</span>
              {item.preview ? (
                <Badge className="ml-auto h-5 border-zinc-700 px-1.5 text-[9px] text-zinc-500" variant="outline">
                  LABS
                </Badge>
              ) : null}
              {item.id === "queue" && pending > 0 ? (
                <span className="ml-auto grid min-w-5 place-items-center rounded-full bg-white px-1.5 py-0.5 text-[10px] font-bold text-black">
                  {pending}
                </span>
              ) : null}
              {item.id === "leads" && (state?.leadSummary.active ?? 0) > 0 ? (
                <span className="ml-auto font-mono text-[10px] text-zinc-600">{state?.leadSummary.active}</span>
              ) : null}
            </button>
          );
        })}
      </nav>
      <div className="border-t border-zinc-900 p-3">
        <div className="rounded-md border border-zinc-900 bg-black p-3">
          <div className="flex items-center gap-2 text-xs font-medium text-zinc-300">
            <Database className="size-3.5 text-zinc-500" />
            Durable local store
          </div>
          <p className="mt-1.5 text-[11px] leading-4 text-zinc-600">Secrets encrypted at rest. Data stays on this host.</p>
        </div>
        <div className="mt-3 flex items-center justify-between px-1">
          <RuntimeBadge state={state} />
          <Tooltip>
            <TooltipTrigger
              aria-label="Open integrations"
              render={
                <button
                  className="grid size-8 place-items-center rounded-md text-zinc-600 hover:bg-zinc-900 hover:text-zinc-200"
                  onClick={() => onNavigate("integrations")}
                  type="button"
                />
              }
            >
              <Settings2 className="size-4" />
            </TooltipTrigger>
            <TooltipContent>Connections</TooltipContent>
          </Tooltip>
        </div>
      </div>
    </div>
  );
}

function PageSkeleton() {
  return (
    <div className="space-y-6" aria-label="Loading workspace">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((item) => (
          <Skeleton className="h-32 rounded-lg bg-zinc-900" key={item} />
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-[1.3fr_0.7fr]">
        <Skeleton className="h-96 rounded-lg bg-zinc-900" />
        <Skeleton className="h-96 rounded-lg bg-zinc-900" />
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: PostStatus }) {
  return (
    <Badge className={cn("gap-1.5 border px-2 py-1 font-medium capitalize", statusStyles[status])} variant="outline">
      <CircleDot className="size-3" />
      {status}
    </Badge>
  );
}

function MetricCard({
  label,
  value,
  detail,
  icon: Icon,
  active,
}: {
  label: string;
  value: number;
  detail: string;
  icon: LucideIcon;
  active?: boolean;
}) {
  return (
    <Card className={cn("min-h-32 justify-between", active && "border-zinc-600")}>
      <CardHeader className="flex-row items-center justify-between">
        <p className="text-xs font-medium text-zinc-500">{label}</p>
        <div className="grid size-8 place-items-center rounded-md border border-zinc-800 bg-black text-zinc-500">
          <Icon className="size-3.5" />
        </div>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-semibold tracking-[-0.04em] text-zinc-50 tabular-nums">{value}</p>
        <p className="mt-1.5 text-[11px] text-zinc-600">{detail}</p>
      </CardContent>
    </Card>
  );
}

function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="grid min-h-56 place-items-center px-6 py-10 text-center">
      <div>
        <div className="mx-auto grid size-10 place-items-center rounded-md border border-zinc-800 bg-zinc-950 text-zinc-500">
          <Icon className="size-4" />
        </div>
        <h3 className="mt-4 text-sm font-medium text-zinc-200">{title}</h3>
        <p className="mx-auto mt-2 max-w-sm text-xs leading-5 text-zinc-600">{description}</p>
        {action ? <div className="mt-5">{action}</div> : null}
      </div>
    </div>
  );
}

function Field({
  label,
  htmlFor,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <Label className="text-xs text-zinc-300" htmlFor={htmlFor}>{label}</Label>
        {hint ? <span className="text-[10px] text-zinc-600">{hint}</span> : null}
      </div>
      {children}
    </div>
  );
}

function MediaPreview({ url, label = "Instagram image preview" }: { url: string; label?: string }) {
  if (!url.trim()) return null;
  let safeUrl: string;
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:" || !parsed.hostname || parsed.username || parsed.password || parsed.hash) {
      return null;
    }
    safeUrl = parsed.toString();
  } catch {
    return null;
  }
  return (
    <div className="overflow-hidden rounded-md border border-fuchsia-500/20 bg-black">
      <div
        aria-label={label}
        className="aspect-square w-full bg-zinc-950 bg-cover bg-center"
        role="img"
        style={{ backgroundImage: `url(${JSON.stringify(safeUrl)})` }}
      />
      <div className="flex items-center justify-between gap-3 border-t border-zinc-900 px-3 py-2.5">
        <p className="min-w-0 truncate font-mono text-[10px] text-zinc-600">{safeUrl}</p>
        <a className="shrink-0 text-zinc-500 hover:text-zinc-200" href={safeUrl} rel="noreferrer" target="_blank">
          <span className="sr-only">Open Instagram image in a new tab</span>
          <SquareArrowOutUpRight className="size-3.5" />
        </a>
      </div>
    </div>
  );
}

function SetupRow({
  complete,
  label,
  description,
  onClick,
}: {
  complete: boolean;
  label: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      className="group flex w-full items-center gap-3 border-t border-zinc-900 px-5 py-4 text-left first:border-t-0 hover:bg-zinc-950"
      onClick={onClick}
      type="button"
    >
      <span
        className={cn(
          "grid size-7 shrink-0 place-items-center rounded-full border",
          complete ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400" : "border-zinc-800 bg-black text-zinc-700",
        )}
      >
        {complete ? <Check className="size-3.5" /> : <span className="size-1.5 rounded-full bg-current" />}
      </span>
      <span className="min-w-0 flex-1">
        <span className={cn("block text-xs font-medium", complete ? "text-zinc-300" : "text-zinc-100")}>{label}</span>
        <span className="mt-1 block text-[11px] leading-4 text-zinc-600">{description}</span>
      </span>
      <ChevronRight className="size-4 text-zinc-700 transition-transform group-hover:translate-x-0.5 group-hover:text-zinc-400" />
    </button>
  );
}

function ConnectionStatus({ configured, verified }: { configured: boolean; verified: boolean }) {
  if (verified) {
    return <Badge className="border-emerald-500/25 bg-emerald-500/8 text-emerald-300" variant="outline">Verified now</Badge>;
  }
  return (
    <Badge className={cn(configured ? "border-zinc-700 text-zinc-300" : "border-zinc-800 text-zinc-600")} variant="outline">
      {configured ? "Configured" : "Not configured"}
    </Badge>
  );
}

function IntegrationIcon({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid size-10 place-items-center rounded-md border border-zinc-700 bg-black text-zinc-200 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
      {children}
    </div>
  );
}

export function GrowthConsole() {
  const [activeView, setActiveView] = useState<ViewId>("command");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [onboardingOpen, setOnboardingOpen] = useState(false);
  const [appState, setAppState] = useState<PublicAppState | null>(null);
  const handledRemoteEdits = useRef(new Set<string>());
  const [initialError, setInitialError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [queueFilter, setQueueFilter] = useState<QueueFilter>("all");
  const [editPost, setEditPost] = useState<GeneratedPost | null>(null);
  const [editForm, setEditForm] = useState({
    title: "",
    body: "",
    hashtags: "",
    callToAction: "",
    imagePrompt: "",
    imageNegativePrompt: "",
    imageAltText: "",
    mediaUrl: "",
  });
  const [mediaGenerationBrief, setMediaGenerationBrief] = useState<{
    id: string;
    prompt: string;
    negativePrompt: string;
    altText: string;
  } | null>(null);
  const [scheduleTarget, setScheduleTarget] = useState<GeneratedPost | null>(null);
  const [scheduleAt, setScheduleAt] = useState(defaultScheduleAt);
  const [selectedRecoveryJobId, setSelectedRecoveryJobId] = useState<string | null>(null);
  const [dismissedRecoveryIds, setDismissedRecoveryIds] = useState<string[]>([]);
  const [recoveryMode, setRecoveryMode] = useState<"choice" | "reschedule">("choice");
  const [recoveryAt, setRecoveryAt] = useState(defaultScheduleAt);
  const [providerVerified, setProviderVerified] = useState(false);
  const [telegramVerified, setTelegramVerified] = useState(false);
  const [providerModels, setProviderModels] = useState<string[]>([]);
  const [aiSetupMode, setAiSetupMode] = useState<"local" | "cloud">("local");
  const [localAi, setLocalAi] = useState<LocalAiStatus | null>(null);
  const [localPull, setLocalPull] = useState<{ percentage: number; status: string } | null>(null);
  const [customProtocol, setCustomProtocol] = useState<ProviderProtocolHint>("auto");
  const [protocolChoiceRequired, setProtocolChoiceRequired] = useState(false);
  const [discoveryMessage, setDiscoveryMessage] = useState("");

  const [providerForm, setProviderForm] = useState<{
    kind: ProviderKind;
    baseUrl: string;
    model: string;
    apiKey: string;
  }>({ kind: "ollama", baseUrl: "http://127.0.0.1:11434", model: "", apiKey: "" });
  const selectedProvider = getProviderPreset(providerForm.kind);
  const providerHasStoredKey = Boolean(
    appState?.provider.hasApiKey
      && appState.provider.kind === providerForm.kind
      && appState.provider.baseUrl === providerForm.baseUrl.replace(/\/$/, ""),
  );
  const providerNeedsKey = selectedProvider.apiKeyRequired
    && !providerHasStoredKey
    && !providerForm.apiKey.trim();
  const providerCanConnect = Boolean(
    providerForm.baseUrl.trim()
      && !providerNeedsKey
      && (!["openai-compatible", "anthropic-compatible"].includes(providerForm.kind) || providerForm.model.trim()),
  );
  const [telegramForm, setTelegramForm] = useState({ botToken: "", chatId: "" });
  const [slackForm, setSlackForm] = useState({
    name: "Slack approvals",
    approvalChannelId: "",
    botToken: "",
    appToken: "",
    enabled: true,
  });
  const [wordpressForm, setWordpressForm] = useState<WordPressConnectorForm>({
    name: "Company blog",
    siteUrl: "",
    username: "",
    applicationPassword: "",
    enabled: true,
  });
  const [metaForm, setMetaForm] = useState<MetaConnectorForm>({
    name: "Company Facebook Page",
    pageId: "",
    apiVersion: "v25.0",
    pageAccessToken: "",
    enabled: true,
  });
  const [instagramForm, setInstagramForm] = useState<InstagramConnectorForm>({
    name: "Company Instagram",
    userId: "",
    apiVersion: "v25.0",
    accessToken: "",
    enabled: true,
  });
  const [linkedinForm, setLinkedinForm] = useState<LinkedInConnectorForm>({
    name: "My LinkedIn profile",
    personId: "",
    apiVersion: "202607",
    accessToken: "",
    enabled: true,
  });
  const [linkedinOrganizationForm, setLinkedinOrganizationForm] = useState<LinkedInOrganizationConnectorForm>({
    name: "My LinkedIn Company Page",
    personId: "",
    organizationId: "",
    apiVersion: "202607",
    accessToken: "",
    enabled: true,
  });
  const [deleteConnector, setDeleteConnector] = useState<ConnectorAccount | null>(null);
  const [generateForm, setGenerateForm] = useState<{
    topic: string;
    channel: ContentChannel;
    tone: string;
    objective: string;
    mediaUrl: string;
    notifyTelegram: boolean;
    notifySlack: boolean;
  }>({
    topic: "",
    channel: "linkedin",
    tone: "Clear, useful and confident",
    objective: "Build awareness and start relevant conversations",
    mediaUrl: "",
    notifyTelegram: true,
    notifySlack: false,
  });

  const acceptAppState = useCallback((next: PublicAppState) => {
    setAppState(next);
    const request = next.remoteEditRequest;
    if (!request || handledRemoteEdits.current.has(request.id)) return;
    handledRemoteEdits.current.add(request.id);
    const post = next.posts.find(
      (item) => item.id === request.postId && item.revision === request.revision,
    );
    if (post) {
      setQueueFilter("pending");
      setActiveView("queue");
      setMobileOpen(false);
      setEditPost(post);
      setEditForm({
        title: post.title,
        body: post.body,
        hashtags: post.hashtags.join(" "),
        callToAction: post.callToAction,
        imagePrompt: post.imagePrompt,
        imageNegativePrompt: post.imageNegativePrompt,
        imageAltText: post.imageAltText,
        mediaUrl: post.mediaUrl ?? "",
      });
      toast.info(`Edit requested from ${request.source}`, {
        description: `Revision ${request.revision} is open. Saving will create a fresh revision.`,
      });
    } else {
      toast.warning("Remote edit request is stale", {
        description: "Open the latest draft revision from the approval queue.",
      });
    }
    void requestJson<{ ok: boolean }>(`/api/approval-actions/${request.id}/edit/ack`, {
      method: "POST",
    }).then(() => {
      setAppState((current) => (
        current?.remoteEditRequest?.id === request.id
          ? { ...current, remoteEditRequest: null }
          : current
      ));
    }).catch(() => undefined);
  }, []);

  const loadState = useCallback(async () => {
    setLoading(true);
    setInitialError("");
    try {
      const next = await requestJson<PublicAppState>("/api/state", { cache: "no-store" });
      acceptAppState(next);
    } catch (error) {
      setInitialError(error instanceof Error ? error.message : "Could not load the local workspace.");
    } finally {
      setLoading(false);
    }
  }, [acceptAppState]);

  const refreshLocalAi = useCallback(async (baseUrl: string) => {
    try {
      const status = await requestJson<LocalAiStatus>(
        `/api/providers/local/status?base_url=${encodeURIComponent(baseUrl)}`,
        { cache: "no-store" },
      );
      setLocalAi(status);
      setProviderModels(status.models);
      return status;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not inspect local AI.");
      return null;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void requestJson<PublicAppState>("/api/state", { cache: "no-store" })
      .then((next) => {
        if (cancelled) return;
        acceptAppState(next);
        if (next.onboarding.showWizard) setOnboardingOpen(true);
        setProviderForm({
          kind: next.provider.kind,
          baseUrl: next.provider.baseUrl,
          model: next.provider.model,
          apiKey: "",
        });
        setAiSetupMode(next.provider.kind === "ollama" ? "local" : "cloud");
        setTelegramForm({ chatId: next.telegram.chatId, botToken: "" });
        setGenerateForm((current) => ({
          ...current,
          tone: current.tone === "Clear and confident" ? next.workspace.tone || current.tone : current.tone,
          notifyTelegram: next.telegram.configured,
        }));
        const slack = next.connectors.accounts.find((account) => account.adapterId === "slack");
        if (slack) {
          setSlackForm({
            name: slack.name,
            approvalChannelId: String(slack.config.approval_channel_id ?? ""),
            botToken: "",
            appToken: "",
            enabled: slack.enabled,
          });
        }
        const wordpress = next.connectors.accounts.find((account) => account.adapterId === "wordpress");
        if (wordpress) {
          setWordpressForm({
            name: wordpress.name,
            siteUrl: String(wordpress.config.site_url ?? ""),
            username: "",
            applicationPassword: "",
            enabled: wordpress.enabled,
          });
        }
        const meta = next.connectors.accounts.find((account) => account.adapterId === "meta");
        if (meta) {
          setMetaForm({
            name: meta.name,
            pageId: String(meta.config.page_id ?? ""),
            apiVersion: String(meta.config.api_version ?? "v25.0"),
            pageAccessToken: "",
            enabled: meta.enabled,
          });
        }
        const instagram = next.connectors.accounts.find((account) => account.adapterId === "instagram");
        if (instagram) {
          setInstagramForm({
            name: instagram.name,
            userId: String(instagram.config.user_id ?? ""),
            apiVersion: String(instagram.config.api_version ?? "v25.0"),
            accessToken: "",
            enabled: instagram.enabled,
          });
        }
        const linkedin = next.connectors.accounts.find((account) => account.adapterId === "linkedin");
        if (linkedin) {
          setLinkedinForm({
            name: linkedin.name,
            personId: String(linkedin.config.person_id ?? ""),
            apiVersion: String(linkedin.config.api_version ?? "202607"),
            accessToken: "",
            enabled: linkedin.enabled,
          });
        }
        const linkedinOrganization = next.connectors.accounts.find((account) => account.adapterId === "linkedin-organization");
        if (linkedinOrganization) {
          setLinkedinOrganizationForm({
            name: linkedinOrganization.name,
            personId: String(linkedinOrganization.config.person_id ?? ""),
            organizationId: String(linkedinOrganization.config.organization_id ?? ""),
            apiVersion: String(linkedinOrganization.config.api_version ?? "202607"),
            accessToken: "",
            enabled: linkedinOrganization.enabled,
          });
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setInitialError(error instanceof Error ? error.message : "Could not load the local workspace.");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [acceptAppState]);

  const schedulerShouldRefresh = Boolean(
    !appState?.scheduler.paused
      && appState?.jobs.some((job) => ["queued", "retrying", "running"].includes(job.status)),
  );
  const slackShouldRefresh = Boolean(
    appState?.connectors.accounts.some(
      (account) => account.adapterId === "slack" && account.enabled && account.status === "verified",
    ),
  );

  useEffect(() => {
    if (!appState?.telegram.pollingEnabled && !schedulerShouldRefresh && !slackShouldRefresh) return;
    const interval = window.setInterval(() => {
      void requestJson<PublicAppState>("/api/state", { cache: "no-store" })
        .then(acceptAppState)
        .catch(() => undefined);
    }, 5_000);
    return () => window.clearInterval(interval);
  }, [acceptAppState, appState?.telegram.pollingEnabled, schedulerShouldRefresh, slackShouldRefresh]);

  const recoveryJob = useMemo(() => {
    const jobs = appState?.jobs.filter(
      (job) => job.status === "missed" && Boolean(job.recoveryRequiredAt),
    ) ?? [];
    return jobs.find((job) => job.id === selectedRecoveryJobId)
      ?? jobs.find((job) => !dismissedRecoveryIds.includes(job.id))
      ?? null;
  }, [appState?.jobs, dismissedRecoveryIds, selectedRecoveryJobId]);

  const counts = useMemo(() => {
    const posts = appState?.posts ?? [];
    return {
      pending: posts.filter((post) => post.status === "pending").length,
      approved: posts.filter((post) => post.status === "approved").length,
      published: posts.filter((post) => post.status === "published").length,
      attention: posts.filter((post) => post.status === "failed" || Boolean(post.lastError)).length,
    };
  }, [appState?.posts]);

  const setup = useMemo(() => {
    const business = Boolean(appState?.workspace.profileComplete);
    const provider = Boolean(appState?.provider.verified);
    const telegram = Boolean(appState?.telegram.configured && appState.telegram.pollingEnabled);
    return { business, provider, telegram, complete: [business, provider, telegram].filter(Boolean).length };
  }, [appState]);

  const slackAccount = useMemo(
    () => appState?.connectors.accounts.find((account) => account.adapterId === "slack") ?? null,
    [appState?.connectors.accounts],
  );

  const wordpressAccount = useMemo(
    () => appState?.connectors.accounts.find((account) => account.adapterId === "wordpress") ?? null,
    [appState?.connectors.accounts],
  );

  const metaAccount = useMemo(
    () => appState?.connectors.accounts.find((account) => account.adapterId === "meta") ?? null,
    [appState?.connectors.accounts],
  );

  const instagramAccount = useMemo(
    () => appState?.connectors.accounts.find((account) => account.adapterId === "instagram") ?? null,
    [appState?.connectors.accounts],
  );

  const linkedinAccount = useMemo(
    () => appState?.connectors.accounts.find((account) => account.adapterId === "linkedin") ?? null,
    [appState?.connectors.accounts],
  );

  const linkedinOrganizationAccount = useMemo(
    () => appState?.connectors.accounts.find((account) => account.adapterId === "linkedin-organization") ?? null,
    [appState?.connectors.accounts],
  );

  const upcomingConnectors = useMemo(
    () => appState?.connectors.catalog.filter((connector) => !["telegram", "slack", "wordpress", "google-places", "meta", "instagram", "linkedin", "linkedin-organization"].includes(connector.adapterId)) ?? [],
    [appState?.connectors.catalog],
  );

  const filteredPosts = useMemo(
    () => (appState?.posts ?? []).filter((post) => queueFilter === "all" || post.status === queueFilter),
    [appState?.posts, queueFilter],
  );

  function navigate(id: ViewId) {
    setActiveView(id);
    setMobileOpen(false);
    if (id === "integrations" && aiSetupMode === "local" && !localAi) {
      void refreshLocalAi(providerForm.baseUrl);
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function connectProvider(nextForm = providerForm) {
    setBusy("provider-test");
    setProviderVerified(false);
    try {
      const saved = await requestJson<StateResponse>("/api/settings/provider", {
        method: "PUT",
        body: JSON.stringify(nextForm),
      });
      setAppState(saved.state);
      setProviderForm((current) => ({ ...current, apiKey: "" }));

      const result = await requestJson<ProviderConnectionResult>("/api/providers/test", { method: "POST" });
      const models = result.models ?? [];
      setProviderModels(models);

      if (nextForm.kind === "ollama" && !nextForm.model && models[0]) {
        const detectedModel = models[0];
        const selected = await requestJson<StateResponse>("/api/settings/provider", {
          method: "PUT",
          body: JSON.stringify({ ...nextForm, apiKey: "", model: detectedModel }),
        });
        setAppState(selected.state);
        setProviderForm((current) => ({ ...current, apiKey: "", model: detectedModel }));
        await requestJson<ProviderConnectionResult>("/api/providers/test", { method: "POST" });
      }

      setProviderVerified(Boolean(nextForm.model || models[0]));
      toast.success(result.message, { description: result.latencyMs ? `${result.latencyMs} ms` : undefined });
      return true;
    } catch (error) {
      setProviderVerified(false);
      toast.error(error instanceof Error ? error.message : "Provider test failed.");
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function testProviderConnection(event?: FormEvent) {
    event?.preventDefault();
    await connectProvider();
  }

  async function discoverCustomProvider() {
    setBusy("provider-discover");
    setProviderVerified(false);
    setDiscoveryMessage("");
    try {
      const result = await requestJson<ProviderDiscoveryResult>("/api/providers/discover", {
        method: "POST",
        body: JSON.stringify({
          baseUrl: providerForm.baseUrl,
          protocolHint: customProtocol,
          apiKey: customProtocol === "auto" ? "" : providerForm.apiKey,
        }),
      });
      setDiscoveryMessage(result.message);
      setProtocolChoiceRequired(result.requiresProtocolChoice);
      if (!result.ok || !result.detectedKind) {
        toast.warning("Choose the API protocol", { description: result.message });
        return;
      }
      const model = result.models.includes(providerForm.model) ? providerForm.model : result.models[0] ?? "";
      const detectedForm = {
        ...providerForm,
        kind: result.detectedKind,
        baseUrl: result.normalizedBaseUrl,
        model,
      };
      setProviderModels(result.models);
      setProviderForm(detectedForm);
      setCustomProtocol(result.detectedKind === "ollama" ? "ollama" : result.detectedKind as ProviderProtocolHint);
      setAiSetupMode(result.detectedKind === "ollama" ? "local" : "cloud");
      const saved = await requestJson<StateResponse>("/api/settings/provider", {
        method: "PUT",
        body: JSON.stringify(detectedForm),
      });
      setAppState(saved.state);
      setProviderForm((current) => ({ ...current, apiKey: "" }));
      setProviderVerified(Boolean(model));
      toast.success(result.message, { description: model ? `Selected ${model}` : "Choose or download a model next." });
      if (result.detectedKind === "ollama") await refreshLocalAi(result.normalizedBaseUrl);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not detect this provider.");
    } finally {
      setBusy(null);
    }
  }

  async function downloadRecommendedModel() {
    if (!localAi?.ollamaRunning) return;
    const model = localAi.selectedRecommendation;
    setBusy("local-model-pull");
    setLocalPull({ percentage: 0, status: `Preparing ${model}` });
    try {
      const response = await fetch("/api/providers/local/pull", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ baseUrl: providerForm.baseUrl, model }),
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
        const lines = buffered.split("\n");
        buffered = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.trim()) continue;
          const update = JSON.parse(line) as { ok: boolean; status?: string; percentage?: number; verified?: boolean; error?: string };
          if (!update.ok) throw new Error(update.error || "Model download failed.");
          setLocalPull({ percentage: update.percentage ?? 0, status: update.status || "Downloading model" });
          verified ||= Boolean(update.verified);
        }
        if (done) break;
      }
      if (!verified) throw new Error("The model download ended before verification.");
      const nextForm = { ...providerForm, kind: "ollama" as const, model, apiKey: "" };
      setProviderForm(nextForm);
      await connectProvider(nextForm);
      await refreshLocalAi(providerForm.baseUrl);
      toast.success(`${model} is installed and ready`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not download the local model.");
    } finally {
      setBusy(null);
    }
  }

  async function saveTelegram(event?: FormEvent) {
    event?.preventDefault();
    setBusy("telegram-save");
    try {
      const response = await requestJson<StateResponse>("/api/settings/telegram", {
        method: "PUT",
        body: JSON.stringify(telegramForm),
      });
      setAppState(response.state);
      setTelegramForm((current) => ({ ...current, botToken: "" }));
      setTelegramVerified(false);
      toast.success("Telegram settings saved");
      return true;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save Telegram.");
      return false;
    } finally {
      setBusy(null);
    }
  }

  async function testTelegramConnection() {
    const saved = await saveTelegram();
    if (!saved) return;
    setBusy("telegram-test");
    try {
      const result = await requestJson<{ ok: boolean; message: string }>("/api/integrations/telegram/test", { method: "POST" });
      setTelegramVerified(true);
      toast.success(result.message);
    } catch (error) {
      setTelegramVerified(false);
      toast.error(error instanceof Error ? error.message : "Telegram test failed.");
    } finally {
      setBusy(null);
    }
  }

  async function generatePost(event: FormEvent) {
    event.preventDefault();
    setBusy("generate");
    try {
      const response = await requestJson<{
        ok: boolean;
        post: GeneratedPost;
        notification: { ok: boolean; message: string } | null;
        notifications: Array<{
          channel: "telegram" | "slack";
          ok: boolean;
          message: string;
        }>;
        state: PublicAppState;
      }>("/api/posts/generate", {
        method: "POST",
        body: JSON.stringify(generateForm),
      });
      setAppState(response.state);
      setGenerateForm((current) => ({ ...current, topic: "", mediaUrl: "" }));
      toast.success("Draft generated", { description: `${channelLabels[response.post.channel]} · ${response.post.model}` });
      const notifications = response.notifications ?? (
        response.notification ? [{ channel: "telegram" as const, ...response.notification }] : []
      );
      notifications.forEach((notification) => {
        if (notification.ok) {
          toast.success(notification.message);
        } else {
          toast.warning(`Draft saved, but ${notification.channel} notification failed`, {
            description: notification.message,
          });
        }
      });
      setQueueFilter("pending");
      navigate("queue");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Generation failed.");
    } finally {
      setBusy(null);
    }
  }

  async function decidePost(post: GeneratedPost, decision: "approve" | "skip") {
    setBusy(`${decision}-${post.id}`);
    try {
      const response = await requestJson<StateResponse>(`/api/posts/${post.id}/decision`, {
        method: "POST",
        body: JSON.stringify({ decision, revision: post.revision }),
      });
      setAppState(response.state);
      toast.success(decision === "approve" ? "Draft approved and locked" : "Draft skipped without publishing");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Decision failed.");
    } finally {
      setBusy(null);
    }
  }

  async function regeneratePost(post: GeneratedPost) {
    setBusy(`regenerate-${post.id}`);
    try {
      const response = await requestJson<StateResponse & { post: GeneratedPost; message: string }>(
        `/api/posts/${post.id}/regenerate`,
        {
          method: "POST",
          body: JSON.stringify({ revision: post.revision }),
        },
      );
      setAppState(response.state);
      toast.success("Fresh revision generated", { description: response.message });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not regenerate this draft.");
      await loadState();
    } finally {
      setBusy(null);
    }
  }

  async function sendSlackApproval(post: GeneratedPost) {
    setBusy(`slack-approval-${post.id}`);
    try {
      const response = await requestJson<StateResponse & { message: string }>(
        `/api/posts/${post.id}/approvals/slack`,
        {
          method: "POST",
          body: JSON.stringify({ revision: post.revision }),
        },
      );
      setAppState(response.state);
      toast.success(response.message);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not send this draft to Slack.");
    } finally {
      setBusy(null);
    }
  }

  async function publishPost(post: GeneratedPost) {
    setBusy(`publish-${post.id}`);
    try {
      const response = await requestJson<StateResponse>(`/api/posts/${post.id}/publish`, {
        method: "POST",
        body: JSON.stringify({ revision: post.revision }),
      });
      setAppState(response.state);
      toast.success(`Published to ${publisherDisplayName(post.channel)}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Publish failed.");
      await loadState();
    } finally {
      setBusy(null);
    }
  }

  function openSchedule(post: GeneratedPost) {
    setScheduleTarget(post);
    setScheduleAt(defaultScheduleAt());
  }

  async function schedulePost(event: FormEvent) {
    event.preventDefault();
    if (!scheduleTarget) return;
    const runAt = new Date(scheduleAt);
    if (Number.isNaN(runAt.getTime())) {
      toast.error("Choose a valid publish time.");
      return;
    }
    setBusy(`schedule-${scheduleTarget.id}`);
    try {
      const response = await requestJson<StateResponse & { message: string }>(`/api/posts/${scheduleTarget.id}/schedule`, {
        method: "POST",
        body: JSON.stringify({ revision: scheduleTarget.revision, runAt: runAt.toISOString() }),
      });
      setAppState(response.state);
      setScheduleTarget(null);
      toast.success(response.message, { description: formatDate(runAt.toISOString()) });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not schedule this draft.");
    } finally {
      setBusy(null);
    }
  }

  async function configureScheduler(paused: boolean) {
    setBusy("scheduler-state");
    try {
      const response = await requestJson<StateResponse & { message: string }>("/api/scheduler", {
        method: "PUT",
        body: JSON.stringify({ paused }),
      });
      setAppState(response.state);
      toast.success(response.message);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update the local scheduler.");
    } finally {
      setBusy(null);
    }
  }

  async function cancelScheduledJob(job: LocalJob) {
    setBusy(`cancel-job-${job.id}`);
    try {
      const response = await requestJson<StateResponse>(`/api/jobs/${job.id}/cancel`, { method: "POST" });
      setAppState(response.state);
      toast.success("Scheduled publish cancelled");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not cancel this job.");
    } finally {
      setBusy(null);
    }
  }

  async function retryScheduledJob(job: LocalJob) {
    setBusy(`retry-job-${job.id}`);
    try {
      const response = await requestJson<StateResponse>(`/api/jobs/${job.id}/retry`, { method: "POST" });
      setAppState(response.state);
      toast.success("Scheduled publish requeued", { description: "Review possible prior delivery before retrying." });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not retry this job.");
    } finally {
      setBusy(null);
    }
  }

  function openRecovery(job: LocalJob, mode: "choice" | "reschedule" = "choice") {
    setDismissedRecoveryIds((current) => current.filter((id) => id !== job.id));
    setSelectedRecoveryJobId(job.id);
    setRecoveryMode(mode);
    setRecoveryAt(defaultScheduleAt());
  }

  function dismissRecovery() {
    if (recoveryJob) {
      setDismissedRecoveryIds((current) => (
        current.includes(recoveryJob.id) ? current : [...current, recoveryJob.id]
      ));
    }
    setSelectedRecoveryJobId(null);
    setRecoveryMode("choice");
  }

  async function recoverScheduledJob(
    job: LocalJob,
    decision: "run_now" | "reschedule" | "skip",
  ) {
    let runAt: string | undefined;
    if (decision === "reschedule") {
      const selected = new Date(recoveryAt);
      if (Number.isNaN(selected.getTime()) || selected.getTime() <= Date.now()) {
        toast.error("Choose a future publish time.");
        return;
      }
      runAt = selected.toISOString();
    }
    setBusy(`recover-job-${job.id}-${decision}`);
    try {
      const response = await requestJson<StateResponse & { message: string }>(
        `/api/jobs/${job.id}/recover`,
        {
          method: "POST",
          body: JSON.stringify({ decision, ...(runAt ? { runAt } : {}) }),
        },
      );
      acceptAppState(response.state);
      setSelectedRecoveryJobId(null);
      setRecoveryMode("choice");
      toast.success(response.message, {
        description: decision === "run_now"
          ? "The single local worker will start it safely."
          : decision === "skip"
            ? "The approved draft remains available; no publisher was called."
            : formatDate(runAt ?? ""),
      });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not recover this scheduled job.");
    } finally {
      setBusy(null);
    }
  }

  function openEdit(post: GeneratedPost) {
    setEditPost(post);
    setEditForm({
      title: post.title,
      body: post.body,
      hashtags: post.hashtags.join(" "),
      callToAction: post.callToAction,
      imagePrompt: post.imagePrompt,
      imageNegativePrompt: post.imageNegativePrompt,
      imageAltText: post.imageAltText,
      mediaUrl: post.mediaUrl ?? "",
    });
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (!editPost) return;
    setBusy(`edit-${editPost.id}`);
    try {
      const hashtags = editForm.hashtags
        .split(/[\s,]+/)
        .map((tag) => tag.trim().replace(/^#/, ""))
        .filter(Boolean);
      const response = await requestJson<StateResponse>(`/api/posts/${editPost.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          revision: editPost.revision,
          title: editForm.title,
          body: editForm.body,
          hashtags,
          callToAction: editForm.callToAction,
          imagePrompt: editForm.imagePrompt,
          imageNegativePrompt: editForm.imageNegativePrompt,
          imageAltText: editForm.imageAltText,
          mediaUrl: editForm.mediaUrl || null,
        }),
      });
      setAppState(response.state);
      setEditPost(null);
      toast.success("Draft updated", { description: "Approval was reset for this new version." });
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update the draft.");
    } finally {
      setBusy(null);
    }
  }

  async function configureTelegramPolling(enabled: boolean) {
    setBusy("telegram-polling");
    try {
      const response = await requestJson<StateResponse & { message: string }>("/api/integrations/telegram/polling", {
        method: "PUT",
        body: JSON.stringify({ enabled }),
      });
      setAppState(response.state);
      toast.success(response.message);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not update local Telegram approvals.");
    } finally {
      setBusy(null);
    }
  }

  async function saveSlackConnector(event?: FormEvent, quiet = false) {
    event?.preventDefault();
    setBusy("slack-save");
    try {
      const secrets: Record<string, string> = {};
      if (slackForm.botToken.trim()) secrets.bot_token = slackForm.botToken.trim();
      if (slackForm.appToken.trim()) secrets.app_token = slackForm.appToken.trim();
      const response = await requestJson<StateResponse & { account: ConnectorAccount }>(
        slackAccount ? `/api/connectors/${slackAccount.id}` : "/api/connectors",
        {
          method: slackAccount ? "PUT" : "POST",
          body: JSON.stringify({
            adapterId: "slack",
            name: slackForm.name,
            config: { approval_channel_id: slackForm.approvalChannelId },
            secrets,
            scopes: ["chat:write", "connections:write"],
            enabled: slackForm.enabled,
          }),
        },
      );
      setAppState(response.state);
      setSlackForm((current) => ({ ...current, botToken: "", appToken: "" }));
      if (!quiet) toast.success("Slack connector saved in the encrypted local vault");
      return response.account.id;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save the Slack connector.");
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function testSlackConnection() {
    const accountId = await saveSlackConnector(undefined, true);
    if (!accountId) return;
    setBusy("slack-test");
    try {
      const response = await requestJson<StateResponse & { message: string }>(`/api/connectors/${accountId}/test`, {
        method: "POST",
      });
      setAppState(response.state);
      toast.success(response.message);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Slack connection test failed.");
      await loadState();
    } finally {
      setBusy(null);
    }
  }

  async function saveWordPressConnector(event?: FormEvent, quiet = false) {
    event?.preventDefault();
    setBusy("wordpress-save");
    try {
      const secrets: Record<string, string> = {};
      if (wordpressForm.username.trim()) secrets.username = wordpressForm.username.trim();
      if (wordpressForm.applicationPassword.trim()) {
        secrets.application_password = wordpressForm.applicationPassword.trim();
      }
      const response = await requestJson<StateResponse & { account: ConnectorAccount }>(
        wordpressAccount ? `/api/connectors/${wordpressAccount.id}` : "/api/connectors",
        {
          method: wordpressAccount ? "PUT" : "POST",
          body: JSON.stringify({
            adapterId: "wordpress",
            name: wordpressForm.name,
            config: { site_url: wordpressForm.siteUrl },
            secrets,
            scopes: ["posts:write"],
            enabled: wordpressForm.enabled,
          }),
        },
      );
      setAppState(response.state);
      setWordpressForm((current) => ({ ...current, username: "", applicationPassword: "" }));
      if (!quiet) toast.success("WordPress connector saved in the encrypted local vault");
      return response.account.id;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save the WordPress connector.");
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function testWordPressConnection() {
    const accountId = await saveWordPressConnector(undefined, true);
    if (!accountId) return;
    setBusy("wordpress-test");
    try {
      const response = await requestJson<StateResponse & { message: string }>(`/api/connectors/${accountId}/test`, {
        method: "POST",
      });
      setAppState(response.state);
      toast.success(response.message);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "WordPress connection test failed.");
      await loadState();
    } finally {
      setBusy(null);
    }
  }

  async function saveMetaConnector(event?: FormEvent, quiet = false) {
    event?.preventDefault();
    setBusy("meta-save");
    try {
      const secrets: Record<string, string> = {};
      if (metaForm.pageAccessToken.trim()) {
        secrets.page_access_token = metaForm.pageAccessToken.trim();
      }
      const response = await requestJson<StateResponse & { account: ConnectorAccount }>(
        metaAccount ? `/api/connectors/${metaAccount.id}` : "/api/connectors",
        {
          method: metaAccount ? "PUT" : "POST",
          body: JSON.stringify({
            adapterId: "meta",
            name: metaForm.name,
            config: { page_id: metaForm.pageId, api_version: metaForm.apiVersion },
            secrets,
            scopes: ["pages_read_engagement", "pages_manage_posts"],
            enabled: metaForm.enabled,
          }),
        },
      );
      setAppState(response.state);
      setMetaForm((current) => ({ ...current, pageAccessToken: "" }));
      if (!quiet) toast.success("Facebook Page connector saved in the encrypted local vault");
      return response.account.id;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save the Facebook Page connector.");
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function testMetaConnection() {
    const accountId = await saveMetaConnector(undefined, true);
    if (!accountId) return;
    setBusy("meta-test");
    try {
      const response = await requestJson<StateResponse & { message: string }>(`/api/connectors/${accountId}/test`, {
        method: "POST",
      });
      setAppState(response.state);
      toast.success(response.message);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Facebook Page connection test failed.");
      await loadState();
    } finally {
      setBusy(null);
    }
  }

  async function saveInstagramConnector(event?: FormEvent, quiet = false) {
    event?.preventDefault();
    setBusy("instagram-save");
    try {
      const secrets: Record<string, string> = {};
      if (instagramForm.accessToken.trim()) {
        secrets.access_token = instagramForm.accessToken.trim();
      }
      const response = await requestJson<StateResponse & { account: ConnectorAccount }>(
        instagramAccount ? `/api/connectors/${instagramAccount.id}` : "/api/connectors",
        {
          method: instagramAccount ? "PUT" : "POST",
          body: JSON.stringify({
            adapterId: "instagram",
            name: instagramForm.name,
            config: { user_id: instagramForm.userId, api_version: instagramForm.apiVersion },
            secrets,
            scopes: ["instagram_business_basic", "instagram_business_content_publish"],
            enabled: instagramForm.enabled,
          }),
        },
      );
      setAppState(response.state);
      setInstagramForm((current) => ({ ...current, accessToken: "" }));
      if (!quiet) toast.success("Instagram connector saved in the encrypted local vault");
      return response.account.id;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save the Instagram connector.");
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function testInstagramConnection() {
    const accountId = await saveInstagramConnector(undefined, true);
    if (!accountId) return;
    setBusy("instagram-test");
    try {
      const response = await requestJson<StateResponse & { message: string }>(`/api/connectors/${accountId}/test`, {
        method: "POST",
      });
      setAppState(response.state);
      toast.success(response.message);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Instagram connection test failed.");
      await loadState();
    } finally {
      setBusy(null);
    }
  }

  async function saveLinkedInConnector(event?: FormEvent, quiet = false) {
    event?.preventDefault();
    setBusy("linkedin-save");
    try {
      const secrets: Record<string, string> = {};
      if (linkedinForm.accessToken.trim()) {
        secrets.access_token = linkedinForm.accessToken.trim();
      }
      const response = await requestJson<StateResponse & { account: ConnectorAccount }>(
        linkedinAccount ? `/api/connectors/${linkedinAccount.id}` : "/api/connectors",
        {
          method: linkedinAccount ? "PUT" : "POST",
          body: JSON.stringify({
            adapterId: "linkedin",
            name: linkedinForm.name,
            config: { person_id: linkedinForm.personId, api_version: linkedinForm.apiVersion },
            secrets,
            scopes: ["openid", "profile", "w_member_social"],
            enabled: linkedinForm.enabled,
          }),
        },
      );
      setAppState(response.state);
      setLinkedinForm((current) => ({ ...current, accessToken: "" }));
      if (!quiet) toast.success("LinkedIn connector saved in the encrypted local vault");
      return response.account.id;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save the LinkedIn connector.");
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function testLinkedInConnection() {
    const accountId = await saveLinkedInConnector(undefined, true);
    if (!accountId) return;
    setBusy("linkedin-test");
    try {
      const response = await requestJson<StateResponse & { message: string }>(`/api/connectors/${accountId}/test`, {
        method: "POST",
      });
      setAppState(response.state);
      toast.success(response.message);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "LinkedIn connection test failed.");
      await loadState();
    } finally {
      setBusy(null);
    }
  }

  async function saveLinkedInOrganizationConnector(event?: FormEvent, quiet = false) {
    event?.preventDefault();
    setBusy("linkedin-organization-save");
    try {
      const secrets: Record<string, string> = {};
      if (linkedinOrganizationForm.accessToken.trim()) {
        secrets.access_token = linkedinOrganizationForm.accessToken.trim();
      }
      const response = await requestJson<StateResponse & { account: ConnectorAccount }>(
        linkedinOrganizationAccount
          ? `/api/connectors/${linkedinOrganizationAccount.id}`
          : "/api/connectors",
        {
          method: linkedinOrganizationAccount ? "PUT" : "POST",
          body: JSON.stringify({
            adapterId: "linkedin-organization",
            name: linkedinOrganizationForm.name,
            config: {
              person_id: linkedinOrganizationForm.personId,
              organization_id: linkedinOrganizationForm.organizationId,
              api_version: linkedinOrganizationForm.apiVersion,
            },
            secrets,
            scopes: ["openid", "profile", "w_organization_social", "rw_organization_admin"],
            enabled: linkedinOrganizationForm.enabled,
          }),
        },
      );
      setAppState(response.state);
      setLinkedinOrganizationForm((current) => ({ ...current, accessToken: "" }));
      if (!quiet) toast.success("LinkedIn Company Page connector saved in the encrypted local vault");
      return response.account.id;
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save the LinkedIn Company Page connector.");
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function testLinkedInOrganizationConnection() {
    const accountId = await saveLinkedInOrganizationConnector(undefined, true);
    if (!accountId) return;
    setBusy("linkedin-organization-test");
    try {
      const response = await requestJson<StateResponse & { message: string }>(`/api/connectors/${accountId}/test`, {
        method: "POST",
      });
      setAppState(response.state);
      toast.success(response.message);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "LinkedIn Company Page permission check failed.");
      await loadState();
    } finally {
      setBusy(null);
    }
  }

  async function removeConnector() {
    if (!deleteConnector) return;
    const adapterId = deleteConnector.adapterId;
    setBusy(`${adapterId}-delete`);
    try {
      const response = await requestJson<StateResponse>(`/api/connectors/${deleteConnector.id}`, { method: "DELETE" });
      setAppState(response.state);
      setDeleteConnector(null);
      if (adapterId === "slack") {
        setSlackForm({
          name: "Slack approvals",
          approvalChannelId: "",
          botToken: "",
          appToken: "",
          enabled: true,
        });
      } else if (adapterId === "wordpress") {
        setWordpressForm({
          name: "Company blog",
          siteUrl: "",
          username: "",
          applicationPassword: "",
          enabled: true,
        });
      } else if (adapterId === "meta") {
        setMetaForm({
          name: "Company Facebook Page",
          pageId: "",
          apiVersion: "v25.0",
          pageAccessToken: "",
          enabled: true,
        });
      } else if (adapterId === "instagram") {
        setInstagramForm({
          name: "Company Instagram",
          userId: "",
          apiVersion: "v25.0",
          accessToken: "",
          enabled: true,
        });
      } else if (adapterId === "linkedin") {
        setLinkedinForm({
          name: "My LinkedIn profile",
          personId: "",
          apiVersion: "202607",
          accessToken: "",
          enabled: true,
        });
      } else if (adapterId === "linkedin-organization") {
        setLinkedinOrganizationForm({
          name: "My LinkedIn Company Page",
          personId: "",
          organizationId: "",
          apiVersion: "202607",
          accessToken: "",
          enabled: true,
        });
      }
      toast.success(`${deleteConnector.adapterName} connector removed from this computer`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not remove the connector.");
    } finally {
      setBusy(null);
    }
  }

  const meta = pageMeta[activeView];

  return (
    <div className="min-h-screen bg-black text-zinc-100">
      <div aria-hidden className="control-grid pointer-events-none fixed inset-x-0 top-0 h-[520px] opacity-80" />

      {appState ? (
        <OnboardingWizard
          onOpenAdvancedAi={() => {
            setOnboardingOpen(false);
            navigate("integrations");
          }}
          onOpenChange={setOnboardingOpen}
          onStateChange={(state) => {
            setAppState(state);
            setGenerateForm((current) => ({ ...current, tone: state.workspace.tone || current.tone }));
          }}
          open={onboardingOpen}
          state={appState}
        />
      ) : null}

      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 border-r border-zinc-900 bg-[#050505] lg:block">
        <SidebarContent active={activeView} onNavigate={navigate} state={appState} />
      </aside>

      <Sheet onOpenChange={setMobileOpen} open={mobileOpen}>
        <SheetContent className="w-[286px] border-zinc-800 bg-[#050505] p-0" side="left">
          <SheetHeader className="sr-only">
            <SheetTitle>Navigation</SheetTitle>
            <SheetDescription>Socium workspace navigation</SheetDescription>
          </SheetHeader>
          <SidebarContent active={activeView} onNavigate={navigate} state={appState} />
        </SheetContent>
      </Sheet>

      <div className="relative lg:pl-60">
        <header className="sticky top-0 z-20 flex h-16 items-center border-b border-zinc-900 bg-black/90 px-4 backdrop-blur-xl sm:px-6 lg:h-[72px] lg:px-8">
          <Button aria-label="Open navigation" className="mr-3 lg:hidden" onClick={() => setMobileOpen(true)} size="icon" variant="ghost">
            <Menu className="size-4" />
          </Button>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <p className="truncate text-[10px] font-semibold tracking-[0.18em] text-zinc-600 uppercase">{meta.eyebrow}</p>
              <span aria-hidden className="hidden text-zinc-800 sm:inline">/</span>
              <p className="hidden truncate text-[10px] text-zinc-700 sm:block">{appState?.workspace.name || "Local workspace"}</p>
            </div>
            <h1 className="mt-1 truncate text-sm font-semibold text-zinc-100 sm:text-base">{meta.title}</h1>
          </div>
          <div className="ml-3 flex items-center gap-2">
            <Button aria-label={appState?.onboarding.status === "completed" ? "Open setup guide" : "Resume guided setup"} className="md:hidden" onClick={() => appState?.onboarding.status === "completed" ? navigate("guide") : setOnboardingOpen(true)} size="icon" variant="ghost">
              <BookOpenCheck className="size-4" />
            </Button>
            <Button className="hidden md:inline-flex" onClick={() => appState?.onboarding.status === "completed" ? navigate("guide") : setOnboardingOpen(true)} variant="outline">
              <BookOpenCheck /> {appState?.onboarding.status === "completed" ? "Setup guide" : "Resume setup"}
            </Button>
            <Button className="hidden sm:inline-flex" onClick={() => navigate("create")}>
              <Plus /> New content
            </Button>
            <Button aria-label="Create content" className="sm:hidden" onClick={() => navigate("create")} size="icon">
              <Plus />
            </Button>
          </div>
        </header>

        <main className="relative mx-auto w-full max-w-[1500px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <div className="mb-6 hidden sm:block">
            <p className="max-w-2xl text-sm leading-6 text-zinc-500">{meta.description}</p>
          </div>

          {loading ? <PageSkeleton /> : null}

          {!loading && initialError ? (
            <Card className="mx-auto mt-20 max-w-lg">
              <EmptyState
                action={<Button onClick={() => void loadState()} variant="outline"><RefreshCw /> Retry</Button>}
                description={initialError}
                icon={AlertTriangle}
                title="Local API is not responding"
              />
            </Card>
          ) : null}

          {!loading && appState && activeView === "guide" ? (
            <SetupGuide
              onCreateContent={() => navigate("create")}
              onOpenConnections={() => navigate("integrations")}
              onOpenQueue={() => navigate("queue")}
              onOpenScheduler={() => navigate("scheduler")}
              onOpenOnboarding={() => setOnboardingOpen(true)}
              state={appState}
            />
          ) : null}

          {!loading && appState && activeView === "command" ? (
            <div className="space-y-4">
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <MetricCard active={counts.pending > 0} detail="Needs a human decision" icon={Clock3} label="Awaiting approval" value={counts.pending} />
                <MetricCard detail="Locked and ready" icon={ShieldCheck} label="Approved" value={counts.approved} />
                <MetricCard detail="Confirmed remote posts" icon={Rocket} label="Published" value={counts.published} />
                <MetricCard active={counts.attention > 0} detail="Errors requiring action" icon={AlertTriangle} label="Needs attention" value={counts.attention} />
              </div>

              <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(340px,0.65fr)]">
                <Card>
                  <CardHeader className="border-b border-zinc-900">
                    <CardTitle>Recent content</CardTitle>
                    <CardDescription>Real drafts generated in this workspace.</CardDescription>
                    <CardAction>
                      <Button onClick={() => navigate("queue")} size="sm" variant="ghost">View queue <ArrowRight /></Button>
                    </CardAction>
                  </CardHeader>
                  <CardContent className="p-0">
                    {appState.posts.length === 0 ? (
                      <EmptyState
                        action={<Button disabled={!appState.provider.configured} onClick={() => navigate(appState.provider.configured ? "create" : "integrations")} variant="outline"><Sparkles /> {appState.provider.configured ? "Create first draft" : "Connect AI first"}</Button>}
                        description="Generated content will appear here with its approval and publishing state."
                        icon={FilePenLine}
                        title="No content yet"
                      />
                    ) : (
                      <div className="divide-y divide-zinc-900">
                        {appState.posts.slice(0, 6).map((post) => (
                          <button className="group flex w-full items-center gap-4 px-5 py-4 text-left hover:bg-zinc-950" key={post.id} onClick={() => { setQueueFilter(post.status); navigate("queue"); }} type="button">
                            <div className="grid size-9 shrink-0 place-items-center rounded-md border border-zinc-800 bg-black text-zinc-500">
                              <FilePenLine className="size-4" />
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="flex items-center gap-2">
                                <p className="truncate text-xs font-medium text-zinc-200">{post.title}</p>
                                <span className="hidden text-[10px] text-zinc-700 sm:inline">{channelLabels[post.channel]}</span>
                              </div>
                              <p className="mt-1 truncate text-[11px] text-zinc-600">{post.model} · {formatCompactDate(post.updatedAt)}</p>
                            </div>
                            <StatusBadge status={post.status} />
                          </button>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="border-b border-zinc-900">
                    <CardTitle>System readiness</CardTitle>
                    <CardDescription>{setup.complete}/3 modules configured</CardDescription>
                    <CardAction><span className="font-mono text-xs text-zinc-500">{Math.round((setup.complete / 3) * 100)}%</span></CardAction>
                    <Progress aria-label="System readiness" className="col-span-full mt-3" value={(setup.complete / 3) * 100} />
                  </CardHeader>
                  <CardContent className="p-0">
                    <SetupRow complete={setup.business} description="Used as factual context for generation." label="Business profile" onClick={() => navigate("integrations")} />
                    <SetupRow complete={setup.provider} description="Ollama or any OpenAI-compatible API." label="AI provider" onClick={() => navigate("integrations")} />
                    <SetupRow complete={setup.telegram} description="Approval notifications and publishing." label="Telegram" onClick={() => navigate("integrations")} />
                  </CardContent>
                </Card>
              </div>

              <Card>
                <CardHeader className="border-b border-zinc-900">
                  <CardTitle>Latest activity</CardTitle>
                  <CardDescription>Written to the local audit log.</CardDescription>
                </CardHeader>
                <CardContent className="p-0">
                  {appState.audit.length === 0 ? (
                    <EmptyState description="Configuration and workflow actions will be recorded here." icon={Activity} title="No recorded activity" />
                  ) : (
                    <div className="divide-y divide-zinc-900">
                      {appState.audit.slice(0, 5).map((event) => (
                        <div className="flex gap-3 px-5 py-3.5" key={event.id}>
                          <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-zinc-600" />
                          <div className="min-w-0 flex-1">
                            <p className="text-xs text-zinc-300">{event.summary}</p>
                            <p className="mt-1 font-mono text-[10px] text-zinc-700">{event.action}</p>
                          </div>
                          <time className="shrink-0 text-[10px] text-zinc-600" dateTime={event.createdAt}>{formatDate(event.createdAt)}</time>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          ) : null}

          {!loading && appState && activeView === "create" ? (
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
              <Card>
                <CardHeader className="border-b border-zinc-900">
                  <div className="flex items-center gap-3">
                    <IntegrationIcon><Sparkles className="size-4" /></IntegrationIcon>
                    <div>
                      <CardTitle>Generation brief</CardTitle>
                      <CardDescription>One useful brief becomes one reviewable draft.</CardDescription>
                    </div>
                  </div>
                </CardHeader>
                <CardContent>
                  <form className="space-y-5" onSubmit={generatePost}>
                    <Field htmlFor="topic" label="Topic or source brief" hint="Required">
                      <Textarea
                        id="topic"
                        maxLength={1000}
                        onChange={(event) => setGenerateForm((current) => ({ ...current, topic: event.target.value }))}
                        placeholder="Example: Explain how our accounting service helps small retailers close monthly books faster. Do not invent statistics."
                        required
                        rows={7}
                        value={generateForm.topic}
                      />
                    </Field>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Field htmlFor="channel" label="Channel">
                        <Select
                          onValueChange={(value) => value && setGenerateForm((current) => ({ ...current, channel: value as ContentChannel }))}
                          value={generateForm.channel}
                        >
                          <SelectTrigger className="h-10 w-full rounded-md border-input bg-[#080808]" id="channel">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent className="border border-zinc-700 bg-[#0c0c0c]">
                            {channels.map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </Field>
                      <Field htmlFor="tone" label="Tone">
                        <Input id="tone" maxLength={160} onChange={(event) => setGenerateForm((current) => ({ ...current, tone: event.target.value }))} value={generateForm.tone} />
                      </Field>
                    </div>
                    <Field htmlFor="objective" label="Objective">
                      <Input id="objective" maxLength={500} onChange={(event) => setGenerateForm((current) => ({ ...current, objective: event.target.value }))} value={generateForm.objective} />
                    </Field>
                    {generateForm.channel === "instagram" ? (
                      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_180px]">
                        <div className="space-y-3">
                          <Field htmlFor="media-url" label="Public image URL" hint="Required for Instagram">
                            <Input
                              id="media-url"
                              onChange={(event) => setGenerateForm((current) => ({ ...current, mediaUrl: event.target.value }))}
                              pattern="https://.+"
                              placeholder="https://cdn.example.com/campaign-image.jpg"
                              required
                              type="url"
                              value={generateForm.mediaUrl}
                            />
                          </Field>
                          <div className="flex gap-2 rounded-md border border-fuchsia-500/20 bg-fuchsia-500/5 p-3 text-xs leading-5 text-fuchsia-100">
                            <ShieldCheck className="mt-0.5 size-4 shrink-0" />
                            Meta fetches this image during publishing, so it must be reachable over public HTTPS. Localhost and private network URLs are rejected.
                          </div>
                        </div>
                        <MediaPreview url={generateForm.mediaUrl} />
                      </div>
                    ) : null}
                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="flex items-center justify-between gap-5 rounded-md border border-zinc-800 bg-black px-4 py-3.5">
                        <div>
                          <Label className="text-xs text-zinc-200" htmlFor="notify-telegram">Telegram approval</Label>
                          <p className="mt-1 text-[11px] text-zinc-600">Send to the configured Telegram chat.</p>
                        </div>
                        <Switch
                          checked={generateForm.notifyTelegram}
                          disabled={!appState.telegram.configured}
                          id="notify-telegram"
                          onCheckedChange={(checked) => setGenerateForm((current) => ({ ...current, notifyTelegram: checked }))}
                        />
                      </div>
                      <div className="flex items-center justify-between gap-5 rounded-md border border-zinc-800 bg-black px-4 py-3.5">
                        <div>
                          <Label className="text-xs text-zinc-200" htmlFor="notify-slack">Slack approval</Label>
                          <p className="mt-1 text-[11px] text-zinc-600">Send revision-bound action buttons.</p>
                        </div>
                        <Switch
                          checked={generateForm.notifySlack}
                          disabled={slackAccount?.status !== "verified" || !slackAccount.enabled}
                          id="notify-slack"
                          onCheckedChange={(checked) => setGenerateForm((current) => ({ ...current, notifySlack: checked }))}
                        />
                      </div>
                    </div>
                    {!appState.provider.configured ? (
                      <div className="flex items-start gap-3 rounded-md border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-200">
                        <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                        <span>Connect an AI provider and choose a model before generating.</span>
                      </div>
                    ) : null}
                    <div className="flex justify-end border-t border-zinc-900 pt-5">
                      <Button disabled={!appState.provider.configured || !generateForm.topic.trim() || (generateForm.channel === "instagram" && !generateForm.mediaUrl.trim()) || busy === "generate"} size="lg" type="submit">
                        {busy === "generate" ? <Loader2 className="animate-spin" /> : <Sparkles />}
                        {busy === "generate" ? "Generating…" : "Generate review draft"}
                      </Button>
                    </div>
                  </form>
                </CardContent>
              </Card>

              <div className="space-y-4">
                <Card>
                  <CardHeader>
                    <CardTitle>Active engine</CardTitle>
                    <CardDescription>Generation uses the saved connection.</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="flex items-center justify-between gap-3 rounded-md border border-zinc-800 bg-black p-3">
                      <div className="flex min-w-0 items-center gap-3">
                        <Bot className="size-4 shrink-0 text-zinc-500" />
                        <div className="min-w-0">
                          <p className="truncate text-xs font-medium text-zinc-200">{appState.provider.configured ? appState.provider.model : "No model"}</p>
                          <p className="mt-1 truncate font-mono text-[10px] text-zinc-600">{appState.provider.kind}</p>
                        </div>
                      </div>
                      <span className={cn("size-2 rounded-full", appState.provider.configured ? "bg-emerald-400" : "bg-zinc-700")} />
                    </div>
                    <Button className="w-full" onClick={() => navigate("integrations")} variant="outline"><Settings2 /> Configure engine</Button>
                  </CardContent>
                </Card>
                <Card>
                  <CardHeader>
                    <CardTitle>Approval boundary</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4 text-xs leading-5 text-zinc-500">
                    <div className="flex gap-3"><LockKeyhole className="mt-0.5 size-4 shrink-0 text-zinc-400" /><p>AI can create a pending draft, but the publish endpoint rejects unapproved versions.</p></div>
                    <Separator className="bg-zinc-900" />
                    <div className="flex gap-3"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-zinc-400" /><p>Editing an approved draft automatically invalidates that approval.</p></div>
                  </CardContent>
                </Card>
              </div>
            </div>
          ) : null}

          {!loading && appState && activeView === "queue" ? (
            <div className="space-y-4">
              <div className="flex flex-col gap-3 rounded-lg border border-zinc-900 bg-[#050505] p-2 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex gap-1 overflow-x-auto">
                  {(["all", "pending", "approved", "publishing", "published", "skipped"] as QueueFilter[]).map((filter) => {
                    const total = filter === "all" ? appState.posts.length : appState.posts.filter((post) => post.status === filter).length;
                    return (
                      <button className={cn("flex h-8 items-center gap-2 whitespace-nowrap rounded-md px-3 text-xs font-medium transition-colors", queueFilter === filter ? "bg-zinc-800 text-white" : "text-zinc-600 hover:bg-zinc-900 hover:text-zinc-300")} key={filter} onClick={() => setQueueFilter(filter)} type="button">
                        <span className="capitalize">{filter}</span><span className="font-mono text-[10px] text-zinc-500">{total}</span>
                      </button>
                    );
                  })}
                </div>
                <Button onClick={() => navigate("create")} size="sm"><Plus /> New draft</Button>
              </div>

              {filteredPosts.length === 0 ? (
                <Card>
                  <EmptyState
                    action={<Button onClick={() => navigate("create")} variant="outline"><Plus /> Create content</Button>}
                    description={appState.posts.length === 0 ? "Generate your first draft with a connected AI provider." : "No drafts match this status filter."}
                    icon={Inbox}
                    title={appState.posts.length === 0 ? "Queue is empty" : `No ${queueFilter} drafts`}
                  />
                </Card>
              ) : (
                <div className="grid gap-4 2xl:grid-cols-2">
                  {filteredPosts.map((post) => {
                    const scheduledJob = appState.jobs.find(
                      (job) => job.payload.post_id === post.id
                        && job.payload.revision === post.revision
                        && ["queued", "retrying", "running"].includes(job.status),
                    );
                    const publisherReady = post.channel === "telegram"
                      || (post.channel === "blog" && wordpressAccount?.status === "verified" && wordpressAccount.enabled)
                      || (post.channel === "facebook" && metaAccount?.status === "verified" && metaAccount.enabled)
                      || (post.channel === "instagram" && Boolean(post.mediaUrl) && instagramAccount?.status === "verified" && instagramAccount.enabled)
                      || (post.channel === "linkedin" && linkedinAccount?.status === "verified" && linkedinAccount.enabled)
                      || (post.channel === "linkedin-company" && linkedinOrganizationAccount?.status === "verified" && linkedinOrganizationAccount.enabled);
                    return (
                    <Card className="min-w-0" key={post.id}>
                      <CardHeader className="border-b border-zinc-900">
                        <div className="flex min-w-0 items-center gap-2">
                          <Badge className="border-zinc-800 bg-black text-zinc-400" variant="outline">{channelLabels[post.channel]}</Badge>
                          <StatusBadge status={post.status} />
                        </div>
                        <CardAction>
                          <p className="font-mono text-[10px] text-zinc-700">{post.id.slice(0, 8)}</p>
                        </CardAction>
                      </CardHeader>
                      <CardContent className="flex flex-1 flex-col">
                        <div className="flex-1">
                          <h2 className="text-base font-semibold leading-6 text-zinc-100">{post.title}</h2>
                          <p className="mt-3 max-w-[75ch] whitespace-pre-wrap text-sm leading-6 text-zinc-400">{post.body}</p>
                          {post.mediaUrl ? <div className="mt-4 max-w-64"><MediaPreview label={`Media preview for ${post.title}`} url={post.mediaUrl} /></div> : null}
                          {post.hashtags.length > 0 ? (
                            <div className="mt-4 flex flex-wrap gap-1.5">
                              {post.hashtags.map((tag) => <span className="rounded bg-zinc-900 px-1.5 py-1 text-[11px] text-zinc-500" key={tag}>#{tag.replace(/^#/, "")}</span>)}
                            </div>
                          ) : null}
                          {(post.callToAction || post.imagePrompt || post.imageAltText) ? (
                            <details className="mt-4 rounded-md border border-violet-500/15 bg-violet-500/5 px-3 py-2.5 text-xs text-zinc-500">
                              <summary className="cursor-pointer font-medium text-violet-200">Brand content kit · profile R{post.brandProfileVersion}</summary>
                              <div className="mt-3 space-y-3">
                                {post.callToAction ? <div><p className="font-mono text-[9px] tracking-[0.12em] text-zinc-600 uppercase">Call to action</p><p className="mt-1 leading-5 text-zinc-300">{post.callToAction}</p></div> : null}
                                {post.imagePrompt ? <div><p className="font-mono text-[9px] tracking-[0.12em] text-zinc-600 uppercase">Image prompt</p><p className="mt-1 leading-5 text-zinc-400">{post.imagePrompt}</p></div> : null}
                                {post.imageNegativePrompt ? <div><p className="font-mono text-[9px] tracking-[0.12em] text-zinc-600 uppercase">Visual exclusions</p><p className="mt-1 leading-5 text-zinc-500">{post.imageNegativePrompt}</p></div> : null}
                                {post.imageAltText ? <div><p className="font-mono text-[9px] tracking-[0.12em] text-zinc-600 uppercase">Planned alt text</p><p className="mt-1 leading-5 text-zinc-400">{post.imageAltText}</p></div> : null}
                                {post.imagePrompt ? <Button onClick={() => { setMediaGenerationBrief({ id: `${post.id}:${post.revision}`, prompt: post.imagePrompt, negativePrompt: post.imageNegativePrompt, altText: post.imageAltText }); navigate("media"); toast.success("Brand image brief opened in Media Studio"); }} size="sm" variant="outline"><Images />Create image from this brief</Button> : null}
                              </div>
                            </details>
                          ) : null}
                          {post.rationale ? (
                            <details className="mt-4 rounded-md border border-zinc-900 bg-black px-3 py-2.5 text-xs text-zinc-500">
                              <summary className="cursor-pointer font-medium text-zinc-400">AI rationale</summary>
                              <p className="mt-2 leading-5">{post.rationale}</p>
                            </details>
                          ) : null}
                          {scheduledJob ? (
                            <div className="mt-4 flex items-start gap-2 rounded-md border border-sky-500/20 bg-sky-500/5 p-3 text-xs leading-5 text-sky-200">
                              <Clock3 className="mt-0.5 size-3.5 shrink-0" />
                              <div><p className="font-medium">Scheduled for {formatDate(scheduledJob.runAt)}</p><p className="text-sky-300/60">{scheduledJob.status} · attempt {scheduledJob.attempts}/{scheduledJob.maxAttempts}</p></div>
                            </div>
                          ) : null}
                          {post.lastError ? (
                            <div className="mt-4 flex gap-2 rounded-md border border-red-500/20 bg-red-500/5 p-3 text-xs leading-5 text-red-300">
                              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />{post.lastError}
                            </div>
                          ) : null}
                        </div>
                        <div className="mt-5 flex flex-col gap-3 border-t border-zinc-900 pt-4 sm:flex-row sm:items-center sm:justify-between">
                          <div>
                            <p className="font-mono text-[10px] text-zinc-600">{post.model}</p>
                            <time className="mt-1 block text-[10px] text-zinc-700" dateTime={post.updatedAt}>Updated {formatDate(post.updatedAt)}</time>
                          </div>
                          <div className="flex flex-wrap items-center gap-2">
                            {!['publishing', 'published'].includes(post.status) ? <Button onClick={() => openEdit(post)} size="sm" variant="outline"><Pencil /> Edit</Button> : null}
                            {post.status === "pending" ? (
                              <>
                                {slackAccount?.status === "verified" && slackAccount.enabled ? (
                                  <Button disabled={busy === `slack-approval-${post.id}`} onClick={() => void sendSlackApproval(post)} size="sm" variant="outline">{busy === `slack-approval-${post.id}` ? <Loader2 className="animate-spin" /> : <MessageCircle />} Send to Slack</Button>
                                ) : null}
                                <Button disabled={busy === `regenerate-${post.id}`} onClick={() => void regeneratePost(post)} size="sm" variant="outline">{busy === `regenerate-${post.id}` ? <Loader2 className="animate-spin" /> : <RefreshCw />} Regenerate</Button>
                                <Button disabled={busy === `skip-${post.id}`} onClick={() => void decidePost(post, "skip")} size="sm" variant="ghost">{busy === `skip-${post.id}` ? <Loader2 className="animate-spin" /> : <X />} Skip</Button>
                                <Button disabled={busy === `approve-${post.id}`} onClick={() => void decidePost(post, "approve")} size="sm">{busy === `approve-${post.id}` ? <Loader2 className="animate-spin" /> : <Check />} Approve</Button>
                              </>
                            ) : null}
                            {post.status === "approved" && publisherReady ? (
                              <>
                                <Button disabled={Boolean(scheduledJob)} onClick={() => openSchedule(post)} size="sm" variant="outline"><Clock3 /> {scheduledJob ? "Scheduled" : "Schedule"}</Button>
                                <Button disabled={busy === `publish-${post.id}` || Boolean(scheduledJob)} onClick={() => void publishPost(post)} size="sm">{busy === `publish-${post.id}` ? <Loader2 className="animate-spin" /> : <Send />} {post.channel === "blog" ? "Publish to WordPress" : post.channel === "facebook" ? "Publish to Facebook" : post.channel === "instagram" ? "Publish to Instagram" : post.channel === "linkedin" ? "Publish to LinkedIn" : post.channel === "linkedin-company" ? "Publish to Company Page" : "Publish now"}</Button>
                              </>
                            ) : null}
                            {post.status === "approved" && post.channel === "blog" && !publisherReady ? (
                              <Button onClick={() => navigate("integrations")} size="sm" variant="outline"><PlugZap /> Connect WordPress</Button>
                            ) : null}
                            {post.status === "approved" && post.channel === "facebook" && !publisherReady ? (
                              <Button onClick={() => navigate("integrations")} size="sm" variant="outline"><PlugZap /> Connect Facebook Page</Button>
                            ) : null}
                            {post.status === "approved" && post.channel === "instagram" && !publisherReady && !post.mediaUrl ? (
                              <Button onClick={() => openEdit(post)} size="sm" variant="outline"><Pencil /> Add image URL</Button>
                            ) : null}
                            {post.status === "approved" && post.channel === "instagram" && !publisherReady && Boolean(post.mediaUrl) ? (
                              <Button onClick={() => navigate("integrations")} size="sm" variant="outline"><PlugZap /> Connect Instagram</Button>
                            ) : null}
                            {post.status === "approved" && post.channel === "linkedin" && !publisherReady ? (
                              <Button onClick={() => navigate("integrations")} size="sm" variant="outline"><PlugZap /> Connect LinkedIn</Button>
                            ) : null}
                            {post.status === "approved" && post.channel === "linkedin-company" && !publisherReady ? (
                              <Button onClick={() => navigate("integrations")} size="sm" variant="outline"><PlugZap /> Connect Company Page</Button>
                            ) : null}
                            {post.status === "approved" && !["telegram", "blog", "facebook", "instagram", "linkedin", "linkedin-company"].includes(post.channel) ? (
                              <span className="rounded-md border border-zinc-800 px-2.5 py-1.5 text-[11px] text-zinc-600">Publisher not installed</span>
                            ) : null}
                            {post.status === "publishing" ? (
                              <span className="inline-flex items-center gap-2 rounded-md border border-violet-500/20 px-2.5 py-1.5 text-[11px] text-violet-300"><Loader2 className="size-3 animate-spin" /> Sending safely</span>
                            ) : null}
                            {post.status === "published" && post.remoteId ? (
                              post.remoteUrl ? (
                                <a className="inline-flex items-center gap-1.5 font-mono text-[10px] text-emerald-400 hover:text-emerald-300" href={post.remoteUrl} rel="noreferrer" target="_blank">remote:{post.remoteId}<SquareArrowOutUpRight className="size-3" /></a>
                              ) : <span className="font-mono text-[10px] text-emerald-400">remote:{post.remoteId}</span>
                            ) : null}
                          </div>
                        </div>
                      </CardContent>
                    </Card>
                    );
                  })}
                </div>
              )}
            </div>
          ) : null}

          {!loading && appState && activeView === "leads" ? (
            <LeadsWorkspace onStateChange={setAppState} state={appState} />
          ) : null}

          {!loading && appState && activeView === "media" ? (
            <MediaLibrary
              imageProvider={appState.imageProvider}
              initialGenerationBrief={mediaGenerationBrief}
              onStateChange={setAppState}
              onUseInDraft={(asset) => {
                if (!asset.publicSourceUrl) return;
                setGenerateForm((current) => ({
                  ...current,
                  channel: "instagram",
                  mediaUrl: asset.publicSourceUrl ?? "",
                }));
                toast.success("Media source added to an Instagram draft", {
                  description: asset.originalName,
                });
                navigate("create");
              }}
            />
          ) : null}

          {!loading && appState && activeView === "seo" ? (
            <SeoWorkspace schedulerPaused={appState.scheduler.paused} />
          ) : null}

          {!loading && appState && activeView === "scheduler" ? (
            <div className="space-y-4">
              <Card>
                <CardHeader className="border-b border-zinc-900">
                  <div className="flex items-center gap-3">
                    <IntegrationIcon><Clock3 className="size-4" /></IntegrationIcon>
                    <div><CardTitle>Local job worker</CardTitle><CardDescription>SQLite-backed queue that survives app and computer restarts.</CardDescription></div>
                  </div>
                  <CardAction>
                    <Badge className={cn(
                      appState.scheduler.resourceMode === "needs_attention"
                        ? "border-red-500/25 bg-red-500/8 text-red-300"
                        : appState.scheduler.paused
                          ? "border-amber-500/25 bg-amber-500/8 text-amber-300"
                          : "border-emerald-500/25 bg-emerald-500/8 text-emerald-300",
                    )} variant="outline">
                      {appState.scheduler.resourceMode.replace("_", " ")}
                    </Badge>
                  </CardAction>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    <div className="rounded-md border border-zinc-900 bg-black p-3"><p className="text-[10px] uppercase tracking-[0.14em] text-zinc-700">Worker use</p><p className="mt-2 font-mono text-sm text-zinc-200">{appState.scheduler.workersActive} / {appState.scheduler.workerLimit}</p></div>
                    <div className="rounded-md border border-zinc-900 bg-black p-3"><p className="text-[10px] uppercase tracking-[0.14em] text-zinc-700">Recovery</p><p className={cn("mt-2 font-mono text-sm", appState.scheduler.recoveryPending ? "text-orange-300" : "text-zinc-200")}>{appState.scheduler.recoveryPending} waiting</p></div>
                    <div className="rounded-md border border-zinc-900 bg-black p-3"><p className="text-[10px] uppercase tracking-[0.14em] text-zinc-700">Next wake</p><p className="mt-2 truncate text-xs text-zinc-300">{appState.scheduler.nextWakeAt ? formatDate(appState.scheduler.nextWakeAt) : "Event only"}</p></div>
                    <div className="rounded-md border border-zinc-900 bg-black p-3"><p className="text-[10px] uppercase tracking-[0.14em] text-zinc-700">Idle since</p><p className="mt-2 truncate text-xs text-zinc-300">{appState.scheduler.idleSince ? formatCompactDate(appState.scheduler.idleSince) : "Working"}</p></div>
                  </div>
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
                    <div className="grid gap-1 text-xs text-zinc-500">
                      <p>Idle mode waits for the exact next deadline or a local event; no rapid scheduler polling runs.</p>
                      <p>Only one bounded worker runs at a time. Overdue publishes always require Run now, Reschedule, or Skip.</p>
                      {appState.scheduler.lastError ? <p className="text-red-400">{appState.scheduler.lastError}</p> : null}
                    </div>
                    <Button disabled={busy === "scheduler-state"} onClick={() => void configureScheduler(!appState.scheduler.paused)} variant={appState.scheduler.paused ? "default" : "outline"}>
                      {busy === "scheduler-state" ? <Loader2 className="animate-spin" /> : appState.scheduler.paused ? <Play /> : <Pause />}
                      {appState.scheduler.paused ? "Resume worker" : "Pause worker"}
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {appState.jobs.length === 0 ? (
                <Card>
                  <EmptyState action={<Button onClick={() => navigate("queue")} variant="outline"><Inbox /> Open approval queue</Button>} description="Approve a Telegram draft, then choose Schedule." icon={Clock3} title="No local jobs yet" />
                </Card>
              ) : (
                <div className="grid gap-4 xl:grid-cols-2">
                  {appState.jobs.map((job) => {
                    const post = appState.posts.find((item) => item.id === job.payload.post_id);
                    return (
                      <Card key={job.id}>
                        <CardHeader className="border-b border-zinc-900">
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-2">
                              <Badge className={jobStatusStyles[job.status]} variant="outline">{job.status}</Badge>
                              <Badge className="border-zinc-800 bg-black text-zinc-500" variant="outline">revision {job.payload.revision}</Badge>
                            </div>
                            <CardTitle className="mt-3 truncate">{post?.title ?? "Draft unavailable"}</CardTitle>
                            <CardDescription>{job.kind} · {job.id.slice(0, 8)}</CardDescription>
                          </div>
                        </CardHeader>
                        <CardContent className="space-y-4">
                          <div className="grid grid-cols-2 gap-3 rounded-md border border-zinc-900 bg-black p-3 text-xs">
                            <div><p className="text-zinc-600">Run time</p><p className="mt-1 text-zinc-300">{formatDate(job.runAt)}</p><p className="mt-1 text-[10px] text-zinc-600">{formatCompactDate(job.runAt)}</p></div>
                            <div><p className="text-zinc-600">Attempts</p><p className="mt-1 font-mono text-zinc-300">{job.attempts} / {job.maxAttempts}</p></div>
                          </div>
                          {job.lastError ? <div className={cn("flex gap-2 rounded-md p-3 text-xs leading-5", job.status === "missed" ? "border border-orange-500/20 bg-orange-500/5 text-orange-200" : "border border-red-500/20 bg-red-500/5 text-red-300")}><AlertTriangle className="mt-0.5 size-3.5 shrink-0" />{job.lastError}</div> : null}
                          <div className="flex flex-wrap justify-end gap-2">
                            {["queued", "retrying"].includes(job.status) ? <Button disabled={busy === `cancel-job-${job.id}`} onClick={() => void cancelScheduledJob(job)} size="sm" variant="outline">{busy === `cancel-job-${job.id}` ? <Loader2 className="animate-spin" /> : <X />} Cancel</Button> : null}
                            {job.status === "failed" ? <Button disabled={busy === `retry-job-${job.id}`} onClick={() => void retryScheduledJob(job)} size="sm">{busy === `retry-job-${job.id}` ? <Loader2 className="animate-spin" /> : <RefreshCw />} Retry after review</Button> : null}
                            {job.status === "missed" ? <Button onClick={() => openRecovery(job)} size="sm"><AlertTriangle /> Review missed publish</Button> : null}
                          </div>
                        </CardContent>
                      </Card>
                    );
                  })}
                </div>
              )}
            </div>
          ) : null}

          {!loading && appState && activeView === "integrations" ? (
            <div className="space-y-4">
              <Card className="border-amber-500/20 bg-[radial-gradient(circle_at_top_left,rgba(251,191,36,0.09),transparent_42%),#070707]">
                <CardContent className="flex flex-col gap-4 py-4 lg:flex-row lg:items-center lg:justify-between">
                  <div className="flex items-start gap-3">
                    <PlugZap className="mt-0.5 size-4 shrink-0 text-amber-300" />
                    <div>
                      <p className="text-sm font-medium text-zinc-100">Connect only what you use</p>
                      <p className="mt-1 max-w-3xl text-xs leading-5 text-zinc-500">One AI provider is enough. Dashboard approval is built in; Telegram, Slack, and every publishing destination are optional. You never need to configure every connector.</p>
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    <Badge className="border-emerald-500/25 bg-emerald-500/8 text-emerald-300" variant="outline">1 AI REQUIRED</Badge>
                    <Badge className="border-zinc-700 text-zinc-500" variant="outline">ALL OTHERS OPTIONAL</Badge>
                  </div>
                </CardContent>
              </Card>

              <Card className={cn(appState.storage.warnings.length > 0 && "border-amber-500/25")}>
                <CardHeader className="border-b border-zinc-900">
                  <div className="flex items-center gap-3">
                    <IntegrationIcon><Database className="size-4" /></IntegrationIcon>
                    <div><CardTitle>Local storage</CardTitle><CardDescription>Runtime updates cannot overwrite your database, media, credentials, or downloaded AI models.</CardDescription></div>
                  </div>
                  <CardAction>
                    <Badge className={appState.storage.healthy ? "border-emerald-500/25 bg-emerald-500/8 text-emerald-300" : "border-amber-500/25 bg-amber-500/8 text-amber-300"} variant="outline">
                      {appState.storage.healthy ? "HEALTHY" : "CHECK STORAGE"}
                    </Badge>
                  </CardAction>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="grid gap-3 lg:grid-cols-3">
                    {(["runtime", "data", "models"] as const).map((location) => {
                      const details = appState.storage.locations[location];
                      const used = location === "runtime" ? appState.storage.usage.runtimeBytes : location === "data" ? appState.storage.usage.dataBytes : appState.storage.usage.modelsBytes;
                      const volume = location === "runtime" ? null : appState.storage.volumes[location];
                      const usedPercent = volume?.totalBytes ? Math.min(100, Math.round(((volume.totalBytes - volume.freeBytes) / volume.totalBytes) * 100)) : 0;
                      return (
                        <div className="min-w-0 rounded-lg border border-zinc-800 bg-black/60 p-3" key={location}>
                          <div className="flex items-center justify-between gap-2">
                            <p className="text-xs font-semibold capitalize text-zinc-200">{location}</p>
                            <Badge className="border-zinc-800 text-[9px] text-zinc-500" variant="outline">{details.kind}</Badge>
                          </div>
                          <p className="mt-2 truncate font-mono text-[10px] text-zinc-500" title={details.path}>{details.path}</p>
                          <div className="mt-3 flex items-center justify-between text-[10px] text-zinc-600">
                            <span>{formatBytes(used)} used</span>
                            {volume ? <span>{formatBytes(volume.freeBytes)} free</span> : null}
                          </div>
                          {volume ? <Progress aria-label={location === "data" ? "Durable data disk usage" : "Local AI disk usage"} className="mt-2 h-1" value={usedPercent} /> : null}
                        </div>
                      );
                    })}
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                    {Object.entries(appState.storage.usage.categories).map(([category, bytes]) => (
                      <div className="flex items-center justify-between rounded-md border border-zinc-900 bg-[#050505] px-3 py-2" key={category}>
                        <span className="text-[10px] capitalize text-zinc-600">{category}</span>
                        <span className="font-mono text-[10px] text-zinc-300">{formatBytes(bytes)}</span>
                      </div>
                    ))}
                  </div>
                  {appState.storage.warnings.length > 0 ? (
                    <div className="rounded-md border border-amber-500/20 bg-amber-500/5 p-3">
                      {appState.storage.warnings.map((warning) => <p className="flex items-start gap-2 text-xs text-amber-200" key={warning}><AlertTriangle className="mt-0.5 size-3 shrink-0" />{warning}</p>)}
                    </div>
                  ) : null}
                  <div className="flex flex-col gap-2 rounded-md border border-zinc-900 bg-[#050505] p-3 text-xs text-zinc-500 lg:flex-row lg:items-center lg:justify-between">
                    <div><p className="text-zinc-300">Move storage safely from the terminal</p><p className="mt-1">Socium verifies the copy and keeps the old location until you confirm the new one works.</p></div>
                    <code className="overflow-x-auto rounded bg-black px-3 py-2 text-[10px] text-amber-300">{appState.storage.moveCommand}</code>
                  </div>
                </CardContent>
              </Card>

              <BrandProfileCard
                key={`${appState.workspace.profileVersion}-${appState.workspace.updatedAt ?? "new"}`}
                onStateChange={(state) => {
                  setAppState(state);
                  setGenerateForm((current) => ({ ...current, tone: state.workspace.tone || current.tone }));
                }}
                workspace={appState.workspace}
              />

              <div className="grid gap-4 xl:grid-cols-2">
                <Card>
                  <CardHeader className="border-b border-zinc-900">
                    <div className="flex items-center gap-3">
                      <IntegrationIcon><Bot className="size-4" /></IntegrationIcon>
                      <div><CardTitle>AI provider</CardTitle><CardDescription>Choose a service, add its key, and connect.</CardDescription></div>
                    </div>
                    <CardAction><ConnectionStatus configured={appState.provider.configured} verified={providerVerified || appState.provider.verified} /></CardAction>
                  </CardHeader>
                  <CardContent>
                    <form className="space-y-4" onSubmit={(event) => void testProviderConnection(event)}>
                      <div className="grid gap-3 sm:grid-cols-2" role="group" aria-label="AI setup type">
                        <button
                          aria-label="Use local AI"
                          aria-pressed={aiSetupMode === "local"}
                          className={cn("rounded-lg border p-3 text-left transition-colors", aiSetupMode === "local" ? "border-emerald-500/35 bg-emerald-500/8" : "border-zinc-800 bg-black hover:border-zinc-700")}
                          onClick={() => {
                            const preset = getProviderPreset("ollama");
                            setAiSetupMode("local");
                            setProviderForm({ kind: preset.kind, baseUrl: preset.baseUrl, model: "", apiKey: "" });
                            setProviderModels([]);
                            setProviderVerified(false);
                            setLocalAi(null);
                            void refreshLocalAi(preset.baseUrl);
                          }}
                          type="button"
                        >
                          <div className="flex items-center justify-between gap-3"><span className="flex items-center gap-2 text-xs font-semibold text-zinc-100"><Cpu className="size-4 text-emerald-400" />Local AI</span><Badge className="border-emerald-500/25 bg-emerald-500/8 text-[9px] text-emerald-300" variant="outline">RECOMMENDED</Badge></div>
                          <p className="mt-2 text-[10px] leading-4 text-zinc-500">Private, no per-post API bill, and your business context stays on this computer.</p>
                        </button>
                        <button
                          aria-label="Use cloud API"
                          aria-pressed={aiSetupMode === "cloud"}
                          className={cn("rounded-lg border p-3 text-left transition-colors", aiSetupMode === "cloud" ? "border-sky-500/35 bg-sky-500/8" : "border-zinc-800 bg-black hover:border-zinc-700")}
                          onClick={() => {
                            const preset = providerForm.kind === "ollama" ? getProviderPreset("openrouter") : getProviderPreset(providerForm.kind);
                            setAiSetupMode("cloud");
                            setProviderForm({ kind: preset.kind, baseUrl: preset.baseUrl, model: preset.defaultModel, apiKey: "" });
                            setProviderModels([]);
                            setProviderVerified(false);
                          }}
                          type="button"
                        >
                          <div className="flex items-center gap-2 text-xs font-semibold text-zinc-100"><Cloud className="size-4 text-sky-400" />Cloud API</div>
                          <p className="mt-2 text-[10px] leading-4 text-zinc-500">Use OpenRouter, NVIDIA, OpenAI, Gemini, Anthropic, or your own API.</p>
                        </button>
                      </div>

                      <Field htmlFor="provider-kind" label="AI service">
                        <Select
                          onValueChange={(value) => {
                            if (!value) return;
                            const preset = getProviderPreset(value as ProviderKind);
                            setProviderForm({
                              kind: preset.kind,
                              baseUrl: preset.baseUrl,
                              model: preset.defaultModel,
                              apiKey: "",
                            });
                            setProviderModels([]);
                            setProviderVerified(false);
                            setAiSetupMode(preset.kind === "ollama" ? "local" : "cloud");
                            setCustomProtocol(preset.kind === "anthropic-compatible" ? "anthropic-compatible" : preset.kind === "openai-compatible" ? "auto" : "auto");
                            setProtocolChoiceRequired(false);
                            setDiscoveryMessage("");
                            if (preset.kind === "ollama") {
                              setLocalAi(null);
                              void refreshLocalAi(preset.baseUrl);
                            }
                          }}
                          value={providerForm.kind}
                        >
                          <SelectTrigger className="h-10 w-full rounded-md border-input bg-[#080808]" id="provider-kind"><SelectValue /></SelectTrigger>
                          <SelectContent className="border border-zinc-700 bg-[#0c0c0c]">
                            {PROVIDER_PRESETS.filter((preset) => aiSetupMode === "local" ? preset.kind === "ollama" : preset.kind !== "ollama").map((preset) => <SelectItem key={preset.kind} value={preset.kind}>{preset.label}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      </Field>

                      <div className="rounded-md border border-zinc-800 bg-black p-3">
                        <p className="text-xs font-medium text-zinc-200">{selectedProvider.label}</p>
                        <p className="mt-1 text-[11px] leading-5 text-zinc-600">{selectedProvider.description}</p>
                        <div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] text-zinc-600">
                          <Badge className="border-zinc-800 text-zinc-500" variant="outline">
                            {providerForm.model || "Model auto-detect"}
                          </Badge>
                          <span>No Socium account required</span>
                        </div>
                      </div>

                      {providerForm.kind === "ollama" ? (
                        <div className="space-y-3 rounded-lg border border-emerald-500/15 bg-emerald-500/[0.03] p-3">
                          {!localAi ? <div className="flex items-center gap-2 text-xs text-zinc-500"><Loader2 className="size-3 animate-spin" />Inspecting this computer and Ollama…</div> : (
                            <>
                              <div className="grid gap-2 sm:grid-cols-3">
                                <div className="rounded-md border border-zinc-900 bg-black p-2"><p className="text-[9px] uppercase tracking-wider text-zinc-600">Memory</p><p className="mt-1 text-xs text-zinc-200">{formatBytes(localAi.memoryBytes)}</p></div>
                                <div className="rounded-md border border-zinc-900 bg-black p-2"><p className="text-[9px] uppercase tracking-wider text-zinc-600">Graphics</p><p className="mt-1 truncate text-xs text-zinc-200" title={localAi.gpu?.name}>{localAi.gpu?.name || "CPU / unified memory"}</p></div>
                                <div className="rounded-md border border-zinc-900 bg-black p-2"><p className="text-[9px] uppercase tracking-wider text-zinc-600">Ollama</p><p className={cn("mt-1 text-xs", localAi.ollamaRunning ? "text-emerald-300" : "text-amber-300")}>{localAi.ollamaRunning ? "Running" : localAi.ollamaInstalled ? "Installed, not running" : "Not detected"}</p></div>
                              </div>
                              <div className="rounded-md border border-zinc-900 bg-black p-3">
                                <div className="flex flex-wrap items-start justify-between gap-3">
                                  <div><p className="text-xs font-medium text-zinc-200">Recommended: {localAi.selectedRecommendation}</p><p className="mt-1 max-w-xl text-[10px] leading-4 text-zinc-500">{localAi.recommendationReason}</p></div>
                                  <Badge className="border-zinc-800 text-[9px] text-zinc-500" variant="outline">{localAi.recommendationTier}</Badge>
                                </div>
                                <p className="mt-2 truncate font-mono text-[9px] text-zinc-700" title={localAi.modelsDirectory}>Models: {localAi.modelsDirectory}</p>
                              </div>
                              {localAi.ollamaRunning && !localAi.recommendedModelInstalled ? (
                                <div className="space-y-2">
                                  <Button disabled={busy === "local-model-pull"} onClick={() => void downloadRecommendedModel()} type="button" variant="outline">
                                    {busy === "local-model-pull" ? <Loader2 className="animate-spin" /> : <Download />} Download {localAi.selectedRecommendation}
                                  </Button>
                                  {localPull ? <div className="space-y-1"><div className="flex justify-between text-[10px] text-zinc-500"><span>{localPull.status}</span><span>{localPull.percentage}%</span></div><Progress aria-label="Local model download" value={localPull.percentage} /></div> : null}
                                </div>
                              ) : null}
                              {!localAi.ollamaRunning ? <p className="text-[10px] leading-4 text-amber-300">Start Ollama after installing it, then select Check again. Socium will not start or elevate software without your approval.</p> : null}
                              <Button onClick={() => { setLocalAi(null); void refreshLocalAi(providerForm.baseUrl); }} size="sm" type="button" variant="ghost"><RefreshCw />Check again</Button>
                            </>
                          )}
                        </div>
                      ) : null}

                      {providerForm.kind !== "ollama" ? (
                        <Field
                          htmlFor="provider-key"
                          label="API key"
                          hint={providerHasStoredKey ? "Stored securely — leave blank to keep it" : selectedProvider.apiKeyRequired ? "Required" : "Optional"}
                        >
                          <Input
                            autoComplete="off"
                            id="provider-key"
                            onChange={(event) => setProviderForm((current) => ({ ...current, apiKey: event.target.value }))}
                            placeholder={providerHasStoredKey ? "••••••••••••" : selectedProvider.keyPlaceholder}
                            required={selectedProvider.apiKeyRequired && !providerHasStoredKey}
                            type="password"
                            value={providerForm.apiKey}
                          />
                          <CredentialHelp
                            description={selectedProvider.credentialHelp}
                            primary={{ href: selectedProvider.credentialUrl, label: selectedProvider.credentialLabel }}
                            secondary={selectedProvider.docsUrl ? { href: selectedProvider.docsUrl, label: "Official guide" } : undefined}
                          />
                        </Field>
                      ) : null}

                      {providerForm.kind === "ollama" ? (
                        <CredentialHelp
                          description={selectedProvider.credentialHelp}
                          primary={{ href: selectedProvider.credentialUrl, label: selectedProvider.credentialLabel }}
                          secondary={selectedProvider.docsUrl ? { href: selectedProvider.docsUrl, label: "Browse models" } : undefined}
                        />
                      ) : null}

                      {["openai-compatible", "anthropic-compatible"].includes(providerForm.kind) ? (
                        <div className="space-y-3 rounded-md border border-violet-500/20 bg-violet-500/[0.04] p-3">
                          <div className="flex items-start gap-2"><ShieldCheck className="mt-0.5 size-4 shrink-0 text-violet-300" /><div><p className="text-xs font-medium text-zinc-200">Safe API detection</p><p className="mt-1 text-[10px] leading-4 text-zinc-500">Auto detection sends no key. If authentication blocks detection, choose one protocol below; your key is then sent only to that contract on this exact origin.</p></div></div>
                          {protocolChoiceRequired || providerForm.kind === "anthropic-compatible" ? (
                            <Field htmlFor="provider-protocol" label="API protocol" hint="Choose what your provider documents">
                              <Select onValueChange={(value) => value && setCustomProtocol(value as ProviderProtocolHint)} value={customProtocol}>
                                <SelectTrigger className="h-10 w-full rounded-md border-input bg-[#080808]" id="provider-protocol"><SelectValue /></SelectTrigger>
                                <SelectContent className="border border-zinc-700 bg-[#0c0c0c]">
                                  <SelectItem value="openai-compatible">OpenAI-compatible</SelectItem>
                                  <SelectItem value="anthropic-compatible">Anthropic-compatible</SelectItem>
                                  <SelectItem value="ollama">Ollama</SelectItem>
                                </SelectContent>
                              </Select>
                            </Field>
                          ) : null}
                          {discoveryMessage ? <p className="text-[10px] leading-4 text-zinc-400">{discoveryMessage}</p> : null}
                          <Button disabled={busy === "provider-discover" || !providerForm.baseUrl.trim()} onClick={() => void discoverCustomProvider()} type="button" variant="outline">
                            {busy === "provider-discover" ? <Loader2 className="animate-spin" /> : <SearchCheck />} {customProtocol === "auto" ? "Detect API & models" : "Test selected protocol"}
                          </Button>
                        </div>
                      ) : null}

                      <details className="rounded-md border border-zinc-900 bg-black px-3 py-2.5" key={providerForm.kind} open={providerForm.kind === "openai-compatible" ? true : undefined}>
                        <summary className="cursor-pointer text-xs font-medium text-zinc-500">Advanced settings</summary>
                        <div className="mt-4 space-y-4 border-t border-zinc-900 pt-4">
                          <Field htmlFor="provider-url" label="Base URL" hint={providerForm.kind === "ollama" ? "Change only if Ollama uses another port" : ["openai-compatible", "anthropic-compatible"].includes(providerForm.kind) ? "Your API root or /v1 URL" : "Managed by this preset"}>
                            <Input
                              disabled={!['ollama', 'openai-compatible', 'anthropic-compatible'].includes(providerForm.kind)}
                              id="provider-url"
                              onChange={(event) => { setProviderForm((current) => ({ ...current, baseUrl: event.target.value })); setProtocolChoiceRequired(false); setDiscoveryMessage(""); if (providerForm.kind === "ollama") setLocalAi(null); }}
                              required
                              type="url"
                              value={providerForm.baseUrl}
                            />
                          </Field>
                          <Field htmlFor="provider-model" label="Model" hint={providerForm.kind === "ollama" ? "Detected from installed Ollama models" : "A working default is already selected"}>
                            <Input
                              id="provider-model"
                              list="provider-models"
                              maxLength={180}
                              onChange={(event) => setProviderForm((current) => ({ ...current, model: event.target.value }))}
                              placeholder={providerForm.kind === "ollama" ? "Detected after connection" : "model-name"}
                              required={["openai-compatible", "anthropic-compatible"].includes(providerForm.kind)}
                              value={providerForm.model}
                            />
                            <datalist id="provider-models">{providerModels.map((model) => <option key={model} value={model} />)}</datalist>
                          </Field>
                        </div>
                      </details>

                      <div className="flex flex-col gap-3 border-t border-zinc-900 pt-4 sm:flex-row sm:items-center sm:justify-between">
                        <div className="flex items-start gap-2 text-[10px] leading-4 text-zinc-600">
                          <LockKeyhole className="mt-0.5 size-3 shrink-0" />
                          API keys are encrypted and stay on this device.
                        </div>
                        <Button disabled={busy === "provider-test" || !providerCanConnect} type="submit">
                          {busy === "provider-test" ? <Loader2 className="animate-spin" /> : <PlugZap />}
                          {busy === "provider-test" ? "Connecting…" : providerForm.kind === "ollama" && !providerForm.model ? "Find local model" : "Connect provider"}
                        </Button>
                      </div>
                    </form>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader className="border-b border-zinc-900">
                    <div className="flex items-center gap-3">
                      <IntegrationIcon><MessageCircle className="size-4" /></IntegrationIcon>
                      <div><CardTitle>Telegram</CardTitle><CardDescription>Approval notifications and real publishing.</CardDescription></div>
                    </div>
                    <CardAction><ConnectionStatus configured={appState.telegram.configured} verified={telegramVerified} /></CardAction>
                  </CardHeader>
                  <CardContent>
                    <form className="space-y-4" onSubmit={(event) => void saveTelegram(event)}>
                      <Field htmlFor="bot-token" label="Bot token" hint={appState.telegram.hasBotToken ? "Stored — blank keeps current token" : "From @BotFather"}>
                        <Input autoComplete="off" id="bot-token" onChange={(event) => setTelegramForm((current) => ({ ...current, botToken: event.target.value }))} placeholder={appState.telegram.hasBotToken ? "••••••••••••" : "123456:ABC…"} type="password" value={telegramForm.botToken} />
                        <CredentialHelp
                          description="Open @BotFather, send /newbot, finish the prompts, then paste this bot token above. Message the new bot once before testing."
                          primary={{ href: "https://t.me/BotFather", label: "Get bot token" }}
                          secondary={{ href: "https://core.telegram.org/bots/tutorial", label: "Official guide" }}
                        />
                      </Field>
                      <Field htmlFor="chat-id" label="Approval chat ID" hint="User, group, or channel"><Input id="chat-id" maxLength={160} onChange={(event) => setTelegramForm((current) => ({ ...current, chatId: event.target.value }))} placeholder="-1001234567890" required value={telegramForm.chatId} /></Field>
                      <div className="space-y-3 rounded-md border border-zinc-800 bg-black p-3">
                        <div className="flex items-start gap-3">
                          <RadioTower className={cn("mt-0.5 size-4 shrink-0", appState.telegram.pollingActive ? "text-emerald-400" : "text-zinc-500")} />
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <p className="text-xs font-medium text-zinc-300">Local approval listener</p>
                              {appState.telegram.pollingActive ? <Badge className="border-emerald-500/25 bg-emerald-500/8 text-emerald-300" variant="outline">Listening</Badge> : appState.telegram.pollingEnabled ? <Badge className="border-amber-500/25 bg-amber-500/8 text-amber-300" variant="outline">{appState.telegram.pollingStatus}</Badge> : null}
                            </div>
                            <p className="mt-1 text-[11px] leading-4 text-zinc-600">Receives Telegram button decisions through outbound long polling. No domain, tunnel, or public webhook required.</p>
                            {appState.telegram.lastError ? <p className="mt-2 text-[11px] leading-4 text-red-400">{appState.telegram.lastError}</p> : null}
                          </div>
                        </div>
                        <Button className="w-full" disabled={!appState.telegram.configured || busy === "telegram-polling"} onClick={() => void configureTelegramPolling(!appState.telegram.pollingEnabled)} type="button" variant="outline">{busy === "telegram-polling" ? <Loader2 className="animate-spin" /> : <RadioTower />} {appState.telegram.pollingEnabled ? "Stop local approvals" : "Start local approvals"}</Button>
                      </div>
                      <div className="flex flex-wrap justify-end gap-2 border-t border-zinc-900 pt-4">
                        <Button disabled={busy === "telegram-save"} type="submit" variant="outline">{busy === "telegram-save" ? <Loader2 className="animate-spin" /> : <Check />} Save</Button>
                        <Button disabled={busy === "telegram-test" || busy === "telegram-save"} onClick={() => void testTelegramConnection()} type="button">{busy === "telegram-test" ? <Loader2 className="animate-spin" /> : <PlugZap />} Save & test</Button>
                      </div>
                    </form>
                  </CardContent>
                </Card>
              </div>

              <Card className="overflow-hidden">
                <CardHeader className="border-b border-zinc-900">
                  <div className="flex items-center gap-3">
                    <IntegrationIcon><LockKeyhole className="size-4" /></IntegrationIcon>
                    <div><CardTitle>Slack approval connector</CardTitle><CardDescription>Outbound approval buttons and local Socket Mode decisions.</CardDescription></div>
                  </div>
                  <CardAction>
                    <Badge
                      className={cn(
                        slackAccount?.status === "verified" && slackAccount.listener.status !== "retrying" && "border-emerald-500/25 bg-emerald-500/8 text-emerald-300",
                        slackAccount?.listener.status === "retrying" && "border-amber-500/25 bg-amber-500/8 text-amber-300",
                        slackAccount?.status === "error" && "border-red-500/25 bg-red-500/8 text-red-300",
                        (!slackAccount || slackAccount.status === "saved") && "border-zinc-700 text-zinc-400",
                      )}
                      variant="outline"
                    >
                      {slackAccount?.listener.active ? "Listening" : slackAccount?.listener.status === "retrying" ? "Retrying" : slackAccount?.status === "verified" ? "Verified" : slackAccount?.status === "error" ? "Needs attention" : slackAccount ? "Saved" : "Not configured"}
                    </Badge>
                  </CardAction>
                </CardHeader>
                <CardContent className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
                  <form className="space-y-4" onSubmit={(event) => void saveSlackConnector(event)}>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <Field htmlFor="slack-name" label="Connection name"><Input id="slack-name" maxLength={80} onChange={(event) => setSlackForm((current) => ({ ...current, name: event.target.value }))} placeholder="Slack approvals" required value={slackForm.name} /></Field>
                      <Field htmlFor="slack-channel" label="Approval channel ID" hint="Starts with C"><Input id="slack-channel" maxLength={120} onChange={(event) => setSlackForm((current) => ({ ...current, approvalChannelId: event.target.value }))} placeholder="C0123456789" required value={slackForm.approvalChannelId} /></Field>
                      <Field htmlFor="slack-bot-token" label="Bot token" hint={slackAccount?.secretStatus.bot_token ? "Stored securely — blank keeps it" : "Slack OAuth bot token"}>
                        <Input autoComplete="new-password" id="slack-bot-token" onChange={(event) => setSlackForm((current) => ({ ...current, botToken: event.target.value }))} placeholder={slackAccount?.secretStatus.bot_token ? "••••••••••••" : "xoxb-…"} required={!slackAccount?.secretStatus.bot_token} type="password" value={slackForm.botToken} />
                        <CredentialHelp
                          description="Open your Slack app, add the bot scopes, then install/reinstall it to the workspace and copy the xoxb token from OAuth & Permissions."
                          primary={{ href: "https://api.slack.com/apps", label: "Get bot token" }}
                          secondary={{ href: "https://api.slack.com/tutorials/tracks/getting-a-token", label: "Exact steps" }}
                        />
                      </Field>
                      <Field htmlFor="slack-app-token" label="App token" hint={slackAccount?.secretStatus.app_token ? "Stored securely — blank keeps it" : "Socket Mode app token"}>
                        <Input autoComplete="new-password" id="slack-app-token" onChange={(event) => setSlackForm((current) => ({ ...current, appToken: event.target.value }))} placeholder={slackAccount?.secretStatus.app_token ? "••••••••••••" : "xapp-…"} required={!slackAccount?.secretStatus.app_token} type="password" value={slackForm.appToken} />
                        <CredentialHelp
                          description="Open the same Slack app, enable Socket Mode, create an app-level token with connections:write, and paste its xapp token above."
                          primary={{ href: "https://api.slack.com/apps", label: "Get app token" }}
                          secondary={{ href: "https://api.slack.com/apis/events-api/using-socket-mode", label: "Socket Mode steps" }}
                        />
                      </Field>
                    </div>

                    <div className="flex items-center justify-between gap-4 rounded-md border border-zinc-800 bg-black p-3">
                      <div>
                        <Label className="text-xs text-zinc-200" htmlFor="slack-enabled">Connector enabled</Label>
                        <p className="mt-1 text-[11px] leading-4 text-zinc-600">Disable without deleting locally stored settings.</p>
                      </div>
                      <Switch checked={slackForm.enabled} id="slack-enabled" onCheckedChange={(enabled) => setSlackForm((current) => ({ ...current, enabled }))} />
                    </div>

                    {slackAccount?.lastError ? <div className="flex gap-2 rounded-md border border-red-500/20 bg-red-500/5 p-3 text-xs leading-5 text-red-300"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" /><span>{slackAccount.lastError}</span></div> : null}

                    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-900 pt-4">
                      <div>{slackAccount ? <Button disabled={busy === "slack-delete"} onClick={() => setDeleteConnector(slackAccount)} type="button" variant="ghost"><X /> Remove</Button> : null}</div>
                      <div className="flex flex-wrap gap-2">
                        <Button disabled={busy === "slack-save" || busy === "slack-test"} type="submit" variant="outline">{busy === "slack-save" ? <Loader2 className="animate-spin" /> : <Check />} Save</Button>
                        <Button disabled={busy === "slack-save" || busy === "slack-test"} onClick={() => void testSlackConnection()} type="button">{busy === "slack-test" ? <Loader2 className="animate-spin" /> : <PlugZap />} Save & test</Button>
                      </div>
                    </div>
                  </form>

                  <div className="space-y-4 rounded-md border border-zinc-800 bg-black p-4">
                    <div className="flex items-start gap-3">
                      <ShieldCheck className="mt-0.5 size-4 shrink-0 text-emerald-400" />
                      <div><p className="text-xs font-medium text-zinc-200">Local secret vault</p><p className="mt-1 text-[11px] leading-5 text-zinc-600">Tokens are AES-256-GCM encrypted at rest. The API and browser receive presence flags, never token values.</p></div>
                    </div>
                    <Separator className="bg-zinc-900" />
                    <div className="flex items-start gap-3 rounded-md border border-zinc-900 p-3">
                      <RadioTower className={cn("mt-0.5 size-4 shrink-0", slackAccount?.listener.active ? "text-emerald-400" : slackAccount?.listener.status === "retrying" ? "text-amber-400" : "text-zinc-600")} />
                      <div className="min-w-0"><p className="text-xs font-medium text-zinc-300">Socket Mode listener · <span className="font-normal capitalize text-zinc-500">{slackAccount?.listener.status ?? "stopped"}</span></p><p className="mt-1 text-[11px] leading-5 text-zinc-600">Runs outbound-only while this verified connector is enabled.</p>{slackAccount?.listener.lastError ? <p className="mt-2 text-[11px] leading-5 text-amber-300">{slackAccount.listener.lastError}</p> : null}</div>
                    </div>
                    <div>
                      <p className="text-[10px] font-semibold tracking-[0.16em] text-zinc-600 uppercase">Required scopes</p>
                      <div className="mt-2 flex flex-wrap gap-2"><Badge variant="outline">chat:write</Badge><Badge variant="outline">connections:write</Badge></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3 text-xs">
                      <div className="rounded-md border border-zinc-900 p-3"><p className="text-zinc-600">Bot token</p><p className={cn("mt-1", slackAccount?.secretStatus.bot_token ? "text-emerald-300" : "text-zinc-500")}>{slackAccount?.secretStatus.bot_token ? "Stored" : "Missing"}</p></div>
                      <div className="rounded-md border border-zinc-900 p-3"><p className="text-zinc-600">App token</p><p className={cn("mt-1", slackAccount?.secretStatus.app_token ? "text-emerald-300" : "text-zinc-500")}>{slackAccount?.secretStatus.app_token ? "Stored" : "Missing"}</p></div>
                    </div>
                    {slackAccount?.lastVerifiedAt ? <p className="font-mono text-[10px] text-zinc-600">Last verified {formatDate(slackAccount.lastVerifiedAt)}</p> : null}
                    <p className="text-[11px] leading-5 text-zinc-700">Approve, Regenerate, Edit, and Skip are one-time actions bound to the exact draft revision. They expire after 72 hours; stale, repeated, or mismatched clicks fail closed.</p>
                  </div>
                </CardContent>
              </Card>

              <WordPressConnectorCard
                account={wordpressAccount}
                busy={busy}
                form={wordpressForm}
                onChange={(patch) => setWordpressForm((current) => ({ ...current, ...patch }))}
                onRemove={() => wordpressAccount && setDeleteConnector(wordpressAccount)}
                onSave={(event) => void saveWordPressConnector(event)}
                onTest={() => void testWordPressConnection()}
              />

              <MetaConnectorCard
                account={metaAccount}
                busy={busy}
                form={metaForm}
                onChange={(patch) => setMetaForm((current) => ({ ...current, ...patch }))}
                onRemove={() => metaAccount && setDeleteConnector(metaAccount)}
                onSave={(event) => void saveMetaConnector(event)}
                onTest={() => void testMetaConnection()}
              />

              <InstagramConnectorCard
                account={instagramAccount}
                busy={busy}
                form={instagramForm}
                onChange={(patch) => setInstagramForm((current) => ({ ...current, ...patch }))}
                onRemove={() => instagramAccount && setDeleteConnector(instagramAccount)}
                onSave={(event) => void saveInstagramConnector(event)}
                onTest={() => void testInstagramConnection()}
              />

              <LinkedInConnectorCard
                account={linkedinAccount}
                busy={busy}
                form={linkedinForm}
                onChange={(patch) => setLinkedinForm((current) => ({ ...current, ...patch }))}
                onRemove={() => linkedinAccount && setDeleteConnector(linkedinAccount)}
                onSave={(event) => void saveLinkedInConnector(event)}
                onTest={() => void testLinkedInConnection()}
              />

              <LinkedInOrganizationConnectorCard
                account={linkedinOrganizationAccount}
                busy={busy}
                form={linkedinOrganizationForm}
                onChange={(patch) => setLinkedinOrganizationForm((current) => ({ ...current, ...patch }))}
                onRemove={() => linkedinOrganizationAccount && setDeleteConnector(linkedinOrganizationAccount)}
                onSave={(event) => void saveLinkedInOrganizationConnector(event)}
                onTest={() => void testLinkedInOrganizationConnection()}
              />

              <div>
                <div className="mb-3 flex items-end justify-between gap-3">
                  <div><h3 className="text-sm font-medium text-zinc-200">Connector roadmap</h3><p className="mt-1 text-xs text-zinc-600">Availability is reported by the backend adapter registry.</p></div>
                  <Badge className="border-zinc-800 text-zinc-500" variant="outline">{upcomingConnectors.length} adapters</Badge>
                </div>
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                  {upcomingConnectors.map((connector) => (
                    <Card className="bg-[#050505]" key={connector.adapterId}>
                      <CardHeader className="pb-3">
                        <div className="flex items-start justify-between gap-3"><IntegrationIcon><PlugZap className="size-4" /></IntegrationIcon><Badge className="border-zinc-800 text-zinc-500 capitalize" variant="outline">{connector.availability.replaceAll("-", " ")}</Badge></div>
                        <div><CardTitle className="text-sm">{connector.name}</CardTitle><CardDescription className="mt-1 leading-5">{connector.description}</CardDescription></div>
                      </CardHeader>
                      <CardContent className="pt-0"><div className="flex flex-wrap gap-1.5">{connector.capabilities.map((capability) => <Badge className="text-[9px] text-zinc-600" key={capability} variant="outline">{capability}</Badge>)}</div></CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            </div>
          ) : null}

          {!loading && appState && activeView === "activity" ? (
            <Card>
              <CardHeader className="border-b border-zinc-900">
                <CardTitle>Audit log</CardTitle>
                <CardDescription>{appState.audit.length} durable event{appState.audit.length === 1 ? "" : "s"} on this host.</CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                {appState.audit.length === 0 ? (
                  <EmptyState description="Save a connection or generate content to create the first event." icon={Activity} title="Audit log is empty" />
                ) : (
                  <div className="divide-y divide-zinc-900">
                    {appState.audit.map((event) => (
                      <div className="grid gap-3 px-5 py-4 sm:grid-cols-[32px_minmax(0,1fr)_auto] sm:items-center" key={event.id}>
                        <div className="grid size-8 place-items-center rounded-md border border-zinc-800 bg-black text-zinc-600"><Activity className="size-3.5" /></div>
                        <div className="min-w-0"><p className="text-xs text-zinc-300">{event.summary}</p><p className="mt-1 font-mono text-[10px] text-zinc-700">{event.action} · {event.entityType}:{event.entityId.slice(0, 12)}</p></div>
                        <time className="text-[10px] text-zinc-600" dateTime={event.createdAt}>{formatDate(event.createdAt)}</time>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          ) : null}
        </main>
      </div>

      <Dialog onOpenChange={(open) => !open && setEditPost(null)} open={Boolean(editPost)}>
        <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Edit draft</DialogTitle>
            <DialogDescription>Saving creates a new content version and resets any previous approval.</DialogDescription>
          </DialogHeader>
          <form className="space-y-4" id="edit-draft-form" onSubmit={saveEdit}>
            <Field htmlFor="edit-title" label="Title"><Input id="edit-title" maxLength={160} onChange={(event) => setEditForm((current) => ({ ...current, title: event.target.value }))} required value={editForm.title} /></Field>
            <Field htmlFor="edit-body" label="Post body"><Textarea id="edit-body" maxLength={12000} onChange={(event) => setEditForm((current) => ({ ...current, body: event.target.value }))} required rows={10} value={editForm.body} /></Field>
            <Field htmlFor="edit-tags" label="Hashtags" hint="Separate with spaces or commas"><Input id="edit-tags" onChange={(event) => setEditForm((current) => ({ ...current, hashtags: event.target.value }))} value={editForm.hashtags} /></Field>
            <Field htmlFor="edit-cta" label="Call to action"><Input id="edit-cta" maxLength={500} onChange={(event) => setEditForm((current) => ({ ...current, callToAction: event.target.value }))} value={editForm.callToAction} /></Field>
            <Field htmlFor="edit-image-prompt" label="Image prompt"><Textarea id="edit-image-prompt" maxLength={4000} onChange={(event) => setEditForm((current) => ({ ...current, imagePrompt: event.target.value }))} rows={5} value={editForm.imagePrompt} /></Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field htmlFor="edit-image-negative-prompt" label="Visual exclusions"><Textarea id="edit-image-negative-prompt" maxLength={2000} onChange={(event) => setEditForm((current) => ({ ...current, imageNegativePrompt: event.target.value }))} rows={3} value={editForm.imageNegativePrompt} /></Field>
              <Field htmlFor="edit-image-alt-text" label="Planned alt text"><Textarea id="edit-image-alt-text" maxLength={500} onChange={(event) => setEditForm((current) => ({ ...current, imageAltText: event.target.value }))} rows={3} value={editForm.imageAltText} /></Field>
            </div>
            {editPost?.channel === "instagram" ? (
              <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_160px]">
                <Field htmlFor="edit-media-url" label="Public image URL" hint="Required for Instagram">
                  <Input id="edit-media-url" onChange={(event) => setEditForm((current) => ({ ...current, mediaUrl: event.target.value }))} pattern="https://.+" required type="url" value={editForm.mediaUrl} />
                </Field>
                <MediaPreview label={`Updated media preview for ${editPost.title}`} url={editForm.mediaUrl} />
              </div>
            ) : null}
            <div className="flex gap-2 rounded-md border border-amber-500/20 bg-amber-500/5 p-3 text-xs leading-5 text-amber-200"><AlertTriangle className="mt-0.5 size-4 shrink-0" />Editing invalidates approval. The updated draft returns to Pending.</div>
          </form>
          <DialogFooter className="border-zinc-800 bg-[#090909]">
            <Button onClick={() => setEditPost(null)} type="button" variant="ghost">Cancel</Button>
            <Button disabled={Boolean(editPost && busy === `edit-${editPost.id}`)} form="edit-draft-form" type="submit">{editPost && busy === `edit-${editPost.id}` ? <Loader2 className="animate-spin" /> : <Check />} Save new version</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog onOpenChange={(open) => !open && setScheduleTarget(null)} open={Boolean(scheduleTarget)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Schedule approved draft</DialogTitle>
            <DialogDescription>The durable local worker will publish this exact revision to {scheduleTarget ? publisherDisplayName(scheduleTarget.channel) : "the selected publisher"}.</DialogDescription>
          </DialogHeader>
          <form className="space-y-4" id="schedule-draft-form" onSubmit={schedulePost}>
            <div className="rounded-md border border-zinc-900 bg-black p-3">
              <p className="truncate text-sm font-medium text-zinc-200">{scheduleTarget?.title}</p>
              <p className="mt-1 font-mono text-[10px] text-zinc-600">revision {scheduleTarget?.revision} · {scheduleTarget?.id.slice(0, 8)}</p>
            </div>
            <Field htmlFor="schedule-at" label="Publish time" hint="Your computer's local timezone">
              <Input id="schedule-at" onChange={(event) => setScheduleAt(event.target.value)} required type="datetime-local" value={scheduleAt} />
            </Field>
            <div className="flex gap-2 rounded-md border border-sky-500/20 bg-sky-500/5 p-3 text-xs leading-5 text-sky-200"><ShieldCheck className="mt-0.5 size-4 shrink-0" />If Socium is closed or paused at this time, nothing is posted automatically. You will choose Run now, Reschedule, or Skip after restart.</div>
          </form>
          <DialogFooter className="border-zinc-800 bg-[#090909]">
            <Button onClick={() => setScheduleTarget(null)} type="button" variant="ghost">Cancel</Button>
            <Button disabled={Boolean(scheduleTarget && busy === `schedule-${scheduleTarget.id}`)} form="schedule-draft-form" type="submit">{scheduleTarget && busy === `schedule-${scheduleTarget.id}` ? <Loader2 className="animate-spin" /> : <Clock3 />} Schedule locally</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog onOpenChange={(open) => !open && dismissRecovery()} open={Boolean(recoveryJob)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Missed scheduled publish</DialogTitle>
            <DialogDescription>Socium did not silently catch up. Review this exact approved revision before anything is sent.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="rounded-md border border-orange-500/20 bg-orange-500/5 p-4">
              <div className="flex items-start gap-3">
                <AlertTriangle className="mt-0.5 size-4 shrink-0 text-orange-300" />
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-zinc-100">{recoveryJob ? appState?.posts.find((post) => post.id === recoveryJob.payload.post_id)?.title ?? "Approved draft" : "Approved draft"}</p>
                  <p className="mt-1 font-mono text-[10px] text-zinc-600">revision {recoveryJob?.payload.revision} · scheduled {recoveryJob ? formatDate(recoveryJob.runAt) : ""}</p>
                  <p className="mt-3 text-xs leading-5 text-orange-100/80">{recoveryJob?.recoveryReason ?? "The scheduled time passed while the local worker was unavailable."}</p>
                </div>
              </div>
            </div>
            {recoveryMode === "reschedule" ? (
              <Field htmlFor="recovery-at" label="New publish time" hint="Choose a future time in your local timezone">
                <Input id="recovery-at" onChange={(event) => setRecoveryAt(event.target.value)} required type="datetime-local" value={recoveryAt} />
              </Field>
            ) : (
              <div className="grid gap-2 sm:grid-cols-3">
                <Button disabled={Boolean(recoveryJob && busy?.startsWith(`recover-job-${recoveryJob.id}`))} onClick={() => recoveryJob && void recoverScheduledJob(recoveryJob, "run_now")} type="button"><Play /> Run now</Button>
                <Button disabled={Boolean(recoveryJob && busy?.startsWith(`recover-job-${recoveryJob.id}`))} onClick={() => setRecoveryMode("reschedule")} type="button" variant="outline"><Clock3 /> Reschedule</Button>
                <Button disabled={Boolean(recoveryJob && busy?.startsWith(`recover-job-${recoveryJob.id}`))} onClick={() => recoveryJob && void recoverScheduledJob(recoveryJob, "skip")} type="button" variant="ghost"><X /> Skip</Button>
              </div>
            )}
          </div>
          <DialogFooter className="border-zinc-800 bg-[#090909]">
            {recoveryMode === "reschedule" ? (
              <>
                <Button onClick={() => setRecoveryMode("choice")} type="button" variant="ghost">Back</Button>
                <Button disabled={Boolean(recoveryJob && busy === `recover-job-${recoveryJob.id}-reschedule`)} onClick={() => recoveryJob && void recoverScheduledJob(recoveryJob, "reschedule")} type="button">{recoveryJob && busy === `recover-job-${recoveryJob.id}-reschedule` ? <Loader2 className="animate-spin" /> : <Clock3 />} Confirm new time</Button>
              </>
            ) : <Button onClick={dismissRecovery} type="button" variant="ghost">Decide later</Button>}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog onOpenChange={(open) => !open && setDeleteConnector(null)} open={Boolean(deleteConnector)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Remove {deleteConnector?.adapterName} connector?</DialogTitle>
            <DialogDescription>This deletes the connection and its encrypted credentials from this computer. It does not change the remote service.</DialogDescription>
          </DialogHeader>
          <div className="rounded-md border border-red-500/20 bg-red-500/5 p-3 text-xs leading-5 text-red-200">This local deletion cannot be undone. You can reconnect later with fresh tokens.</div>
          <DialogFooter className="border-zinc-800 bg-[#090909]">
            <Button disabled={busy === `${deleteConnector?.adapterId}-delete`} onClick={() => setDeleteConnector(null)} type="button" variant="ghost">Cancel</Button>
            <Button disabled={busy === `${deleteConnector?.adapterId}-delete`} onClick={() => void removeConnector()} type="button" variant="destructive">{busy === `${deleteConnector?.adapterId}-delete` ? <Loader2 className="animate-spin" /> : <X />} Remove locally</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
