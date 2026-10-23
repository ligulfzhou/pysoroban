# Releasing to PyPI

The package name is `pysoroban-compiler`. Publishing is a maintainer action.
This repository does not upload a release by itself. This release is `0.19.0a3`.

`.github/workflows/publish.yml` builds an sdist and a wheel when a GitHub
Release is published, then uploads them with
[PyPI trusted publishing](https://docs.pypi.org/trusted-publishers/). The
publish job requests an OIDC token for the GitHub environment named `pypi`.
It does not read a PyPI API token.

## One-time setup

1. On PyPI, open the `pysoroban-compiler` project and add a trusted publisher
   (or a pending publisher if the project is not created yet):

   - Owner: `ligulfzhou`
   - Repository: `pysoroban`
   - Workflow filename: `publish.yml`
   - Environment name: `pypi`

2. On GitHub, open Settings → Environments and create an environment named
   `pypi`. The name has to match the workflow. Protection rules are optional.
   Do not add a `PYPI_API_TOKEN` secret.

## Build locally

From a clean checkout of the commit you intend to tag:

```bash
python -m pip install build
export SOURCE_DATE_EPOCH="$(git log -1 --pretty=%ct)"
python -m build
python scripts/normalize_sdist.py dist/*.tar.gz
```

Run that twice. The wheel is reproducible from `SOURCE_DATE_EPOCH` alone.
The sdist's gzip header and tar timestamps still follow the clock, so
`scripts/normalize_sdist.py` rewrites them to the same epoch. After that
pass, both files in `dist/` must have the same SHA-256 as the previous run.
The workflow sets the same epoch from the tagged commit and runs the same
normalizer.

## Publish

1. Merge the release commit to `main`. The version in `pyproject.toml` is the
   version that will be uploaded.
2. Push a tag whose name is `v` plus that version, for example `v0.19.0a3`.
3. Publish a GitHub Release from that tag. The workflow starts on
   `release: published`. Pushing the tag alone does not upload to PyPI.
4. Confirm the new files on
   <https://pypi.org/project/pysoroban-compiler/>.

The workflow refuses a release whose tag, without a leading `v`, differs from
`project.version`. A manual run of the workflow builds the distributions and
does not publish them.
