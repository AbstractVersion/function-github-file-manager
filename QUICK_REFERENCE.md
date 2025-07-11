# GitHub File Manager Function - Quick Reference

## Function Input Template

```yaml
apiVersion: github.fn.kubecore.io/v1beta1
kind: Input
spec:
  # Choose authentication method:
  githubToken: "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # OR
  
  # GitHub App with direct values (development/testing)
  githubApp:
    appId: "123456"
    installationId: "78901234"
    privateKey: "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"
  
  # GitHub App with secret references (production - NEW in v0.2.0)
  githubApp:
    appId:
      secretRef:
        name: "github-app-repo-creds"
        namespace: "argocd"
        key: "githubAppID"
    installationId:
      secretRef:
        name: "github-app-repo-creds"
        namespace: "argocd"
        key: "githubAppInstallationID"
    privateKey:
      secretRef:
        name: "github-app-repo-creds"
        namespace: "argocd"
        key: "githubAppPrivateKey"
  
  files:
    - repository: "owner/repo"          # Required: GitHub repo
      branch: "main"                    # Optional: defaults to "main"
      path: "apps/config.yaml"          # Required: file path
      content: |                       # Required: file content
        apiVersion: v1
        kind: ConfigMap
      commitMessage: "Update config"    # Required: commit message
```

## Common Patterns

### 1. Single File Deployment
```yaml
functions:
  - name: deploy-config
    type: function
    functionRef:
      name: function-github-file-manager
    input:
      apiVersion: github.fn.kubecore.io/v1beta1
      kind: Input
      spec:
        githubToken: "$(credentials.github.token)"
        files:
          - repository: "myorg/k8s-configs"
            path: "apps/myapp/deployment.yaml"
            content: |
              apiVersion: apps/v1
              kind: Deployment
              metadata:
                name: myapp
              spec:
                replicas: 3
            commitMessage: "Deploy myapp"
```

### 2. Multi-Environment Deployment
```yaml
files:
  - repository: "myorg/gitops"
    branch: "dev"
    path: "environments/dev/app.yaml"
    content: "$(dev.config)"
    commitMessage: "Update dev environment"
  - repository: "myorg/gitops"
    branch: "main" 
    path: "environments/prod/app.yaml"
    content: "$(prod.config)"
    commitMessage: "Update prod environment"
```

### 3. GitOps + IaC Pattern
```yaml
files:
  # Kubernetes manifests
  - repository: "myorg/k8s-manifests"
    path: "apps/frontend/deployment.yaml"
    content: "$(k8s.deployment)"
    commitMessage: "Deploy frontend $(version)"
  # Terraform configuration
  - repository: "myorg/terraform"
    path: "environments/$(env)/main.tf"
    content: "$(terraform.config)"
    commitMessage: "Update $(env) infrastructure"
```

## Authentication Setup

### GitHub Token (Quick Setup)
1. Go to GitHub Settings → Developer settings → Personal access tokens
2. Generate token with `repo` scope
3. Use in composition:
```yaml
spec:
  githubToken: "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

### GitHub App (Production)
1. Create GitHub App with Contents: Write permission
2. Install on target repositories
3. Get App ID, Installation ID, and Private Key
4. Use in composition:
```yaml
spec:
  githubApp:
    appId: "123456"
    installationId: "78901234"
    privateKey: "$(secret.github.privateKey)"
```

## Error Codes & Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| `AuthenticationFailed` | Invalid credentials | Check token/app credentials |
| `RepositoryAccessDenied` | No repo access | Verify repo exists and permissions |
| `BranchNotFound` | Branch doesn't exist | Create branch or use existing one |
| `ContentTooLarge` | File > 100MB | Split file or use Git LFS |
| `RateLimited` | API limits exceeded | Use GitHub App or wait |

## Function Status Examples

### Success
```yaml
status:
  conditions:
    - type: Ready
      status: True
      reason: GitHubCommitSuccessful
  githubCommits:
    - repository: "owner/repo"
      sha: "abc123"
      commitUrl: "https://github.com/owner/repo/commit/abc123"
```

### Failure
```yaml
status:
  conditions:
    - type: Ready
      status: False
      reason: AuthenticationFailed
      message: "GitHub API authentication failed"
```

## Debugging Commands

```bash
# Check function status
kubectl get functions
kubectl describe function function-github-file-manager

# Check function logs
kubectl logs -n crossplane-system -l pkg.crossplane.io/function=function-github-file-manager

# Test GitHub access
curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user
```

## Best Practices

1. **Security**: Always use Kubernetes secrets for credentials
2. **Rate Limits**: Use GitHub Apps for production (higher limits)
3. **Error Handling**: Include error checking in compositions
4. **Content Size**: Keep files under 1MB for best performance
5. **Commit Messages**: Use descriptive messages for traceability
6. **Branch Strategy**: Use separate branches for different environments

## Integration with Other Functions

### With Patch & Transform
```yaml
functions:
  - name: create-resources
    type: function
    functionRef:
      name: function-patch-and-transform
    # Create K8s resources first
  
  - name: commit-to-git
    type: function
    functionRef:
      name: function-github-file-manager
    # Then commit to GitOps repo
```

### With Go Templating
```yaml
functions:
  - name: generate-manifests
    type: function
    functionRef:
      name: function-go-templating
    # Generate YAML from templates
  
  - name: commit-manifests
    type: function
    functionRef:
      name: function-github-file-manager
    # Commit generated manifests
```

## File Content Templates

### Kubernetes Deployment
```yaml
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
```

### Terraform Variables
```yaml
content: |
  variable "environment" {
    description = "Environment name"
    type        = string
    default     = "$(spec.environment)"
  }
  
  variable "instance_count" {
    description = "Number of instances"
    type        = number
    default     = $(spec.instances)
  }
```

### ArgoCD Application
```yaml
content: |
  apiVersion: argoproj.io/v1alpha1
  kind: Application
  metadata:
    name: $(spec.appName)
    namespace: argocd
  spec:
    project: default
    source:
      repoURL: $(spec.gitRepo)
      targetRevision: $(spec.gitBranch)
      path: $(spec.gitPath)
    destination:
      server: https://kubernetes.default.svc
      namespace: $(spec.namespace)
    syncPolicy:
      automated:
        prune: true
        selfHeal: true
``` 