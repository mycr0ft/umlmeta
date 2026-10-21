# Releasing to PyPI

`umlmeta` publishes with **trusted publishing** (OIDC): the GitHub Actions
workflow gets a short-lived token from PyPI, and no API token is stored in the
repository.

## One-time setup (PyPI side)

The project name has to exist on PyPI and have a trusted publisher that
matches this repository. Do this once, from your PyPI account:

1. **Create the project.** <https://pypi.org/manage/account/publishing/> →
   *Publishing* → *Add a new project* → `umlmeta`. (PyPI creates a pending
   project; the first upload finalises it.)
2. **Add the trusted publisher.** On the `umlmeta` *Manage* page →
   *Publishing* → *Add a new publisher* → *GitHub*:
   - Owner: `mycr0ft`
   - Repository: `umlmeta`
   - Workflow name: `python-publish.yml`
   - Environment name: `pypi`

   The environment `pypi` already exists on the GitHub repository
   (created with the repository); it must match exactly.

   The claims the workflow sends are printed in the failed publish run's log,
   so you can copy them from there if you want to double-check.

3. **Publish.** Create the GitHub release; the `Upload Python Package`
   workflow fires on `release: published` and uploads the distributions.

## What the workflow does

`.github/workflows/python-publish.yml`:

- builds an sdist and a wheel with `python -m build`,
- publishes them with `pypa/gh-action-pypi-publish@release/v1` using the
  `pypi` GitHub environment and OIDC.

## Releasing a new version

```sh
# bump the version in pyproject.toml and src/umlmeta/__init__.py (__version__)
# update CHANGELOG.md
git commit -am "v0.X.Y: ..."
git tag -a v0.X.Y -m "v0.X.Y: ..."
git push origin master && git push origin v0.X.Y
gh release create v0.X.Y --title "v0.X.Y" --notes "..."
```

## Checking what happened

```sh
gh run list -R mycr0ft/umlmeta --limit 5
gh run view <id> -R mycr0ft/umlmeta --log-failed
curl -s https://pypi.org/pypi/umlmeta/json | python3 -m json.tool | head -20
```

## If the publish fails with `invalid-publisher`

That means PyPI has no trusted publisher matching the claims. The claims are
in the run log. The usual causes:

- the repository name in the PyPI publisher entry is `uml2py` rather than
  `umlmeta` (the repository was renamed),
- the workflow name does not match `python-publish.yml`,
- the environment name does not match `pypi`.
