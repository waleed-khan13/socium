export type ProviderKind =
  | "ollama"
  | "openai"
  | "gemini"
  | "anthropic"
  | "anthropic-compatible"
  | "openrouter"
  | "nvidia"
  | "openai-compatible";
export type ImageProviderKind = "openai-images" | "automatic1111" | "comfyui";
export type ContentChannel = "linkedin" | "linkedin-company" | "instagram" | "facebook" | "x" | "telegram" | "blog";
export type PostStatus = "pending" | "approved" | "rejected" | "publishing" | "published" | "failed";
export type LocalJobStatus = "queued" | "retrying" | "running" | "completed" | "failed" | "cancelled" | "missed";
export type ConnectorCapability = "approval" | "notification" | "publish" | "leads" | "analytics" | "cms";
export type ConnectorAvailability = "available" | "planned" | "access-gated" | "notification-only" | "built-in";
export type LeadSource = "csv" | "linkedin-export" | "crm-export" | "manual" | "website-crawl";
export type LeadStatus = "new" | "qualified" | "contacted" | "archived";
export type ConsentStatus = "unknown" | "granted" | "not_applicable" | "denied" | "withdrawn";
export type LegalBasis = "consent" | "legitimate_interest" | "existing_customer" | "contract" | "other";
export type OutreachDraftStatus = "draft" | "approved" | "rejected" | "exported";
export type SeoCheckStatus = "passed" | "warning" | "failed";
export type SeoCheckCategory = "technical" | "onPage" | "content" | "social";

export interface BrandMediaSummary {
  id: string;
  originalName: string;
  previewUrl: string;
  altText: string;
}

export interface WorkspaceSettings {
  name: string;
  businessName: string;
  description: string;
  timezone: string;
  website: string;
  industry: string;
  productsServices: string;
  targetAudience: string;
  location: string;
  goals: string[];
  callToAction: string;
  language: string;
  tone: string;
  contentPillars: string[];
  restrictedClaims: string[];
  brandedHashtags: string[];
  logoMediaId: string | null;
  logo: BrandMediaSummary | null;
  referenceMediaIds: string[];
  referenceMedia: BrandMediaSummary[];
  primaryColor: string;
  secondaryColor: string;
  accentColor: string;
  visualStyle: string;
  profileVersion: number;
  confirmedAt: string | null;
  updatedAt: string | null;
  profileComplete: boolean;
  missingFields: string[];
}

export interface PublicProviderSettings {
  kind: ProviderKind;
  baseUrl: string;
  model: string;
  hasApiKey: boolean;
  configured: boolean;
  verified: boolean;
  updatedAt: string | null;
}

export type OnboardingStep = "welcome" | "storage" | "ai" | "brand" | "finish";

export interface PublicOnboardingState {
  version: number;
  status: "not-started" | "in-progress" | "dismissed" | "completed";
  showWizard: boolean;
  currentStep: OnboardingStep;
  startedAt: string | null;
  dismissedAt: string | null;
  completedAt: string | null;
  storageConfirmed: boolean;
  storageReady: boolean;
  aiConfigured: boolean;
  aiVerified: boolean;
  brandConfirmed: boolean;
  ready: boolean;
  completedSteps: number;
  totalSteps: number;
}

export interface PublicImageProviderSettings {
  kind: ImageProviderKind;
  baseUrl: string;
  model: string;
  hasApiKey: boolean;
  hasWorkflow: boolean;
  configured: boolean;
  updatedAt: string | null;
}

export interface PublicTelegramSettings {
  chatId: string;
  hasBotToken: boolean;
  configured: boolean;
  pollingEnabled: boolean;
  pollingActive: boolean;
  pollingStatus: string;
  lastError: string | null;
  updatedAt: string | null;
}

export interface GeneratedPost {
  id: string;
  revision: number;
  topic: string;
  channel: ContentChannel;
  tone: string;
  objective: string;
  title: string;
  body: string;
  hashtags: string[];
  mediaUrl: string | null;
  rationale: string;
  status: PostStatus;
  providerKind: ProviderKind;
  model: string;
  createdAt: string;
  updatedAt: string;
  approvedAt: string | null;
  publishedAt: string | null;
  remoteId: string | null;
  remoteUrl: string | null;
  lastError: string | null;
}

export interface AuditEvent {
  id: string;
  action: string;
  entityType: "settings" | "provider" | "post" | "publisher" | "scheduler" | "connector" | "lead" | "outreach" | "seo" | "media";
  entityId: string;
  summary: string;
  createdAt: string;
}

export interface MediaAsset {
  id: string;
  originalName: string;
  mimeType: "image/jpeg" | "image/png" | "image/webp";
  byteSize: number;
  width: number;
  height: number;
  sha256: string;
  source: string;
  sourceAssetId: string | null;
  publicSourceUrl: string | null;
  altText: string;
  generationPrompt: string | null;
  generationNegativePrompt: string | null;
  generationProvider: ImageProviderKind | null;
  generationModel: string | null;
  generationParameters: Record<string, string | number | boolean>;
  contentUrl: string;
  previewUrl: string;
  instagramReady: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface MediaLibraryResponse {
  items: MediaAsset[];
  total: number;
  maxUploadBytes: number;
  storagePolicy: "local-only";
}

export interface MediaGenerationJob {
  id: string;
  kind: "media.generate";
  status: LocalJobStatus;
  payload: {
    request: {
      prompt: string;
      negative_prompt: string;
      preset: "square" | "portrait" | "landscape";
      quality: "low" | "medium" | "high" | "auto";
      steps: number;
      guidance_scale: number;
      seed: number;
    };
    provider: { kind: ImageProviderKind; model: string; updated_at: string };
  };
  runAt: string;
  attempts: number;
  maxAttempts: number;
  lockedAt: string | null;
  completedAt: string | null;
  lastError: string | null;
  progressPercent: number;
  progressMessage: string | null;
  cancelRequested: boolean;
  remoteRef: string | null;
  resultRef: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface LocalJob {
  id: string;
  kind: "post.publish";
  status: LocalJobStatus;
  payload: {
    post_id: string;
    revision: number;
    channel: ContentChannel;
  };
  runAt: string;
  attempts: number;
  maxAttempts: number;
  lockedAt: string | null;
  completedAt: string | null;
  lastError: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface PublicSchedulerState {
  paused: boolean;
  active: boolean;
  status: string;
  lastError: string | null;
  catchUpHours: number;
}

export interface ConnectorFieldSpec {
  key: string;
  label: string;
  required: boolean;
  placeholder: string;
  helpText: string;
}

export interface ConnectorManifest {
  adapterId: string;
  name: string;
  description: string;
  availability: ConnectorAvailability;
  capabilities: ConnectorCapability[];
  configFields: ConnectorFieldSpec[];
  secretFields: ConnectorFieldSpec[];
  allowedScopes: string[];
  requiredScopes: string[];
  docsUrl: string | null;
}

export interface ConnectorAccount {
  id: string;
  adapterId: string;
  adapterName: string;
  name: string;
  config: Record<string, string | boolean>;
  secretStatus: Record<string, boolean>;
  scopes: string[];
  capabilities: ConnectorCapability[];
  enabled: boolean;
  status: "saved" | "verified" | "error";
  remoteAccountId: string | null;
  lastVerifiedAt: string | null;
  lastError: string | null;
  listener: {
    active: boolean;
    status: "stopped" | "starting" | "connecting" | "listening" | "retrying";
    lastError: string | null;
  };
  createdAt: string;
  updatedAt: string;
}

export interface PublicConnectorsState {
  catalog: ConnectorManifest[];
  accounts: ConnectorAccount[];
}

export interface LeadEvidence {
  source: LeadSource;
  sourceLabel: string;
  sourceRef?: string;
  importedAt: string;
}

export interface IcpScoreReason {
  code: string;
  label: string;
  points: number;
  detail: string;
}

export interface IcpProfile {
  id: number;
  name: string;
  targetKeywords: string[];
  excludedKeywords: string[];
  targetLocations: string[];
  requireWebsite: boolean;
  requireContact: boolean;
  version: number;
  configured: boolean;
  updatedAt: string | null;
}

export interface Lead {
  id: string;
  businessName: string;
  website: string | null;
  email: string | null;
  phone: string | null;
  location: string | null;
  source: LeadSource;
  sourceLabel: string;
  sourceRef: string | null;
  notes: string;
  evidence: LeadEvidence[];
  status: LeadStatus;
  suppressed: boolean;
  suppressionReason: string | null;
  suppressedAt: string | null;
  icpScore: number | null;
  icpReasons: IcpScoreReason[];
  icpProfileVersion: number | null;
  icpScoredAt: string | null;
  manualScore: number | null;
  manualScoreReason: string | null;
  manualScoreUpdatedAt: string | null;
  effectiveScore: number | null;
  consentStatus: ConsentStatus;
  legalBasis: LegalBasis | null;
  legalBasisNote: string;
  retentionUntil: string | null;
  complianceReviewedAt: string | null;
  outreachReady: boolean;
  outreachBlockers: string[];
  retentionExpired: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface LeadSummary {
  total: number;
  active: number;
  suppressed: number;
  new: number;
  qualified: number;
  contacted: number;
  highIntent: number;
  outreachReady: number;
  retentionExpired: number;
}

export interface OutreachDraft {
  id: string;
  leadId: string;
  revision: number;
  channel: "email";
  objective: string;
  tone: string;
  subject: string;
  body: string;
  rationale: string;
  status: OutreachDraftStatus;
  providerKind: ProviderKind;
  model: string;
  createdAt: string;
  updatedAt: string;
  approvedAt: string | null;
  exportedAt: string | null;
}

export interface LocalFileExport {
  filename: string;
  mimeType: string;
  content: string;
}

export interface SeoAuditCheck {
  code: string;
  label: string;
  category: SeoCheckCategory;
  status: SeoCheckStatus;
  severity: "info" | "low" | "medium" | "high";
  evidence: string;
  recommendation: string;
  weight: number;
}

export interface SeoAuditMetrics {
  title: string;
  titleLength: number;
  description: string;
  descriptionLength: number;
  canonicalUrl: string;
  language: string;
  h1Count: number;
  h2Count: number;
  wordCount: number;
  imageCount: number;
  imagesMissingAlt: number;
  internalLinks: number;
  externalLinks: number;
  structuredDataTypes: string[];
  htmlBytes: number;
  indexable: boolean;
  passedChecks: number;
  warningChecks: number;
  failedChecks: number;
}

export interface SeoAuditSnapshot {
  id: string;
  requestedUrl: string;
  finalUrl: string;
  hostname: string;
  trigger: "manual" | "scheduled";
  statusCode: number;
  overallScore: number;
  previousScore: number | null;
  scoreDelta: number | null;
  scores: {
    technical: number;
    onPage: number;
    content: number;
    social: number;
  };
  metrics: SeoAuditMetrics;
  checks: SeoAuditCheck[];
  robotsRespected: boolean;
  userAgent: string;
  durationMs: number;
  createdAt: string;
}

export interface SeoAuditSummary {
  snapshots: number;
  sites: number;
  averageScore: number;
  openFailures: number;
  lastAuditAt: string | null;
}

export interface SeoAuditListResponse {
  items: SeoAuditSnapshot[];
  summary: SeoAuditSummary;
}

export interface SeoAuditJob {
  id: string;
  kind: "seo.audit";
  status: LocalJobStatus;
  payload: { url: string };
  runAt: string;
  attempts: number;
  maxAttempts: number;
  lockedAt: string | null;
  completedAt: string | null;
  lastError: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface LeadListResponse {
  items: Lead[];
  total: number;
  limit: number;
  offset: number;
}

export interface LeadImportRow {
  businessName: string;
  website: string;
  email: string;
  phone: string;
  location: string;
  sourceRef: string;
  notes: string;
}

export interface LeadImportResult {
  processed: number;
  created: number;
  merged: number;
  unchanged: number;
  suppressed: number;
}

export interface GooglePlaceAttribution {
  provider: string;
  providerUri: string;
}

export interface GooglePlaceResult {
  placeId: string;
  name: string;
  address: string;
  website: string;
  phone: string;
  googleMapsUri: string;
  attributions: GooglePlaceAttribution[];
}

export interface GooglePlacesSearchResponse {
  ok: boolean;
  results: GooglePlaceResult[];
  storagePolicy: "transient";
  attribution: "Google Maps";
}

export interface WebsiteCrawlResult extends LeadImportRow {
  pages: Array<{ url: string; title: string }>;
  robotsRespected: boolean;
  userAgent: string;
}

export interface PublicAppState {
  features: {
    edition: "social-v1";
    labsEnabled: boolean;
    previewModules: Array<"lead-intelligence" | "local-seo">;
  };
  workspace: WorkspaceSettings;
  provider: PublicProviderSettings;
  onboarding: PublicOnboardingState;
  imageProvider: PublicImageProviderSettings;
  telegram: PublicTelegramSettings;
  posts: GeneratedPost[];
  jobs: LocalJob[];
  scheduler: PublicSchedulerState;
  connectors: PublicConnectorsState;
  leadSummary: LeadSummary;
  icpProfile: IcpProfile;
  audit: AuditEvent[];
  runtime: {
    version: string;
    mode: string;
    persistent: boolean;
    database: string;
  };
  storage: {
    locations: Record<"runtime" | "data" | "models", { path: string; kind: "local" | "network" | "removable" | "cloud-synced" }>;
    usage: {
      runtimeBytes: number;
      dataBytes: number;
      modelsBytes: number;
      categories: Record<"database" | "credentials" | "media" | "logs" | "exports" | "backups" | "other", number>;
    };
    volumes: Record<"data" | "models", { available: boolean; totalBytes: number; freeBytes: number; lowSpace: boolean }>;
    warnings: string[];
    healthy: boolean;
    moveCommand: string;
    sourcePreservation: string;
  };
}

export interface ProviderConnectionResult {
  ok: boolean;
  message: string;
  models?: string[];
  latencyMs?: number;
}

export type ProviderProtocolHint = "auto" | "ollama" | "openai-compatible" | "anthropic-compatible";

export interface ProviderDiscoveryResult {
  ok: boolean;
  status: "detected" | "failed" | "needs-protocol";
  detectedKind: ProviderKind | null;
  normalizedBaseUrl: string;
  models: string[];
  message: string;
  requiresProtocolChoice: boolean;
  candidates: ProviderProtocolHint[];
  local: boolean;
  latencyMs: number;
}

export interface LocalAiStatus {
  platform: string;
  architecture: string;
  memoryBytes: number;
  gpu: { name: string; memoryBytes: number } | null;
  recommendedModel: string;
  recommendationTier: string;
  recommendationReason: string;
  ollamaInstalled: boolean;
  ollamaRunning: boolean;
  baseUrl: string;
  models: string[];
  selectedRecommendation: string;
  recommendedModelInstalled: boolean;
  modelsDirectory: string;
  error: string | null;
}
