# Local Testing Guide for GitHub File Manager Function

This guide explains how to test the function locally and debug GitHub App authentication issues.

## 🏃‍♂️ Running the Function Locally

### Prerequisites
1. Python 3.11+ installed
2. GitHub repository access for testing
3. GitHub App or Personal Access Token

### Setup Environment

```bash
# Navigate to function directory
cd function-github-file-manager

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# Or using hatch
pip install hatch
hatch shell
```

### Start Function Server

```bash
# Start the function in debug mode (insecure for local testing)
python function/main.py --insecure --debug

# The function will start listening on 0.0.0.0:9443
# You should see: "Serving function..."
```

## ✨ **NEW in v0.2.0: Secret Reference Support**

The function now supports Kubernetes secret references! You can use either:

1. **Direct credentials** (for local testing):
```yaml
githubApp:
  appId: "123456"
  installationId: "78901234" 
  privateKey: "-----BEGIN RSA PRIVATE KEY-----\n..."
```

2. **Secret references** (for production):
```yaml
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
```

## 🧪 Testing Methods

### Method 1: Unit Tests (Recommended for Auth Issues)

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific GitHub App tests
python -m pytest tests/test_fn.py::TestGitHubFileManager::test_commit_new_file_with_github_app -v

# Run with debug output
python -m pytest tests/ -v -s --log-cli-level=DEBUG
```

### Method 2: Interactive Testing Script

Create a test script to isolate authentication issues:

```python
# test_auth.py
import logging
import sys
from function.fn import GitHubFileManager

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Test GitHub App Authentication
def test_github_app_auth():
    """Test GitHub App authentication step by step."""
    
    # Replace with your actual GitHub App credentials
    github_app = {
        "appId": "YOUR_APP_ID",          # e.g., "123456"
        "installationId": "YOUR_INST_ID", # e.g., "78901234"
        "privateKey": """-----BEGIN RSA PRIVATE KEY-----
YOUR_PRIVATE_KEY_HERE
-----END RSA PRIVATE KEY-----"""
    }
    
    try:
        print("🔧 Testing GitHub App Authentication...")
        
        # Initialize manager
        manager = GitHubFileManager(
            logger=logger,
            github_app=github_app
        )
        print("✅ GitHubFileManager initialized successfully")
        
        # Test JWT generation
        print("\n🔑 Testing JWT token generation...")
        jwt_token = manager._generate_jwt_token()
        print(f"✅ JWT Token generated: {jwt_token[:50]}...")
        
        # Test installation access token
        print("\n🎫 Testing installation access token...")
        access_token = manager._get_installation_access_token()
        print(f"✅ Access token obtained: {access_token[:20]}...")
        
        # Test auth headers
        print("\n📋 Testing auth headers...")
        headers = manager._get_auth_headers()
        print(f"✅ Auth headers: {headers}")
        
        return True
        
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        import traceback
        traceback.print_exc()
        return False

# Test Personal Access Token
def test_personal_token_auth():
    """Test Personal Access Token authentication."""
    
    # Replace with your actual token
    github_token = "ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    
    try:
        print("\n🔧 Testing Personal Access Token...")
        
        manager = GitHubFileManager(
            logger=logger,
            github_token=github_token
        )
        print("✅ GitHubFileManager initialized successfully")
        
        # Test auth headers
        headers = manager._get_auth_headers()
        print(f"✅ Auth headers: {headers}")
        
        return True
        
    except Exception as e:
        print(f"❌ Token authentication failed: {e}")
        return False

# Test actual file commit (optional)
def test_file_commit(manager, test_repo="your-org/test-repo"):
    """Test actual file commit to GitHub."""
    
    try:
        print(f"\n📁 Testing file commit to {test_repo}...")
        
        result = manager.commit_file(
            repository=test_repo,
            path="test/crossplane-function-test.txt",
            content=f"Test from GitHub File Manager Function\nTimestamp: {__import__('datetime').datetime.now()}",
            message="Test commit from Crossplane function",
            branch="main"
        )
        
        print(f"✅ File committed successfully: {result}")
        return True
        
    except Exception as e:
        print(f"❌ File commit failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 GitHub File Manager Function - Authentication Test\n")
    
    # Test GitHub App auth
    app_success = test_github_app_auth()
    
    # Test Personal Access Token auth
    token_success = test_personal_token_auth()
    
    print(f"\n📊 Results:")
    print(f"   GitHub App Auth: {'✅ PASS' if app_success else '❌ FAIL'}")
    print(f"   Personal Token Auth: {'✅ PASS' if token_success else '❌ FAIL'}")
```

Save this as `test_auth.py` and run:
```bash
python test_auth.py
```

### Method 3: HTTP Testing with gRPC Client

Create a gRPC test client:

```python
# test_grpc.py
import asyncio
import json
import grpc
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from crossplane.function.proto.v1 import run_function_pb2_grpc as fnv1_grpc
from google.protobuf import json_format

async def test_function():
    """Test the function via gRPC."""
    
    # Test input for GitHub App
    test_input = {
        "githubApp": {
            "appId": "YOUR_APP_ID",
            "installationId": "YOUR_INSTALLATION_ID", 
            "privateKey": "YOUR_PRIVATE_KEY"
        },
        "files": [
            {
                "repository": "your-org/test-repo",
                "path": "test/function-test.yaml",
                "content": "apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: test",
                "commitMessage": "Test from function",
                "branch": "main"
            }
        ]
    }
    
    # Create request
    req = fnv1.RunFunctionRequest()
    req.input.CopyFrom(json_format.ParseDict(test_input, req.input))
    
    # Connect to function
    async with grpc.aio.insecure_channel('localhost:9443') as channel:
        stub = fnv1_grpc.FunctionRunnerServiceStub(channel)
        
        try:
            response = await stub.RunFunction(req)
            print("✅ Function executed successfully")
            print(f"Response: {response}")
            
            # Parse context
            context = json_format.MessageToDict(response.context)
            print(f"Context: {json.dumps(context, indent=2)}")
            
        except Exception as e:
            print(f"❌ Function execution failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_function())
```

## 🐛 Debugging GitHub App Authentication

### Common Issues and Solutions

#### 1. Private Key Format Issues
```python
# ❌ Wrong format (common mistake)
private_key = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA..."

# ✅ Correct format 
private_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA7wH8H9...
...
-----END RSA PRIVATE KEY-----"""
```

#### 2. App ID vs Installation ID Confusion
```python
# Make sure you have the right IDs:
# - App ID: Found in GitHub App settings (numeric)
# - Installation ID: Get from app installation URL or API
```

#### 3. JWT Token Issues
Test JWT generation manually:
```python
import jwt
import time

def test_jwt_generation(app_id, private_key):
    """Test JWT generation manually."""
    
    now = int(time.time())
    payload = {
        "iat": now - 60,  # issued 1 minute ago
        "exp": now + 600,  # expires in 10 minutes  
        "iss": app_id,
    }
    
    try:
        token = jwt.encode(payload, private_key, algorithm="RS256")
        print(f"✅ JWT generated: {token}")
        
        # Decode to verify
        decoded = jwt.decode(token, private_key, algorithms=["RS256"])
        print(f"✅ JWT decoded: {decoded}")
        
        return token
    except Exception as e:
        print(f"❌ JWT generation failed: {e}")
        return None
```

#### 4. Installation Token Issues
Test installation token request:
```python
import requests

def test_installation_token(jwt_token, installation_id):
    """Test getting installation token."""
    
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    
    response = requests.post(url, headers=headers)
    
    if response.status_code == 201:
        token_data = response.json()
        print(f"✅ Installation token: {token_data['token'][:20]}...")
        return token_data['token']
    else:
        print(f"❌ Failed to get installation token: {response.status_code}")
        print(f"Response: {response.text}")
        return None
```

### Getting GitHub App Credentials

#### 1. Create GitHub App
```bash
# Go to: https://github.com/settings/apps
# Click "New GitHub App"

# Required fields:
# - GitHub App name: your-app-name
# - Homepage URL: http://localhost (for testing)
# - Webhook URL: http://localhost (can disable webhooks)

# Permissions needed:
# - Repository permissions:
#   - Contents: Read and Write
#   - Metadata: Read
```

#### 2. Get App ID
```bash
# Found in app settings page
# Format: numeric string like "123456"
```

#### 3. Generate Private Key
```bash
# In GitHub App settings:
# 1. Scroll to "Private keys"
# 2. Click "Generate a private key"
# 3. Download the .pem file
# 4. Use the content directly (including BEGIN/END lines)
```

#### 4. Install App and Get Installation ID
```bash
# 1. Install the app on your test repository
# 2. Get installation ID from URL: 
#    https://github.com/settings/installations/{INSTALLATION_ID}
# 3. Or use GitHub API:
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     https://api.github.com/app/installations
```

### Environment Variables for Testing
```bash
# Create .env file for testing
echo "GITHUB_APP_ID=your_app_id" >> .env
echo "GITHUB_APP_INSTALLATION_ID=your_installation_id" >> .env
echo "GITHUB_PRIVATE_KEY_PATH=/path/to/private-key.pem" >> .env
echo "GITHUB_TOKEN=ghp_your_personal_token" >> .env
echo "TEST_REPOSITORY=your-org/test-repo" >> .env
```

## 🔍 Debug Commands

### Check Function Logs
```bash
# When running locally
python function/main.py --insecure --debug

# Check GitHub API access manually
curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/user

# Test GitHub App JWT
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     https://api.github.com/app
```

### Verify GitHub App Permissions
```bash
# Check app installation
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
     https://api.github.com/app/installations/YOUR_INSTALLATION_ID

# Check repository access
curl -H "Authorization: token YOUR_INSTALLATION_TOKEN" \
     https://api.github.com/repos/owner/repo
```

## 🧪 Complete Test Script

Save this as `full_test.py`:

```python
#!/usr/bin/env python3
"""Complete test script for GitHub File Manager Function."""

import os
import sys
import json
import time
import asyncio
import logging
from datetime import datetime

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def main():
    """Run complete test suite."""
    
    print("🚀 GitHub File Manager Function - Complete Test Suite")
    print("=" * 60)
    
    # Load configuration
    config = {
        "github_app": {
            "appId": os.getenv("GITHUB_APP_ID"),
            "installationId": os.getenv("GITHUB_APP_INSTALLATION_ID"),
            "privateKey": load_private_key()
        },
        "github_token": os.getenv("GITHUB_TOKEN"),
        "test_repo": os.getenv("TEST_REPOSITORY", "your-org/test-repo")
    }
    
    # Validate configuration
    if not validate_config(config):
        sys.exit(1)
    
    # Run tests
    tests = [
        ("Personal Access Token", test_token_auth, config["github_token"]),
        ("GitHub App Auth", test_app_auth, config["github_app"]),
        ("File Commit (Token)", test_file_commit_token, config),
        ("File Commit (App)", test_file_commit_app, config),
    ]
    
    results = {}
    for name, test_func, test_config in tests:
        print(f"\n📋 Running: {name}")
        try:
            result = test_func(test_config)
            results[name] = "PASS" if result else "FAIL"
            print(f"   {'✅ PASS' if result else '❌ FAIL'}")
        except Exception as e:
            results[name] = f"ERROR: {e}"
            print(f"   ❌ ERROR: {e}")
    
    # Print summary
    print(f"\n📊 Test Results:")
    print("=" * 40)
    for test, result in results.items():
        status = "✅" if result == "PASS" else "❌"
        print(f"   {status} {test}: {result}")
    
    return all(r == "PASS" for r in results.values())

def load_private_key():
    """Load private key from file or environment."""
    key_path = os.getenv("GITHUB_PRIVATE_KEY_PATH")
    if key_path and os.path.exists(key_path):
        with open(key_path) as f:
            return f.read()
    
    return os.getenv("GITHUB_PRIVATE_KEY")

def validate_config(config):
    """Validate test configuration."""
    issues = []
    
    if not config["github_token"]:
        issues.append("GITHUB_TOKEN not set")
    
    if not config["github_app"]["appId"]:
        issues.append("GITHUB_APP_ID not set")
    
    if not config["github_app"]["installationId"]:
        issues.append("GITHUB_APP_INSTALLATION_ID not set")
    
    if not config["github_app"]["privateKey"]:
        issues.append("GitHub private key not found")
    
    if issues:
        print("❌ Configuration issues:")
        for issue in issues:
            print(f"   - {issue}")
        return False
    
    return True

def test_token_auth(token):
    """Test personal access token authentication."""
    from function.fn import GitHubFileManager
    
    manager = GitHubFileManager(logger=logger, github_token=token)
    headers = manager._get_auth_headers()
    return "Authorization" in headers

def test_app_auth(app_config):
    """Test GitHub App authentication."""
    from function.fn import GitHubFileManager
    
    manager = GitHubFileManager(logger=logger, github_app=app_config)
    
    # Test JWT generation
    jwt_token = manager._generate_jwt_token()
    if not jwt_token:
        return False
    
    # Test installation token
    access_token = manager._get_installation_access_token()
    return bool(access_token)

def test_file_commit_token(config):
    """Test file commit with personal access token."""
    from function.fn import GitHubFileManager
    
    manager = GitHubFileManager(logger=logger, github_token=config["github_token"])
    
    content = f"""# Test File
Generated by GitHub File Manager Function
Timestamp: {datetime.now().isoformat()}
Method: Personal Access Token
"""
    
    result = manager.commit_file(
        repository=config["test_repo"],
        path="tests/token-test.md",
        content=content,
        message="Test commit via personal access token",
        branch="main"
    )
    
    return result["success"]

def test_file_commit_app(config):
    """Test file commit with GitHub App."""
    from function.fn import GitHubFileManager
    
    manager = GitHubFileManager(logger=logger, github_app=config["github_app"])
    
    content = f"""# Test File
Generated by GitHub File Manager Function  
Timestamp: {datetime.now().isoformat()}
Method: GitHub App
App ID: {config["github_app"]["appId"]}
"""
    
    result = manager.commit_file(
        repository=config["test_repo"],
        path="tests/app-test.md", 
        content=content,
        message="Test commit via GitHub App",
        branch="main"
    )
    
    return result["success"]

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
```

Run the complete test:
```bash
# Set environment variables
export GITHUB_APP_ID="123456"
export GITHUB_APP_INSTALLATION_ID="78901234" 
export GITHUB_PRIVATE_KEY_PATH="/path/to/private-key.pem"
export GITHUB_TOKEN="ghp_your_token"
export TEST_REPOSITORY="your-org/test-repo"

# Run test
python full_test.py
```

This comprehensive testing approach will help you identify exactly where the GitHub App authentication is failing! 