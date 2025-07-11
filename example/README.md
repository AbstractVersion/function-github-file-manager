# GitHub File Manager Function Example

This example demonstrates how to use the GitHub File Manager function to commit Kubernetes manifests to GitHub repositories using both **Personal Access Token** and **GitHub App** authentication.

## Overview

The function automatically commits application manifests (Deployment, Service, Kustomization) to a GitHub repository when a KubeApp is applied. It supports two authentication methods for maximum flexibility and security.

## Authentication Methods

### Option 1: GitHub App Authentication (Recommended for Production)

GitHub Apps provide more granular permissions and better security for production environments.

#### GitHub App Setup

1. **Create a GitHub App:**
   ```bash
   # Go to your GitHub organization settings
   # Navigate to: Settings → Developer settings → GitHub Apps → New GitHub App
   ```

2. **Configure App permissions:**
   - Repository permissions:
     - Contents: **Read & Write** (to commit files)
     - Metadata: **Read** (to access repository info)
   - Install the app on your target repositories

3. **Get credentials:**
   - **App ID**: Found in your app settings
   - **Installation ID**: Get from the app installation URL
   - **Private Key**: Generate and download in app settings

#### Production Secret Setup

```yaml
# Create Kubernetes secret for GitHub App credentials
apiVersion: v1
kind: Secret
metadata:
  name: github-app-credentials
type: Opaque
data:
  app-id: MTIzNDU2  # base64 encoded app ID
  installation-id: MTIzNDU2Nzg=  # base64 encoded installation ID  
  private-key: <base64-encoded-private-key-pem>

---
# Reference in composition
spec:
  githubApp:
    appId: 
      secretRef:
        name: github-app-credentials
        key: app-id
    installationId:
      secretRef:
        name: github-app-credentials
        key: installation-id
    privateKey:
      secretRef:
        name: github-app-credentials
        key: private-key
```

### Option 2: Personal Access Token (Development)

Simpler setup for development and testing environments.

```yaml
# Create secret for personal access token
apiVersion: v1
kind: Secret
metadata:
  name: github-token
type: Opaque
data:
  token: <base64-encoded-token>

---
# Reference in composition
spec:
  githubToken: 
    secretRef:
      name: github-token
      key: token
```

## Files

- `functions.yaml` - Function package definition for development
- `composition.yaml` - Composition demonstrating both authentication methods
- `xr.yaml` - Example KubeApp resource with GitHub App authentication

## Usage

### 1. Install the Function

```bash
crossplane xpkg install function ghcr.io/kubecore/function-github-file-manager:latest
```

### 2. Set up Authentication

Choose either GitHub App (recommended) or Personal Access Token authentication and create the appropriate Kubernetes secrets.

### 3. Apply the Composition

```bash
kubectl apply -f composition.yaml
```

### 4. Create a KubeApp

```bash
kubectl apply -f xr.yaml
```

This will create files in your GitHub repository:
- `kubeapps/example-rest-api/base/resources.yaml` - Deployment and Service
- `kubeapps/example-rest-api/base/kustomization.yaml` - Kustomization file
- `kubeapps/example-rest-api/overlays/{env}/kustomization.yaml` - Environment overlays (if configured)

## Generated Repository Structure

```
your-repo/
├── kubeapps/
│   └── example-rest-api/
│       ├── base/
│       │   ├── resources.yaml      # Deployment + Service
│       │   └── kustomization.yaml  # Base kustomization
│       └── overlays/
│           ├── dev/
│           │   └── kustomization.yaml
│           ├── staging/
│           │   └── kustomization.yaml
│           └── prod/
│               └── kustomization.yaml
```

## Benefits of GitHub App Authentication

- **Enhanced Security**: Fine-grained permissions, no personal token exposure
- **Organization Control**: Centrally managed app installations
- **Audit Trail**: Better tracking of automated commits
- **Token Management**: Automatic token rotation and expiration
- **Rate Limits**: Higher API rate limits compared to personal tokens

## Development Workflow

1. **Local Testing**: Use personal access token for quick iteration
2. **Staging**: GitHub App with limited repository access
3. **Production**: GitHub App with strict permissions and secret management

## Troubleshooting

### GitHub App Issues

```bash
# Check app installation
curl -H "Authorization: Bearer <jwt-token>" \
  https://api.github.com/app/installations

# Verify installation permissions
curl -H "Authorization: token <installation-token>" \
  https://api.github.com/installation/repositories
```

### Function Debugging

```bash
# Check function logs
kubectl logs -l app=function-github-file-manager

# Check composition status
kubectl describe composition kubeapp-github-deployer

# Check XR status and events
kubectl describe xr example-rest-api
```

## Security Best Practices

1. **Never hardcode credentials** in compositions or XRs
2. **Use GitHub Apps** for production environments
3. **Limit repository access** to only required repositories
4. **Rotate secrets regularly** using automated secret management
5. **Monitor API usage** and set up alerting for unusual activity
6. **Use separate apps** for different environments or teams
