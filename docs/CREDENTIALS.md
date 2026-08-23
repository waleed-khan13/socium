# Connector credentials

Socium does not require every connector. The minimum useful setup is a business profile plus **one AI provider**. Draft review and approval work in the local dashboard without Telegram or Slack. Connect only the remote approval channel and publishing destinations you actually use.

## What is required?

| Area | Requirement |
| --- | --- |
| AI generation | Choose exactly one: Ollama, OpenAI, Gemini, Claude, OpenRouter, NVIDIA, or a compatible server. |
| Human approval | The local dashboard is built in. Telegram and Slack are optional remote approval channels. |
| Publishing | Every destination is optional. Connect only the platform or platforms where Socium should publish. |
| Lead discovery | Google Places is optional and used only by the Labs lead-discovery screen. |
| Image generation | Optional. Local ComfyUI/Automatic1111 or an Images API can be configured independently. |

## AI provider keys

| Provider | Exact credential page | What to do |
| --- | --- | --- |
| Ollama | [Download Ollama](https://ollama.com/download) | No token. Install and start Ollama; Socium recommends and downloads a compatible model, or you may choose one from the [model library](https://ollama.com/library). |
| OpenAI | [OpenAI API keys](https://platform.openai.com/api-keys) | Create a new secret key. ChatGPT subscriptions and API billing are separate. |
| Google Gemini | [Google AI Studio API keys](https://aistudio.google.com/apikey) | Select/create a Google Cloud project, then create an API key. |
| Claude / Anthropic | [Claude Console API keys](https://platform.claude.com/settings/keys) | Create a key in the Claude Console. |
| OpenRouter | [OpenRouter keys](https://openrouter.ai/settings/keys) | Create a key in the default workspace. |
| NVIDIA NIM | [NVIDIA Build API keys](https://build.nvidia.com/settings/api-keys) | Sign in and generate an NVIDIA API key. |
| Custom / I'm not sure | Your server's documentation | Socium first discovers Ollama, OpenAI-compatible, or Anthropic-compatible contracts without a key. If authentication blocks discovery, select the documented protocol before entering its credential. LM Studio, LocalAI, llama.cpp, and similar local servers commonly need no key. |

## Approval and publishing credentials

| Connector | Exact starting page | What to do |
| --- | --- | --- |
| Telegram | [Open @BotFather](https://t.me/BotFather) | Send `/newbot`, complete the prompts, copy the bot token, then message the bot once. See Telegram's [official bot tutorial](https://core.telegram.org/bots/tutorial). |
| Slack | [Your Slack apps](https://api.slack.com/apps) | Install the app to get the `xoxb-` bot token. Enable Socket Mode and create an app-level `xapp-` token with `connections:write`. See [Slack token types](https://api.slack.com/concepts/token-types). |
| WordPress | `https://YOUR-SITE/wp-admin/profile.php` | Sign in, open **Users → Profile → Application Passwords**, create one named Socium, and copy it. Do not use the normal login password. See [WordPress authentication](https://developer.wordpress.org/rest-api/using-the-rest-api/authentication/). |
| Facebook Page | [Meta Graph API Explorer](https://developers.facebook.com/tools/explorer/) | Create/select an app, authorize the required Pages permissions, and obtain the Page token for the target Page. Manage apps at [Meta for Developers](https://developers.facebook.com/apps/). |
| Instagram Professional | [Meta for Developers apps](https://developers.facebook.com/apps/) | Add the Instagram product, configure Instagram Login, and generate a token for the Business or Creator account. Follow the [Instagram Login API guide](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/). |
| LinkedIn Member | [LinkedIn OAuth Token Generator](https://www.linkedin.com/developers/tools/oauth/token-generator) | Create/select an app, enable the required products, and authorize the member scopes. Manage apps at [LinkedIn Developers](https://www.linkedin.com/developers/apps). |
| LinkedIn Company Page | [LinkedIn Developers apps](https://www.linkedin.com/developers/apps) | Link the app to the Page, obtain approval for organization products/scopes, and authorize a Page admin. The [token generator](https://www.linkedin.com/developers/tools/oauth/token-generator) only offers scopes already approved for the app. |

## Optional data and media credentials

| Feature | Exact credential page | What to do |
| --- | --- | --- |
| Google Places | [Google Cloud credentials](https://console.cloud.google.com/apis/credentials) | Enable [Places API (New)](https://console.cloud.google.com/apis/library/places-backend.googleapis.com), create a separate API key, and restrict it to that API. |
| OpenAI Images | [OpenAI API keys](https://platform.openai.com/api-keys) | Create a Platform API key. It can be separate from the text-provider key. |
| Automatic1111 / Forge | [Local API setup](https://github.com/AUTOMATIC1111/stable-diffusion-webui/wiki/API) | No provider token. Only enter `username:password` if the local WebUI was started with `--api-auth`. |
| ComfyUI | [ComfyUI API server guide](https://docs.comfy.org/development/core-concepts/api-server) | No provider token for the normal local server. |

## Token safety

- Paste tokens only into Socium's localhost UI. Never commit them to Git, screenshots, issues, or documentation.
- Socium encrypts saved secrets in the local vault and returns only presence flags to the browser after saving.
- Custom automatic discovery never sends a key. An authenticated custom endpoint requires an explicit protocol choice so the secret is sent to one selected contract rather than tested across candidates.
- Use the narrowest scopes the connector lists, test the connection, and revoke a credential from its provider dashboard if it is exposed.
- Do not paste a Telegram token into a browser URL to discover a chat ID; that can leave the token in browser history. Message the bot and use Socium's connection test/listener flow instead.
