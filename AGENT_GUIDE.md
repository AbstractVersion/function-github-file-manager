# GitHub File Manager Function - Agent Usage Guide

## Overview
The GitHub File Manager Function is a Crossplane composition function that commits files directly to GitHub repositories using the GitHub API. This guide provides AI agents with comprehensive information on how to use this function effectively in Crossplane compositions.

## Function Specification

### Input Schema
```yaml
apiVersion: github.fn.kubecore.io/v1beta1
kind: Input
spec:
  # Authentication (choose ONE)
  githubToken: string                 # Personal Access Token (development)
  githubApp:                         # GitHub App (production recommended)
    appId: string                    # GitHub App ID
    installationId: string           # Installation ID for target repositories
    privateKey: string               # PEM-formatted private key
  
  # File operations
  files:                             # Array of files to commit
    - repository: string             # Format: "owner/repo"
      branch: string                 # Target branch (default: "main")
      path: string                   # File path in repository
      content: string                # File content
      commitMessage: string          # Commit message for this file
```

### Authentication Methods

#### 1. Personal Access Token (Development)
```yaml
spec:
  githubToken: "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

**Use Cases:**
- Development and testing
- Personal repositories
- Quick prototyping

**Limitations:**
- Less secure than GitHub Apps
- Rate limits apply to user account
- No fine-grained permissions

#### 2. GitHub App (Production Recommended)
```yaml
spec:
  githubApp:
    appId: "123456"
    installationId: "78901234"
    privateKey: |
      -----BEGIN RSA PRIVATE KEY-----
      MIIEpAIBAAKCAQEA...
      -----END RSA PRIVATE KEY-----
```

**Use Cases:**
- Production deployments
- Organization repositories
- Fine-grained access control
- Higher rate limits

### Expected Behavior

#### Success Scenario
1. **Authentication**: Function authenticates with GitHub using provided credentials
2. **Repository Access**: Validates access to each specified repository
3. **File Operations**: For each file:
   - Checks if file exists at the specified path
   - If exists: Updates the file with new content
   - If not exists: Creates new file
   - Commits changes with provided message
4. **Response**: Returns success status with commit information

#### Error Scenarios
- **Authentication Failure**: Invalid token or GitHub App credentials
- **Repository Access**: No access to specified repository
- **Branch Not Found**: Target branch doesn't exist
- **Content Too Large**: File content exceeds GitHub limits
- **Rate Limiting**: GitHub API rate limits exceeded

## Usage in Compositions

### Basic Single File Example
```yaml
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: deploy-app-config
spec:
  compositeTypeRef:
    apiVersion: platform.io/v1alpha1
    kind: XApplication
  
  functions:
    - name: commit-config
      type: function
      step: github-commit
      functionRef:
        name: function-github-file-manager
      input:
        apiVersion: github.fn.kubecore.io/v1beta1
        kind: Input
        spec:
          githubToken: "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
          files:
            - repository: "my-org/gitops-repo"
              branch: "main"
              path: "apps/my-app/config.yaml"
              content: |
                apiVersion: v1
                kind: ConfigMap
                metadata:
                  name: my-app-config
                data:
                  environment: "production"
                  replicas: "3"
              commitMessage: "Update my-app configuration via Crossplane"
```

### Multi-File Multi-Repository Example
```yaml
functions:
  - name: deploy-to-multiple-repos
    type: function
    step: github-multi-commit
    functionRef:
      name: function-github-file-manager
    input:
      apiVersion: github.fn.kubecore.io/v1beta1
      kind: Input
      spec:
        githubApp:
          appId: "123456"
          installationId: "78901234"
          privateKey: |
            -----BEGIN RSA PRIVATE KEY-----
            MIIEpAIBAAKCAQEA...
            -----END RSA PRIVATE KEY-----
        files:
          # Application deployment
          - repository: "my-org/k8s-manifests"
            branch: "main"
            path: "apps/frontend/deployment.yaml"
            content: |
              apiVersion: apps/v1
              kind: Deployment
              metadata:
                name: frontend
              spec:
                replicas: 3
                selector:
                  matchLabels:
                    app: frontend
                template:
                  metadata:
                    labels:
                      app: frontend
                  spec:
                    containers:
                    - name: frontend
                      image: nginx:1.21
            commitMessage: "Deploy frontend v1.21"
          
          # Infrastructure as Code
          - repository: "my-org/terraform-config"
            branch: "infrastructure"
            path: "environments/prod/variables.tf"
            content: |
              variable "instance_count" {
                description = "Number of instances"
                type        = number
                default     = 3
              }
            commitMessage: "Update prod instance count to 3"
          
          # Documentation update
          - repository: "my-org/docs"
            branch: "main"
            path: "deployments/frontend.md"
            content: |
              # Frontend Deployment
              
              Last updated: $(date)
              Version: v1.21
              Replicas: 3
            commitMessage: "Update frontend deployment documentation"
```

### Using with Composite Resource Values
```yaml
functions:
  - name: deploy-from-cr
    type: function
    step: github-commit
    functionRef:
      name: function-github-file-manager
    input:
      apiVersion: github.fn.kubecore.io/v1beta1
      kind: Input
      spec:
        githubToken: "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        files:
          - repository: "my-org/gitops-repo"
            branch: "main"
            path: "apps/$(spec.appName)/deployment.yaml"
            content: |
              apiVersion: apps/v1
              kind: Deployment
              metadata:
                name: $(spec.appName)
                namespace: $(spec.namespace)
              spec:
                replicas: $(spec.replicas)
                selector:
                  matchLabels:
                    app: $(spec.appName)
                template:
                  metadata:
                    labels:
                      app: $(spec.appName)
                  spec:
                    containers:
                    - name: $(spec.appName)
                      image: $(spec.image)
                      ports:
                      - containerPort: $(spec.port)
            commitMessage: "Deploy $(spec.appName) v$(spec.version)"
```

## Security Best Practices

### 1. Use Kubernetes Secrets for Credentials
```yaml
# Secret creation
apiVersion: v1
kind: Secret
metadata:
  name: github-credentials
  namespace: crossplane-system
type: Opaque
data:
  token: Z2hwX3h4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eA==  # base64 encoded

---
# Usage in composition
spec:
  githubToken:
    secretRef:
      name: github-credentials
      key: token
```

### 2. GitHub App Setup for Production
1. **Create GitHub App**: Go to GitHub Settings → Developer settings → GitHub Apps
2. **Set Permissions**: Contents (Read & Write), Metadata (Read)
3. **Install on Repositories**: Install the app on target repositories
4. **Store Credentials Securely**: Use Kubernetes secrets for app credentials

### 3. Least Privilege Access
- Grant only necessary repository access
- Use separate GitHub Apps for different environments
- Regularly rotate credentials

## Error Handling and Debugging

### Common Error Patterns

#### Authentication Errors
```yaml
# Error: Invalid token
status:
  conditions:
    - type: Ready
      status: False
      reason: AuthenticationFailed
      message: "GitHub API authentication failed: Bad credentials"
```

**Solution**: Verify token validity and permissions

#### Repository Access Errors
```yaml
# Error: Repository not found or no access
status:
  conditions:
    - type: Ready
      status: False
      reason: RepositoryAccessDenied
      message: "Cannot access repository 'owner/repo': Not Found"
```

**Solution**: Check repository exists and credentials have access

#### Content Errors
```yaml
# Error: File too large
status:
  conditions:
    - type: Ready
      status: False
      reason: ContentTooLarge
      message: "File content exceeds GitHub size limit of 100MB"
```

**Solution**: Split large files or use Git LFS

### Debugging Steps
1. **Check Function Logs**: `kubectl logs -n crossplane-system <function-pod>`
2. **Verify Credentials**: Test GitHub API access manually
3. **Validate Repository Access**: Ensure repositories exist and are accessible
4. **Check Rate Limits**: Monitor GitHub API rate limit headers

## Function Outputs

The function doesn't produce traditional Crossplane resources but updates the composite resource status with operation results:

### Success Status
```yaml
status:
  conditions:
    - type: Ready
      status: True
      reason: GitHubCommitSuccessful
      message: "Successfully committed 3 files to GitHub repositories"
  githubCommits:
    - repository: "owner/repo1"
      branch: "main"
      path: "apps/app1/config.yaml"
      sha: "abc123def456"
      commitUrl: "https://github.com/owner/repo1/commit/abc123def456"
    - repository: "owner/repo2"
      branch: "develop"
      path: "infrastructure/terraform.tf"
      sha: "def456ghi789"
      commitUrl: "https://github.com/owner/repo2/commit/def456ghi789"
```

### Partial Failure Status
```yaml
status:
  conditions:
    - type: Ready
      status: False
      reason: PartialFailure
      message: "2 of 3 files committed successfully, 1 failed"
  githubCommits:
    - repository: "owner/repo1"
      branch: "main"
      path: "apps/app1/config.yaml"
      sha: "abc123def456"
      commitUrl: "https://github.com/owner/repo1/commit/abc123def456"
      status: "success"
    - repository: "owner/repo2"
      branch: "main"
      path: "apps/app2/config.yaml"
      sha: null
      commitUrl: null
      status: "failed"
      error: "Repository not found"
```

## Integration Patterns

### 1. GitOps Deployment Pattern
```yaml
# Use with ArgoCD or Flux for GitOps
functions:
  - name: patch-and-transform
    type: function
    step: create-resources
    functionRef:
      name: function-patch-and-transform
    # ... create Kubernetes resources
  
  - name: commit-to-gitops
    type: function
    step: gitops-commit
    functionRef:
      name: function-github-file-manager
    input:
      # ... commit generated manifests to GitOps repo
```

### 2. Infrastructure as Code Pattern
```yaml
# Generate and commit Terraform configurations
functions:
  - name: generate-terraform
    type: function
    step: terraform-generation
    functionRef:
      name: function-go-templating
    # ... generate Terraform from templates
  
  - name: commit-terraform
    type: function
    step: terraform-commit
    functionRef:
      name: function-github-file-manager
    # ... commit generated Terraform to IaC repo
```

### 3. Documentation Automation Pattern
```yaml
# Auto-update documentation based on deployments
functions:
  - name: deploy-resources
    type: function
    step: deployment
    functionRef:
      name: function-patch-and-transform
    # ... deploy application
  
  - name: update-docs
    type: function
    step: documentation
    functionRef:
      name: function-github-file-manager
    # ... update deployment documentation
```

## Rate Limiting and Performance

### GitHub API Limits
- **Personal Access Token**: 5,000 requests/hour
- **GitHub App**: 15,000 requests/hour per installation
- **Large Files**: 100MB per file limit

### Optimization Strategies
1. **Batch Operations**: Group multiple file changes in single function call
2. **Conditional Updates**: Only commit when content actually changes
3. **Use GitHub Apps**: Higher rate limits for production workloads
4. **Monitor Usage**: Track API usage to avoid limits

## Testing and Validation

### Local Testing
```bash
# Test function locally (from function directory)
python function/main.py --insecure --debug
```

### Integration Testing
```yaml
# Test composition with function
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: test-github-function
spec:
  compositeTypeRef:
    apiVersion: platform.io/v1alpha1
    kind: XTest
  functions:
    - name: test-commit
      type: function
      functionRef:
        name: function-github-file-manager
      input:
        apiVersion: github.fn.kubecore.io/v1beta1
        kind: Input
        spec:
          githubToken: "test-token"
          files:
            - repository: "test-org/test-repo"
              path: "test/file.yaml"
              content: "test: content"
              commitMessage: "Test commit"
```

## Troubleshooting Checklist

1. **Function Installation**:
   - [ ] Function pod is running in crossplane-system namespace
   - [ ] Function CRD is properly installed
   - [ ] No CRD validation errors

2. **Authentication**:
   - [ ] GitHub token/app credentials are valid
   - [ ] Credentials have necessary permissions
   - [ ] Secrets are properly formatted and accessible

3. **Repository Access**:
   - [ ] Target repositories exist
   - [ ] Credentials have write access to repositories
   - [ ] Target branches exist

4. **Function Execution**:
   - [ ] Input schema is valid
   - [ ] File content is within GitHub limits
   - [ ] Commit messages are provided
   - [ ] No rate limiting issues

This function enables powerful GitOps workflows by allowing Crossplane compositions to directly manage Git repositories, bridging the gap between infrastructure provisioning and configuration management. 