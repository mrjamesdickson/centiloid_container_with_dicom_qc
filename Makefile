# Centiloid Container Build Automation
# Usage:
#   make build          - Build container with auto-incremented version
#   make build-push     - Build and push to DockerHub
#   make build VERSION=1.2.0 - Build with specific version
#   make version        - Show current version

.PHONY: build build-push version clean help

# Get current version from command.json
VERSION := $(shell grep '"version":' command.json | sed 's/.*"version": "\([^"]*\)".*/\1/')
IMAGE_NAME := xnatworks/xnat_centiloid_container

# Auto-increment patch version
NEW_VERSION := $(shell echo $(VERSION) | awk -F. '{$$NF = $$NF + 1;} 1' | sed 's/ /./g')

# Use provided VERSION_OVERRIDE or auto-increment
BUILD_VERSION := $(if $(VERSION_OVERRIDE),$(VERSION_OVERRIDE),$(NEW_VERSION))

help:
	@echo "Centiloid Container Build System"
	@echo ""
	@echo "Usage:"
	@echo "  make build              - Build with auto-incremented version ($(NEW_VERSION))"
	@echo "  make build-push         - Build and push to DockerHub"
	@echo "  make build VERSION=X.Y.Z - Build with specific version"
	@echo "  make version            - Show current version"
	@echo "  make clean              - Clean Docker images"
	@echo ""
	@echo "Current version: $(VERSION)"
	@echo "Next version: $(NEW_VERSION)"

version:
	@echo "Current version: $(VERSION)"
	@echo "Next auto-increment: $(NEW_VERSION)"

update-version:
	@echo "Updating version from $(VERSION) to $(BUILD_VERSION)"
	@sed -i.bak \
		-e 's|"version": "[^"]*"|"version": "$(BUILD_VERSION)"|' \
		-e 's|"image": "[^"]*"|"image": "$(IMAGE_NAME):v$(BUILD_VERSION)"|' \
		command.json
	@rm -f command.json.bak
	@sed -i.bak \
		's|ET.SubElement(root, "centiloid:container_version").text = "[^"]*"|ET.SubElement(root, "centiloid:container_version").text = "$(BUILD_VERSION)"|' \
		app/xnat_upload.py
	@rm -f app/xnat_upload.py.bak
	@echo "✓ Updated to version $(BUILD_VERSION)"

commit-version: update-version
	@git add command.json app/xnat_upload.py
	@git commit -m "Update to version $(BUILD_VERSION)" -m "🤖 Generated with [Claude Code](https://claude.ai/code)" -m "Co-Authored-By: Claude <noreply@anthropic.com>"
	@echo "✓ Committed version $(BUILD_VERSION)"

build: commit-version
	@echo "Building $(IMAGE_NAME):v$(BUILD_VERSION)"
	@docker build -t $(IMAGE_NAME):v$(BUILD_VERSION) .
	@docker tag $(IMAGE_NAME):v$(BUILD_VERSION) $(IMAGE_NAME):latest
	@git push origin main
	@echo "✓ Built and tagged $(IMAGE_NAME):v$(BUILD_VERSION)"

build-push: build
	@echo "Pushing to DockerHub..."
	@docker push $(IMAGE_NAME):v$(BUILD_VERSION)
	@docker push $(IMAGE_NAME):latest
	@echo "✓ Pushed $(IMAGE_NAME):v$(BUILD_VERSION) to DockerHub"

clean:
	@echo "Cleaning up Docker images..."
	@docker rmi $(IMAGE_NAME):latest $(IMAGE_NAME):v$(VERSION) 2>/dev/null || true
	@echo "✓ Cleaned up Docker images"

# Override version from command line
ifdef VERSION
BUILD_VERSION := $(VERSION)
endif