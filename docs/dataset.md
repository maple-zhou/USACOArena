# Dataset Deployment

This repository still expects the public dataset release to be unpacked directly under the repository root, but its role has changed in the Hydro-based release.

Released local resource dataset:

- `https://1drv.ms/u/c/1ef7b7bac0da57e6/IQCzXH4s4Ab7RJiSkpzbkO5eAdwrEzRBLW05RTlQyWknkLo?e=hSjB5X`

In this version:

- official problem storage, hidden tests, and judging are owned by Hydro
- the repository dataset is primarily used for hint corpora, textbook material, and guide content

## 1. Required Layout

After extracting the released archive, the repository should contain:

```text
dataset/
  corpuses/
    cpbook_v2.json
    USACO_strategy.json
  datasets/
    USACO_guide.json
    usaco_2025_dict.json  # optional compatibility metadata
```

## 2. Why These Files Matter

- `dataset/datasets/USACO_guide.json`: guide / tutorial content used by hint flows
- `dataset/corpuses/cpbook_v2.json`: textbook corpus used by hint flows
- `dataset/corpuses/USACO_strategy.json`: competition strategy hint corpus
- `dataset/datasets/usaco_2025_dict.json`: optional legacy compatibility metadata retained for release completeness

The formal contest problem library is no longer loaded from a local `dataset/datasets/usaco_2025/` tree. It is served from Hydro after the released `usacoarena_hydro_problemset_normalized.zip` archive is imported. See `docs/oj.md`.

## 3. Validation Commands

```bash
test -f dataset/datasets/USACO_guide.json
test -f dataset/corpuses/cpbook_v2.json
test -f dataset/corpuses/USACO_strategy.json
```

Optional compatibility checks:

```bash
test -f dataset/datasets/usaco_2025_dict.json
```

Inspect a sample of the extracted files:

```bash
find dataset -maxdepth 3 -type f | sort | head -50
```

## 4. Server Integration

The default server config now leaves `problem_data_dir` empty and only relies on local dataset files for hint-related resources:

```json
{
  "data": {
    "problem_data_dir": "",
    "textbook_data_dir": "dataset/corpuses/cpbook_v2.json"
  }
}
```

This lives in `config/server_config.json`.

If your corpora are stored elsewhere, override the textbook path when starting the server:

```bash
uv run python -m usacoarena.main \
  --config config/server_config.json \
  --textbook-data-dir /abs/path/to/cpbook_v2.json
```

## 5. Hint-Related Data

The server still auto-loads:

- `dataset/datasets/USACO_guide.json`
- `dataset/corpuses/USACO_strategy.json`
- `dataset/corpuses/cpbook_v2.json`

Do not rename these files unless you also patch the corresponding loader code.

## 6. Release Recommendation

For public release:

1. publish the dataset archive for hint/textbook resources
2. publish the Hydro addon package separately
3. publish the normalized Hydro problemset zip separately

This keeps the main repository lightweight while making the Hydro-based deployment path explicit and reproducible.
