---
name: scaffold-service
description: Scaffold a new service repository (service.yaml, README.md, Dockerfile) and register its HTTP endpoints. Use when someone asks to scaffold, bootstrap, create, or set up a new service, microservice, or API project.
---

# scaffold-service

A service needs three facts before anything can be written: its **name**,
its **owner**, and the **port** it listens on.

## Ask for what you were not given

Take whatever the request already supplies. For anything missing, ask the
user and wait for the answer before you write.

Do not invent a value and do not fall back on a plausible default. Port 8080
is a guess, not a decision, and a scaffolded file makes a guess look settled.

## Scaffold with scaffoldctl, never yourself

The files are written only by the CLI:

```
scaffoldctl init --name <name> --owner <owner> --port <port>
```

That one command writes all three files: `service.yaml`, `README.md`, and
`Dockerfile`.

**Write into the current directory.** Do not create a directory named
after the service and work inside it, and do not `cd` anywhere first. The
files belong where you started.

## Register endpoints one at a time

If the request also names HTTP endpoints, add each one after `init`:

```
scaffoldctl add-endpoint --method <method> --path <path>
```

Run it once per endpoint. It updates `service.yaml` and appends a row to
`docs/endpoints.md`.

## Never write these files yourself

Do not create or edit `service.yaml`, `README.md`, `Dockerfile`, or
`docs/endpoints.md` with your own file-writing tools, and do not write them
through a shell redirect. The CLI owns their format.
