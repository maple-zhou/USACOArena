# USACOArena Hydro Addon

This directory is the Hydro addon source shipped with `USACOArena_hydro`.

## What It Does

The addon adds a machine-facing API layer on top of Hydro so that USACOArena can:

- list available problems
- resolve paper-facing long problem IDs via tags
- fetch problem metadata and public samples
- submit official solutions
- poll records
- run Hydro-backed pretests on custom input

## Install

From the Hydro host:

```bash
hydrooj addon add /path/to/USACOArena/hydro_plugin_usacoarena
```

Then restart Hydro.

## Required Hydro Settings

- `usacoarenaHydro.apiBase`
- `usacoarenaHydro.apiToken`

Recommended values:

```text
usacoarenaHydro.apiBase=/usacoarena/api
usacoarenaHydro.apiToken=<strong-random-token>
```

## Release Packaging

This addon is intentionally kept as a standalone directory so it can be archived and released independently from the main repository. A simple release artifact can be created by packaging this folder as-is.
