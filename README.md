# GitHub File Manager Function for Crossplane

A Crossplane composition function that commits files directly to GitHub repositories using either personal access tokens or GitHub App authentication.

## 🚀 Installation

Install the function from GitHub Container Registry:

```bash
# Install the function
kubectl apply -f - <<EOF
apiVersion: pkg.crossplane.io/v1beta1
kind: Function
metadata:
  name: function-github-file-manager
spec:
  package: ghcr.io/abstractversion/function-github-file-manager:latest
EOF
```

## ✨ Features

- **Direct GitHub API integration** - No intermediate Kubernetes resources
- **Dual authentication support** - Personal access tokens and GitHub Apps
- **Multiple files per operation** - Commit multiple files in a single function call
- **Branch targeting** - Specify target branches for commits
- **Idempotent operations** - Handles both file creation and updates automatically
- **Comprehensive error handling** - Clear error messages and partial failure support
- **Production ready** - Includes timeouts, retries, and security best practices

## 🔐 Authentication Methods

### Personal Access Token (Development)
Simple authentication using a GitHub personal access token:

```yaml
input:
  apiVersion: github.fn.kubecore.io/v1beta1
  kind: Input
  githubToken: "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  files: [...]
```

### GitHub App (Production Recommended)
More secure authentication using GitHub App credentials:

```yaml
input:
  apiVersion: github.fn.kubecore.io/v1beta1
  kind: Input
  githubApp:
    appId: "12345"
    installationId: "67890"
    privateKey: |
      -----BEGIN RSA PRIVATE KEY-----
      YOUR_PRIVATE_KEY_HERE
      -----END RSA PRIVATE KEY-----
  files: [...]
```

## 📋 Usage Examples

### Basic Usage in a Composition

```yaml
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: gitops-deployment
spec:
  compositeTypeRef:
    apiVersion: platform.io/v1alpha1
    kind: XApplication
  
  functions:
    - name: commit-to-gitops
      type: function
      step: github-commit
      functionRef:
        name: function-github-file-manager
      input:
        apiVersion: github.fn.kubecore.io/v1beta1
        kind: Input
        githubToken: "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        files:
          - repository: "my-org/gitops-repo"
            path: "apps/my-app/deployment.yaml"
            content: |
              apiVersion: apps/v1
              kind: Deployment
              metadata:
                name: my-app
              spec:
                replicas: 3
                selector:
                  matchLabels:
                    app: my-app
                template:
                  metadata:
                    labels:
                      app: my-app
                  spec:
                    containers:
                    - name: app
                      image: nginx:latest
            commitMessage: "Deploy my-app v1.0.0"
            branch: "main"
```

### Multiple Files with Different Branches

```yaml
input:
  apiVersion: github.fn.kubecore.io/v1beta1
  kind: Input
  githubToken: "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  files:
    - repository: "my-org/config-repo"
      path: "environments/dev/app-config.yaml"
      content: |
        apiVersion: v1
        kind: ConfigMap
        metadata:
          name: app-config
        data:
          environment: "development"
      commitMessage: "Update dev configuration"
      branch: "development"
      
    - repository: "my-org/config-repo"
      path: "environments/prod/app-config.yaml"
      content: |
        apiVersion: v1
        kind: ConfigMap
        metadata:
          name: app-config
        data:
          environment: "production"
      commitMessage: "Update prod configuration"
      branch: "main"
```

### Using with Kubernetes Secrets

For production deployments, store credentials in Kubernetes secrets:

```yaml
# Create secret with GitHub token
apiVersion: v1
kind: Secret
metadata:
  name: github-credentials
type: Opaque
data:
  token: Z2hwX3h4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eA== # base64 encoded
---
# Use in composition
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
spec:
  functions:
    - name: commit-to-gitops
      type: function
      functionRef:
        name: function-github-file-manager
      input:
        apiVersion: github.fn.kubecore.io/v1beta1
        kind: Input
        githubToken:
          secretRef:
            name: github-credentials
            key: token
        files: [...]
```

## 🔧 GitHub App Setup

For production use, create a GitHub App:

1. **Create GitHub App**:
   - Go to GitHub Settings → Developer settings → GitHub Apps
   - Click "New GitHub App"
   - Set permissions: Contents (Read & Write), Metadata (Read)

2. **Get Credentials**:
   - App ID: Found in app settings
   - Installation ID: Install app on repositories, get from installation URL
   - Private Key: Generate and download from app settings

3. **Use in Kubernetes**:
   ```yaml
   apiVersion: v1
   kind: Secret
   metadata:
     name: github-app-credentials
   type: Opaque
   data:
     app-id: MTIzNDU=  # base64 encoded
     installation-id: Njc4OTA=  # base64 encoded
     private-key: LS0tLS1CRUdJTi... # base64 encoded private key
   ```

## 📊 Function Output

The function provides detailed context about operations:

```yaml
# Success response
context:
  github-file-manager:
    success: true
    filesProcessed: 2
    results:
      - success: true
        path: "apps/my-app/deployment.yaml"
        sha: "abc123def456"
        githubUrl: "https://github.com/my-org/repo/blob/main/apps/my-app/deployment.yaml"
    errors: []

# Partial failure response  
context:
  github-file-manager:
    success: false
    filesProcessed: 1
    results:
      - success: true
        path: "apps/app1/config.yaml"
        sha: "abc123"
        githubUrl: "https://github.com/my-org/repo/blob/main/apps/app1/config.yaml"
    errors:
      - "Failed to process file apps/app2/config.yaml: API rate limit exceeded"
```

## 🏗️ Development

### Local Testing

```bash
# Clone the repository
git clone https://github.com/AbstractVersion/function-github-file-manager
cd function-github-file-manager

# Install dependencies
pip install -e .

# Run tests
python -m pytest tests/ -v

# Run linting
ruff check .

# Start development server
python function/main.py --insecure --debug
```

### Building Custom Versions

```bash
# Build the function package
docker build -t my-github-function .

# Build Crossplane package
crossplane xpkg build --package-file=function.xpkg --package-root=package/

# Push to your registry
crossplane xpkg push my-registry.io/my-github-function:v1.0.0 function.xpkg
```

## 🔒 Security Considerations

- **Use GitHub Apps** for production deployments (better security and rate limits)
- **Store credentials** in Kubernetes secrets, not in composition YAML
- **Limit repository access** using GitHub App permissions
- **Use branch protection** rules on target repositories
- **Monitor function logs** for failed operations and security events

## 📝 Input Schema

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `githubToken` | string | conditional | GitHub personal access token |
| `githubApp` | object | conditional | GitHub App credentials |
| `githubApp.appId` | string | required* | GitHub App ID |
| `githubApp.installationId` | string | required* | Installation ID |
| `githubApp.privateKey` | string | required* | Private key (PEM format) |
| `files` | array | required | List of files to commit |
| `files[].repository` | string | required | Repository in "owner/repo" format |
| `files[].path` | string | required | File path within repository |
| `files[].content` | string | required | File content |
| `files[].commitMessage` | string | required | Commit message |
| `files[].branch` | string | optional | Target branch (default: "main") |

*Required when using GitHub App authentication

## 🐛 Troubleshooting

### Common Issues

1. **Permission Denied**: Ensure token/app has write access to repository
2. **Rate Limit**: Use GitHub App for higher rate limits (5000 vs 1000 requests/hour)
3. **File Not Found**: Function automatically handles both creation and updates
4. **Invalid Credentials**: Check token expiration and permissions

### Debug Mode

Enable verbose logging by setting the function to debug mode in your development environment.

## 📄 License

Apache License 2.0 - see [LICENSE](LICENSE) file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Ensure all tests pass and linting is clean
6. Submit a pull request

## 📞 Support

- **Issues**: Report bugs and feature requests on [GitHub Issues](https://github.com/AbstractVersion/function-github-file-manager/issues)
- **Discussions**: Join discussions on [GitHub Discussions](https://github.com/AbstractVersion/function-github-file-manager/discussions)
