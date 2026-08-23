"use client";

import {
  ArrowRight,
  Bot,
  Building2,
  Check,
  FileCheck2,
  LockKeyhole,
  MessageCircle,
  RadioTower,
  ShieldCheck,
  TerminalSquare,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { PublicAppState } from "@/lib/app-types";
import { cn } from "@/lib/utils";

type SetupGuideProps = {
  state: PublicAppState;
  onCreateContent: () => void;
  onOpenConnections: () => void;
  onOpenQueue: () => void;
  onOpenScheduler: () => void;
  onOpenOnboarding: () => void;
};

type GuideStep = {
  action: string;
  complete: boolean;
  description: string;
  detail: string;
  icon: LucideIcon;
  label: string;
  onAction: () => void;
  optional?: boolean;
};

const runtimeCommands = [
  { command: "npx socium start", label: "Start again" },
  { command: "npx socium doctor", label: "Check the installation" },
  { command: "npx socium update", label: "Install an available update" },
  { command: "npx socium uninstall --yes", label: "Remove runtime, keep local data" },
];

function GuideStepCard({ step, number }: { step: GuideStep; number: number }) {
  const Icon = step.icon;
  return (
    <li>
      <Card className={cn("h-full overflow-hidden", step.complete && "border-emerald-500/20")}>
        <CardContent className="flex h-full flex-col p-0">
          <div className="flex flex-1 gap-4 p-5">
            <div
              className={cn(
                "grid size-10 shrink-0 place-items-center rounded-md border",
                step.complete
                  ? "border-emerald-500/25 bg-emerald-500/8 text-emerald-300"
                  : "border-zinc-800 bg-black text-zinc-500",
              )}
            >
              {step.complete ? <Check className="size-4" /> : <Icon className="size-4" />}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[10px] text-zinc-700">STEP {number}</span>
                <Badge
                  className={cn(
                    "border text-[9px]",
                    step.complete
                      ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-300"
                      : "border-zinc-800 text-zinc-500",
                  )}
                  variant="outline"
                >
                  {step.complete ? "COMPLETE" : step.optional ? "RECOMMENDED" : "REQUIRED"}
                </Badge>
              </div>
              <h2 className="mt-2 text-sm font-semibold text-zinc-100">{step.label}</h2>
              <p className="mt-1 text-xs leading-5 text-zinc-500">{step.description}</p>
              <p className="mt-3 text-[11px] leading-5 text-zinc-600">{step.detail}</p>
            </div>
          </div>
          <div className="border-t border-zinc-900 px-5 py-3">
            <Button className="w-full justify-between" onClick={step.onAction} size="sm" variant="ghost">
              {step.complete ? "Review settings" : step.action}
              <ArrowRight className="size-3.5" />
            </Button>
          </div>
        </CardContent>
      </Card>
    </li>
  );
}

export function SetupGuide({
  state,
  onCreateContent,
  onOpenConnections,
  onOpenQueue,
  onOpenScheduler,
  onOpenOnboarding,
}: SetupGuideProps) {
  const approvalReady = Boolean(
    (state.telegram.configured && state.telegram.pollingEnabled)
      || state.connectors.accounts.some(
        (account) => account.enabled && account.status === "verified" && account.capabilities.includes("approval"),
      ),
  );
  const publisherAccounts = state.connectors.accounts.filter(
    (account) => account.enabled && account.status === "verified" && account.capabilities.includes("publish"),
  );
  const publisherReady = state.telegram.configured || publisherAccounts.length > 0;
  const publisherSummary = [
    ...(state.telegram.configured ? ["Telegram"] : []),
    ...publisherAccounts.map((account) => account.adapterName),
  ].join(", ");

  const steps: GuideStep[] = [
    {
      action: "Add business profile",
      complete: state.workspace.profileComplete,
      description: "Give generation a factual description of the business, audience, location, and safe claims.",
      detail: "This profile becomes reusable context for every draft. Do not place API keys or private customer data in the description.",
      icon: Building2,
      label: "Describe the business",
      onAction: onOpenConnections,
    },
    {
      action: "Connect an AI provider",
      complete: state.provider.verified,
      description: "Choose local Ollama, OpenAI, Gemini, Claude, OpenRouter, or NVIDIA and connect it with one form.",
      detail: "Hosted presets only need their own API key. Socium supplies the endpoint and a working default model. Ollama models are detected locally. No Socium account is required.",
      icon: Bot,
      label: "Connect the content engine",
      onAction: onOpenConnections,
    },
    {
      action: "Add remote approvals",
      complete: approvalReady,
      description: "Dashboard approval works without another connector. Add Telegram or Slack only if reviews should reach another app.",
      detail: "Optional: Telegram needs a bot token, chat ID, and polling enabled. Slack needs bot/app tokens, Socket Mode, and an invited approval channel.",
      icon: MessageCircle,
      label: "Connect an external approval channel",
      onAction: onOpenConnections,
      optional: true,
    },
    {
      action: "Connect a publisher",
      complete: publisherReady,
      description: publisherReady
        ? `Ready publishers: ${publisherSummary}.`
        : "Connect Telegram, WordPress, Facebook, Instagram, or LinkedIn with official API credentials.",
      detail: "Use app tokens or application passwords, never social account passwords or browser cookies. Save & test must succeed before remote publishing.",
      icon: RadioTower,
      label: "Connect where content will publish",
      onAction: onOpenConnections,
      optional: true,
    },
    {
      action: "Create the first draft",
      complete: state.posts.length > 0,
      description: "Generate a channel-aware draft, inspect the exact revision, then approve, publish now, or schedule it.",
      detail: "Editing creates a new revision and invalidates stale approvals. Nothing is published merely because it was generated.",
      icon: FileCheck2,
      label: "Run a safe end-to-end test",
      onAction: state.posts.length > 0 ? onOpenQueue : onCreateContent,
    },
  ];
  const completed = steps.filter((step) => step.complete).length;

  return (
    <div className="space-y-4">
      <Card className="relative overflow-hidden border-zinc-800 bg-[radial-gradient(circle_at_top_right,rgba(255,255,255,0.07),transparent_32%),#080808]">
        <div aria-hidden className="absolute inset-y-0 left-0 w-px bg-gradient-to-b from-white/60 via-white/10 to-transparent" />
        <CardHeader className="gap-5 p-6 sm:p-7">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
            <div className="max-w-2xl">
              <Badge className="border-zinc-700 bg-black/70 text-zinc-300" variant="outline">FIRST-RUN GUIDE</Badge>
              <h2 className="mt-4 text-xl font-semibold tracking-[-0.03em] text-zinc-100 sm:text-2xl">Set up your first approved post</h2>
              <CardDescription className="mt-2 max-w-xl text-sm leading-6">
                Complete the live checklist below. Your progress is calculated from this local workspace and updates as connections are verified.
              </CardDescription>
            </div>
            <div className="grid min-w-44 gap-3 rounded-md border border-zinc-800 bg-black/70 p-4">
              <div><p className="font-mono text-2xl font-semibold text-white">{completed}/{steps.length}</p><p className="mt-1 text-[10px] font-medium tracking-[0.14em] text-zinc-600 uppercase">Milestones ready</p></div>
              <Button onClick={onOpenOnboarding} size="sm">{state.onboarding.status === "completed" ? "Review guided setup" : "Resume guided setup"}<ArrowRight /></Button>
            </div>
          </div>
          <Progress aria-label="Setup guide progress" value={(completed / steps.length) * 100} />
        </CardHeader>
      </Card>

      <ol className="grid gap-4 lg:grid-cols-2">
        {steps.map((step, index) => <GuideStepCard key={step.label} number={index + 1} step={step} />)}
      </ol>

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader className="border-b border-zinc-900">
            <div className="flex items-center gap-3">
              <div className="grid size-9 place-items-center rounded-md border border-zinc-800 bg-black text-zinc-400">
                <ShieldCheck className="size-4" />
              </div>
              <div>
                <CardTitle>How the safe workflow works</CardTitle>
                <CardDescription>Generation and publication are deliberately separate.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {[
              ["1", "Generate", "Your selected model creates a local draft from the business profile and brief."],
              ["2", "Review", "Telegram, Slack, or the local queue shows the exact numbered revision."],
              ["3", "Approve", "Only that unchanged revision becomes eligible to publish or schedule."],
              ["4", "Deliver", "The local worker sends it through the configured official publisher API."],
            ].map(([number, label, detail]) => (
              <div className="flex gap-3" key={label}>
                <span className="grid size-6 shrink-0 place-items-center rounded-full border border-zinc-800 bg-black font-mono text-[10px] text-zinc-500">{number}</span>
                <div>
                  <p className="text-xs font-medium text-zinc-300">{label}</p>
                  <p className="mt-1 text-[11px] leading-5 text-zinc-600">{detail}</p>
                </div>
              </div>
            ))}
            <div className="flex flex-wrap gap-2 pt-2">
              <Button onClick={onOpenQueue} size="sm" variant="outline">Open approval queue</Button>
              <Button onClick={onOpenScheduler} size="sm" variant="ghost">Open scheduler</Button>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="border-b border-zinc-900">
            <div className="flex items-center gap-3">
              <div className="grid size-9 place-items-center rounded-md border border-zinc-800 bg-black text-zinc-400">
                <TerminalSquare className="size-4" />
              </div>
              <div>
                <CardTitle>Runtime commands</CardTitle>
                <CardDescription>Run these from Terminal, PowerShell, or your shell.</CardDescription>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {runtimeCommands.map((item) => (
              <div className="rounded-md border border-zinc-900 bg-black p-3" key={item.command}>
                <p className="text-[10px] text-zinc-600">{item.label}</p>
                <code className="mt-1.5 block overflow-x-auto font-mono text-[11px] text-zinc-300">{item.command}</code>
              </div>
            ))}
            <div className="flex gap-2 pt-2 text-[11px] leading-5 text-zinc-600">
              <LockKeyhole className="mt-0.5 size-3.5 shrink-0" />
              Normal uninstall preserves the local data directory. Add <code className="text-zinc-400">--purge-data</code> only when you intentionally want to erase it.
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
