"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Check, Download, ExternalLink, Loader2, Monitor, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { requestJson } from "@/lib/api";
import type { SocialBrowserAccount, SocialBrowserState } from "@/lib/app-types";

const activeStatuses = ["queued", "retrying", "running"];
type BrowserState = SocialBrowserState & { browserInstalled: boolean; driverAvailable: boolean };

export function SocialBrowserCard({ onChanged }: { onChanged: () => void | Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("My LinkedIn profile");
  const [consent, setConsent] = useState(false);
  const query = useQuery({
    queryKey: ["social-browser"],
    queryFn: () => requestJson<BrowserState>("/api/social-browser"),
    refetchInterval: (value) => value.state.data?.jobs.some((job) => activeStatuses.includes(job.status)) ? 2000 : false,
  });
  const state = query.data;
  const activeJob = state?.jobs.find((job) => activeStatuses.includes(job.status));

  async function action(path: string, method = "POST", body?: object) {
    setBusy(true);
    try {
      await requestJson(`/api/social-browser${path}`, { method, ...(body ? { body: JSON.stringify(body) } : {}) });
      await query.refetch();
      await onChanged();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Browser action failed.");
    } finally {
      setBusy(false);
    }
  }

  async function remove(account: SocialBrowserAccount) {
    if (window.confirm(`Remove the saved browser login for ${account.name}? Local session files will be deleted. Posts and history stay; bound drafts will need this same account reconnected.`)) {
      await action(`/accounts/${account.id}`, "DELETE");
    }
  }

  return (
    <Card className="min-w-0 overflow-hidden" id="browser-publishing">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-3">
          <Monitor aria-hidden="true" className="size-5 shrink-0" />
          <CardTitle>Publish through your browser</CardTitle>
          <Badge variant="outline">Experimental · LinkedIn member</Badge>
        </div>
        <CardDescription className="text-base">No social API key. Log in once in a separate local browser; approved posts use that saved session.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5 text-base">
        <div className="flex gap-3 rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 text-amber-200">
          <AlertTriangle aria-hidden="true" className="mt-1 size-5 shrink-0" />
          <p className="leading-7">LinkedIn restricts automated activity and may restrict your account. This initial adapter requires an English interface and can stop when LinkedIn changes its page. CAPTCHA, MFA, and re-login always require you. The official API connector below remains available.</p>
        </div>
        <p className="leading-7 text-muted-foreground">Local browser cookies are sensitive and stay in Socium’s private data folder—not the encrypted API vault. Socium does not read your existing Chrome profile. Only one publishing browser runs at a time and closes after its task. Internet access is still required; cloud AI and Slack/Telegram keep their own credentials.</p>
        {query.isPending ? <p role="status">Loading browser setup…</p> : query.isError ? (
          <div role="alert" className="space-y-2"><p>Browser setup could not be loaded.</p><Button variant="outline" onClick={() => void query.refetch()}>Retry</Button></div>
        ) : state ? (
          <>
            {!state.browserInstalled ? (
              <div className="space-y-3 rounded-lg border p-4">
                <p>1. Download the optional Chromium browser. It uses extra disk space; no Python, Node or developer tools need to be installed by the user.</p>
                {!state.driverAvailable ? <p role="alert">This runtime is missing the browser driver. Update Socium before continuing.</p> : null}
                <Button className="min-h-11" disabled={busy || Boolean(activeJob) || !state.driverAvailable} onClick={() => void action("/install")}><Download />Install publishing browser</Button>
              </div>
            ) : <p className="flex items-center gap-2"><Check aria-hidden="true" className="size-5" />Publishing browser installed</p>}
            {activeJob ? (
              <div className="flex flex-wrap items-center gap-3 rounded-lg border p-4">
                <Loader2 aria-hidden="true" className="size-5 motion-safe:animate-spin" />
                <p role="status" className="min-w-0 flex-1">{activeJob.message || "Waiting for the local worker…"}</p>
                <Button className="min-h-11" disabled={busy} variant="outline" onClick={() => void action(`/jobs/${activeJob.id}/cancel`)}>Cancel</Button>
              </div>
            ) : state.jobs[0]?.status === "failed" ? (
              <p role="alert" className="rounded-lg border border-destructive/40 p-4">{state.jobs[0].error || "Operation stopped. Check your session and retry."}</p>
            ) : state.jobs[0]?.status === "completed" ? <p role="status">{state.jobs[0].message || "Browser operation completed."}</p> : null}
            <div className="space-y-4">
              {state.accounts.map((account) => (
                <section aria-label={account.name} key={account.id} className="space-y-3 rounded-lg border p-4">
                  <div className="flex flex-wrap items-center gap-2"><h3 className="font-semibold">{account.name}</h3><Badge variant="outline">{account.status.replaceAll("_", " ")}</Badge>{account.preferred ? <Badge>For new drafts</Badge> : null}</div>
                  {account.identity ? <a className="block break-all underline underline-offset-4" href={account.identity} target="_blank" rel="noreferrer">{account.identity}</a> : <p className="text-muted-foreground">2. Open login, then complete sign-in yourself in the browser window.</p>}
                  {account.lastErrorCode ? <p>Session needs attention: {account.lastErrorCode.replaceAll("_", " ").toLowerCase()}.</p> : null}
                  <div className="flex flex-wrap gap-2">
                    <Button className="min-h-11" disabled={busy || Boolean(activeJob) || !state.browserInstalled} onClick={() => void action(`/accounts/${account.id}/connect`)}><ExternalLink />Open login</Button>
                    <Button className="min-h-11" variant="outline" disabled={busy || Boolean(activeJob) || !state.browserInstalled} onClick={() => void action(`/accounts/${account.id}/verify`)}><RefreshCw />Verify session</Button>
                    {!account.preferred && account.status === "connected" ? <Button className="min-h-11" variant="outline" disabled={busy || Boolean(activeJob)} onClick={() => void action(`/accounts/${account.id}/prefer`)}>Use for new drafts</Button> : null}
                    <Button className="min-h-11" variant="ghost" disabled={busy || Boolean(activeJob) || account.status === "disconnected"} onClick={() => void remove(account)}><Trash2 />Remove login</Button>
                  </div>
                </section>
              ))}
            </div>
            <form className="space-y-4 border-t pt-4" onSubmit={(event) => { event.preventDefault(); void action("/accounts", "POST", { platform: "linkedin", name, acknowledge_policy_risk: consent }); }}>
              <label className="block space-y-2"><span>Account label</span><Input className="min-h-11 text-base" required maxLength={160} value={name} onChange={(event) => setName(event.target.value)} /></label>
              <label className="flex min-h-11 cursor-pointer items-start gap-3 py-2"><input className="mt-1 size-5 shrink-0 accent-pink-500" type="checkbox" checked={consent} onChange={(event) => setConsent(event.target.checked)} /><span>I understand the platform restrictions and account risk, and want to use browser automation on my account.</span></label>
              <Button className="min-h-11" disabled={busy || Boolean(activeJob) || !consent || !name.trim() || !state.browserInstalled} type="submit">Add LinkedIn browser account</Button>
            </form>
            <p className="text-muted-foreground">Selecting an account only affects future drafts. Existing posts keep their original destination. Facebook, Instagram and other browser adapters are not enabled yet.</p>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
