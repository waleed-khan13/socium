import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const projectRoot = process.cwd();
const webPort = Number(process.env.SOCIUM_E2E_WEB_PORT ?? "3100");
const apiPort = Number(process.env.SOCIUM_E2E_API_PORT ?? "8100");
const mockPort = Number(process.env.SOCIUM_E2E_MOCK_PORT ?? "4100");
const runtimeDirectory = path.join(projectRoot, "output", "playwright", "runtime", String(process.pid));
const children = new Set();
let stopping = false;

const mockState = {
  modelRequests: 0,
  generationRequests: 0,
  imageGenerationRequests: 0,
  wordpressAuthChecks: 0,
  wordpressPublishes: 0,
  metaAuthChecks: 0,
  metaPublishes: 0,
  instagramAuthChecks: 0,
  instagramContainers: 0,
  instagramStatusChecks: 0,
  instagramPublishes: 0,
  linkedinAuthChecks: 0,
  linkedinImageUploads: 0,
  linkedinPublishes: 0,
  linkedinOrganizationAuthChecks: 0,
  linkedinOrganizationPublishes: 0,
  lastPublishedPost: null,
  lastFacebookPost: null,
  lastInstagramContainer: null,
  lastInstagramPublish: null,
  lastLinkedInPost: null,
  lastLinkedInHeaders: null,
  lastLinkedInOrganizationPost: null,
  lastLinkedInOrganizationHeaders: null,
  lastImageGeneration: null,
  lastGenerationRequest: null,
};

function sendJson(response, statusCode, payload) {
  response.writeHead(statusCode, {
    "access-control-allow-origin": "*",
    "cache-control": "no-store",
    "content-type": "application/json; charset=utf-8",
  });
  response.end(JSON.stringify(payload));
}

async function readJson(request) {
  const chunks = [];
  for await (const chunk of request) chunks.push(chunk);
  if (chunks.length === 0) return {};
  return JSON.parse(Buffer.concat(chunks).toString("utf8"));
}

const mockServer = createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", `http://127.0.0.1:${mockPort}`);

  try {
    if (request.method === "GET" && url.pathname === "/__e2e/health") {
      sendJson(response, 200, { ok: true });
      return;
    }

    if (request.method === "GET" && url.pathname === "/__e2e/state") {
      sendJson(response, 200, mockState);
      return;
    }

    if (request.method === "GET" && url.pathname === "/v1/models") {
      mockState.modelRequests += 1;
      sendJson(response, 200, { data: [{ id: "e2e-model" }] });
      return;
    }

    if (request.method === "POST" && url.pathname === "/v1/chat/completions") {
      mockState.generationRequests += 1;
      mockState.lastGenerationRequest = await readJson(request);
      const generationPrompt = mockState.lastGenerationRequest.messages
        ?.map((message) => message.content)
        .join("\n") ?? "";
      const facebookDraft = generationPrompt.includes("Channel: facebook");
      const instagramDraft = generationPrompt.includes("Channel: instagram");
      const linkedinDraft = generationPrompt.includes("Channel: linkedin\n");
      const linkedinOrganizationDraft = generationPrompt.includes("Channel: linkedin-company");
      const skipDraft = generationPrompt.includes("Topic: Phase eight skip");
      const recoveryDraft = generationPrompt.includes("Topic: Phase nine recovery");
      sendJson(response, 200, {
        choices: [
          {
            message: {
              content: JSON.stringify({
                title: recoveryDraft
                  ? "A restart-safe scheduled draft"
                  : skipDraft
                  ? "A skippable X review draft"
                  : linkedinOrganizationDraft
                  ? "A reviewed LinkedIn Company Page update"
                  : linkedinDraft
                  ? "A reviewed LinkedIn member update"
                  : instagramDraft
                  ? "A reviewed Instagram image update"
                  : facebookDraft
                    ? "A useful Facebook Page update"
                    : "A practical local growth checklist",
                body: recoveryDraft
                  ? "This approved revision must wait for an explicit recovery decision if its local deadline is missed."
                  : skipDraft
                  ? "This revision exists only to verify an explicit non-publication decision."
                  : linkedinOrganizationDraft
                  ? "Share one useful company lesson, make the customer value clear, and publish only the exact reviewed Page update."
                  : linkedinDraft
                  ? "Share one practical lesson, make the professional value clear, and keep the published text human-reviewed."
                  : instagramDraft
                  ? "Show one practical campaign idea, keep the caption useful, and publish the exact reviewed image."
                  : facebookDraft
                  ? "Share one useful local insight, invite a relevant response, and keep the final post human-reviewed."
                  : "Start with one clear customer problem, publish a useful answer, and review the result before the next post.",
                hashtags: recoveryDraft
                  ? ["#Socium", "#RestartSafe"]
                  : skipDraft
                  ? ["#Socium", "#SkipReview"]
                  : linkedinOrganizationDraft
                  ? ["#CompanyGrowth", "#HumanReviewed"]
                  : linkedinDraft
                  ? ["#ProfessionalGrowth", "#HumanReviewed"]
                  : instagramDraft
                  ? ["#InstagramForBusiness", "#HumanReviewed"]
                  : facebookDraft
                    ? ["#LocalBusiness", "#FacebookMarketing"]
                    : ["#Socium", "#SmallBusiness"],
                callToAction: "Book a practical workflow review.",
                imagePrompt: "A dark editorial small-business workspace with amber and emerald lighting, authentic tools, clear composition, no embedded text",
                imageNegativePrompt: "watermark, distorted logo, unreadable text, duplicate objects",
                imageAltText: "Small-business workspace arranged for a practical marketing workflow review",
                rationale: recoveryDraft
                  ? "A missed local deadline proves that Socium asks before catch-up publication."
                  : skipDraft
                  ? "A disposable draft proves that Skip is distinct from approval and publication."
                  : linkedinOrganizationDraft
                  ? "A concise Page post exercises permission-verified LinkedIn organization publishing."
                  : linkedinDraft
                  ? "A concise public text post exercises the official LinkedIn Posts API member flow."
                  : instagramDraft
                  ? "A public image URL and exact approved caption exercise Instagram's container workflow."
                  : facebookDraft
                  ? "A concise, reviewed update is appropriate for the connected Facebook Page."
                  : "A concrete checklist gives a small business an immediately useful next step.",
              }),
            },
          },
        ],
      });
      return;
    }

    if (request.method === "POST" && url.pathname === "/v1/images/generations") {
      mockState.imageGenerationRequests += 1;
      mockState.lastImageGeneration = await readJson(request);
      sendJson(response, 200, {
        data: [
          {
            b64_json:
              "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGNkOPGfgYGBiQEMABR/Act0bgo/AAAAAElFTkSuQmCC",
          },
        ],
      });
      return;
    }

    if (request.method === "GET" && url.pathname === "/wp-json/wp/v2/users/me") {
      mockState.wordpressAuthChecks += 1;
      sendJson(response, 200, {
        id: 7,
        name: "E2E Editor",
        capabilities: { edit_posts: true },
      });
      return;
    }

    if (request.method === "POST" && url.pathname === "/wp-json/wp/v2/posts") {
      mockState.wordpressPublishes += 1;
      mockState.lastPublishedPost = await readJson(request);
      sendJson(response, 201, {
        id: 4242,
        link: `http://127.0.0.1:${mockPort}/posts/4242`,
      });
      return;
    }

    if (request.method === "GET" && url.pathname === "/meta/v25.0/123456789012345") {
      mockState.metaAuthChecks += 1;
      if (request.headers.authorization !== "Bearer e2e-page-access-token") {
        sendJson(response, 401, { error: { code: 190, message: "Invalid OAuth access token." } });
        return;
      }
      if (url.searchParams.get("fields") !== "id,name") {
        sendJson(response, 400, { error: { code: 100, message: "Unsupported fields request." } });
        return;
      }
      sendJson(response, 200, {
        id: "123456789012345",
        name: "Northstar Studio",
      });
      return;
    }

    if (request.method === "POST" && url.pathname === "/meta/v25.0/123456789012345/feed") {
      mockState.metaPublishes += 1;
      const chunks = [];
      for await (const chunk of request) chunks.push(chunk);
      mockState.lastFacebookPost = Object.fromEntries(
        new URLSearchParams(Buffer.concat(chunks).toString("utf8")),
      );
      sendJson(response, 200, { id: "123456789012345_987654321" });
      return;
    }

    if (request.method === "GET" && url.pathname === "/instagram/v25.0/17841400000000000") {
      mockState.instagramAuthChecks += 1;
      if (request.headers.authorization !== "Bearer e2e-instagram-access-token") {
        sendJson(response, 401, { error: { code: 190, message: "Invalid OAuth access token." } });
        return;
      }
      if (url.searchParams.get("fields") !== "id,username,account_type") {
        sendJson(response, 400, { error: { code: 100, message: "Unsupported fields request." } });
        return;
      }
      sendJson(response, 200, {
        id: "17841400000000000",
        username: "northstarstudio",
        account_type: "BUSINESS",
      });
      return;
    }

    if (request.method === "POST" && url.pathname === "/instagram/v25.0/17841400000000000/media") {
      mockState.instagramContainers += 1;
      if (request.headers.authorization !== "Bearer e2e-instagram-access-token") {
        sendJson(response, 401, { error: { code: 190, message: "Invalid OAuth access token." } });
        return;
      }
      const chunks = [];
      for await (const chunk of request) chunks.push(chunk);
      mockState.lastInstagramContainer = Object.fromEntries(
        new URLSearchParams(Buffer.concat(chunks).toString("utf8")),
      );
      sendJson(response, 200, { id: "18000000000000010" });
      return;
    }

    if (request.method === "GET" && url.pathname === "/instagram/v25.0/18000000000000010") {
      mockState.instagramStatusChecks += 1;
      if (request.headers.authorization !== "Bearer e2e-instagram-access-token") {
        sendJson(response, 401, { error: { code: 190, message: "Invalid OAuth access token." } });
        return;
      }
      if (url.searchParams.get("fields") !== "status_code,status") {
        sendJson(response, 400, { error: { code: 100, message: "Unsupported status fields." } });
        return;
      }
      sendJson(response, 200, { status_code: "FINISHED", status: "Finished" });
      return;
    }

    if (request.method === "POST" && url.pathname === "/instagram/v25.0/17841400000000000/media_publish") {
      mockState.instagramPublishes += 1;
      if (request.headers.authorization !== "Bearer e2e-instagram-access-token") {
        sendJson(response, 401, { error: { code: 190, message: "Invalid OAuth access token." } });
        return;
      }
      const chunks = [];
      for await (const chunk of request) chunks.push(chunk);
      mockState.lastInstagramPublish = Object.fromEntries(
        new URLSearchParams(Buffer.concat(chunks).toString("utf8")),
      );
      sendJson(response, 200, { id: "18000000000000011" });
      return;
    }

    if (request.method === "GET" && url.pathname === "/linkedin/v2/userinfo") {
      mockState.linkedinAuthChecks += 1;
      if (!["Bearer e2e-linkedin-access-token", "Bearer e2e-linkedin-company-token"].includes(request.headers.authorization)) {
        sendJson(response, 401, { status: 401, message: "Invalid OAuth access token." });
        return;
      }
      sendJson(response, 200, {
        sub: "782bbtaQ",
        name: "Waleed Khan",
        given_name: "Waleed",
        family_name: "Khan",
      });
      return;
    }

    if (request.method === "GET" && url.pathname.startsWith("/linkedin/rest/organizationAuthorizations/")) {
      mockState.linkedinOrganizationAuthChecks += 1;
      if (request.headers.authorization !== "Bearer e2e-linkedin-company-token") {
        sendJson(response, 401, { status: 401, message: "Invalid Company Page token." });
        return;
      }
      if (!url.pathname.includes("ORGANIC_SHARE_CREATE")) {
        sendJson(response, 400, { status: 400, message: "Missing organic share authorization action." });
        return;
      }
      sendJson(response, 200, {
        impersonator: "urn:li:person:782bbtaQ",
        organization: "urn:li:organization:5515715",
        status: { "com.linkedin.organization.Approved": {} },
      });
      return;
    }

    if (
      request.method === "POST"
      && url.pathname === "/linkedin/rest/images"
      && url.searchParams.get("action") === "initializeUpload"
    ) {
      const companyUpload = request.headers.authorization === "Bearer e2e-linkedin-company-token";
      const memberUpload = request.headers.authorization === "Bearer e2e-linkedin-access-token";
      if (!companyUpload && !memberUpload) {
        sendJson(response, 401, { status: 401, message: "Invalid OAuth access token." });
        return;
      }
      const body = await readJson(request);
      const owner = body?.initializeUploadRequest?.owner;
      if (typeof owner !== "string" || !owner.startsWith("urn:li:")) {
        sendJson(response, 400, { status: 400, message: "Missing image owner." });
        return;
      }
      const uploadKind = companyUpload ? "company" : "member";
      sendJson(response, 200, {
        value: {
          image: `urn:li:image:e2e-${uploadKind}-image`,
          uploadUrl: `http://127.0.0.1:${mockPort}/linkedin/upload/${uploadKind}`,
        },
      });
      return;
    }

    if (request.method === "PUT" && url.pathname.startsWith("/linkedin/upload/")) {
      const expectedToken = url.pathname.endsWith("/company")
        ? "Bearer e2e-linkedin-company-token"
        : "Bearer e2e-linkedin-access-token";
      if (request.headers.authorization !== expectedToken) {
        sendJson(response, 401, { status: 401, message: "Invalid image upload token." });
        return;
      }
      let uploadedBytes = 0;
      for await (const chunk of request) uploadedBytes += chunk.length;
      if (uploadedBytes === 0) {
        sendJson(response, 400, { status: 400, message: "Image upload was empty." });
        return;
      }
      mockState.linkedinImageUploads += 1;
      response.writeHead(201, { "cache-control": "no-store" });
      response.end();
      return;
    }

    if (request.method === "POST" && url.pathname === "/linkedin/rest/posts") {
      const companyPublish = request.headers.authorization === "Bearer e2e-linkedin-company-token";
      const validMemberPublish = request.headers.authorization === "Bearer e2e-linkedin-access-token";
      const capturedHeaders = {
        authorization: request.headers.authorization,
        linkedinVersion: request.headers["linkedin-version"],
        restliVersion: request.headers["x-restli-protocol-version"],
      };
      if (!companyPublish && !validMemberPublish) {
        sendJson(response, 401, { status: 401, message: "Invalid OAuth access token." });
        return;
      }
      if (request.headers["linkedin-version"] !== "202607") {
        sendJson(response, 400, { status: 400, message: "Missing LinkedIn version." });
        return;
      }
      if (request.headers["x-restli-protocol-version"] !== "2.0.0") {
        sendJson(response, 400, { status: 400, message: "Missing Rest.li version." });
        return;
      }
      const publishedBody = await readJson(request);
      if (companyPublish) {
        mockState.linkedinOrganizationPublishes += 1;
        mockState.lastLinkedInOrganizationHeaders = capturedHeaders;
        mockState.lastLinkedInOrganizationPost = publishedBody;
      } else {
        mockState.linkedinPublishes += 1;
        mockState.lastLinkedInHeaders = capturedHeaders;
        mockState.lastLinkedInPost = publishedBody;
      }
      response.writeHead(201, {
        "access-control-allow-origin": "*",
        "cache-control": "no-store",
        "content-type": "application/json; charset=utf-8",
        "x-restli-id": companyPublish
          ? "urn:li:share:7190000000000000004"
          : "urn:li:share:7190000000000000003",
      });
      response.end("{}");
      return;
    }

    sendJson(response, 404, { message: `Unhandled E2E route: ${request.method} ${url.pathname}` });
  } catch (error) {
    sendJson(response, 500, {
      message: error instanceof Error ? error.message : "Unexpected E2E mock error.",
    });
  }
});

function launch(command, args, extraEnv = {}) {
  const child = spawn(command, args, {
    cwd: projectRoot,
    env: { ...process.env, ...extraEnv },
    stdio: "inherit",
    windowsHide: true,
  });
  children.add(child);
  child.on("error", (error) => {
    console.error(`[e2e] Could not start ${command}:`, error);
    shutdown(1);
  });
  child.on("exit", (code) => {
    children.delete(child);
    if (!stopping) {
      console.error(`[e2e] ${command} exited unexpectedly with code ${code ?? 1}.`);
      shutdown(code ?? 1);
    }
  });
  return child;
}

async function waitFor(url, timeoutMs = 60_000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(2_000) });
      if (response.ok) return;
      lastError = new Error(`HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Timed out waiting for ${url}: ${lastError instanceof Error ? lastError.message : "unknown error"}`);
}

function shutdown(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill();
  mockServer.close(() => process.exit(code));
  setTimeout(() => process.exit(code), 1_000).unref();
}

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => shutdown(0));
}

process.on("uncaughtException", (error) => {
  console.error("[e2e] Uncaught error:", error);
  shutdown(1);
});

await mkdir(runtimeDirectory, { recursive: true });
await new Promise((resolve, reject) => {
  mockServer.once("error", reject);
  mockServer.listen(mockPort, "127.0.0.1", resolve);
});

launch(
  "uv",
  ["run", "--project", "backend", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(apiPort)],
  {
    SOCIUM_API_HOST: "127.0.0.1",
    SOCIUM_API_PORT: String(apiPort),
    SOCIUM_DATA_DIR: runtimeDirectory,
    SOCIUM_SCHEDULER_INTERVAL: "0.25",
    SOCIUM_SLACK_SOCKET_MODE: "0",
    SOCIUM_ENABLE_LABS: "0",
    SOCIUM_AUTO_UPDATE_CHECKS: "0",
    SOCIUM_META_GRAPH_BASE_URL: `http://127.0.0.1:${mockPort}/meta`,
    SOCIUM_INSTAGRAM_GRAPH_BASE_URL: `http://127.0.0.1:${mockPort}/instagram`,
    SOCIUM_LINKEDIN_API_BASE_URL: `http://127.0.0.1:${mockPort}/linkedin`,
  },
);

await waitFor(`http://127.0.0.1:${apiPort}/api/health`);

launch(
  process.execPath,
  [
    path.join(projectRoot, "node_modules", "next", "dist", "bin", "next"),
    "dev",
    "-H",
    "127.0.0.1",
    "-p",
    String(webPort),
    "--webpack",
  ],
  {
    SOCIUM_API_URL: `http://127.0.0.1:${apiPort}`,
  },
);

console.log(`[e2e] Socium: http://127.0.0.1:${webPort}`);
console.log(`[e2e] External service mock: http://127.0.0.1:${mockPort}`);
