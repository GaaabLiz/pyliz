# ==============================================================================
#
#   _____  ______ _      ______           _____ ______
#  |  __ \|  ____| |    |  ____|   /\    / ____|  ____|
#  | |__) | |__  | |    | |__     /  \  | (___ | |__
#  |  _  /|  __| | |    |  __|   / /\ \  \___ \|  __|
#  | | \ \| |____| |____| |____ / ____ \ ____) | |____
#  |_|  \_\______|______|______/_/    \_\_____/|______|
#
#  Bump versions, tag releases, and prepare notes and artifacts.
# ==============================================================================

## bump-patch-beta      – Bump to next patch pre-release, e.g. 1.2.3 → 1.2.4b1
.PHONY: bump-patch-beta
bump-patch-beta:
	uv version --bump patch --bump beta

## bump-patch           – Bump the patch component, e.g. 1.2.3 → 1.2.4
.PHONY: bump-patch
bump-patch:
	uv version --bump patch

## bump-minor           – Bump the minor component, e.g. 1.2.3 → 1.3.0
.PHONY: bump-minor
bump-minor:
	uv version --bump minor

## bump-major           – Bump the major component, e.g. 1.2.3 → 2.0.0
.PHONY: bump-major
bump-major:
	uv version --bump major

# ── Internal helper ──────────────────────────────────────────────────────────
#
#  Shared recipe executed after every version bump target.
#  Steps:
#    1. Optionally patches the version string inside the Inno Setup .iss file.
#    2. Commits all staged changes with a "bump: vX.Y.Z" message.
#    3. Pull-rebases to incorporate remote changes, then pushes.
define _release_impl
	@set -eu; \
	VERSION=$$(uv version --short); \
	echo "Releasing version $$VERSION …"; \
	if [ -f "$(INNO_SETUP_FILE)" ]; then \
		echo "  Updating Inno Setup version …"; \
		$(SED_INPLACE) \
			"s/#define $(INNO_SETUP_VERSION_VARIABLE) \"[^\"]*\"/#define $(INNO_SETUP_VERSION_VARIABLE) \"$$VERSION\"/" \
			"$(INNO_SETUP_FILE)"; \
	fi; \
	git commit -am "bump: v$$VERSION"; \
	git pull --rebase; \
	git push
endef

define _tag_impl
	@set -eu; \
	VERSION=$$(uv version --short); \
	RELEASE_COMMIT=$$(git rev-parse HEAD); \
	git tag "v$$VERSION" "$$RELEASE_COMMIT"; \
	git push origin "refs/tags/v$$VERSION"
endef

## release-patch-beta   – bump-patch-beta + gen-project-module + commit & push
.PHONY: release-patch-beta

release-patch-beta:
	$(MAKE) --no-print-directory bump-patch-beta
	$(MAKE) --no-print-directory gen-project-module
	$(call _release_impl)

## release-patch        – bump-patch + gen-project-module + commit & push
.PHONY: release-patch

release-patch:
	$(MAKE) --no-print-directory bump-patch
	$(MAKE) --no-print-directory gen-project-module
	$(call _release_impl)

## release-minor        – bump-minor + gen-project-module + commit & push
.PHONY: release-minor

release-minor:
	$(MAKE) --no-print-directory bump-minor
	$(MAKE) --no-print-directory gen-project-module
	$(call _release_impl)

## release-major        – bump-major + gen-project-module + commit & push
.PHONY: release-major

release-major:
	$(MAKE) --no-print-directory bump-major
	$(MAKE) --no-print-directory gen-project-module
	$(call _release_impl)

## tag                  – Pull and publish the branch, then tag and push its current version
.PHONY: tag
tag:
	@set -eu; \
	git pull --rebase; \
	git push
	$(call _tag_impl)

## release-patch-beta-tag – release-patch-beta + tag
.PHONY: release-patch-beta-tag
release-patch-beta-tag: release-patch-beta
	$(call _tag_impl)

## release-patch-tag    – release-patch + tag
.PHONY: release-patch-tag
release-patch-tag: release-patch
	$(call _tag_impl)

## release-minor-tag    – release-minor + tag
.PHONY: release-minor-tag
release-minor-tag: release-minor
	$(call _tag_impl)

## release-major-tag    – release-major + tag
.PHONY: release-major-tag
release-major-tag: release-major
	$(call _tag_impl)

## ci-install-git-cliff   – Ensure git-cliff is available in CI
.PHONY: ci-install-git-cliff
ci-install-git-cliff:
	@echo "[ci-install-git-cliff] Installing git-cliff via uv tool"
	uv tool install git-cliff==$(CI_GIT_CLIFF_VERSION)

## ci-generate-release-notes – Generate latest release notes into CI_RELEASE_NOTES_FILE
.PHONY: ci-generate-release-notes
ci-generate-release-notes:
	@echo "[ci-generate-release-notes] Writing $(CI_RELEASE_NOTES_FILE)"
	uvx --from git-cliff==$(CI_GIT_CLIFF_VERSION) git-cliff --config $(CI_GIT_CLIFF_CONFIG) --latest --strip header > $(CI_RELEASE_NOTES_FILE)

## ci-build-release-package – Build distributions with this release's notes in PyPI metadata
.PHONY: ci-build-release-package
ci-build-release-package:
	@set -eu; \
	if [ ! -s "$(CI_RELEASE_NOTES_FILE)" ]; then \
		echo "Error: $(CI_RELEASE_NOTES_FILE) is missing or empty."; \
		exit 1; \
	fi; \
	README_BACKUP=$$(mktemp); \
	cp README.md "$$README_BACKUP"; \
	restore_readme() { cp "$$README_BACKUP" README.md; rm -f "$$README_BACKUP"; }; \
	trap restore_readme EXIT; \
	printf '\n\n## Release notes\n\n' >> README.md; \
	cat "$(CI_RELEASE_NOTES_FILE)" >> README.md; \
	$(MAKE) --no-print-directory build

## ci-generate-docs       – Generate project documentation for release automation
.PHONY: ci-generate-docs
ci-generate-docs:
	@echo "[ci-generate-docs] Generating docs/api/ for $(PYTHON_MAIN_PACKAGE)"
	$(MAKE) --no-print-directory docs

## ci-prepare-release-docs-branch – Start optional docs publication from the tagged commit
.PHONY: ci-prepare-release-docs-branch
ci-prepare-release-docs-branch:
	@set -eu; \
	if [ -z "$${GITHUB_REF_NAME:-}" ] || [ -z "$${GITHUB_SHA:-}" ]; then \
		echo "Error: release tag context is missing."; exit 1; \
	fi; \
	TARGET_BRANCH="$(RELEASE_TARGET_BRANCH)"; \
	PR_BRANCH="automation/release-updates-$$GITHUB_REF_NAME"; \
	git fetch origin "refs/heads/$$TARGET_BRANCH:refs/remotes/origin/$$TARGET_BRANCH"; \
	if ! git merge-base --is-ancestor "$$GITHUB_SHA" "origin/$$TARGET_BRANCH"; then \
		echo "Error: release commit $$GITHUB_SHA is not contained in origin/$$TARGET_BRANCH."; \
		exit 1; \
	fi; \
	git switch --create "$$PR_BRANCH" "$$GITHUB_SHA"

## ci-open-release-docs-pr – Open/update a PR for generated API documentation
.PHONY: ci-open-release-docs-pr
ci-open-release-docs-pr:
	@set -eu; \
	if [ -z "$${GITHUB_REF_NAME:-}" ] || [ -z "$${GITHUB_SHA:-}" ]; then \
		echo "Error: release tag context is missing."; exit 1; \
	fi; \
	if [ -z "$${GH_TOKEN:-}" ]; then \
		echo "Error: GH_TOKEN is not set."; exit 1; \
	fi; \
	TARGET_BRANCH="$(RELEASE_TARGET_BRANCH)"; \
	PR_BRANCH="automation/release-updates-$$GITHUB_REF_NAME"; \
	if [ "$$(git branch --show-current)" != "$$PR_BRANCH" ]; then \
		echo "Error: expected to run on branch $$PR_BRANCH."; exit 1; \
	fi; \
	git config user.name "github-actions[bot]"; \
	git config user.email "github-actions[bot]@users.noreply.github.com"; \
	if [ "$(CI_ENABLE_RELEASE_DOCS)" != "1" ]; then \
		echo "Error: CI_ENABLE_RELEASE_DOCS must be 1 to open a docs PR."; exit 1; \
	fi; \
	git add -A -- docs/api; \
	if git diff --cached --quiet; then \
		echo "No generated API documentation changes to publish."; exit 0; \
	fi; \
	git commit -m "docs: update generated API docs for $$GITHUB_REF_NAME"; \
	REMOTE_REF=$$(git ls-remote origin "refs/heads/$$PR_BRANCH"); \
	REMOTE_SHA=$${REMOTE_REF%%[[:space:]]*}; \
	if [ -n "$$REMOTE_SHA" ]; then \
		git push --force-with-lease="refs/heads/$$PR_BRANCH:$$REMOTE_SHA" origin "HEAD:refs/heads/$$PR_BRANCH"; \
	else \
		git push origin "HEAD:refs/heads/$$PR_BRANCH"; \
	fi; \
	PR_NUMBER=$$(GH_TOKEN="$$GH_TOKEN" gh pr list --repo "$$GITHUB_REPOSITORY" --head "$$PR_BRANCH" --state open --json number --jq '.[0].number // empty'); \
	if [ -n "$$PR_NUMBER" ]; then \
		GH_TOKEN="$$GH_TOKEN" gh pr edit "$$PR_NUMBER" --repo "$$GITHUB_REPOSITORY" \
			--title "docs: update generated API documentation for $$GITHUB_REF_NAME" \
			--body "Generated API documentation for release $$GITHUB_REF_NAME."; \
	else \
		GH_TOKEN="$$GH_TOKEN" gh pr create --repo "$$GITHUB_REPOSITORY" \
			--base "$$TARGET_BRANCH" --head "$$PR_BRANCH" \
			--title "docs: update generated API documentation for $$GITHUB_REF_NAME" \
			--body "Generated API documentation for release $$GITHUB_REF_NAME."; \
	fi

## ci-build-release-assets – Build release assets for the current runner OS with verbose diagnostics
.PHONY: ci-build-release-assets
ci-build-release-assets:
	@set -eu; \
	echo "[ci-build-release-assets] Runner OS=$(OS_NAME)"; \
	echo "[ci-build-release-assets] APPS_LIST=$(if $(strip $(APPS_LIST)),$(APPS_LIST),<empty>)"; \
	echo "[ci-build-release-assets] ENABLE_WINDOWS_INSTALLER=$(ENABLE_WINDOWS_INSTALLER)"; \
	if [ -n "$(strip $(APPS_LIST))" ]; then \
		$(MAKE) --no-print-directory gen-project-module; \
	fi; \
	if [ "$(OS_NAME)" = "windows" ] && [ "$(ENABLE_WINDOWS_INSTALLER)" = "1" ]; then \
		echo "[ci-build-release-assets] Building Windows installer because ENABLE_WINDOWS_INSTALLER=1"; \
		$(MAKE) --no-print-directory install-inno; \
		$(MAKE) --no-print-directory build-exe-onefile; \
		$(MAKE) --no-print-directory installer; \
	elif [ -n "$(strip $(APPS_LIST))" ]; then \
		echo "[ci-build-release-assets] APPS_LIST is set -> building onefile executables"; \
		$(MAKE) --no-print-directory build-exe-onefile; \
	else \
		echo "[ci-build-release-assets] No platform assets configured; package distributions are built once by CI."; \
	fi; \
	if [ -n "$(call builds_macos_bundle,$(OS_NAME))" ] && [ -n "$(strip $(APPS_LIST))" ]; then \
		echo "[ci-build-release-assets] Archiving windowed macOS app bundles for release"; \
		$(foreach app,$(APPS_LIST),\
			APP_DIR="$(call app_bundle_path,$(app))"; \
			if [ ! -d "$$APP_DIR" ]; then echo "Error: expected macOS app bundle $$APP_DIR was not built."; exit 1; fi; \
			ditto -c -k --sequesterRsrc --keepParent "$$APP_DIR" "$$APP_DIR.zip"; \
			rm -rf "$$APP_DIR"; \
		) \
	fi; \
	$(MAKE) --no-print-directory ci-list-build-artifacts

expected_release_files = $(foreach app,$(APPS_LIST),"$(call app_release_path,$(app),$(OS_NAME))")
ifeq ($(OS_NAME),windows)
ifeq ($(ENABLE_WINDOWS_INSTALLER),1)
expected_release_files += "$(CI_CONFIG_INSTALLER_PATH)"
endif
endif

ci-verify-release-artifacts ci-stage-release-artifacts: export TEMPLATE_SETTING_RELEASE_ARTIFACTS = $(RELEASE_ARTIFACTS)

## ci-verify-release-artifacts – Verify each required app and installer is included in RELEASE_ARTIFACTS
.PHONY: ci-verify-release-artifacts
ci-verify-release-artifacts:
	@uv run --no-sync python .mk/scripts.py release-artifacts -- $(expected_release_files)

## ci-stage-release-artifacts – Verify and stage native files for GitHub Actions upload
.PHONY: ci-stage-release-artifacts
ci-stage-release-artifacts:
	@uv run --no-sync python .mk/scripts.py release-artifacts --stage -- $(expected_release_files)

## ci-verify-release-version – Fail unless the current v-tag matches the project version
.PHONY: ci-verify-release-version
ci-verify-release-version:
	@if [ "$$GITHUB_REF_TYPE" != "tag" ] || [ -z "$$GITHUB_REF_NAME" ]; then \
		echo "Error: release version verification requires a pushed tag."; \
		exit 1; \
	fi; \
	VERSION=$$(uv version --short); \
	TAG_VERSION=$${GITHUB_REF_NAME#v}; \
	if [ "$$VERSION" != "$$TAG_VERSION" ]; then \
		echo "Error: tag version '$$TAG_VERSION' does not match pyproject version '$$VERSION'."; \
		exit 1; \
	fi; \
	echo "Verified release version $$VERSION."

## ci-verify-release-target-branch – Require the release tag to be on RELEASE_TARGET_BRANCH
.PHONY: ci-verify-release-target-branch
ci-verify-release-target-branch:
	@set -eu; \
	if [ -z "$${GITHUB_SHA:-}" ]; then \
		echo "Error: release commit SHA is missing."; \
		exit 1; \
	fi; \
	TARGET_BRANCH="$(RELEASE_TARGET_BRANCH)"; \
	if ! git show-ref --verify --quiet "refs/remotes/origin/$$TARGET_BRANCH"; then \
		echo "Error: target branch $$TARGET_BRANCH was not fetched."; \
		exit 1; \
	fi; \
	if ! git merge-base --is-ancestor "$$GITHUB_SHA" "origin/$$TARGET_BRANCH"; then \
		echo "Error: release commit $$GITHUB_SHA is not contained in origin/$$TARGET_BRANCH."; \
		exit 1; \
	fi; \
	echo "Verified release commit $$GITHUB_SHA is on $$TARGET_BRANCH."

## ci-release-branch      – Print RELEASE_TARGET_BRANCH
.PHONY: ci-release-branch
ci-release-branch:
	@echo $(RELEASE_TARGET_BRANCH)

## ci-windows-installer   – Print ENABLE_WINDOWS_INSTALLER (1 or 0)
.PHONY: ci-windows-installer
ci-windows-installer:
	@echo $(ENABLE_WINDOWS_INSTALLER)

## ci-release-artifacts   – Print each RELEASE_ARTIFACTS glob pattern on its own line
.PHONY: ci-release-artifacts
ci-release-artifacts:
	@set -f; for pattern in $(RELEASE_ARTIFACTS); do printf '%s\n' "$$pattern"; done

## ci-print-release-target-branch – Legacy alias of ci-release-branch
.PHONY: ci-print-release-target-branch
ci-print-release-target-branch: ci-release-branch

## ci-print-windows-installer-enabled – Legacy alias of ci-windows-installer
.PHONY: ci-print-windows-installer-enabled
ci-print-windows-installer-enabled: ci-windows-installer

## ci-print-release-artifacts – Legacy alias of ci-release-artifacts
.PHONY: ci-print-release-artifacts
ci-print-release-artifacts: ci-release-artifacts
