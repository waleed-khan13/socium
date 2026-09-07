# Licensed lead-provider plugins

Socium does not scrape protected platforms or bundle third-party lead data. A user who already has a valid export from a licensed provider can add an import manifest under the local data directory:

`plugins/lead-providers/<provider-id>.json`

Example:

```json
{
  "id": "example-provider",
  "displayName": "Example Provider",
  "license": "Customer-owned commercial subscription",
  "homepageUrl": "https://provider.example",
  "importFormat": "csv",
  "fields": ["business_name", "website", "full_name", "job_title", "email", "phone"]
}
```

The manifest advertises an import format only. Socium does not execute plugin code in its API process and does not receive the provider account password, session cookie, or API key. Provider-specific download automation can be delivered later as a separately reviewed adapter. Every imported contact still passes Socium's consent, suppression, legal-basis, and retention gates before outreach.
