#!/data/data/com.termux/files/usr/bin/bash
set -e

REPO="https://github.com/kentcacho090-netizen/autoc.git"
BRANCH="smart-automation-foundation"
DIR="${HOME}/autoc"

if [ -d "${DIR}/.git" ]; then
  echo "[AutoC] Repository found: ${DIR}"
  git -C "${DIR}" remote set-url origin "${REPO}" 2>/dev/null || true
  git -C "${DIR}" fetch --prune origin "${BRANCH}"
  git -C "${DIR}" checkout "${BRANCH}"
  git -C "${DIR}" merge --ff-only "origin/${BRANCH}"
else
  echo "[AutoC] Local repository not found; cloning ${BRANCH}..."
  rm -rf "${DIR}.repair"
  git clone --branch "${BRANCH}" --single-branch "${REPO}" "${DIR}.repair"
  if [ -d "${DIR}" ]; then
    mv "${DIR}" "${DIR}.old"
  fi
  mv "${DIR}.repair" "${DIR}"
fi

echo "[AutoC] Sync complete."
git -C "${DIR}" status --short --branch
