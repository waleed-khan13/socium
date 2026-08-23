import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type TestInfo } from "@playwright/test";

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

async function dismissOnboardingIfPresent(page: Page) {
  const dialog = page.getByRole("dialog", { name: "Socium first-run setup" });
  if (await dialog.isVisible().catch(() => false)) {
    await dialog.getByRole("button", { name: "Set up later" }).click();
    await expect(dialog).toHaveCount(0);
  }
}

test("runs first-run onboarding, publishing, and approval workflows", async ({ page }, testInfo) => {
  await page.goto("/");
  const onboarding = page.getByRole("dialog", { name: "Socium first-run setup" });
  await expect(onboarding.getByRole("heading", { name: "Welcome to Socium" })).toBeVisible();
  await expect(onboarding.getByText("LOCAL-FIRST · NO SOCIUM ACCOUNT")).toBeVisible();
  await expectNoAccessibilityViolations(page, testInfo, "onboarding-welcome");

  await onboarding.getByRole("button", { name: "Start setup" }).click();
  await expect(onboarding.getByRole("heading", { name: "Confirm private storage" })).toBeVisible();
  await expect(onboarding.getByText("Both durable locations are available.")).toBeVisible();
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
  await expect(page.getByText(/SOCIUM LOCAL.*v1\.0\.5/)).toBeVisible();
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
  expect(releaseState.runtime.version).toBe("1.0.5");
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
  await postCard.getByRole("button", { name: "Edit" }).click();

  const editDialog = page.getByRole("dialog", { name: "Edit draft" });
  await expect(editDialog).toBeVisible();
  await editDialog.getByLabel("Title").fill(editedTitle);
  await editDialog
    .getByLabel("Post body")
    .fill("Define one customer problem, publish one useful answer, and review the result before repeating the cycle.");
  await editDialog.getByLabel("Hashtags").fill("#Socium #Reviewed");
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
    revision: 2,
    status: "published",
    title: editedTitle,
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
    generationRequests: 1,
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
    generationRequests: 2,
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
    generationRequests: 3,
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
  const linkedinForm = page.getByLabel("LinkedIn Member ID").locator("xpath=ancestor::form");
  await linkedinForm.getByLabel("Connection name").fill("E2E LinkedIn profile");
  await linkedinForm.getByLabel("LinkedIn Member ID").fill("782bbtaQ");
  await linkedinForm.getByLabel("LinkedIn API version").fill("202607");
  await linkedinForm.getByLabel("OAuth Access Token").fill("e2e-linkedin-access-token");
  await linkedinForm.getByRole("button", { name: "Save & test" }).click();
  await expect(page.getByText("Connected to LinkedIn as Waleed Khan.")).toBeVisible();

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
    generationRequests: 4,
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
    generationRequests: 5,
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

});

test("offers simple prebuilt AI providers without a Socium account", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Growth command" })).toBeVisible();
  await dismissOnboardingIfPresent(page);
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
    ["Google Gemini", "gemini-3.7-flash", "Get Gemini key", "https://aistudio.google.com/apikey"],
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
  const slackCard = page.getByText("Slack approval connector", { exact: true }).locator('xpath=ancestor::div[@data-slot="card"]');
  await expect(slackCard.getByRole("link", { name: "Get bot token" })).toHaveAttribute("href", "https://api.slack.com/apps");
  await expect(slackCard.getByRole("link", { name: "Get app token" })).toHaveAttribute("href", "https://api.slack.com/apps");
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

test("manages a real local media asset and hands its HTTPS source to a draft", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Growth command" })).toBeVisible();
  await dismissOnboardingIfPresent(page);
  await navigate(page, "Media library", "Media library");
  await expect(page.getByText("No media stored yet")).toBeVisible();

  await page.getByLabel("Adapter").click();
  await page.getByRole("option", { name: "OpenAI-compatible Images API" }).click();
  await expect(page.getByRole("link", { name: "Get Images API key" })).toHaveAttribute("href", "https://platform.openai.com/api-keys");
  await page.getByLabel("Base URL").fill(`${mockBaseUrl}/v1`);
  await page.getByLabel("Model").fill("e2e-image-model");
  await page.getByLabel("API key").fill("e2e-image-key");
  await page.getByRole("button", { name: "Save & test" }).click();
  await expect(page.getByText("Image provider connected")).toBeVisible();

  const imagePrompt = "A cyan product launch scene on a deep black background with editorial lighting";
  await page.getByLabel("Campaign image prompt").fill(imagePrompt);
  await page.getByLabel("Aspect").click();
  await page.getByRole("option", { name: "Landscape" }).click();
  await page.getByLabel("Quality").click();
  await page.getByRole("option", { name: "Medium" }).click();
  const imageGenerationResponse = page.waitForResponse(
    (response) => response.url().endsWith("/api/media/generations") && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Generate image" }).click();
  expect((await imageGenerationResponse).status()).toBe(200);
  await expect(page.getByText("Image generation queued")).toBeVisible();
  await expect(page.getByText("Image saved privately and ready for review.")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("AI provenance")).toBeVisible();
  await expect(page.getByTitle(imagePrompt)).toBeVisible();

  const imageMockResponse = await page.request.get(`${mockBaseUrl}/__e2e/state`);
  const imageMockState = await imageMockResponse.json();
  expect(imageMockState.imageGenerationRequests).toBe(1);
  expect(imageMockState.lastImageGeneration).toEqual({
    model: "e2e-image-model",
    prompt: imagePrompt,
    n: 1,
    size: "1536x1024",
    quality: "medium",
    output_format: "png",
  });

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
  await expect(page.getByText("3 stored images")).toBeVisible();

  const transformedCard = page
    .getByText("e2e-campaign-portrait.webp", { exact: true })
    .locator('xpath=ancestor::div[@data-slot="card"]');
  await expect(transformedCard.getByText("1080×1350", { exact: false })).toBeVisible();
  await transformedCard.getByRole("button", { name: "Delete e2e-campaign-portrait.webp" }).click();
  const deleteDialog = page.getByRole("dialog", { name: "Delete e2e-campaign-portrait.webp?" });
  await expect(deleteDialog.getByText("This deletion cannot be undone.", { exact: false })).toBeVisible();
  await deleteDialog.getByRole("button", { name: "Delete local files" }).click();
  await expect(page.getByText("Media asset deleted from this computer")).toBeVisible();
  await expect(page.getByText("2 stored images")).toBeVisible();
});

test("passes automated accessibility checks in core workflow views", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Growth command" })).toBeVisible();
  await dismissOnboardingIfPresent(page);
  await expectNoAccessibilityViolations(page, testInfo, "growth-command");

  await navigate(page, "Setup guide", "Setup guide");
  await expectNoAccessibilityViolations(page, testInfo, "setup-guide");

  await navigate(page, "Integrations", "Connections");
  await expectNoAccessibilityViolations(page, testInfo, "connections");

  await navigate(page, "Media library", "Media library");
  await expectNoAccessibilityViolations(page, testInfo, "media-library");

  await navigate(page, "Approval queue", "Approval queue");
  await expectNoAccessibilityViolations(page, testInfo, "approval-queue");
});

test("supports keyboard navigation on the mobile layout", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Growth command" })).toBeVisible();
  await dismissOnboardingIfPresent(page);

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
