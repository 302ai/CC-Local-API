from __future__ import annotations

import os
import re
import subprocess
from urllib.parse import unquote, urlparse

from fastapi import HTTPException


def validate_and_normalize_github_url(url: str) -> tuple[str, str | None, str | None]:
    """Validate and normalize a GitHub repository URL.

    Supports URLs with subpaths:
    - https://github.com/<owner>/<repo>
    - https://github.com/<owner>/<repo>.git
    - https://github.com/<owner>/<repo>/tree/<branch>/<path/to/folder>
    - https://github.com/<owner>/<repo>/blob/<branch>/<path/to/file>

    Returns:
        (normalized_repo_url, subpath, branch)
    """

    url = (url or "").strip().rstrip("/")
    if not url:
        raise HTTPException(status_code=400, detail="github_url is empty")

    url = unquote(url)

    # Strip trailing markdown file (e.g. SKILL.md)
    url = re.sub(r"/[^/]+\.md$", "", url)

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="github_url must be http(s)")

    if parsed.netloc.lower() != "github.com":
        raise HTTPException(status_code=400, detail="Only github.com repositories are allowed")

    path = parsed.path.strip("/")

    # owner/repo and optional /tree|blob/branch/subpath
    m = re.match(
        r"^([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?(?:/(?:tree|blob)/([^/]+)(?:/(.+))?)?$",
        path,
    )
    if not m:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid github_url format, expected https://github.com/<owner>/<repo> "
                "or https://github.com/<owner>/<repo>/tree/<branch>/<path>"
            ),
        )

    owner, repo = m.group(1), m.group(2)
    branch = m.group(3)
    subpath = m.group(4)

    if subpath:
        subpath = subpath.rstrip("/")

    normalized_url = f"https://github.com/{owner}/{repo}"
    return normalized_url, subpath, branch


def clone_github_repo(
    github_url: str,
    dest_dir: str,
    branch: str | None = None,
    sparse_path: str | None = None,
) -> None:
    """Clone a GitHub repository.

    Args:
        github_url: normalized repo URL (string).
        dest_dir: destination directory.
        branch: branch name.
        sparse_path: if set, use sparse checkout to only fetch this subpath.
    """

    if sparse_path:
        _sparse_clone(github_url, dest_dir, branch, sparse_path)
    else:
        _full_clone(github_url, dest_dir, branch)


def _full_clone(github_url: str, dest_dir: str, branch: str | None = None) -> None:
    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd += ["-b", branch]
    cmd += [github_url, dest_dir]

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        raise HTTPException(status_code=400, detail=f"Failed to clone github repo: {stderr or str(e)}")


def _sparse_clone(
    github_url: str,
    dest_dir: str,
    branch: str | None,
    sparse_path: str,
) -> None:
    """Sparse clone: only checkout the specified folder/file path."""

    try:
        subprocess.run(["git", "init", dest_dir], capture_output=True, text=True, check=True)

        subprocess.run(
            ["git", "-C", dest_dir, "remote", "add", "origin", github_url],
            capture_output=True,
            text=True,
            check=True,
        )

        subprocess.run(
            ["git", "-C", dest_dir, "config", "core.sparseCheckout", "true"],
            capture_output=True,
            text=True,
            check=True,
        )

        sparse_checkout_dir = os.path.join(dest_dir, ".git", "info")
        os.makedirs(sparse_checkout_dir, exist_ok=True)
        sparse_checkout_file = os.path.join(sparse_checkout_dir, "sparse-checkout")
        with open(sparse_checkout_file, "w", encoding="utf-8") as f:
            f.write(sparse_path.rstrip("/") + "/\n")

        pull_branch = branch or "main"
        result = subprocess.run(
            ["git", "-C", dest_dir, "pull", "--depth", "1", "origin", pull_branch],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0 and not branch:
            result = subprocess.run(
                ["git", "-C", dest_dir, "pull", "--depth", "1", "origin", "master"],
                capture_output=True,
                text=True,
            )

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise HTTPException(status_code=400, detail=f"Failed to clone github repo: {stderr or 'git pull failed'}")

    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        raise HTTPException(status_code=400, detail=f"Failed to clone github repo: {stderr or str(e)}")
