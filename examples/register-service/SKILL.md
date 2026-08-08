---
name: register-service
description: Register a deployed service with the shared gateway by writing a per-service intake file (services/<name>.yaml, keyed by tier) in the platform repository, appending its CODEOWNERS line, and opening the pull request. Use when someone asks to register a service with the gateway, to front a service through it, or types '/register-service'.
---

# Register a service with the gateway

The gateway routes a hostname to your service's backend. You register the
service by adding one file, `services/<name>.yaml`, plus a CODEOWNERS line, to
the platform repository. `registerctl` does the mechanics: it clones the
platform repo, writes both files, commits, pushes, and opens the pull request.
Your job is the judgment, which is the host, the owning team, and which tiers.

The gateway has three tiers. Your own environment names are your own, so
choosing a tier is a routing decision:

| Gateway tier | What you put there |
|---|---|
| `prod` | your production environment |
| `acc` | your pre-production environment (acceptance, staging) |
| `test` | any other non-production environment (dev, sandbox) |

Only `prod` is fixed. Below it, choose. Omit the tiers you do not use.

## 1. Collect the judgment

- **`--name`**: the service name, which is also the file basename.
- **`--host`**: the hostname clients use, such as `<name>.services.example.com`.
- **`--owner`**: the owning team handle, `@acme/<team>`. Repeat for more than one.
- **Which tiers**: `--test-project`, `--acc-project`, `--prod-project`, each
  naming the project that hosts that tier's backend. Pass only the tiers you
  front. Omitting a tier means leaving the flag off: passing it with an empty
  value is refused rather than read as an omission.

`--region` defaults to `eu-west-1` and names the region in the generated
backend link. Leave it alone.

Ask the operator for anything you were not given. Do not guess a host, an
owner, or a tier: a wrong host routes someone else's traffic.

## 2. Run it

```bash
registerctl \
  --name checkout \
  --host checkout.services.example.com \
  --owner @acme/checkout \
  --test-project checkout-test-4417
```

`registerctl` is on your PATH. Do not write `services/<name>.yaml` yourself and
do not open the pull request with your own tools: the file's format and the
CODEOWNERS line are the CLI's to own, and a hand-written one passes review
while routing nothing.

The backend link is fully determined by the project, the region, and the name,
so there is nothing to look up:

```
https://gateway.example.com/projects/<project>/regions/<region>/backends/<name>
```

Report the pull request URL it prints, and stop. Merging is the platform team's.
