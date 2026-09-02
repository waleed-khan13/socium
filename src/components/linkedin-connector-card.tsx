"use client";

import {
  AlertTriangle,
  BriefcaseBusiness,
  CheckCircle2,
  Loader2,
  LockKeyhole,
  PlugZap,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";

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
import { Separator } from "@/components/ui/separator";
import type { ConnectorAccount } from "@/lib/app-types";
import { cn } from "@/lib/utils";

type Props = {
  account: ConnectorAccount | null;
  busy: string | null;
  oneClickConfigured: boolean;
  onConnect: () => void;
  onRemove: () => void;
};

export function LinkedInConnectorCard({
  account,
  busy,
  oneClickConfigured,
  onConnect,
  onRemove,
}: Props) {
  const connecting = busy === "oauth-linkedin";
  const deleting = busy === "linkedin-delete";
  return (
    <Card className="overflow-hidden border-zinc-800 bg-[#070707]">
      <CardHeader className="border-b border-zinc-900 bg-[radial-gradient(circle_at_top_left,rgba(14,165,233,0.1),transparent_34%)]">
        <div className="flex items-center gap-3">
          <div className="grid size-10 place-items-center rounded-md border border-sky-500/20 bg-sky-500/5 text-sky-300">
            <BriefcaseBusiness className="size-4" />
          </div>
          <div>
            <CardTitle>LinkedIn Member</CardTitle>
            <CardDescription>Official publishing with one provider consent screen.</CardDescription>
          </div>
        </div>
        <CardAction>
          <Badge
            className={cn(
              account?.status === "verified" && "border-sky-500/25 bg-sky-500/8 text-sky-300",
              account?.status === "error" && "border-red-500/25 bg-red-500/8 text-red-300",
            )}
            variant="outline"
          >
            {account?.status === "verified" ? "Connected" : account?.status === "error" ? "Needs attention" : "Not connected"}
          </Badge>
        </CardAction>
      </CardHeader>
      <CardContent className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
        <div className="space-y-5">
          <div className="rounded-md border border-sky-500/15 bg-sky-500/[0.03] p-4">
            <div className="flex items-start gap-3">
              {account?.status === "verified" ? <CheckCircle2 className="mt-0.5 size-4 text-sky-300" /> : <PlugZap className="mt-0.5 size-4 text-sky-300" />}
              <div>
                <p className="text-sm font-medium text-zinc-100">{account?.status === "verified" ? account.name : "No token copying"}</p>
                <p className="mt-1 text-xs leading-5 text-zinc-500">Select Connect, sign in to LinkedIn, and choose Allow. Socium receives the member ID and OAuth token automatically.</p>
              </div>
            </div>
          </div>
          {account?.lastError ? <div className="flex gap-2 rounded-md border border-red-500/20 bg-red-500/5 p-3 text-xs text-red-300"><AlertTriangle className="size-3.5 shrink-0" />{account.lastError}</div> : null}
          {!oneClickConfigured ? <p className="rounded-md border border-amber-500/20 bg-amber-500/5 p-3 text-xs leading-5 text-amber-200">One-click service is not active in this development build yet. No manual token form is shown.</p> : null}
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-900 pt-4">
            <div>{account ? <Button disabled={deleting} onClick={onRemove} variant="ghost"><X />Remove</Button> : null}</div>
            <Button disabled={connecting || !oneClickConfigured} onClick={onConnect}>
              {connecting ? <Loader2 className="animate-spin" /> : account ? <RefreshCw /> : <PlugZap />}
              {connecting ? "Waiting for LinkedIn…" : account ? "Reconnect LinkedIn" : "Connect LinkedIn"}
            </Button>
          </div>
        </div>
        <div className="space-y-4 rounded-md border border-zinc-800 bg-black p-4">
          <div className="flex items-start gap-3"><ShieldCheck className="mt-0.5 size-4 text-sky-400" /><div><p className="text-xs font-medium text-zinc-200">Explicit member consent</p><p className="mt-1 text-[11px] leading-5 text-zinc-600">LinkedIn shows the requested permissions before anything is connected.</p></div></div>
          <Separator className="bg-zinc-900" />
          <div className="flex items-start gap-3"><LockKeyhole className="mt-0.5 size-4 text-zinc-500" /><div><p className="text-xs font-medium text-zinc-300">Encrypted locally</p><p className="mt-1 text-[11px] leading-5 text-zinc-600">The browser never receives the access token. It is saved in the local AES-256-GCM vault.</p></div></div>
          <div className="flex flex-wrap gap-2"><Badge variant="outline">openid</Badge><Badge variant="outline">profile</Badge><Badge variant="outline">w_member_social</Badge></div>
        </div>
      </CardContent>
    </Card>
  );
}
