# ==============================================================================
#
#   _____  _    _ ____  _      _____  _____ _    _
#  |  __ \| |  | |  _ \| |    |_   _|/ ____| |  | |
#  | |__) | |  | | |_) | |      | | | (___ | |__| |
#  |  ___/| |  | |  _ <| |      | |  \___ \|  __  |
#  | |    | |__| | |_) | |____ _| |_ ____) | |  | |
#  |_|     \____/|____/|______|_____|_____/|_|  |_|
#
#  Build and publish packages and manifests for configured destinations.
# ==============================================================================

## ci-publish-pypi        – Publish package artifacts to PyPI (requires trusted publishing)
.PHONY: ci-publish-pypi
ci-publish-pypi:
	uv publish

## ci-export-docker-tag   – Export Docker tag (release tag or pyproject version) to $GITHUB_OUTPUT
.PHONY: ci-export-docker-tag
ci-export-docker-tag:
	@if [ -z "$$GITHUB_OUTPUT" ]; then \
		echo "Error: GITHUB_OUTPUT is not set."; \
		exit 1; \
	fi
	@set -e; \
	TAG="$$GITHUB_REF_NAME"; \
	if [ "$$GITHUB_REF_TYPE" != "tag" ] || [ -z "$$TAG" ]; then \
		TAG=$$(python3 .mk/scripts.py project-version "$(FILE_PROJECT_TOML)"); \
	fi; \
	echo "docker_image_tag=$$TAG" >> "$$GITHUB_OUTPUT"; \
	echo "Resolved Docker image tag: $$TAG"

## ci-docker-login        – Login to Docker Hub using DOCKERHUB_USERNAME and DOCKERHUB_TOKEN
.PHONY: ci-docker-login
ci-docker-login:
	@if [ -z "$$DOCKERHUB_USERNAME" ] || [ -z "$$DOCKERHUB_TOKEN" ]; then \
		echo "Error: DOCKERHUB_USERNAME and DOCKERHUB_TOKEN must be set."; \
		exit 1; \
	fi
	@echo "$$DOCKERHUB_TOKEN" | docker login --username "$$DOCKERHUB_USERNAME" --password-stdin

## ci-docker-build        – Build Docker image for DOCKER_IMAGE_TAG using project.mk Docker settings
.PHONY: ci-docker-build
ci-docker-build:
	@if [ -z "$$DOCKER_IMAGE_TAG" ]; then \
		echo "Error: DOCKER_IMAGE_TAG is not set."; \
		exit 1; \
	fi
	@if [ ! -f "$(CI_DOCKERFILE)" ]; then \
		echo "Error: Dockerfile not found at $(CI_DOCKERFILE)."; \
		exit 1; \
	fi
	docker build \
		-f "$(CI_DOCKERFILE)" \
		--build-arg PYTHON_VERSION="$(CI_DOCKER_PYTHON_VERSION)" \
		--build-arg UV_VERSION="$(CI_DOCKER_UV_VERSION)" \
		--build-arg PYTHON_MAIN_PACKAGE="$(PYTHON_MAIN_PACKAGE)" \
		--build-arg CI_DOCKER_ENTRYPOINT="$(CI_DOCKER_ENTRYPOINT)" \
		-t "$(CI_DOCKERHUB_IMAGE):$$DOCKER_IMAGE_TAG" \
		"$(CI_DOCKER_BUILD_CONTEXT)"

## ci-publish-dockerhub   – Build and push Docker image (and optional latest tag) to Docker Hub
.PHONY: ci-publish-dockerhub
ci-publish-dockerhub: ci-docker-build
	@docker push "$(CI_DOCKERHUB_IMAGE):$$DOCKER_IMAGE_TAG"
	@set -eu; \
	if [ "$(CI_DOCKER_PUSH_LATEST)" = "1" ]; then \
		docker tag "$(CI_DOCKERHUB_IMAGE):$$DOCKER_IMAGE_TAG" "$(CI_DOCKERHUB_IMAGE):latest"; \
		docker push "$(CI_DOCKERHUB_IMAGE):latest"; \
	fi

## ci-build-chocolatey-assets – Build Windows artefacts consumed by the Chocolatey package
## ci-build-winget-assets  – Build Windows artefacts consumed by the WinGet manifests
.PHONY: ci-build-chocolatey-assets ci-build-winget-assets
ci-build-chocolatey-assets ci-build-winget-assets: ci-build-release-assets

## ci-pack-chocolatey     – Generate nuspec/install script and build a .nupkg in dist/chocolatey/
.PHONY: ci-pack-chocolatey
ci-pack-chocolatey:
	@set -eu; \
	VERSION=$$(uv version --short); \
	INSTALLER_URL=$$(uv run python -c 'import sys; print(sys.argv[1].replace("{version}", sys.argv[2]))' "$(CI_CHOCOLATEY_INSTALLER_URL)" "$$VERSION"); \
	mkdir -p .chocolatey/tools dist/chocolatey; \
	printf '%s\n' \
		'<?xml version="1.0" encoding="utf-8"?>' \
		'<package xmlns="http://schemas.microsoft.com/packaging/2015/06/nuspec.xsd">' \
		'  <metadata>' \
		'    <id>$(CI_CHOCOLATEY_PACKAGE_ID)</id>' \
		'    <version>'"$$VERSION"'</version>' \
		'    <title>$(CI_CHOCOLATEY_PACKAGE_TITLE)</title>' \
		'    <authors>$(CI_CHOCOLATEY_AUTHORS)</authors>' \
		'    <projectUrl>$(CI_CHOCOLATEY_PROJECT_URL)</projectUrl>' \
		'    <licenseUrl>$(CI_CHOCOLATEY_LICENSE_URL)</licenseUrl>' \
		'    <tags>$(CI_CHOCOLATEY_TAGS)</tags>' \
		'    <summary>$(CI_CHOCOLATEY_SUMMARY)</summary>' \
		'    <description>$(CI_CHOCOLATEY_DESCRIPTION)</description>' \
		'  </metadata>' \
		'  <files>' \
		'    <file src="tools\\**" target="tools" />' \
		'  </files>' \
		'</package>' > .chocolatey/$(CI_CHOCOLATEY_PACKAGE_ID).nuspec; \
	printf '%s\n' \
		'$$ErrorActionPreference = "Stop"' \
		'$$packageArgs = @{' \
		'  packageName    = "$(CI_CHOCOLATEY_PACKAGE_ID)"' \
		'  fileType       = "EXE"' \
		'  url64bit       = "'"$$INSTALLER_URL"'"' \
		'  silentArgs     = "$(CI_CHOCOLATEY_SILENT_ARGS)"' \
		'  validExitCodes = @($(CI_CHOCOLATEY_VALID_EXIT_CODES))' \
		'}' \
		'Install-ChocolateyPackage @packageArgs' > .chocolatey/tools/chocolateyinstall.ps1; \
	choco pack .chocolatey/$(CI_CHOCOLATEY_PACKAGE_ID).nuspec --outputdirectory dist/chocolatey --yes --limit-output

## ci-publish-chocolatey – Push generated .nupkg to Chocolatey source (requires CHOCOLATEY_API_KEY)
.PHONY: ci-publish-chocolatey
ci-publish-chocolatey:
	@if [ -z "$$CHOCOLATEY_API_KEY" ]; then \
		echo "Error: CHOCOLATEY_API_KEY is not set."; \
		exit 1; \
	fi
	@PACKAGE_FILE=$$(ls -1 dist/chocolatey/*.nupkg 2>/dev/null | grep -v '\\.symbols\\.nupkg$$' | head -n 1); \
	if [ -z "$$PACKAGE_FILE" ]; then \
		echo "Error: no .nupkg file found in dist/chocolatey. Run make ci-pack-chocolatey first."; \
		exit 1; \
	fi; \
	echo "Publishing $$PACKAGE_FILE to $(CI_CHOCOLATEY_SOURCE_URL)"; \
	choco push "$$PACKAGE_FILE" --source "$(CI_CHOCOLATEY_SOURCE_URL)" --api-key "$$CHOCOLATEY_API_KEY" --yes --limit-output

## ci-generate-homebrew-formula – Generate a Homebrew formula with the published PyPI source checksum
.PHONY: ci-generate-homebrew-formula
ci-generate-homebrew-formula:
	@set -eu; \
	VERSION=$$(uv version --short); \
	uv run python .mk/scripts.py gen-homebrew-formula \
		"$(FILE_PROJECT_TOML)" \
		"dist/homebrew/$(CI_HOMEBREW_FORMULA_NAME).rb" \
		"$$VERSION" \
		"$(CI_HOMEBREW_FORMULA_NAME)" \
		"$(CI_HOMEBREW_DESCRIPTION)" \
		"$(CI_HOMEBREW_HOMEPAGE)" \
		"$(CI_HOMEBREW_LICENSE)" \
		"$(CI_PYTHON_VERSION)" \
		"$(CI_HOMEBREW_EXECUTABLE)" $(if $(strip $(CI_HOMEBREW_RESOURCES_FILE)),--resources-file "$(CI_HOMEBREW_RESOURCES_FILE)",)

## ci-publish-homebrew – Push generated formula to the Homebrew tap repository
.PHONY: ci-publish-homebrew
ci-publish-homebrew:
	@set -eu; \
	if [ -z "$${HOMEBREW_TAP_TOKEN:-}" ]; then \
		echo "Error: HOMEBREW_TAP_TOKEN is not set."; exit 1; \
	fi; \
	FORMULA="dist/homebrew/$(CI_HOMEBREW_FORMULA_NAME).rb"; \
	if [ ! -f "$$FORMULA" ]; then \
		echo "Error: $$FORMULA not found. Run make ci-generate-homebrew-formula first."; exit 1; \
	fi; \
	VERSION=$$(uv version --short); \
	CLONE_DIR=$$(mktemp -d); \
	trap 'rm -rf "$$CLONE_DIR"' EXIT; \
	echo "[ci-publish-homebrew] Cloning tap $(CI_HOMEBREW_TAP_REPO)"; \
	git clone "https://x-access-token:$$HOMEBREW_TAP_TOKEN@github.com/$(CI_HOMEBREW_TAP_REPO).git" "$$CLONE_DIR"; \
	mkdir -p "$$CLONE_DIR/Formula"; \
	cp "$$FORMULA" "$$CLONE_DIR/Formula/$(CI_HOMEBREW_FORMULA_NAME).rb"; \
	cd "$$CLONE_DIR"; \
	git config user.name "github-actions[bot]"; \
	git config user.email "github-actions[bot]@users.noreply.github.com"; \
	git add "Formula/$(CI_HOMEBREW_FORMULA_NAME).rb"; \
	if git diff --cached --quiet; then \
		echo "[ci-publish-homebrew] Formula is already current for version $$VERSION."; exit 0; \
	fi; \
	git commit -m "$(CI_HOMEBREW_FORMULA_NAME): update to $$VERSION"; \
	git push; \
	echo "[ci-publish-homebrew] Formula pushed to $(CI_HOMEBREW_TAP_REPO)"

winget_manifest_vars := \
	CI_WINGET_HOMEPAGE \
	CI_WINGET_INSTALLER_ARCHITECTURE \
	CI_WINGET_INSTALLER_FILE \
	CI_WINGET_INSTALLER_TYPE \
	CI_WINGET_INSTALLER_URL \
	CI_WINGET_LICENSE \
	CI_WINGET_LICENSE_URL \
	CI_WINGET_MANIFEST_VERSION \
	CI_WINGET_PACKAGE_IDENTIFIER \
	CI_WINGET_PACKAGE_LOCALE \
	CI_WINGET_PACKAGE_NAME \
	CI_WINGET_PUBLISHER \
	CI_WINGET_SHORT_DESCRIPTION \
	CI_WINGET_TAGS

$(foreach var,$(winget_manifest_vars),\
	$(eval ci-generate-winget-manifests: export TEMPLATE_SETTING_$(var) = $$($(var))))

winget_manifest_path = uv run --no-sync python .mk/scripts.py winget-manifest-path "$(CI_WINGET_PACKAGE_IDENTIFIER)" "$$VERSION"

## ci-generate-winget-manifests – Generate WinGet version/defaultLocale/installer manifests
.PHONY: ci-generate-winget-manifests
ci-generate-winget-manifests:
	@set -eu; \
	VERSION=$$(uv version --short); \
	uv run python .mk/scripts.py gen-winget-manifests "$$VERSION"

## ci-validate-winget-manifests – Validate generated WinGet manifests when winget is available
.PHONY: ci-validate-winget-manifests
ci-validate-winget-manifests:
	@set -eu; \
	VERSION=$$(uv version --short); \
	MANIFEST_DIR=$$($(winget_manifest_path) --local); \
	if [ ! -d "$$MANIFEST_DIR" ]; then \
		echo "Error: $$MANIFEST_DIR not found. Run make ci-generate-winget-manifests first."; \
		exit 1; \
	fi; \
	WINGET_BIN=$$(command -v winget 2>/dev/null || command -v winget.exe 2>/dev/null || true); \
	if [ -z "$$WINGET_BIN" ]; then \
		echo "[ci-validate-winget-manifests] winget is not available on this runner -> skipping validation."; \
	else \
		echo "[ci-validate-winget-manifests] Validating $$MANIFEST_DIR"; \
		"$$WINGET_BIN" validate "$$MANIFEST_DIR"; \
	fi

## ci-publish-winget – Push generated manifests to your winget-pkgs fork and open/update a PR
.PHONY: ci-publish-winget
ci-publish-winget:
	@set -eu; \
	if [ -z "$${WINGET_GITHUB_TOKEN:-}" ]; then \
		echo "Error: WINGET_GITHUB_TOKEN is not set."; exit 1; \
	fi; \
	VERSION=$$(uv version --short); \
	SOURCE_DIR="$$PWD/$$($(winget_manifest_path) --local)"; \
	TARGET_PATH=$$($(winget_manifest_path)); \
	BRANCH=$$(uv run python -c 'import re, sys; slug = re.sub(r"[^A-Za-z0-9]+", "-", sys.argv[1]).strip("-").lower(); print(f"winget-{slug}-{sys.argv[2]}")' "$(CI_WINGET_PACKAGE_IDENTIFIER)" "$$VERSION"); \
	FORK_REPO="$(CI_WINGET_FORK_REPO)"; \
	FORK_OWNER=$${FORK_REPO%%/*}; \
	if [ ! -d "$$SOURCE_DIR" ]; then \
		echo "Error: $$SOURCE_DIR not found. Run make ci-generate-winget-manifests first."; exit 1; \
	fi; \
	CLONE_DIR=$$(mktemp -d); \
	trap 'rm -rf "$$CLONE_DIR"' EXIT; \
	echo "[ci-publish-winget] Cloning fork $$FORK_REPO"; \
	git clone --filter=blob:none --no-checkout "https://x-access-token:$$WINGET_GITHUB_TOKEN@github.com/$$FORK_REPO.git" "$$CLONE_DIR"; \
	cd "$$CLONE_DIR"; \
	git sparse-checkout init --cone; \
	git sparse-checkout set "$$TARGET_PATH"; \
	DEFAULT_BRANCH=$$(GH_TOKEN="$$WINGET_GITHUB_TOKEN" gh repo view "$$FORK_REPO" --json defaultBranchRef --jq '.defaultBranchRef.name'); \
	if git ls-remote --exit-code --heads origin "$$BRANCH" >/dev/null 2>&1; then \
		git fetch origin "refs/heads/$$BRANCH:refs/remotes/origin/$$BRANCH"; \
		git checkout -B "$$BRANCH" "refs/remotes/origin/$$BRANCH"; \
	else \
		git fetch origin "refs/heads/$$DEFAULT_BRANCH:refs/remotes/origin/$$DEFAULT_BRANCH"; \
		git checkout -B "$$BRANCH" "refs/remotes/origin/$$DEFAULT_BRANCH"; \
	fi; \
	mkdir -p "$$TARGET_PATH"; \
	cp "$$SOURCE_DIR"/* "$$TARGET_PATH"/; \
	git config user.name "github-actions[bot]"; \
	git config user.email "github-actions[bot]@users.noreply.github.com"; \
	git add "$$TARGET_PATH"; \
	if git diff --cached --quiet; then \
		echo "[ci-publish-winget] Manifests are already current for version $$VERSION."; exit 0; \
	fi; \
	git commit -m "Add $(CI_WINGET_PACKAGE_IDENTIFIER) version $$VERSION"; \
	git push --set-upstream origin "$$BRANCH"; \
	EXISTING_PR=$$(GH_TOKEN="$$WINGET_GITHUB_TOKEN" gh pr list --repo microsoft/winget-pkgs --head "$$FORK_OWNER:$$BRANCH" --state open --json number --jq '.[0].number // empty'); \
	if [ -n "$$EXISTING_PR" ]; then \
		GH_TOKEN="$$WINGET_GITHUB_TOKEN" gh pr edit "$$EXISTING_PR" --repo microsoft/winget-pkgs \
			--title "Add $(CI_WINGET_PACKAGE_IDENTIFIER) version $$VERSION" \
			--body "Automated manifest submission generated from the template release workflow."; \
	else \
		GH_TOKEN="$$WINGET_GITHUB_TOKEN" gh pr create --repo microsoft/winget-pkgs \
			--head "$$FORK_OWNER:$$BRANCH" \
			--title "Add $(CI_WINGET_PACKAGE_IDENTIFIER) version $$VERSION" \
			--body "Automated manifest submission generated from the template release workflow."; \
	fi; \
	echo "[ci-publish-winget] Manifest branch pushed and PR updated for $(CI_WINGET_PACKAGE_IDENTIFIER) $$VERSION"
