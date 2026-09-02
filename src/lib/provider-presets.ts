import type { ProviderKind } from "@/lib/app-types";

export type ProviderPreset = {
  kind: ProviderKind;
  label: string;
  description: string;
  baseUrl: string;
  defaultModel: string;
  apiKeyRequired: boolean;
  keyPlaceholder: string;
  credentialUrl: string;
  credentialLabel: string;
  credentialHelp: string;
  docsUrl?: string;
};

export const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    kind: "ollama",
    label: "Local AI (Ollama)",
    description: "Runs privately on this computer. Socium finds your installed models automatically.",
    baseUrl: "http://127.0.0.1:11434",
    defaultModel: "",
    apiKeyRequired: false,
    keyPlaceholder: "",
    credentialUrl: "https://ollama.com/download",
    credentialLabel: "Download Ollama",
    credentialHelp: "Ollama runs locally and does not need an API key. Install it, pull a model, then let Socium detect it.",
    docsUrl: "https://ollama.com/library",
  },
  {
    kind: "openai",
    label: "OpenAI",
    description: "A ready-to-use OpenAI connection with a cost-conscious default model.",
    baseUrl: "https://api.openai.com/v1",
    defaultModel: "gpt-5.6-luna",
    apiKeyRequired: true,
    keyPlaceholder: "sk-…",
    credentialUrl: "https://platform.openai.com/api-keys",
    credentialLabel: "Get OpenAI key",
    credentialHelp: "Sign in to the OpenAI Platform, create a secret key, and paste it above. A ChatGPT subscription is separate from API billing.",
    docsUrl: "https://platform.openai.com/docs/quickstart",
  },
  {
    kind: "gemini",
    label: "Google Gemini",
    description: "Uses Gemini's official OpenAI-compatible API.",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    defaultModel: "gemini-3.5-flash-lite",
    apiKeyRequired: true,
    keyPlaceholder: "AIza…",
    credentialUrl: "https://aistudio.google.com/apikey",
    credentialLabel: "Get Gemini key",
    credentialHelp: "Open Google AI Studio, create an API key for a project, and paste it above.",
    docsUrl: "https://ai.google.dev/gemini-api/docs/api-key",
  },
  {
    kind: "anthropic",
    label: "Claude (Anthropic)",
    description: "Uses Anthropic's native Messages API and Claude Sonnet by default.",
    baseUrl: "https://api.anthropic.com/v1",
    defaultModel: "claude-sonnet-4-6",
    apiKeyRequired: true,
    keyPlaceholder: "sk-ant-…",
    credentialUrl: "https://platform.claude.com/settings/keys",
    credentialLabel: "Get Claude key",
    credentialHelp: "Open the Claude Console API Keys page, create a key, and paste it above.",
    docsUrl: "https://platform.claude.com/docs/en/api/getting-started",
  },
  {
    kind: "openrouter",
    label: "OpenRouter",
    description: "Starts with OpenRouter's free model router; choose another model any time.",
    baseUrl: "https://openrouter.ai/api/v1",
    defaultModel: "openrouter/free",
    apiKeyRequired: true,
    keyPlaceholder: "sk-or-v1-…",
    credentialUrl: "https://openrouter.ai/settings/keys",
    credentialLabel: "Get OpenRouter key",
    credentialHelp: "Open OpenRouter Keys, create a key, and paste it above. You can keep the free model router selected.",
    docsUrl: "https://openrouter.ai/docs/quickstart",
  },
  {
    kind: "nvidia",
    label: "NVIDIA NIM",
    description: "Connects to NVIDIA's hosted NIM chat API.",
    baseUrl: "https://integrate.api.nvidia.com/v1",
    defaultModel: "meta/llama-3.1-8b-instruct",
    apiKeyRequired: true,
    keyPlaceholder: "nvapi-…",
    credentialUrl: "https://build.nvidia.com/settings/api-keys",
    credentialLabel: "Get NVIDIA key",
    credentialHelp: "Sign in to NVIDIA Build, generate an API key, and paste it above.",
    docsUrl: "https://docs.api.nvidia.com/nim/reference/llm-apis",
  },
  {
    kind: "openai-compatible",
    label: "Custom / I'm not sure",
    description: "Detect Ollama, LM Studio, LocalAI, or another compatible endpoint without guessing where a secret belongs.",
    baseUrl: "http://127.0.0.1:1234/v1",
    defaultModel: "",
    apiKeyRequired: false,
    keyPlaceholder: "Optional API key",
    credentialUrl: "https://github.com/ggml-org/llama.cpp/blob/master/examples/server/README.md",
    credentialLabel: "Setup guide",
    credentialHelp: "LocalAI, LM Studio, llama.cpp, and other compatible servers usually need no key. Use the documentation for your chosen server.",
  },
  {
    kind: "anthropic-compatible",
    label: "Custom Anthropic-compatible",
    description: "Uses an Anthropic Messages-compatible gateway after you explicitly select that protocol.",
    baseUrl: "http://127.0.0.1:4000/v1",
    defaultModel: "",
    apiKeyRequired: false,
    keyPlaceholder: "Optional provider key",
    credentialUrl: "https://docs.anthropic.com/en/api/messages",
    credentialLabel: "Messages API contract",
    credentialHelp: "Use the key issued by your gateway. Socium sends it only after you select the Anthropic-compatible protocol.",
  },
];

export function getProviderPreset(kind: ProviderKind): ProviderPreset {
  return PROVIDER_PRESETS.find((preset) => preset.kind === kind) ?? PROVIDER_PRESETS[0];
}
