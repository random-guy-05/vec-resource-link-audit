# Community contribution submission

- **Kind:** build
- **Title:** VEC Resource Link Audit — conservative checker for shared community links
- **Public link:** https://github.com/random-guy-05/vec-resource-link-audit
- **What it is, and who it helps:** A standard-library CLI that audits public URLs in a JSON resource catalog and distinguishes clear 404/410 responses from access restrictions, rate limits, server errors, and network failures. It uses low concurrency, makes no authenticated requests, avoids crawling, and redacts query strings in reports. It helps maintainers keep the community resource directory useful without falsely labeling bot-blocked links as broken.
- **How someone else runs it:** Run python resource_link_audit.py catalog.json --out link-audit. For alternate JSON layouts, specify --items-key and --url-key. Review link-audit.md, CSV, or JSON manually before changing the catalog.
- **Credit:** Arnav Mana
