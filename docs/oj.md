# Hydro Deployment and Usage

USACOArena now uses [Hydro](https://github.com/hydro-dev/Hydro) as the judge, problem-management system, and visualization frontend. This repository publishes a Hydro addon source directory plus a released addon package and a released Hydro problemset zip for deployment.

## Released Artifacts

- Hydro addon package: `https://1drv.ms/u/c/1ef7b7bac0da57e6/IQDLk840K7kKQIcantsdu2VsAXUUVQsuCxqbkYO0L0sJy0U?e=L6gXuD`
- Hydro problemset zip: `https://1drv.ms/u/c/1ef7b7bac0da57e6/IQByRn0PSlhgQYS1kwPjbS2BAcB17vagQfPh1jINdc-MZEo?e=dBnHiH`

The recommended open-source deployment path is to download these two artifacts directly instead of rebuilding them locally.

## 1. Clone and Install Hydro

Clone the official Hydro repository:

```bash
git clone https://github.com/hydro-dev/Hydro.git ../Hydro
cd ../Hydro
```

Install and start Hydro using the official setup flow documented by Hydro itself. A common one-line installation entry is:

```bash
LANG=zh . <(curl https://hydro.ac/setup.sh)
```

After Hydro is up, confirm that the web UI is reachable. A typical local deployment listens on:

```text
http://127.0.0.1:8888
```

## 2. Install the USACOArena Hydro Addon

Download and extract the released addon package on the Hydro machine, then register the extracted addon directory:

```bash
tar -xzf usacoarena_hydro_plugin_v0.1.0.tar.gz
hydrooj addon add /path/to/usacoarena_hydro_plugin_v0.1.0/hydro_plugin_usacoarena
```

Restart Hydro after adding the addon so the route table and settings schema are reloaded.

The addon exports the following machine-facing endpoints under a configurable base path:

- `GET /usacoarena/api/health`
- `GET /usacoarena/api/problems`
- `GET /usacoarena/api/problems/:problemId`
- `GET /usacoarena/api/resolve?problem_id=...`
- `POST /usacoarena/api/submissions`
- `GET /usacoarena/api/records/:recordId`
- `POST /usacoarena/api/pretest`

## 3. Configure Addon Settings

The addon registers two Hydro system settings:

- `usacoarenaHydro.apiBase`
- `usacoarenaHydro.apiToken`

Recommended values:

```text
usacoarenaHydro.apiBase=/usacoarena/api
usacoarenaHydro.apiToken=<strong-random-token>
```

If you prefer not to require a token on a trusted local deployment, leave `apiToken` empty. For any shared or exposed environment, set a token.

USACOArena should then use the same values in `config/server_config.json`:

```json
{
  "hydro": {
    "base_url": "http://127.0.0.1:8888",
    "api_base": "/usacoarena/api",
    "api_token": "<same-token-or-empty>"
  }
}
```

## 4. Import the Released Problemset Zip

The released Hydro problemset archive is already normalized for USACOArena. It preserves Hydro-native structure and includes the `usacoarena-problem-id:<directory_name>` tags needed to map Hydro-native problems back to paper-facing long IDs such as `1452_platinum_all_pairs_similarity`.

## 5. Import the Problemset into Hydro

Use the Hydro admin UI to import the normalized zip into the target domain.

Recommended import procedure:

1. Create or choose the Hydro domain that will host the USACOArena problemset.
2. Open Hydro's problem import page.
3. Upload the released `usacoarena_hydro_problemset_normalized.zip`.
4. Wait for the import task to finish.
5. Verify that several known problems can be opened in the UI.

After import, test alias resolution through the addon:

```bash
curl -H "Authorization: Bearer <token>" \
  "http://127.0.0.1:8888/usacoarena/api/resolve?problem_id=1452_platinum_all_pairs_similarity"
```

You should receive JSON that includes the resolved Hydro problem doc.

## 6. Wire Hydro into USACOArena

Start the USACOArena server against Hydro:

```bash
cd /path/to/USACOArena_hydro
uv run python -m usacoarena.main \
  --config config/server_config.json \
  --host 0.0.0.0 \
  --port 5000 \
  --hydro-base-url http://127.0.0.1:8888 \
  --hydro-api-token "<token>"
```

Then verify both sides:

```bash
curl http://127.0.0.1:5000/api/system/oj-status
curl http://127.0.0.1:5000/api/problem-library
```

The first endpoint checks Hydro connectivity. The second lists problems through the Hydro-backed loader.

## 7. Debug One Submission Against Hydro

You can still run single-problem or ad-hoc checks through USACOArena, but they now route through Hydro:

```bash
uv run python scripts/run_solo_agent.py \
  --problem-id 1452_platinum_all_pairs_similarity \
  --agent-config config/paper/competitors/solo_gpt5.json \
  --oj-endpoint http://127.0.0.1:8888
```

In this Hydro-based release, `--oj-endpoint` is retained only as a compatibility alias for the Hydro base URL.

## 8. Release Boundary

The intended open-source release boundary is:

- `USACOArena_hydro` repository: competition framework, docs, addon source, normalization tooling
- external addon package: released `usacoarena_hydro_plugin_v0.1.0.tar.gz`
- external Hydro problemset zip: released `usacoarena_hydro_problemset_normalized.zip`
- Hydro core: cloned separately from the official upstream repository

This keeps the published USACOArena repository lightweight while still providing a reproducible Hydro integration path.
