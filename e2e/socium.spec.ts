import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page, type TestInfo } from "@playwright/test";

import type { PublicAppState } from "../src/lib/app-types";

const mockBaseUrl = `http://127.0.0.1:${process.env.SOCIUM_E2E_MOCK_PORT ?? "4100"}`;

test("rejects cross-origin requests at the localhost API proxy", async ({ request }) => {
  const response = await request.post("/api/state", {
    data: {},
    headers: { Origin: "https://attacker.example" },
  });
  expect(response.status()).toBe(403);
  expect(await response.json()).toMatchObject({
    ok: false,
    error: expect.stringContaining("same-origin"),
  });
});

async function navigate(page: Page, label: string, heading: string) {
  await expect(page.getByText(/LOCAL.*v\d+\.\d+\.\d+/)).toBeVisible({ timeout: 60_000 });
  await page.getByRole("navigation", { name: "Primary" }).getByRole("button", { name: label }).click();
  await expect(page.getByRole("heading", { level: 1, name: heading })).toBeVisible();
}

async function expectNoAccessibilityViolations(page: Page, testInfo: TestInfo, name: string) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();

  await testInfo.attach(`${name}-axe-results`, {
    body: JSON.stringify(results, null, 2),
    contentType: "application/json",
  });

  const violations = results.violations.map((violation) => ({
    help: violation.help,
    id: violation.id,
    impact: violation.impact,
    nodes: violation.nodes.map((node) => ({
      failureSummary: node.failureSummary,
      target: node.target,
    })),
  }));

  expect(violations, `${name} has automated WCAG A/AA violations`).toEqual([]);
}

async function expectDialogFitsViewport(
  page: Page,
  dialog: Locator,
  viewport: { width: number; height: number },
) {
  await page.setViewportSize(viewport);
  await expect(dialog).toBeVisible();

  const minimumExpectedWidth = viewport.width >= 1024
    ? 1000
    : viewport.width >= 640
      ? viewport.width - 70
      : viewport.width - 40;
  await expect.poll(
    async () => (await dialog.boundingBox())?.width ?? 0,
    { message: `dialog should reflow at ${viewport.width}x${viewport.height}` },
  ).toBeGreaterThan(minimumExpectedWidth);

  const box = await dialog.boundingBox();
  expect(box, `dialog should have a box at ${viewport.width}x${viewport.height}`).not.toBeNull();
  if (!box) return;

  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.y).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 1);
  expect(box.y + box.height).toBeLessThanOrEqual(viewport.height + 1);

  const horizontalOverflow = await dialog.evaluate(
    (element) => element.scrollWidth - element.clientWidth,
  );
  expect(horizontalOverflow, `dialog should not clip horizontally at ${viewport.width}x${viewport.height}`).toBeLessThanOrEqual(1);
}

async function dismissOnboardingIfPresent(page: Page) {
  await page.getByText(/LOCAL.*v\d+\.\d+\.\d+/).first().waitFor({ state: "attached", timeout: 60_000 });
  const dialog = page.getByRole("dialog", { name: "Socium first-run setup" });
  if (await dialog.isVisible().catch(() => false)) {
    await dialog.getByRole("button", { name: "Set up later" }).click();
    await expect(dialog).toHaveCount(0);
  }
}

test("runs first-run onboarding, publishing, and approval workflows", async ({ page }, testInfo) => {
  test.setTimeout(240_000);
  await page.goto("/");
  const onboarding = page.getByRole("dialog", { name: "Socium first-run setup" });
  await expect(onboarding.getByRole("heading", { name: "Welcome to Socium" })).toBeVisible();
  await expect(onboarding.getByText("LOCAL-FIRST · NO SOCIUM ACCOUNT")).toBeVisible();
  for (const viewport of [
    { width: 360, height: 800 },
    { width: 768, height: 1024 },
    { width: 1600, height: 900 },
  ]) {
    await expectDialogFitsViewport(page, onboarding, viewport);
  }
  await page.setViewportSize({ width: 1280, height: 720 });
  await expectNoAccessibilityViolations(page, testInfo, "onboarding-welcome");

  await onboarding.getByRole("button", { name: "Start setup" }).click();
  await expect(onboarding.getByRole("heading", { name: "Confirm private storage" })).toBeVisible();
  await expect(onboarding.getByText("Both durable locations are available.")).toBeVisible();
  await onboarding.getByRole("button", { name: "Change storage locations" }).click();
  const storagePicker = page.getByRole("dialog", { name: "Choose private storage folders" });
  await expect(storagePicker.getByLabel("Selected Socium data folder")).toHaveValue(/.+/);
  await expect(storagePicker.getByLabel("Selected Socium models folder")).toHaveValue(/.+/);
  await expect(storagePicker.getByRole("button", { name: "Move safely & restart" })).toBeDisabled();
  await expectNoAccessibilityViolations(page, testInfo, "onboarding-storage-picker");
  await storagePicker.getByRole("button", { name: "Cancel" }).click();
  await expect(storagePicker).toHaveCount(0);
  await onboarding.getByRole("button", { name: "Confirm these locations" }).click();

  await expect(onboarding.getByRole("heading", { name: "Connect one AI" })).toBeVisible();
  await onboarding.getByRole("button", { name: "Set up cloud AI" }).click();
  await onboarding.getByLabel("AI service").click();
  await page.getByRole("option", { name: "Custom / I'm not sure" }).click();
  await onboarding.getByLabel("API base URL").fill(mockBaseUrl);
  await onboarding.getByLabel("Model").fill("e2e-model");
  await onboarding.getByLabel("API key").fill("e2e-provider-key");
  await onboarding.getByRole("button", { name: "Connect and verify cloud AI" }).click();
  await expect(page.getByText("AI connection verified")).toBeVisible();
  await expect(onboarding.getByText("AI verified", { exact: true })).toBeVisible();
  await onboarding.getByRole("button", { name: "Continue to brand" }).click();

  await expect(onboarding.getByRole("heading", { name: "Confirm your brand" })).toBeVisible();
  await page.route("**/api/settings/brand-profile/discover", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        draft: {
          businessName: "Northstar Studio",
          website: "https://northstar.example/",
          description: "Northstar Studio helps local service businesses build useful marketing systems.",
          industry: "Marketing technology",
          productsServices: "Private social publishing workflows with human approval.",
          targetAudience: "Privacy-conscious local service businesses.",
          location: "Lahore, Pakistan",
          goals: ["Build useful awareness", "Earn qualified conversations"],
          callToAction: "Book a practical workflow review.",
          language: "English",
          tone: "Clear, practical, and calm",
          contentPillars: ["Local-first AI", "Human-reviewed publishing"],
          brandedHashtags: ["#NorthstarStudio", "#HumanReviewed"],
          primaryColor: "#f59e0b",
          secondaryColor: "#18181b",
          accentColor: "#10b981",
          headingFont: "Sora",
          bodyFont: "Inter",
          visualStyle: "Dark, clear layouts with authentic product imagery.",
        },
        fieldOrigins: {},
        sources: [{ url: "https://northstar.example/", title: "Northstar Studio" }],
        signals: { colors: ["#f59e0b"], fonts: ["Sora", "Inter"], logoCandidates: [], socialLinks: [] },
        logoAsset: null,
        provider: { kind: "openai-compatible", model: "e2e-model", local: false },
        warnings: [],
        storagePolicy: "editable-draft",
      }),
      status: 200,
    });
  });
  await onboarding.getByLabel("Business website to analyze").fill("https://northstar.example");
  await onboarding.getByRole("button", { name: "Analyze & fill" }).click();
  await expect(onboarding.getByText("1 PAGES READ")).toBeVisible();
  await expect(onboarding.getByLabel("Business name")).toHaveValue("Northstar Studio");
  await expect(onboarding.getByLabel("Heading font")).toHaveValue("Sora");
  await expect(onboarding.getByLabel("Body font")).toHaveValue("Inter");
  await onboarding.getByLabel("Workspace name").fill("E2E workspace");
  await onboarding.getByLabel("Business name").fill("Northstar Studio");
  await onboarding
    .getByLabel("What the business does")
    .fill("Northstar Studio helps local service businesses build clear, useful marketing systems.");
  await onboarding.getByLabel("Products or services").fill("Private social publishing workflows with human approval.");
  await onboarding.getByLabel("Target audience").fill("Privacy-conscious local service businesses.");
  await onboarding.getByLabel("Marketing goals").fill("Build useful awareness\nEarn qualified conversations");
  await onboarding.getByLabel("Content pillars").fill("Local-first AI\nHuman-reviewed publishing");
  await onboarding.getByLabel("Default call to action").fill("Book a practical workflow review.");
  await onboarding.getByLabel("Restricted claims or topics").fill("Guaranteed growth\nInvented customer results");
  await onboarding.getByLabel("Branded hashtags").fill("#NorthstarStudio #HumanReviewed");
  await onboarding.getByLabel("Preferred visual style").fill("Dark, clear layouts with authentic product imagery.");
  await onboarding.getByLabel("Timezone").fill("Asia/Karachi");
  await onboarding.getByRole("button", { name: "Save & confirm profile" }).click();
  await expect(page.getByText("Brand profile revision 1 confirmed")).toBeVisible();
  await expect(onboarding.getByText("CONFIRMED · R1")).toBeVisible();
  await onboarding.getByRole("button", { name: "Review setup" }).click();

  await expect(onboarding.getByRole("heading", { name: "Ready for your first draft" })).toBeVisible();
  await expect(onboarding.getByText("AI connection verified")).toBeVisible();
  await onboarding.getByRole("button", { name: "Finish setup" }).click();
  await expect(onboarding).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1, name: "Growth command" })).toBeVisible();
  await expect(page.getByText(/SOCIUM LOCAL.*v1\.1\.0/)).toBeVisible();
  const primaryNavigation = page.getByRole("navigation", { name: "Primary" });
  await expect(primaryNavigation.getByRole("button", { name: "Lead intelligence" })).toHaveCount(0);
  await expect(primaryNavigation.getByRole("button", { name: "Local SEO lab" })).toHaveCount(0);

  await navigate(page, "Setup guide", "Setup guide");
  await expect(page.getByRole("heading", { level: 2, name: "Set up your first approved post" })).toBeVisible();
  await expect(page.getByText("Milestones ready")).toBeVisible();
  await expect(page.getByText("How the safe workflow works")).toBeVisible();

  const releaseStateResponse = await page.request.get("/api/state");
  expect(releaseStateResponse.ok()).toBeTruthy();
  const releaseState = (await releaseStateResponse.json()) as PublicAppState;
  expect(releaseState.features).toEqual({ edition: "social-v1", labsEnabled: false, previewModules: [] });
  expect(releaseState.runtime.version).toBe("1.1.0");
  expect(releaseState.onboarding.status).toBe("completed");
  expect(releaseState.onboarding.ready).toBe(true);

  await page.reload();
  await expect(page.getByRole("dialog", { name: "Socium first-run setup" })).toHaveCount(0);
  await expect(page.getByRole("heading", { level: 1, name: "Growth command" })).toBeVisible();

  await navigate(page, "Integrations", "Connections");
  await expect(page.getByText("Connect only what you use", { exact: true })).toBeVisible();
  await expect(page.getByText("ALL OTHERS OPTIONAL", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Phone Number ID")).toHaveCount(0);
  await expect(page.getByRole("switch", { name: "WhatsApp alert" })).toHaveCount(0);

  await expect(page.getByText("CONFIRMED · R1")).toBeVisible();

  const wordpressForm = page.getByLabel("Site URL").locator("xpath=ancestor::form");
  await wordpressForm.getByLabel("Connection name").fill("E2E WordPress");
  await wordpressForm.getByLabel("Site URL").fill(mockBaseUrl);
  await wordpressForm.getByLabel("Username").fill("editor");
  await wordpressForm.getByLabel("Application Password").fill("e2e-application-password");
  await wordpressForm.getByRole("button", { name: "Save & test" }).click();
  await expect(page.getByText("Connected to WordPress as E2E Editor.")).toBeVisible();

  await navigate(page, "Create content", "Create a draft");
  await page.getByLabel("Topic or source brief").fill(
    "Create a practical checklist that helps a local business publish useful content consistently.",
  );
  await page.getByLabel("Channel").click();
  await page.getByRole("option", { name: "Blog" }).click();

  const generateResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/posts/generate") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Generate review draft" }).click();
  await expect((await generateResponse).status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1, name: "Approval queue" })).toBeVisible();

  const generatedTitle = "A practical local growth checklist";
  const editedTitle = "A reviewed local growth checklist";
  await expect(page.getByRole("heading", { level: 2, name: generatedTitle })).toBeVisible();
  await page.getByRole("button", { name: /^all / }).click();

  let postCard = page
    .getByRole("heading", { level: 2, name: generatedTitle })
    .locator('xpath=ancestor::div[@data-slot="card"]');
  await expect(postCard.getByText("pending", { exact: true })).toBeVisible();
  const regenerateResponse = page.waitForResponse(
    (response) => /\/api\/posts\/[^/]+\/regenerate$/.test(response.url()) && response.request().method() === "POST",
  );
  await postCard.getByRole("button", { name: "Regenerate post", exact: true }).click();
  await expect((await regenerateResponse).status()).toBe(200);
  await expect(page.getByText("Fresh revision generated")).toBeVisible();
  const regeneratedStateResponse = await page.request.get("/api/state");
  const regeneratedState = (await regeneratedStateResponse.json()) as PublicAppState;
  const regeneratedPost = regeneratedState.posts.find((post) => post.channel === "blog");
  expect(regeneratedPost?.revision).toBe(2);
  const staleDecision = await page.request.post(`/api/posts/${regeneratedPost?.id}/decision`, {
    data: { decision: "approve", revision: 1 },
  });
  expect(staleDecision.status()).toBe(400);
  await postCard.getByText("Brand content kit · profile R1").click();
  await expect(postCard.getByText("Book a practical workflow review.", { exact: true })).toBeVisible();
  await expect(postCard.getByText(/A dark editorial small-business workspace/)).toBeVisible();
  await expect(postCard.getByText(/Small-business workspace arranged/)).toBeVisible();
  await expect(postCard.getByRole("button", { name: "Regenerate image", exact: true })).toBeVisible();
  await navigate(page, "Media library", "Media library");
  await expect(page.getByText(/A dark editorial small-business workspace/)).toBeVisible();
  await expect(page.getByRole("img", { name: /Small-business workspace arranged/ })).toBeVisible();
  await navigate(page, "Approval queue", "Approval queue");
  postCard = page
    .getByRole("heading", { level: 2, name: generatedTitle })
    .locator('xpath=ancestor::div[@data-slot="card"]');
  await postCard.getByRole("button", { name: "Edit" }).click();

  const editDialog = page.getByRole("dialog", { name: "Edit draft" });
  await expect(editDialog).toBeVisible();
  await editDialog.getByLabel("Title").fill(editedTitle);
  await editDialog
    .getByLabel("Post body")
    .fill("Define one customer problem, publish one useful answer, and review the result before repeating the cycle.");
  await editDialog.getByLabel("Hashtags").fill("#Socium #Reviewed");
  await editDialog.getByLabel("Call to action").fill("Read the reviewed workflow guide.");
  await editDialog.getByLabel("Image prompt").fill("A reviewed dark editorial workflow scene");
  await editDialog.getByLabel("Planned alt text").fill("Reviewed workflow scene in a dark editorial workspace");
  await editDialog.getByRole("button", { name: "Save new version" }).click();
  await expect(page.getByText("Draft updated")).toBeVisible();

  postCard = page
    .getByRole("heading", { level: 2, name: editedTitle })
    .locator('xpath=ancestor::div[@data-slot="card"]');
  await expect(postCard.getByText("pending", { exact: true })).toBeVisible();
  await postCard.getByRole("button", { name: "Approve" }).click();
  await expect(postCard.getByText("approved", { exact: true })).toBeVisible();

  const publishResponse = page.waitForResponse(
    (response) => /\/api\/posts\/[^/]+\/publish$/.test(response.url()) && response.request().method() === "POST",
  );
  await postCard.getByRole("button", { name: "Publish to WordPress" }).click();
  await expect((await publishResponse).status()).toBe(200);
  await expect(postCard.getByText("published", { exact: true })).toBeVisible();
  await expect(postCard.getByText("remote:4242", { exact: true })).toBeVisible();

  const stateResponse = await page.request.get("/api/state");
  expect(stateResponse.ok()).toBeTruthy();
  const state = (await stateResponse.json()) as PublicAppState;
  expect(state.posts).toHaveLength(1);
  expect(state.posts[0]).toMatchObject({
    channel: "blog",
    remoteId: "4242",
    remoteUrl: `${mockBaseUrl}/posts/4242`,
    revision: 3,
    status: "published",
    title: editedTitle,
    callToAction: "Read the reviewed workflow guide.",
    imagePrompt: "A reviewed dark editorial workflow scene",
    imageAltText: "Reviewed workflow scene in a dark editorial workspace",
    brandProfileVersion: 1,
  });

  const mockStateResponse = await page.request.get(`${mockBaseUrl}/__e2e/state`);
  expect(mockStateResponse.ok()).toBeTruthy();
  const mockState = (await mockStateResponse.json()) as {
    generationRequests: number;
    lastPublishedPost: { content: string; status: string; title: string };
    modelRequests: number;
    wordpressAuthChecks: number;
    wordpressPublishes: number;
    lastGenerationRequest: { messages: Array<{ role: string; content: string }> };
  };
  expect(mockState).toMatchObject({
    generationRequests: 2,
    modelRequests: 1,
    wordpressAuthChecks: 1,
    wordpressPublishes: 1,
  });
  expect(mockState.lastPublishedPost).toMatchObject({ status: "publish", title: editedTitle });
  expect(mockState.lastPublishedPost.content).toContain("Define one customer problem");
  expect(mockState.lastPublishedPost.content).toContain("#Reviewed");
  const brandPrompt = mockState.lastGenerationRequest.messages.find((message) => message.role === "user")?.content ?? "";
  expect(brandPrompt).toContain("Confirmed brand profile revision: 1");
  expect(brandPrompt).toContain("Target audience: Privacy-conscious local service businesses.");
  expect(brandPrompt).toContain("Restricted claims or topics: Guaranteed growth; Invented customer results");
  expect(brandPrompt).toContain("Branded hashtags: #NorthstarStudio #HumanReviewed");

  await navigate(page, "Integrations", "Connections");
  const metaForm = page.getByLabel("Facebook Page ID").locator("xpath=ancestor::form");
  await metaForm.getByLabel("Connection name").fill("E2E Facebook Page");
  await metaForm.getByLabel("Facebook Page ID").fill("123456789012345");
  await metaForm.getByLabel("Graph API version").fill("v25.0");
  await metaForm.getByLabel("Page Access Token").fill("e2e-page-access-token");
  await metaForm.getByRole("button", { name: "Save & test" }).click();
  await expect(page.getByText("Connected to Facebook Page Northstar Studio.")).toBeVisible();

  await navigate(page, "Create content", "Create a draft");
  await page.getByLabel("Topic or source brief").fill(
    "Create one concise, useful update for our local Facebook audience.",
  );
  await page.getByLabel("Channel").click();
  await page.getByRole("option", { name: "Facebook" }).click();

  const facebookGenerateResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/posts/generate") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Generate review draft" }).click();
  await expect((await facebookGenerateResponse).status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1, name: "Approval queue" })).toBeVisible();
  await page.getByRole("button", { name: /^all / }).click();

  const facebookTitle = "A useful Facebook Page update";
  const facebookCard = page
    .getByRole("heading", { level: 2, name: facebookTitle })
    .locator('xpath=ancestor::div[@data-slot="card"]');
  await facebookCard.getByRole("button", { name: "Approve" }).click();
  await expect(facebookCard.getByText("approved", { exact: true })).toBeVisible();

  const facebookPublishResponse = page.waitForResponse(
    (response) => /\/api\/posts\/[^/]+\/publish$/.test(response.url()) && response.request().method() === "POST",
  );
  await facebookCard.getByRole("button", { name: "Publish to Facebook" }).click();
  await expect((await facebookPublishResponse).status()).toBe(200);
  await expect(facebookCard.getByText("published", { exact: true })).toBeVisible();
  await expect(facebookCard.getByText("remote:123456789012345_987654321", { exact: true })).toBeVisible();

  const finalStateResponse = await page.request.get("/api/state");
  const finalState = (await finalStateResponse.json()) as PublicAppState;
  expect(finalState.posts).toHaveLength(2);
  expect(finalState.posts.find((post) => post.channel === "facebook")).toMatchObject({
    remoteId: "123456789012345_987654321",
    revision: 1,
    status: "published",
    title: facebookTitle,
  });

  const finalMockResponse = await page.request.get(`${mockBaseUrl}/__e2e/state`);
  const finalMockState = (await finalMockResponse.json()) as {
    generationRequests: number;
    lastFacebookPost: { message: string };
    metaAuthChecks: number;
    metaPublishes: number;
  };
  expect(finalMockState).toMatchObject({
    generationRequests: 3,
    metaAuthChecks: 1,
    metaPublishes: 1,
  });
  expect(finalMockState.lastFacebookPost.message).toContain("Share one useful local insight");
  expect(finalMockState.lastFacebookPost.message).toContain("#FacebookMarketing");

  await navigate(page, "Integrations", "Connections");
  const instagramForm = page.getByLabel("Professional Account ID").locator("xpath=ancestor::form");
  await instagramForm.getByLabel("Connection name").fill("E2E Instagram");
  await instagramForm.getByLabel("Professional Account ID").fill("17841400000000000");
  await instagramForm.getByLabel("Graph API version").fill("v25.0");
  await instagramForm.getByLabel("Instagram Access Token").fill("e2e-instagram-access-token");
  await instagramForm.getByRole("button", { name: "Save & test" }).click();
  await expect(page.getByText("Connected to Instagram @northstarstudio.")).toBeVisible();

  const instagramImageUrl = "https://cdn.example.test/e2e-instagram.jpg?approved=true";
  await navigate(page, "Create content", "Create a draft");
  await page.getByLabel("Topic or source brief").fill(
    "Create one useful single-image update for our professional Instagram account.",
  );
  await page.getByLabel("Channel").click();
  await page.getByRole("option", { name: "Instagram" }).click();
  await page.getByLabel("Public image URL").fill(instagramImageUrl);
  await expect(page.getByRole("img", { name: "Instagram image preview" })).toBeVisible();

  const instagramGenerateResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/posts/generate") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Generate review draft" }).click();
  await expect((await instagramGenerateResponse).status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1, name: "Approval queue" })).toBeVisible();
  await page.getByRole("button", { name: /^all / }).click();

  const instagramTitle = "A reviewed Instagram image update";
  const instagramCard = page
    .getByRole("heading", { level: 2, name: instagramTitle })
    .locator('xpath=ancestor::div[@data-slot="card"]');
  await expect(instagramCard.getByRole("img", { name: `Media preview for ${instagramTitle}` })).toBeVisible();
  await instagramCard.getByRole("button", { name: "Approve" }).click();
  await expect(instagramCard.getByText("approved", { exact: true })).toBeVisible();

  const instagramPublishResponse = page.waitForResponse(
    (response) => /\/api\/posts\/[^/]+\/publish$/.test(response.url()) && response.request().method() === "POST",
  );
  await instagramCard.getByRole("button", { name: "Publish to Instagram" }).click();
  await expect((await instagramPublishResponse).status()).toBe(200);
  await expect(instagramCard.getByText("published", { exact: true })).toBeVisible();
  await expect(instagramCard.getByText("remote:18000000000000011", { exact: true })).toBeVisible();

  const instagramStateResponse = await page.request.get("/api/state");
  const instagramState = (await instagramStateResponse.json()) as PublicAppState;
  expect(instagramState.posts).toHaveLength(3);
  expect(instagramState.posts.find((post) => post.channel === "instagram")).toMatchObject({
    mediaUrl: instagramImageUrl,
    remoteId: "18000000000000011",
    revision: 1,
    status: "published",
    title: instagramTitle,
  });

  const instagramMockResponse = await page.request.get(`${mockBaseUrl}/__e2e/state`);
  const instagramMockState = (await instagramMockResponse.json()) as {
    generationRequests: number;
    instagramAuthChecks: number;
    instagramContainers: number;
    instagramPublishes: number;
    instagramStatusChecks: number;
    lastInstagramContainer: { caption: string; image_url: string };
    lastInstagramPublish: { creation_id: string };
  };
  expect(instagramMockState).toMatchObject({
    generationRequests: 4,
    instagramAuthChecks: 1,
    instagramContainers: 1,
    instagramPublishes: 1,
    instagramStatusChecks: 1,
  });
  expect(instagramMockState.lastInstagramContainer.image_url).toBe(instagramImageUrl);
  expect(instagramMockState.lastInstagramContainer.caption).toContain("Show one practical campaign idea");
  expect(instagramMockState.lastInstagramContainer.caption).toContain("#HumanReviewed");
  expect(instagramMockState.lastInstagramPublish).toEqual({ creation_id: "18000000000000010" });

  await navigate(page, "Integrations", "Connections");
  await expect(page.getByRole("button", { name: "Connect LinkedIn" })).toBeVisible();
  await expect(page.getByLabel("LinkedIn Member ID")).toHaveCount(0);
  const linkedinCreateResponse = await page.request.post("/api/connectors", {
    data: {
      adapterId: "linkedin",
      name: "E2E LinkedIn profile",
      config: { person_id: "782bbtaQ", api_version: "202607" },
      secrets: { access_token: "e2e-linkedin-access-token" },
      scopes: ["openid", "profile", "w_member_social"],
      enabled: true,
    },
  });
  expect(linkedinCreateResponse.status()).toBe(200);
  const linkedinCreateBody = (await linkedinCreateResponse.json()) as {
    account: { id: string };
  };
  const linkedinTestResponse = await page.request.post(
    `/api/connectors/${linkedinCreateBody.account.id}/test`,
  );
  expect(linkedinTestResponse.status()).toBe(200);
  await page.reload();

  await navigate(page, "Create content", "Create a draft");
  await page.getByLabel("Topic or source brief").fill(
    "Create one useful professional lesson for my LinkedIn network.",
  );
  await page.getByLabel("Channel").click();
  await page.getByRole("option", { name: "LinkedIn", exact: true }).click();

  const linkedinGenerateResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/posts/generate") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Generate review draft" }).click();
  await expect((await linkedinGenerateResponse).status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1, name: "Approval queue" })).toBeVisible();
  await page.getByRole("button", { name: /^all / }).click();

  const linkedinTitle = "A reviewed LinkedIn member update";
  const linkedinCard = page
    .getByRole("heading", { level: 2, name: linkedinTitle })
    .locator('xpath=ancestor::div[@data-slot="card"]');
  await linkedinCard.getByRole("button", { name: "Approve" }).click();
  await expect(linkedinCard.getByText("approved", { exact: true })).toBeVisible();

  const linkedinPublishResponse = page.waitForResponse(
    (response) => /\/api\/posts\/[^/]+\/publish$/.test(response.url()) && response.request().method() === "POST",
  );
  await linkedinCard.getByRole("button", { name: "Publish to LinkedIn" }).click();
  await expect((await linkedinPublishResponse).status()).toBe(200);
  await expect(linkedinCard.getByText("published", { exact: true })).toBeVisible();
  await expect(linkedinCard.getByText("remote:urn:li:share:7190000000000000003", { exact: true })).toBeVisible();

  const linkedinStateResponse = await page.request.get("/api/state");
  const linkedinState = (await linkedinStateResponse.json()) as PublicAppState;
  expect(linkedinState.posts).toHaveLength(4);
  expect(linkedinState.posts.find((post) => post.channel === "linkedin")).toMatchObject({
    remoteId: "urn:li:share:7190000000000000003",
    revision: 1,
    status: "published",
    title: linkedinTitle,
  });

  const linkedinMockResponse = await page.request.get(`${mockBaseUrl}/__e2e/state`);
  const linkedinMockState = (await linkedinMockResponse.json()) as {
    generationRequests: number;
    lastLinkedInHeaders: {
      authorization: string;
      linkedinVersion: string;
      restliVersion: string;
    };
    lastLinkedInPost: {
      author: string;
      commentary: string;
      distribution: { feedDistribution: string };
      isReshareDisabledByAuthor: boolean;
      lifecycleState: string;
      visibility: string;
    };
    linkedinAuthChecks: number;
    linkedinPublishes: number;
  };
  expect(linkedinMockState).toMatchObject({
    generationRequests: 5,
    linkedinAuthChecks: 1,
    linkedinPublishes: 1,
  });
  expect(linkedinMockState.lastLinkedInHeaders).toEqual({
    authorization: "Bearer e2e-linkedin-access-token",
    linkedinVersion: "202607",
    restliVersion: "2.0.0",
  });
  expect(linkedinMockState.lastLinkedInPost).toMatchObject({
    author: "urn:li:person:782bbtaQ",
    distribution: { feedDistribution: "MAIN_FEED" },
    isReshareDisabledByAuthor: false,
    lifecycleState: "PUBLISHED",
    visibility: "PUBLIC",
  });
  expect(linkedinMockState.lastLinkedInPost.commentary).toContain("Share one practical lesson");
  expect(linkedinMockState.lastLinkedInPost.commentary).toContain("#HumanReviewed");

  await navigate(page, "Integrations", "Connections");
  const linkedinCompanyForm = page.getByLabel("LinkedIn Organization ID").locator("xpath=ancestor::form");
  await linkedinCompanyForm.getByLabel("Connection name").fill("E2E LinkedIn Company Page");
  await linkedinCompanyForm.getByLabel("LinkedIn Organization ID").fill("5515715");
  await linkedinCompanyForm.getByLabel("Company Page operator Member ID").fill("782bbtaQ");
  await linkedinCompanyForm.getByLabel("Company Page API version").fill("202607");
  await linkedinCompanyForm.getByLabel("Company Page OAuth Access Token").fill("e2e-linkedin-company-token");
  await linkedinCompanyForm.getByRole("button", { name: "Save & verify permission" }).click();
  await expect(page.getByText("Waleed Khan can publish to LinkedIn Page 5515715.")).toBeVisible();

  await navigate(page, "Create content", "Create a draft");
  await page.getByLabel("Topic or source brief").fill(
    "Create one useful company lesson for our LinkedIn Page audience.",
  );
  await page.getByLabel("Channel").click();
  await page.getByRole("option", { name: "LinkedIn Company Page", exact: true }).click();

  const linkedinCompanyGenerateResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/posts/generate") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Generate review draft" }).click();
  await expect((await linkedinCompanyGenerateResponse).status()).toBe(200);
  await expect(page.getByRole("heading", { level: 1, name: "Approval queue" })).toBeVisible();
  await page.getByRole("button", { name: /^all / }).click();

  const linkedinCompanyTitle = "A reviewed LinkedIn Company Page update";
  const linkedinCompanyCard = page
    .getByRole("heading", { level: 2, name: linkedinCompanyTitle })
    .locator('xpath=ancestor::div[@data-slot="card"]');
  await linkedinCompanyCard.getByRole("button", { name: "Approve" }).click();
  await expect(linkedinCompanyCard.getByText("approved", { exact: true })).toBeVisible();

  const linkedinCompanyPublishResponse = page.waitForResponse(
    (response) => /\/api\/posts\/[^/]+\/publish$/.test(response.url()) && response.request().method() === "POST",
  );
  await linkedinCompanyCard.getByRole("button", { name: "Publish to Company Page" }).click();
  await expect((await linkedinCompanyPublishResponse).status()).toBe(200);
  await expect(linkedinCompanyCard.getByText("published", { exact: true })).toBeVisible();
  await expect(linkedinCompanyCard.getByText("remote:urn:li:share:7190000000000000004", { exact: true })).toBeVisible();

  const linkedinCompanyStateResponse = await page.request.get("/api/state");
  const linkedinCompanyState = (await linkedinCompanyStateResponse.json()) as PublicAppState;
  expect(linkedinCompanyState.posts).toHaveLength(5);
  expect(linkedinCompanyState.posts.find((post) => post.channel === "linkedin-company")).toMatchObject({
    remoteId: "urn:li:share:7190000000000000004",
    revision: 1,
    status: "published",
    title: linkedinCompanyTitle,
  });

  const linkedinCompanyMockResponse = await page.request.get(`${mockBaseUrl}/__e2e/state`);
  const linkedinCompanyMockState = (await linkedinCompanyMockResponse.json()) as {
    generationRequests: number;
    lastLinkedInOrganizationHeaders: {
      authorization: string;
      linkedinVersion: string;
      restliVersion: string;
    };
    lastLinkedInOrganizationPost: {
      author: string;
      commentary: string;
      distribution: { feedDistribution: string };
      isReshareDisabledByAuthor: boolean;
      lifecycleState: string;
      visibility: string;
    };
    linkedinAuthChecks: number;
    linkedinOrganizationAuthChecks: number;
    linkedinOrganizationPublishes: number;
  };
  expect(linkedinCompanyMockState).toMatchObject({
    generationRequests: 6,
    linkedinAuthChecks: 2,
    linkedinOrganizationAuthChecks: 1,
    linkedinOrganizationPublishes: 1,
  });
  expect(linkedinCompanyMockState.lastLinkedInOrganizationHeaders).toEqual({
    authorization: "Bearer e2e-linkedin-company-token",
    linkedinVersion: "202607",
    restliVersion: "2.0.0",
  });
  expect(linkedinCompanyMockState.lastLinkedInOrganizationPost).toMatchObject({
    author: "urn:li:organization:5515715",
    distribution: { feedDistribution: "MAIN_FEED" },
    isReshareDisabledByAuthor: false,
    lifecycleState: "PUBLISHED",
    visibility: "PUBLIC",
  });
  expect(linkedinCompanyMockState.lastLinkedInOrganizationPost.commentary).toContain("Share one useful company lesson");
  expect(linkedinCompanyMockState.lastLinkedInOrganizationPost.commentary).toContain("#HumanReviewed");

  await navigate(page, "Create content", "Create a draft");
  await page.getByLabel("Topic or source brief").fill("Phase eight skip: do not publish this review draft.");
  await page.getByLabel("Channel").click();
  await page.getByRole("option", { name: "X / Twitter" }).click();
  const skipGenerateResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/posts/generate") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Generate review draft" }).click();
  await expect((await skipGenerateResponse).status()).toBe(200);
  await page.getByRole("button", { name: /^all / }).click();
  const skipCard = page
    .getByRole("heading", { level: 2, name: "A skippable X review draft" })
    .locator('xpath=ancestor::div[@data-slot="card"]');
  await expect(skipCard.getByRole("button", { name: "Regenerate post", exact: true })).toBeVisible();
  await expect(skipCard.getByRole("button", { name: "Edit" })).toBeVisible();
  await expect(skipCard.getByRole("button", { name: "Approve" })).toBeVisible();
  await skipCard.getByRole("button", { name: "Skip" }).click();
  await expect(skipCard.getByText("skipped", { exact: true })).toBeVisible();
  await expect(skipCard.getByRole("button", { name: "Approve" })).toHaveCount(0);

  const skippedState = (await (await page.request.get("/api/state")).json()) as PublicAppState;
  expect(skippedState.posts.find((post) => post.title === "A skippable X review draft")).toMatchObject({
    revision: 1,
    status: "skipped",
    approvedAt: null,
    publishedAt: null,
  });

  await navigate(page, "Create content", "Create a draft");
  await page.getByLabel("Topic or source brief").fill("Phase nine recovery: ask before a missed publish.");
  await page.getByLabel("Channel").click();
  await page.getByRole("option", { name: "Blog" }).click();
  const recoveryGenerateResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/posts/generate") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Generate review draft" }).click();
  await expect((await recoveryGenerateResponse).status()).toBe(200);
  await page.getByRole("button", { name: /^all / }).click();
  const recoveryTitle = "A restart-safe scheduled draft";
  const recoveryCard = page
    .getByRole("heading", { level: 2, name: recoveryTitle })
    .locator('xpath=ancestor::div[@data-slot="card"]');
  await recoveryCard.getByRole("button", { name: "Approve" }).click();
  await expect(recoveryCard.getByText("approved", { exact: true })).toBeVisible();

  const beforeRecovery = (await (await page.request.get("/api/state")).json()) as PublicAppState;
  const recoveryPost = beforeRecovery.posts.find((post) => post.title === recoveryTitle);
  expect(recoveryPost).toBeTruthy();
  expect((await page.request.put("/api/scheduler", { data: { paused: true } })).ok()).toBeTruthy();
  const scheduledRecovery = await page.request.post(`/api/posts/${recoveryPost?.id}/schedule`, {
    data: {
      revision: recoveryPost?.revision,
      runAt: new Date(Date.now() - 2_000).toISOString(),
    },
  });
  expect(scheduledRecovery.ok()).toBeTruthy();
  const scheduledJob = (await scheduledRecovery.json()).job as { id: string };
  expect((await page.request.put("/api/scheduler", { data: { paused: false } })).ok()).toBeTruthy();

  await page.reload();
  const recoveryDialog = page.getByRole("dialog", { name: "Missed scheduled publish" });
  await expect(recoveryDialog).toBeVisible();
  await expect(recoveryDialog.getByText(recoveryTitle, { exact: true })).toBeVisible();
  await expect(recoveryDialog.getByRole("button", { name: "Run now" })).toBeVisible();
  await expect(recoveryDialog.getByRole("button", { name: "Reschedule" })).toBeVisible();
  await expect(recoveryDialog.getByRole("button", { name: "Skip" })).toBeVisible();
  await expectNoAccessibilityViolations(page, testInfo, "missed-publish-recovery");
  await recoveryDialog.getByRole("button", { name: "Reschedule" }).click();
  const newRecoveryTime = new Date(Date.now() + 60 * 60 * 1_000);
  const localRecoveryTime = new Date(newRecoveryTime.getTime() - newRecoveryTime.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 16);
  await recoveryDialog.getByLabel("New publish time").fill(localRecoveryTime);
  await recoveryDialog.getByRole("button", { name: "Confirm new time" }).click();
  await expect(recoveryDialog).toHaveCount(0);
  const recoveredState = (await (await page.request.get("/api/state")).json()) as PublicAppState;
  expect(recoveredState.scheduler.recoveryPending).toBe(0);
  expect(recoveredState.scheduler.workerLimit).toBe(1);
  expect(recoveredState.jobs.find((job) => job.id === scheduledJob.id)).toMatchObject({
    status: "queued",
    recoveryRequiredAt: null,
  });
  expect((await page.request.post(`/api/jobs/${scheduledJob.id}/cancel`)).ok()).toBeTruthy();

  await navigate(page, "Scheduler", "Scheduler");
  await expect(page.getByText("Worker use", { exact: true })).toBeVisible();
  await expect(page.getByText("0 / 1", { exact: true })).toBeVisible();
  await expect(page.getByText(/no rapid scheduler polling runs/i)).toBeVisible();

});

test("offers simple prebuilt AI providers without a Socium account", async ({ page }) => {
  await page.goto("/");
  await dismissOnboardingIfPresent(page);
  await expect(page.getByRole("heading", { level: 1, name: "Growth command" })).toBeVisible();
  await navigate(page, "Integrations", "Connections");

  const providerCard = page
    .getByText("AI provider", { exact: true })
    .locator('xpath=ancestor::div[@data-slot="card"]');
  const providerSelect = providerCard.getByLabel("AI service");

  await providerCard.getByRole("button", { name: "Use cloud API" }).click();
  await providerSelect.click();
  await page.getByRole("option", { name: "OpenAI", exact: true }).click();
  await expect(providerCard.getByText("gpt-5.6-luna", { exact: true })).toBeVisible();
  await expect(providerCard.getByText("No Socium account required", { exact: true })).toBeVisible();
  await expect(providerCard.getByRole("link", { name: "Get OpenAI key" })).toHaveAttribute("href", "https://platform.openai.com/api-keys");
  await expect(providerCard.getByRole("button", { name: "Connect provider" })).toBeDisabled();
  await providerCard.getByLabel("API key").fill("test-only-key");
  await expect(providerCard.getByRole("button", { name: "Connect provider" })).toBeEnabled();

  for (const [option, model, credentialLabel, credentialUrl] of [
    ["Google Gemini", "gemini-3.5-flash-lite", "Get Gemini key", "https://aistudio.google.com/apikey"],
    ["Claude (Anthropic)", "claude-sonnet-4-6", "Get Claude key", "https://platform.claude.com/settings/keys"],
    ["OpenRouter", "openrouter/free", "Get OpenRouter key", "https://openrouter.ai/settings/keys"],
    ["NVIDIA NIM", "meta/llama-3.1-8b-instruct", "Get NVIDIA key", "https://build.nvidia.com/settings/api-keys"],
  ] as const) {
    await providerSelect.click();
    await page.getByRole("option", { name: option }).click();
    await expect(providerCard.getByText(model, { exact: true })).toBeVisible();
    await expect(providerCard.getByRole("link", { name: credentialLabel })).toHaveAttribute("href", credentialUrl);
}

  await providerCard.getByRole("button", { name: "Use local AI" }).click();
  await providerSelect.click();
  await page.getByRole("option", { name: "Local AI (Ollama)" }).click();
  await expect(providerCard.getByText("Model auto-detect", { exact: true })).toBeVisible();
  await expect(providerCard.getByRole("link", { name: "Download Ollama" })).toHaveAttribute("href", "https://ollama.com/download");
  await expect(providerCard.getByRole("button", { name: "Find local model" })).toBeEnabled();
  await expect(providerCard.getByLabel("API key")).toHaveCount(0);

  await providerCard.getByRole("button", { name: "Use cloud API" }).click();
  await providerSelect.click();
  await page.getByRole("option", { name: "Custom / I'm not sure" }).click();
  await expect(providerCard.getByLabel("Base URL")).toBeVisible();
  await expect(providerCard.getByLabel("Model")).toBeVisible();
  await providerCard.getByLabel("Base URL").fill(`${mockBaseUrl}/v1`);
  await providerCard.getByRole("button", { name: "Detect API & models" }).click();
  await expect(providerCard.getByText("Provider detected with 1 model(s).")).toBeVisible();
  await expect(providerCard.getByLabel("Model")).toHaveValue("e2e-model");

  const telegramCard = page.getByText("Telegram", { exact: true }).locator('xpath=ancestor::div[@data-slot="card"]');
  await expect(telegramCard.getByRole("link", { name: "Get bot token" })).toHaveAttribute("href", "https://t.me/BotFather");
  await expect(telegramCard.getByLabel("Approval chat ID")).toHaveCount(0);
  const telegramProxySwitch = telegramCard.getByRole("switch", { name: "Use your own Telegram-only proxy" });
  await expect(telegramProxySwitch).toBeVisible();
  await telegramProxySwitch.click();
  await expect(telegramCard.getByRole("button", { name: "Test proxy" })).toBeDisabled();
  await page.route("**/api/integrations/telegram/proxy/test", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ ok: true, message: "Proxy reached the Telegram Bot API successfully." }),
      status: 200,
    });
  });
  await telegramCard.getByLabel("HTTP or SOCKS5 proxy").fill("socks5://proxy.example:1080");
  await telegramCard.getByRole("button", { name: "Test proxy" }).click();
  await expect(telegramCard.getByText("Proxy reached the Telegram Bot API successfully.")).toBeVisible();
  await expect(telegramCard.getByRole("button", { name: /Connect Telegram|Reconnect Telegram/ })).toBeVisible();
  const slackCard = page.getByText("Slack approval connector", { exact: true }).locator('xpath=ancestor::div[@data-slot="card"]');
  await expect(slackCard.getByText("No Slack tokens or channel IDs", { exact: true })).toBeVisible();
  await expect(slackCard.getByLabel("Bot token")).toHaveCount(0);
  await expect(slackCard.getByLabel("App token")).toHaveCount(0);
  await expect(slackCard.getByRole("button", { name: /Connect Slack|Reconnect Slack/ })).toBeVisible();
  const linkedinCard = page.getByText("LinkedIn Member", { exact: true }).locator('xpath=ancestor::div[@data-slot="card"]');
  await expect(linkedinCard.getByText("The browser never receives the access token.", { exact: false })).toBeVisible();
  await expect(linkedinCard.getByLabel("OAuth Access Token")).toHaveCount(0);
  await expect(linkedinCard.getByRole("button", { name: /Connect LinkedIn|Reconnect LinkedIn/ })).toBeVisible();
  const wordpressCard = page
    .getByText("WordPress publisher", { exact: true })
    .locator('xpath=ancestor::div[@data-slot="card"]');
  await expect(wordpressCard.getByRole("link", { name: "WordPress Application Password guide", exact: true })).toHaveAttribute(
    "href",
    "https://developer.wordpress.org/rest-api/using-the-rest-api/authentication/",
  );
  await expect(page.getByRole("link", { name: "Get Page token", exact: true })).toHaveAttribute("href", "https://developers.facebook.com/tools/explorer/");
  await expect(page.getByRole("link", { name: "Get OAuth token", exact: true }).first()).toHaveAttribute("href", "https://www.linkedin.com/developers/tools/oauth/token-generator");
});

test("manages recurring automations with readable scheduling controls", async ({ page }, testInfo) => {
  await page.goto("/");
  await dismissOnboardingIfPresent(page);
  await expect(page.getByRole("heading", { level: 1, name: "Growth command" })).toBeVisible();

  const created = await page.request.post("/api/automations", {
    data: {
      name: "E2E weekly plan",
      enabled: false,
      channel: "linkedin",
      topic: "Share practical local-first marketing lessons.",
      tone: "Clear and useful",
      objective: "Build trust",
      timezone: "Asia/Karachi",
      daysOfWeek: [0, 2, 4],
      publishTime: "10:00",
      approvalChannels: [],
      generateAheadMinutes: 60,
      publishAfterApproval: true,
    },
  });
  expect(created.ok()).toBeTruthy();
  const automation = (await created.json()).automation as { id: string };

  await page.reload();
  await dismissOnboardingIfPresent(page);
  await navigate(page, "Automations", "Automations");
  await expect(page.getByText("E2E weekly plan", { exact: true })).toBeVisible();
  await expect(page.getByText("3 / week", { exact: true })).toBeVisible();
  await expect(page.getByText("Approval-first", { exact: true })).toBeVisible();
  await expectNoAccessibilityViolations(page, testInfo, "automations");

  await page.getByRole("button", { name: "New automation" }).click();
  const createDialog = page.getByRole("dialog", { name: "Create automation" });
  await expect(createDialog.getByLabel("Name")).toBeVisible();
  await expect(createDialog.getByText("3 posts every week", { exact: true })).toBeVisible();
  await expect(createDialog.getByRole("button", { name: "3 per week", exact: true })).toHaveAttribute("aria-pressed", "true");
  await createDialog.getByRole("button", { name: "Daily", exact: true }).click();
  await expect(createDialog.getByText("7 posts every week", { exact: true })).toBeVisible();
  await expect(createDialog.getByRole("switch", { name: /Publish automatically after approval/ })).toBeChecked();
  await createDialog.getByRole("button", { name: "Cancel" }).click();

  const card = page.getByText("E2E weekly plan", { exact: true }).locator('xpath=ancestor::div[@data-slot="card"]');
  await card.getByRole("button", { name: "Edit" }).click();
  const editDialog = page.getByRole("dialog", { name: "Edit automation" });
  await editDialog.getByLabel("Name").fill("E2E updated plan");
  await editDialog.getByRole("button", { name: "Save automation" }).click();
  await expect(page.getByText("E2E updated plan", { exact: true })).toBeVisible();

  const updatedCard = page.getByText("E2E updated plan", { exact: true }).locator('xpath=ancestor::div[@data-slot="card"]');
  await updatedCard.getByRole("button", { name: "Delete" }).click();
  const deleteDialog = page.getByRole("dialog", { name: "Delete automation?" });
  await deleteDialog.getByRole("button", { name: "Delete automation" }).click();
  await expect(page.getByText("E2E updated plan", { exact: true })).toHaveCount(0);
  expect((await page.request.delete(`/api/automations/${automation.id}`)).status()).toBe(404);
});

test("manages a real local media asset and hands its HTTPS source to a draft", async ({ page }) => {
  await page.goto("/");
  await dismissOnboardingIfPresent(page);
  await expect(page.getByRole("heading", { level: 1, name: "Growth command" })).toBeVisible();
  await navigate(page, "Media library", "Media library");
  await expect(page.getByRole("heading", { level: 1, name: "Media library" })).toBeVisible();

  const providerResponse = await page.request.put("/api/settings/provider", {
    data: {
      kind: "openai-compatible",
      baseUrl: `${mockBaseUrl}/v1`,
      model: "e2e-model",
      apiKey: "e2e-provider-key",
    },
  });
  expect(providerResponse.status()).toBe(200);
  await page.reload();
  await navigate(page, "Media library", "Media library");
  await expect(page.getByText("One connected AI", { exact: true })).toBeVisible();
  await expect(page.getByText("No separate image API or adapter is needed.", { exact: true })).toBeVisible();
  await expect(page.getByText("Choose an image-capable AI in Integrations", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Generate image" })).toBeDisabled();

  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
    "base64",
  );
  await page.locator("#media-upload").setInputFiles({
    name: "e2e-campaign.png",
    mimeType: "image/png",
    buffer: png,
  });
  const uploadResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/media") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Store locally" }).click();
  expect((await uploadResponse).status()).toBe(200);
  await expect(page.getByText("Image stored locally")).toBeVisible();

  let assetCard = page
    .getByText("e2e-campaign.png", { exact: true })
    .locator('xpath=ancestor::div[@data-slot="card"]');
  await expect(assetCard.getByRole("img", { name: "Preview of e2e-campaign.png" })).toBeVisible();
  await expect(assetCard.getByRole("button", { name: "Use in draft" })).toBeDisabled();
  await assetCard.getByRole("button", { name: "Edit e2e-campaign.png" }).click();

  const metadataDialog = page.getByRole("dialog", { name: "Edit media metadata" });
  await metadataDialog.getByLabel("Alt text").fill("A green E2E campaign image");
  await metadataDialog.getByLabel("Public HTTPS source").fill("https://cdn.example.test/e2e-campaign.png");
  await metadataDialog.getByRole("button", { name: "Save metadata" }).click();
  await expect(page.getByText("Media metadata saved")).toBeVisible();

  assetCard = page
    .getByText("e2e-campaign.png", { exact: true })
    .locator('xpath=ancestor::div[@data-slot="card"]');
  await expect(assetCard.getByText("HTTPS ready")).toBeVisible();
  await assetCard.getByRole("button", { name: "Use in draft" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Create a draft" })).toBeVisible();
  await expect(page.getByLabel("Public image URL")).toHaveValue("https://cdn.example.test/e2e-campaign.png");

  await navigate(page, "Media library", "Media library");
  assetCard = page
    .getByText("e2e-campaign.png", { exact: true })
    .locator('xpath=ancestor::div[@data-slot="card"]');
  const transformResponse = page.waitForResponse(
    (response) => /\/api\/media\/[^/]+\/transform$/.test(response.url()),
  );
  await assetCard.getByRole("button", { name: "Create Portrait 4:5 transform of e2e-campaign.png" }).click();
  expect((await transformResponse).status()).toBe(200);
  await expect(page.getByText("Portrait 4:5 created")).toBeVisible();

  const transformedCard = page
    .getByText("e2e-campaign-portrait.webp", { exact: true })
    .locator('xpath=ancestor::div[@data-slot="card"]');
  await expect(transformedCard.getByText("1080×1350", { exact: false })).toBeVisible();
  await transformedCard.getByRole("button", { name: "Delete e2e-campaign-portrait.webp" }).click();
  const deleteDialog = page.getByRole("dialog", { name: "Delete e2e-campaign-portrait.webp?" });
  await expect(deleteDialog.getByText("This deletion cannot be undone.", { exact: false })).toBeVisible();
  await deleteDialog.getByRole("button", { name: "Delete local files" }).click();
  await expect(page.getByText("Media asset deleted from this computer")).toBeVisible();
  await expect(page.getByText("e2e-campaign-portrait.webp", { exact: true })).toHaveCount(0);
});

test("passes automated accessibility checks in core workflow views", async ({ page }, testInfo) => {
  await page.goto("/");
  await dismissOnboardingIfPresent(page);
  await expect(page.getByRole("heading", { level: 1, name: "Growth command" })).toBeVisible();
  await expectNoAccessibilityViolations(page, testInfo, "growth-command");

  await navigate(page, "Setup guide", "Setup guide");
  await expectNoAccessibilityViolations(page, testInfo, "setup-guide");

  await navigate(page, "Integrations", "Connections");
  await expectNoAccessibilityViolations(page, testInfo, "connections");

  await navigate(page, "Media library", "Media library");
  await expectNoAccessibilityViolations(page, testInfo, "media-library");

  await navigate(page, "Approval queue", "Approval queue");
  await expectNoAccessibilityViolations(page, testInfo, "approval-queue");

  await navigate(page, "Automations", "Automations");
  await expectNoAccessibilityViolations(page, testInfo, "automations-empty");
});

test("supports keyboard navigation on the mobile layout", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await dismissOnboardingIfPresent(page);
  await expect(page.getByRole("heading", { level: 1, name: "Growth command" })).toBeVisible();

  const navigationTrigger = page.getByRole("button", { name: "Open navigation" });
  await navigationTrigger.focus();
  await expect(navigationTrigger).toBeFocused();
  await navigationTrigger.press("Enter");

  const navigationDialog = page.getByRole("dialog", { name: "Navigation" });
  await expect(navigationDialog).toBeVisible();
  await expectNoAccessibilityViolations(page, testInfo, "mobile-navigation");
  await navigationDialog.getByRole("button", { name: "Activity" }).click();
  await expect(navigationDialog).toBeHidden();
  await expect(page.getByRole("heading", { level: 1, name: "Activity" })).toBeVisible();
});

test("shows safe update, backup, and runtime controls", async ({ page }, testInfo) => {
  await page.goto("/");
  await dismissOnboardingIfPresent(page);
  await navigate(page, "System", "System & updates");
  await expect(page.getByText("Application updates", { exact: true })).toBeVisible();
  await expect(page.getByText("Only version and platform metadata leave this machine.")).toBeVisible();
  await page.getByRole("button", { name: "Back up local data now" }).click();
  await expect(page.getByText("Verified local backup created")).toBeVisible();
  await expect(page.getByText(/\d+ SAVED/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Install safely" })).toBeDisabled();
  await expectNoAccessibilityViolations(page, testInfo, "system-lifecycle");
});
