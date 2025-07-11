"""Tests for GitHub File Manager Function."""

import base64
import dataclasses
import unittest
from unittest.mock import Mock, patch, MagicMock

import requests
from crossplane.function import logging
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from google.protobuf import json_format

from function import fn

# Test credentials - these are not real credentials
TEST_TOKEN = "test_token"  # noqa: S105
TEST_PRIVATE_KEY = (
    "-----BEGIN RSA PRIVATE KEY-----\ntest_key\n-----END RSA PRIVATE KEY-----"
)


class TestSecretResolution(unittest.TestCase):
    """Test secret resolution functionality."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_logger = Mock()

    @patch('function.fn.client.CoreV1Api')
    @patch('function.fn.config.load_incluster_config')
    def test_resolve_secret_value_success(self, mock_load_config, mock_v1_api_class):
        """Test successful secret resolution."""
        # Mock Kubernetes client
        mock_v1_api = Mock()
        mock_v1_api_class.return_value = mock_v1_api
        
        # Mock secret data
        mock_secret = Mock()
        mock_secret.data = {
            "githubAppID": base64.b64encode(b"123456").decode('utf-8'),
            "githubAppPrivateKey": base64.b64encode(b"test-private-key").decode('utf-8')
        }
        mock_v1_api.read_namespaced_secret.return_value = mock_secret
        
        # Test secret resolution
        secret_ref = {
            "name": "github-app-repo-creds",
            "namespace": "argocd", 
            "key": "githubAppID"
        }
        
        result = fn.resolve_secret_value(secret_ref, self.mock_logger)
        
        self.assertEqual(result, "123456")
        mock_v1_api.read_namespaced_secret.assert_called_once_with(
            name="github-app-repo-creds", 
            namespace="argocd"
        )

    @patch('function.fn.client.CoreV1Api')
    @patch('function.fn.config.load_incluster_config')
    def test_resolve_secret_value_missing_key(self, mock_load_config, mock_v1_api_class):
        """Test secret resolution with missing key."""
        mock_v1_api = Mock()
        mock_v1_api_class.return_value = mock_v1_api
        
        mock_secret = Mock()
        mock_secret.data = {"other-key": "dGVzdA=="}  # base64 encoded "test"
        mock_v1_api.read_namespaced_secret.return_value = mock_secret
        
        secret_ref = {
            "name": "test-secret",
            "namespace": "default",
            "key": "missing-key"
        }
        
        result = fn.resolve_secret_value(secret_ref, self.mock_logger)
        
        self.assertIsNone(result)
        self.mock_logger.error.assert_called()

    def test_resolve_credential_value_direct_string(self):
        """Test resolving direct string credential."""
        result = fn.resolve_credential_value("direct-value", self.mock_logger)
        self.assertEqual(result, "direct-value")

    @patch('function.fn.resolve_secret_value')
    def test_resolve_credential_value_secret_ref(self, mock_resolve_secret):
        """Test resolving secret reference credential."""
        mock_resolve_secret.return_value = "resolved-value"
        
        cred_value = {
            "secretRef": {
                "name": "test-secret",
                "key": "test-key"
            }
        }
        
        result = fn.resolve_credential_value(cred_value, self.mock_logger)
        
        self.assertEqual(result, "resolved-value")
        mock_resolve_secret.assert_called_once_with(
            {"name": "test-secret", "key": "test-key"}, 
            self.mock_logger
        )

    def test_resolve_credential_value_invalid_format(self):
        """Test resolving invalid credential format."""
        result = fn.resolve_credential_value(123, self.mock_logger)  # Invalid type
        self.assertIsNone(result)
        self.mock_logger.error.assert_called()


class TestGitHubFileManager(unittest.TestCase):
    """Test the GitHubFileManager class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_logger = Mock()
        self.github_manager_token = fn.GitHubFileManager(
            logger=self.mock_logger, github_token=TEST_TOKEN
        )
        self.github_manager_app = fn.GitHubFileManager(
            logger=self.mock_logger,
            github_app={
                "appId": "12345",
                "installationId": "67890",
                "privateKey": TEST_PRIVATE_KEY,
            },
        )

    def test_init_with_token(self):
        """Test initialization with personal access token."""
        self.assertEqual(self.github_manager_token.github_token, TEST_TOKEN)
        self.assertEqual(self.github_manager_token.logger, self.mock_logger)
        self.assertIsNone(self.github_manager_token.github_app)
        self.assertEqual(
            self.github_manager_token.headers["Accept"],
            "application/vnd.github.v3+json",
        )

    def test_init_with_github_app(self):
        """Test initialization with GitHub App."""
        self.assertIsNone(self.github_manager_app.github_token)
        self.assertIsNotNone(self.github_manager_app.github_app)
        self.assertEqual(self.github_manager_app.github_app["appId"], "12345")

    def test_init_no_auth(self):
        """Test initialization fails without authentication."""
        with self.assertRaises(ValueError) as context:
            fn.GitHubFileManager(logger=self.mock_logger)
        self.assertIn(
            "Either github_token or github_app credentials must be provided",
            str(context.exception),
        )

    def test_init_both_auth(self):
        """Test initialization fails with both authentication methods."""
        with self.assertRaises(ValueError) as context:
            fn.GitHubFileManager(
                logger=self.mock_logger,
                github_token=TEST_TOKEN,
                github_app={
                    "appId": "123",
                    "installationId": "456",
                    "privateKey": "key",
                },
            )
        self.assertIn(
            "Cannot use both github_token and github_app authentication simultaneously",
            str(context.exception),
        )

    @patch("function.fn.requests.get")
    @patch("function.fn.requests.put")
    def test_commit_new_file_with_token(self, mock_put, mock_get):
        """Test committing a new file with personal access token."""
        # Mock file doesn't exist
        mock_get.return_value.status_code = 404

        # Mock successful commit
        mock_put.return_value.status_code = 201
        mock_put.return_value.json.return_value = {
            "content": {"sha": "new_sha"},
            "commit": {"sha": "commit_sha"},
        }

        result = self.github_manager_token.commit_file(
            repository="owner/repo",
            path="path/file.yaml",
            content="test content",
            message="Test commit",
        )

        # Verify GET request to check file existence
        expected_headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Crossplane-GitHub-Function",
            "Authorization": "token test_token",
        }
        mock_get.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/contents/path/file.yaml",
            headers=expected_headers,
            params={"ref": "main"},
            timeout=30,
        )

        # Verify PUT request to commit file
        expected_content = base64.b64encode(b"test content").decode("ascii")
        mock_put.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/contents/path/file.yaml",
            json={
                "message": "Test commit",
                "content": expected_content,
                "branch": "main",
            },
            headers=expected_headers,
            timeout=30,
        )

        # Verify result
        self.assertEqual(
            result,
            {
                "success": True,
                "path": "path/file.yaml",
                "sha": "new_sha",
                "githubUrl": "https://github.com/owner/repo/blob/main/path/file.yaml",
            },
        )

    @patch("function.fn.requests.post")
    @patch("function.fn.requests.get")
    @patch("function.fn.requests.put")
    def test_commit_new_file_with_github_app(self, mock_put, mock_get, mock_post):
        """Test committing a new file with GitHub App authentication."""
        # Mock installation access token response
        mock_post.return_value.status_code = 201
        mock_post.return_value.json.return_value = {
            "token": "ghs_installation_token",
            "expires_at": "2024-01-01T12:00:00Z",
        }

        # Mock file doesn't exist
        mock_get.return_value.status_code = 404

        # Mock successful commit
        mock_put.return_value.status_code = 201
        mock_put.return_value.json.return_value = {
            "content": {"sha": "new_sha"},
            "commit": {"sha": "commit_sha"},
        }

        with patch("function.fn.jwt.encode") as mock_jwt:
            mock_jwt.return_value = "jwt_token"

            result = self.github_manager_app.commit_file(
                repository="owner/repo",
                path="path/file.yaml",
                content="test content",
                message="Test commit",
            )

        # Verify JWT was created
        mock_jwt.assert_called_once()

        # Verify installation token request
        mock_post.assert_called_once_with(
            "https://api.github.com/app/installations/67890/access_tokens",
            headers={
                "Authorization": "Bearer jwt_token",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=30,
        )

        # Verify GET and PUT requests used installation token
        expected_headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Crossplane-GitHub-Function",
            "Authorization": "token ghs_installation_token",
        }

        mock_get.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/contents/path/file.yaml",
            headers=expected_headers,
            params={"ref": "main"},
            timeout=30,
        )

        expected_content = base64.b64encode(b"test content").decode("ascii")
        mock_put.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/contents/path/file.yaml",
            json={
                "message": "Test commit",
                "content": expected_content,
                "branch": "main",
            },
            headers=expected_headers,
            timeout=30,
        )

        # Verify result
        self.assertEqual(
            result,
            {
                "success": True,
                "path": "path/file.yaml",
                "sha": "new_sha",
                "githubUrl": "https://github.com/owner/repo/blob/main/path/file.yaml",
            },
        )

    @patch("function.fn.requests.get")
    @patch("function.fn.requests.put")
    def test_commit_existing_file(self, mock_put, mock_get):
        """Test updating an existing file."""
        # Mock file exists
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"sha": "existing_sha"}

        # Mock successful update
        mock_put.return_value.status_code = 200
        mock_put.return_value.json.return_value = {
            "content": {"sha": "updated_sha"},
            "commit": {"sha": "commit_sha"},
        }

        self.github_manager_token.commit_file(
            repository="owner/repo",
            path="path/file.yaml",
            content="updated content",
            message="Update file",
            branch="develop",
        )

        # Verify GET request includes branch
        expected_headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Crossplane-GitHub-Function",
            "Authorization": "token test_token",
        }
        mock_get.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/contents/path/file.yaml",
            headers=expected_headers,
            params={"ref": "develop"},
            timeout=30,
        )

        # Verify PUT request includes SHA for update
        expected_content = base64.b64encode(b"updated content").decode("ascii")
        mock_put.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/contents/path/file.yaml",
            json={
                "message": "Update file",
                "content": expected_content,
                "branch": "develop",
                "sha": "existing_sha",
            },
            headers=expected_headers,
            timeout=30,
        )

    @patch("function.fn.requests.get")
    @patch("function.fn.requests.put")
    def test_commit_file_failure(self, mock_put, mock_get):
        """Test handling of commit failure."""
        # Mock file doesn't exist
        mock_get.return_value.status_code = 404

        # Mock failed commit
        mock_put.return_value.status_code = 422
        mock_put.return_value.text = "Validation failed"

        with self.assertRaises(requests.RequestException) as context:
            self.github_manager_token.commit_file(
                repository="owner/repo",
                path="path/file.yaml",
                content="test content",
                message="Test commit",
            )

        self.assertIn("Failed to commit", str(context.exception))
        self.assertIn("422", str(context.exception))


class TestFunctionRunner(unittest.IsolatedAsyncioTestCase):
    """Test the FunctionRunner class."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Allow larger diffs for better error messages
        self.maxDiff = 4000

        # Disable logging for cleaner test output
        logging.configure(level=logging.Level.DISABLED)

    async def test_run_function_success(self) -> None:
        """Test successful function execution."""

        @dataclasses.dataclass
        class TestCase:
            reason: str
            req: fnv1.RunFunctionRequest
            expected_files: int
            expected_success: bool

        test_case = TestCase(
            reason="Should successfully commit files to GitHub",
            req=fnv1.RunFunctionRequest(
                meta=fnv1.RequestMeta(tag="test"),
                input={
                    "githubToken": TEST_TOKEN,
                    "files": [
                        {
                            "repository": "owner/repo",
                            "path": "test/file1.yaml",
                            "content": "content1",
                            "commitMessage": "Add file1",
                        },
                        {
                            "repository": "owner/repo",
                            "path": "test/file2.yaml",
                            "content": "content2",
                            "commitMessage": "Add file2",
                        },
                    ],
                },
            ),
            expected_files=2,
            expected_success=True,
        )

        runner = fn.FunctionRunner()

        # Mock the GitHubFileManager
        with patch("function.fn.GitHubFileManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager

            # Mock successful commits
            mock_manager.commit_file.side_effect = [
                {
                    "success": True,
                    "path": "test/file1.yaml",
                    "sha": "sha1",
                    "githubUrl": "url1",
                },
                {
                    "success": True,
                    "path": "test/file2.yaml",
                    "sha": "sha2",
                    "githubUrl": "url2",
                },
            ]

            response = await runner.RunFunction(test_case.req, None)

            # Verify GitHubFileManager was initialized correctly
            mock_manager_class.assert_called_once()
            call_args, call_kwargs = mock_manager_class.call_args
            self.assertEqual(call_kwargs["github_token"], TEST_TOKEN)
            self.assertIsNone(call_kwargs["github_app"])

            # Verify correct number of commit_file calls
            self.assertEqual(
                mock_manager.commit_file.call_count, test_case.expected_files
            )

            # Verify function results
            self.assertEqual(len(response.results), 1)
            self.assertEqual(response.results[0].severity, fnv1.SEVERITY_NORMAL)
            self.assertIn("Successfully committed 2 files", response.results[0].message)

            # Verify context contains success info
            context = json_format.MessageToDict(response.context)
            github_context = context["github-file-manager"]
            self.assertEqual(github_context["success"], test_case.expected_success)
            self.assertEqual(github_context["filesProcessed"], test_case.expected_files)
            self.assertEqual(len(github_context["results"]), test_case.expected_files)

    async def test_run_function_success_github_app(self) -> None:
        """Test successful function execution with GitHub App authentication."""
        req = fnv1.RunFunctionRequest(
            meta=fnv1.RequestMeta(tag="test"),
            input={
                "githubApp": {
                    "appId": "12345",
                    "installationId": "67890",
                    "privateKey": TEST_PRIVATE_KEY,
                },
                "files": [
                    {
                        "repository": "owner/repo",
                        "path": "test/file1.yaml",
                        "content": "content1",
                        "commitMessage": "Add file1",
                    }
                ],
            },
            observed=fnv1.State(),
        )

        runner = fn.FunctionRunner()

        # Mock the GitHubFileManager
        with patch("function.fn.GitHubFileManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager

            # Mock successful commit
            mock_manager.commit_file.return_value = {
                "success": True,
                "path": "test/file1.yaml",
                "sha": "sha1",
                "githubUrl": "url1",
            }

            response = await runner.RunFunction(req, None)

            # Verify GitHubFileManager was initialized with GitHub App
            mock_manager_class.assert_called_once()
            call_args, call_kwargs = mock_manager_class.call_args
            self.assertIsNone(call_kwargs["github_token"])
            self.assertIsNotNone(call_kwargs["github_app"])
            self.assertEqual(call_kwargs["github_app"]["appId"], "12345")

            # Verify function results
            self.assertEqual(len(response.results), 1)
            self.assertEqual(response.results[0].severity, fnv1.SEVERITY_NORMAL)
            self.assertIn("Successfully committed 1 files", response.results[0].message)

    async def test_run_function_missing_auth(self) -> None:
        """Test function execution with missing authentication."""
        req = fnv1.RunFunctionRequest(
            meta=fnv1.RequestMeta(tag="test"),
            input={
                "files": [
                    {
                        "repository": "owner/repo",
                        "path": "test/file1.yaml",
                        "content": "content1",
                        "commitMessage": "Add file1",
                    }
                ]
            },
            observed=fnv1.State(),
        )

        runner = fn.FunctionRunner()
        response = await runner.RunFunction(req, None)

        # Verify function failed with appropriate error
        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].severity, fnv1.SEVERITY_FATAL)
        self.assertIn(
            "Either githubToken or githubApp authentication must be provided",
            response.results[0].message,
        )

        # Verify context contains failure info
        context = json_format.MessageToDict(response.context)
        github_context = context["github-file-manager"]
        self.assertEqual(github_context["success"], False)
        self.assertIn(
            "Either githubToken or githubApp authentication must be provided",
            github_context["error"],
        )

    async def test_run_function_partial_failure(self) -> None:
        """Test function execution with some files failing."""
        req = fnv1.RunFunctionRequest(
            meta=fnv1.RequestMeta(tag="test"),
            input={
                "githubToken": TEST_TOKEN,
                "files": [
                    {
                        "repository": "owner/repo",
                        "path": "test/file1.yaml",
                        "content": "content1",
                        "commitMessage": "Add file1",
                    },
                    {
                        "repository": "owner/repo",
                        "path": "test/file2.yaml",
                        "content": "content2",
                        "commitMessage": "Add file2",
                    },
                ],
            },
            observed=fnv1.State(),
        )

        runner = fn.FunctionRunner()

        # Mock the GitHubFileManager
        with patch("function.fn.GitHubFileManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager

            # Mock mixed success/failure
            mock_manager.commit_file.side_effect = [
                {
                    "success": True,
                    "path": "test/file1.yaml",
                    "sha": "sha1",
                    "githubUrl": "url1",
                },
                requests.RequestException("API error"),
            ]

            response = await runner.RunFunction(req, None)

            # Verify function completed with warnings
            self.assertEqual(len(response.results), 1)
            self.assertEqual(response.results[0].severity, fnv1.SEVERITY_WARNING)
            self.assertIn("completed with 1 errors", response.results[0].message)

            # Verify context contains mixed results
            context = json_format.MessageToDict(response.context)
            github_context = context["github-file-manager"]
            self.assertEqual(github_context["success"], False)
            self.assertEqual(github_context["filesProcessed"], 1)
            self.assertEqual(len(github_context["results"]), 1)
            self.assertEqual(len(github_context["errors"]), 1)

    async def test_run_function_missing_file_fields(self) -> None:
        """Test function execution with missing required file fields."""
        req = fnv1.RunFunctionRequest(
            meta=fnv1.RequestMeta(tag="test"),
            input={
                "githubToken": TEST_TOKEN,
                "files": [
                    {
                        "repository": "owner/repo",
                        "path": "test/file1.yaml",
                        # Missing content and commitMessage
                    }
                ],
            },
            observed=fnv1.State(),
        )

        runner = fn.FunctionRunner()
        response = await runner.RunFunction(req, None)

        # Verify function completed with warnings due to validation errors
        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].severity, fnv1.SEVERITY_WARNING)

        # Verify context contains error details
        context = json_format.MessageToDict(response.context)
        github_context = context["github-file-manager"]
        self.assertEqual(github_context["success"], False)
        self.assertEqual(github_context["filesProcessed"], 0)
        self.assertEqual(len(github_context["errors"]), 1)

    @patch('function.fn.resolve_credential_value')
    async def test_run_function_with_secret_references(self, mock_resolve_cred):
        """Test function execution with secret references."""
        # Mock credential resolution
        mock_resolve_cred.side_effect = lambda val, logger: {
            'secretRef': {
                'name': 'github-app-repo-creds',
                'key': 'githubAppID'
            }
        }.get('secretRef', {}).get('key') == 'githubAppID' and "123456" or \
        {
            'secretRef': {
                'name': 'github-app-repo-creds', 
                'key': 'githubAppInstallationID'
            }
        }.get('secretRef', {}).get('key') == 'githubAppInstallationID' and "78901234" or \
        {
            'secretRef': {
                'name': 'github-app-repo-creds',
                'key': 'githubAppPrivateKey'
            }
        }.get('secretRef', {}).get('key') == 'githubAppPrivateKey' and TEST_PRIVATE_KEY or str(val)
        
        # Simplified mock - just return expected values in order
        mock_resolve_cred.side_effect = ["123456", "78901234", TEST_PRIVATE_KEY]

        req = fnv1.RunFunctionRequest(
            meta=fnv1.RequestMeta(tag="test"),
            input={
                "githubApp": {
                    "appId": {
                        "secretRef": {
                            "name": "github-app-repo-creds",
                            "namespace": "argocd",
                            "key": "githubAppID"
                        }
                    },
                    "installationId": {
                        "secretRef": {
                            "name": "github-app-repo-creds", 
                            "namespace": "argocd",
                            "key": "githubAppInstallationID"
                        }
                    },
                    "privateKey": {
                        "secretRef": {
                            "name": "github-app-repo-creds",
                            "namespace": "argocd", 
                            "key": "githubAppPrivateKey"
                        }
                    }
                },
                "files": [
                    {
                        "repository": "owner/repo",
                        "path": "test/file1.yaml",
                        "content": "content1",
                        "commitMessage": "Add file1",
                    }
                ],
            },
            observed=fnv1.State(),
        )

        runner = fn.FunctionRunner()

        # Mock the GitHubFileManager
        with patch("function.fn.GitHubFileManager") as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager

            # Mock successful commit
            mock_manager.commit_file.return_value = {
                "success": True,
                "path": "test/file1.yaml", 
                "sha": "sha1",
                "githubUrl": "url1",
            }

            response = await runner.RunFunction(req, None)

            # Verify credential resolution was called
            self.assertEqual(mock_resolve_cred.call_count, 3)

            # Verify GitHubFileManager was initialized with resolved credentials
            mock_manager_class.assert_called_once()
            call_args, call_kwargs = mock_manager_class.call_args
            self.assertIsNone(call_kwargs["github_token"])
            self.assertIsNotNone(call_kwargs["github_app"])
            self.assertEqual(call_kwargs["github_app"]["appId"], "123456")
            self.assertEqual(call_kwargs["github_app"]["installationId"], "78901234") 
            self.assertEqual(call_kwargs["github_app"]["privateKey"], TEST_PRIVATE_KEY)

            # Verify function succeeded
            self.assertEqual(len(response.results), 1)
            self.assertEqual(response.results[0].severity, fnv1.SEVERITY_NORMAL)
