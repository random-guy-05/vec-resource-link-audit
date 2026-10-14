# VEC Resource Link Audit

A small, polite command-line link checker for the public Virtual Embryo Challenge resource catalog or another JSON list of public URLs. It helps resource maintainers find links that return clear missing-page responses while distinguishing those from sites that block automated checks or are temporarily unavailable.

The checker makes one HEAD request per HTTP(S) link, with a small byte-range GET only when the server does not support HEAD. It does not crawl pages, follow links found inside them, authenticate, or retry failures. Redirects are followed and both source and final destinations are recorded.

## Run

Requires Python 3.10 or later and no third-party packages.

~~~sh
python resource_link_audit.py catalog.json --out link-audit
~~~

For a JSON object containing an array of resources, pass the array key:

~~~sh
python resource_link_audit.py export.json --items-key resources --url-key public_url
~~~

For a file containing a top-level list, the default URL keys are url, href, public_link, and link. Each record can also contain a title or name. Use --url-key to select another field.

The command writes:

- **link-audit.md** — status summary and a concise table.
- **link-audit.csv** — one row per entry, suitable for spreadsheet triage.
- **link-audit.json** — full machine-readable results and check timestamp.

## Status meanings

| Status | Meaning |
| --- | --- |
| **ok** | A 2xx response from the submitted URL |
| **redirected** | Redirect chain ended at a 2xx destination |
| **missing** | Server returned 404 or 410 |
| **access_restricted** | Server returned 401 or 403; the link may still work in a browser |
| **rate_limited** | Server returned 429 |
| **server_error** | Server returned 5xx; retry manually later |
| **http_error** | Other HTTP response that needs human review |
| **network_error** | DNS, TLS, timeout, or connection problem |
| **invalid_url** | URL is malformed or has no hostname |
| **unsupported_scheme** | URL is not HTTP(S) |

Only missing is treated as a clear dead-link signal. Access restrictions, rate limits, server errors, and network errors are not called broken links. Check those manually before editing a community resource.

## Request limits and privacy

- Default concurrency is three workers; set --workers from 1 through 8.
- A short pause is applied before each check; --pause controls it.
- No cookies, credentials, authorization headers, or API keys are used.
- Query strings and URL fragments are removed from report output to avoid publishing signed links or tokens. The audit request still uses the input URL.
- A range GET reads no response body and closes the connection immediately.
- Run the audit when needed; do not schedule it as a frequent poll.

The tool is a triage aid, not proof that a resource is reachable to every user or that its contents are current.
Run it only on a catalog you trust: each URL is requested from your machine, and normal HTTP redirects are followed.

## Strict mode

The default command always writes a report and exits successfully when individual links fail. Add --strict to return a nonzero exit status only if at least one URL is clearly missing or malformed. Network and access errors never trigger strict failure, so temporary service problems do not masquerade as confirmed dead links.

## License

MIT. See LICENSE.
