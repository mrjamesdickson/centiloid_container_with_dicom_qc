# Build Process Documentation

This repository includes automated build tools that handle version management and Docker builds.

## Quick Start

### Using Makefile (Recommended)

```bash
# Build with auto-incremented version
make build

# Build and push to DockerHub  
make build-push

# Build with specific version
make build VERSION=1.2.0

# Show current version
make version

# Help
make help
```

### Using Build Script

```bash
# Auto-increment patch version and build locally
./build_and_push.sh

# Use specific version and build locally
./build_and_push.sh 1.2.0

# Auto-increment and push to DockerHub
./build_and_push.sh "" push

# Use specific version and push to DockerHub
./build_and_push.sh 1.2.0 push
```

## What Happens During Build

The automated build process:

1. **Version Management**
   - Reads current version from `command.json`
   - Auto-increments patch version (1.1.11 → 1.1.12) or uses provided version
   - Updates `command.json` with new version and image tag
   - Updates container version in `app/xnat_upload.py`

2. **Git Operations**
   - Commits version changes with standardized commit message
   - Pushes to GitHub

3. **Docker Operations**
   - Builds new Docker image with version tag
   - Tags as `latest`
   - Optionally pushes to DockerHub

4. **Validation**
   - Shows git status
   - Confirms successful build

## Files Automatically Updated

- `command.json` - Version and Docker image tag
- `app/xnat_upload.py` - Container version in XML output

## Version Numbering

- **Major.Minor.Patch** format (e.g., 1.1.11)
- Auto-increment increases patch version
- Manual versions can use any valid semver format

## Examples

```bash
# Current version: 1.1.11

# Auto-increment to 1.1.12
make build

# Jump to 1.2.0 
make build VERSION=1.2.0

# Build and push version 2.0.0
make build-push VERSION=2.0.0
```

## Manual Process (Not Recommended)

If you need to build manually:

```bash
# 1. Update versions manually
vim command.json  # Update version and image
vim app/xnat_upload.py  # Update container_version

# 2. Build
docker build -t xnatworks/xnat_centiloid_container:v1.1.12 .
docker tag xnatworks/xnat_centiloid_container:v1.1.12 xnatworks/xnat_centiloid_container:latest

# 3. Commit and push
git add command.json app/xnat_upload.py
git commit -m "Update to version 1.1.12"
git push origin main

# 4. Push to DockerHub
docker push xnatworks/xnat_centiloid_container:v1.1.12
docker push xnatworks/xnat_centiloid_container:latest
```

## Troubleshooting

- **Build fails**: Check Docker is running and you have permissions
- **Push fails**: Ensure you're logged into DockerHub (`docker login`)
- **Version conflicts**: Check no uncommitted changes exist
- **Permission denied**: Make scripts executable (`chmod +x build_and_push.sh`)