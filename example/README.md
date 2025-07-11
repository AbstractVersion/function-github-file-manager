# GitHub File Manager Function Example

This example demonstrates how to use the GitHub File Manager function to commit Kubernetes manifests to GitHub repositories.

## Overview

The function automatically commits application manifests (Deployment, Service, Kustomization) to a GitHub repository when a KubeApp is applied.

## Files

- `functions.yaml` - Function package definition for development
- `composition.yaml` - Composition that uses the GitHub file manager function
- `xr.yaml` - Example KubeApp resource that triggers the function

## Usage

1. **Install the function:**
   ```bash
   crossplane xpkg install function ghcr.io/kubecore/function-github-file-manager:latest
   ```

2. **Apply the composition:**
   ```bash
   kubectl apply -f composition.yaml
   ```

3. **Create a KubeApp:**
   ```bash
   kubectl apply -f xr.yaml
   ```

This will create:
- `kubeapps/example-rest-api/base/resources.yaml` - Deployment and Service
- `kubeapps/example-rest-api/base/kustomization.yaml` - Kustomization file

## GitHub Token

In production, use a Kubernetes secret reference instead of hardcoding the token:

```yaml
spec:
  githubToken: 
    secretRef:
      name: github-token
      key: token
```
