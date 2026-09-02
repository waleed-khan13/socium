"use client";

import { Toaster } from "sonner";

import { TooltipProvider } from "@/components/ui/tooltip";

export function AppProviders({ children }: { children: React.ReactNode }) {
  return (
    <TooltipProvider delay={250}>
      {children}
      <Toaster
        duration={3500}
        position="bottom-right"
        theme="dark"
        toastOptions={{
          style: {
            background: "#0c0c0c",
            border: "1px solid #2b2b2b",
            color: "#fafafa",
            pointerEvents: "none",
          },
        }}
      />
    </TooltipProvider>
  );
}
