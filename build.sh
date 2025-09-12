#!/bin/bash

# Build script for XNAT Centiloid Container
# Usage: ./build.sh [version]
# Example: ./build.sh v1.1.2

set -e  # Exit on any error

# Default version if not provided
VERSION=${1:-"latest"}

# Container registry and image name
REGISTRY="xnatworks"
IMAGE_NAME="xnat_centiloid_container"
FULL_IMAGE_NAME="${REGISTRY}/${IMAGE_NAME}"

echo "=== Building XNAT Centiloid Container ==="
echo "Registry: ${REGISTRY}"
echo "Image: ${IMAGE_NAME}"
echo "Version: ${VERSION}"
echo "Full name: ${FULL_IMAGE_NAME}:${VERSION}"
echo ""

# Build the container
echo "Building container..."
docker build -t "${FULL_IMAGE_NAME}:${VERSION}" .

if [ $? -eq 0 ]; then
    echo "✓ Container built successfully: ${FULL_IMAGE_NAME}:${VERSION}"
    
    # If building a version tag, also update latest
    if [[ "${VERSION}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        echo ""
        echo "Tagging as latest..."
        docker tag "${FULL_IMAGE_NAME}:${VERSION}" "${FULL_IMAGE_NAME}:latest"
        echo "✓ Tagged as latest"
    fi
    
    echo ""
    echo "Built images:"
    docker images | grep "${IMAGE_NAME}" | head -5
    
else
    echo "✗ Container build failed!"
    exit 1
fi

echo ""
echo "=== Build Complete ==="
echo "To test: docker run --rm ${FULL_IMAGE_NAME}:${VERSION} --help"
echo "To push: docker push ${FULL_IMAGE_NAME}:${VERSION}"
if [[ "${VERSION}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "To push latest: docker push ${FULL_IMAGE_NAME}:latest"
fi