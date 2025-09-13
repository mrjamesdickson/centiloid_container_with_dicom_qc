#!/bin/bash

# Automated build and push script that manages versioning
# Usage: ./build_and_push.sh [version] [push]
#   version: new version (e.g., 1.2.0) - if not provided, auto-increments patch
#   push: "push" to push to DockerHub, omit for local build only

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to get current version from command.json
get_current_version() {
    grep '"version":' command.json | sed 's/.*"version": "\([^"]*\)".*/\1/'
}

# Function to increment version (patch level)
increment_version() {
    local version=$1
    local major=$(echo $version | cut -d. -f1)
    local minor=$(echo $version | cut -d. -f2)
    local patch=$(echo $version | cut -d. -f3)
    
    # Increment patch version
    patch=$((patch + 1))
    
    echo "${major}.${minor}.${patch}"
}

# Function to update command.json with new version
update_command_json() {
    local new_version=$1
    local image_tag="xnatworks/xnat_centiloid_container:v${new_version}"
    
    echo -e "${BLUE}Updating command.json to version ${new_version}...${NC}"
    
    # Use sed to update both version and image tag
    sed -i.bak \
        -e "s/\"version\": \"[^\"]*\"/\"version\": \"${new_version}\"/" \
        -e "s/\"image\": \"[^\"]*\"/\"image\": \"${image_tag}\"/" \
        command.json
    
    # Remove backup file
    rm -f command.json.bak
    
    echo -e "${GREEN}✓ Updated command.json to version ${new_version}${NC}"
}

# Function to update container version in xnat_upload.py
update_container_version() {
    local new_version=$1
    
    echo -e "${BLUE}Updating container version in xnat_upload.py...${NC}"
    
    sed -i.bak \
        "s/ET.SubElement(root, \"centiloid:container_version\").text = \"[^\"]*\"/ET.SubElement(root, \"centiloid:container_version\").text = \"${new_version}\"/" \
        app/xnat_upload.py
    
    # Remove backup file
    rm -f app/xnat_upload.py.bak
    
    echo -e "${GREEN}✓ Updated container version in xnat_upload.py to ${new_version}${NC}"
}

# Main script
echo -e "${BLUE}=== Centiloid Container Build & Push Script ===${NC}"

# Get current version
CURRENT_VERSION=$(get_current_version)
echo -e "${YELLOW}Current version: ${CURRENT_VERSION}${NC}"

# Determine new version
if [ -n "$1" ]; then
    NEW_VERSION="$1"
    echo -e "${YELLOW}Using provided version: ${NEW_VERSION}${NC}"
else
    NEW_VERSION=$(increment_version "$CURRENT_VERSION")
    echo -e "${YELLOW}Auto-incremented to version: ${NEW_VERSION}${NC}"
fi

# Confirm version
read -p "Proceed with version ${NEW_VERSION}? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${RED}Aborted${NC}"
    exit 1
fi

# Update version files
update_command_json "$NEW_VERSION"
update_container_version "$NEW_VERSION"

# Git commit version updates
echo -e "${BLUE}Committing version updates...${NC}"
git add command.json app/xnat_upload.py
git commit -m "Update to version ${NEW_VERSION}

🤖 Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>"

# Build Docker image
echo -e "${BLUE}Building Docker image...${NC}"
IMAGE_TAG="xnatworks/xnat_centiloid_container:v${NEW_VERSION}"
docker build -t "$IMAGE_TAG" .

# Tag as latest
docker tag "$IMAGE_TAG" "xnatworks/xnat_centiloid_container:latest"

echo -e "${GREEN}✓ Built ${IMAGE_TAG}${NC}"

# Push to GitHub
echo -e "${BLUE}Pushing to GitHub...${NC}"
git push origin main
echo -e "${GREEN}✓ Pushed to GitHub${NC}"

# Push to DockerHub if requested
if [ "$2" == "push" ]; then
    echo -e "${BLUE}Pushing to DockerHub...${NC}"
    docker push "$IMAGE_TAG"
    docker push "xnatworks/xnat_centiloid_container:latest"
    echo -e "${GREEN}✓ Pushed to DockerHub${NC}"
else
    echo -e "${YELLOW}Skipping DockerHub push (add 'push' as second argument to enable)${NC}"
fi

echo ""
echo -e "${GREEN}🎉 Build complete!${NC}"
echo -e "${GREEN}Version: ${NEW_VERSION}${NC}"
echo -e "${GREEN}Image: ${IMAGE_TAG}${NC}"

# Show git status
echo -e "${BLUE}Git status:${NC}"
git status --short