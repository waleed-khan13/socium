"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Toaster } from "sonner";

import { TooltipProvider } from "@/components/ui/tooltip";

export function AppProviders({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            retry: 1,
            staleTime: 15_000,
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider delay={250}>
        {children}
        <Toaster
          duration={3500}
          position="bottom-right"
          theme="dark"
          toastOptions={{
            style: {
              background: "#111014",
              border: "1px solid #38333d",
              color: "#fafafa",
              pointerEvents: "none",
            },
          }}
        />
      </TooltipProvider>
    </QueryClientProvider>
  );
}
