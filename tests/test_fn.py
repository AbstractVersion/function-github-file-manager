import base64
import dataclasses
import json
import unittest
from unittest.mock import Mock, patch, MagicMock
import requests

from crossplane.function import logging, resource
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from google.protobuf import duration_pb2 as durationpb
from google.protobuf import json_format
from google.protobuf import struct_pb2 as structpb

from function import fn


class TestGitHubFileManager(unittest.TestCase):
    """Test the GitHubFileManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_logger = Mock()
        self.github_manager = fn.GitHubFileManager("test_token", self.mock_logger)
        
    def test_init(self):
        """Test GitHubFileManager initialization."""
        self.assertEqual(self.github_manager.token, "test_token")
        self.assertEqual(self.github_manager.logger, self.mock_logger)
        self.assertEqual(self.github_manager.headers["Authorization"], "token test_token")
        self.assertEqual(self.github_manager.headers["Accept"], "application/vnd.github.v3+json")
        
    @patch('function.fn.requests.get')
    @patch('function.fn.requests.put')
    def test_commit_new_file(self, mock_put, mock_get):
        """Test committing a new file (file doesn't exist)."""
        # Mock file doesn't exist
        mock_get.return_value.status_code = 404
        
        # Mock successful commit
        mock_put.return_value.status_code = 201
        mock_put.return_value.json.return_value = {
            "content": {
                "sha": "abc123",
                "html_url": "https://github.com/owner/repo/blob/main/path/file.yaml"
            }
        }
        
        result = self.github_manager.commit_file(
            repository="owner/repo",
            path="path/file.yaml",
            content="test content",
            message="Test commit"
        )
        
        # Verify GET request to check file existence
        mock_get.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/contents/path/file.yaml",
            headers=self.github_manager.headers,
            params={"ref": "main"}
        )
        
        # Verify PUT request to commit file
        expected_content = base64.b64encode("test content".encode('utf-8')).decode('ascii')
        mock_put.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/contents/path/file.yaml",
            json={
                "message": "Test commit",
                "content": expected_content,
                "branch": "main"
            },
            headers=self.github_manager.headers
        )
        
        # Verify result
        self.assertEqual(result, {
            "success": True,
            "path": "path/file.yaml",
            "sha": "abc123",
            "githubUrl": "https://github.com/owner/repo/blob/main/path/file.yaml"
        })
        
    @patch('function.fn.requests.get')
    @patch('function.fn.requests.put')
    def test_commit_existing_file(self, mock_put, mock_get):
        """Test updating an existing file."""
        # Mock file exists
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"sha": "existing_sha"}
        
        # Mock successful update
        mock_put.return_value.status_code = 200
        mock_put.return_value.json.return_value = {
            "content": {
                "sha": "new_sha",
                "html_url": "https://github.com/owner/repo/blob/main/path/file.yaml"
            }
        }
        
        result = self.github_manager.commit_file(
            repository="owner/repo",
            path="path/file.yaml",
            content="updated content",
            message="Update file",
            branch="develop"
        )
        
        # Verify GET request includes branch
        mock_get.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/contents/path/file.yaml",
            headers=self.github_manager.headers,
            params={"ref": "develop"}
        )
        
        # Verify PUT request includes SHA for update
        expected_content = base64.b64encode("updated content".encode('utf-8')).decode('ascii')
        mock_put.assert_called_once_with(
            "https://api.github.com/repos/owner/repo/contents/path/file.yaml",
            json={
                "message": "Update file",
                "content": expected_content,
                "branch": "develop",
                "sha": "existing_sha"
            },
            headers=self.github_manager.headers
        )
        
    @patch('function.fn.requests.get')
    @patch('function.fn.requests.put')
    def test_commit_file_failure(self, mock_put, mock_get):
        """Test handling of commit failure."""
        # Mock file doesn't exist
        mock_get.return_value.status_code = 404
        
        # Mock failed commit
        mock_put.return_value.status_code = 422
        mock_put.return_value.text = "Validation failed"
        
        with self.assertRaises(requests.RequestException) as context:
            self.github_manager.commit_file(
                repository="owner/repo",
                path="path/file.yaml",
                content="test content",
                message="Test commit"
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
                input=resource.dict_to_struct({
                    "githubToken": "test_token",
                    "files": [
                        {
                            "repository": "owner/repo",
                            "path": "test/file1.yaml",
                            "content": "content1",
                            "commitMessage": "Add file1"
                        },
                        {
                            "repository": "owner/repo",
                            "path": "test/file2.yaml",
                            "content": "content2",
                            "commitMessage": "Add file2",
                            "branch": "develop"
                        }
                    ]
                }),
                observed=fnv1.State(),
            ),
            expected_files=2,
            expected_success=True
        )
        
        runner = fn.FunctionRunner()
        
        # Mock the GitHubFileManager
        with patch('function.fn.GitHubFileManager') as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager
            
            # Mock successful commits
            mock_manager.commit_file.side_effect = [
                {"success": True, "path": "test/file1.yaml", "sha": "sha1", "githubUrl": "url1"},
                {"success": True, "path": "test/file2.yaml", "sha": "sha2", "githubUrl": "url2"}
            ]
            
            response = await runner.RunFunction(test_case.req, None)
            
            # Verify GitHubFileManager was initialized with correct token
            mock_manager_class.assert_called_once()
            init_args = mock_manager_class.call_args[0]
            self.assertEqual(init_args[0], "test_token")
            
            # Verify correct number of commit_file calls
            self.assertEqual(mock_manager.commit_file.call_count, test_case.expected_files)
            
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
            
    async def test_run_function_missing_token(self) -> None:
        """Test function execution with missing GitHub token."""
        req = fnv1.RunFunctionRequest(
            input=resource.dict_to_struct({
                "files": [
                    {
                        "repository": "owner/repo",
                        "path": "test/file.yaml",
                        "content": "content",
                        "commitMessage": "Add file"
                    }
                ]
            }),
            observed=fnv1.State(),
        )
        
        runner = fn.FunctionRunner()
        response = await runner.RunFunction(req, None)
        
        # Verify function failed with appropriate error
        self.assertEqual(len(response.results), 1)
        self.assertEqual(response.results[0].severity, fnv1.SEVERITY_FATAL)
        self.assertIn("GitHub token is required", response.results[0].message)
        
        # Verify context contains failure info
        context = json_format.MessageToDict(response.context)
        github_context = context["github-file-manager"]
        self.assertEqual(github_context["success"], False)
        self.assertIn("GitHub token is required", github_context["error"])
        
    async def test_run_function_partial_failure(self) -> None:
        """Test function execution with some files failing."""
        req = fnv1.RunFunctionRequest(
            input=resource.dict_to_struct({
                "githubToken": "test_token",
                "files": [
                    {
                        "repository": "owner/repo",
                        "path": "test/file1.yaml",
                        "content": "content1",
                        "commitMessage": "Add file1"
                    },
                    {
                        "repository": "owner/repo",
                        "path": "test/file2.yaml",
                        "content": "content2",
                        "commitMessage": "Add file2"
                    }
                ]
            }),
            observed=fnv1.State(),
        )
        
        runner = fn.FunctionRunner()
        
        # Mock the GitHubFileManager
        with patch('function.fn.GitHubFileManager') as mock_manager_class:
            mock_manager = Mock()
            mock_manager_class.return_value = mock_manager
            
            # Mock mixed success/failure
            mock_manager.commit_file.side_effect = [
                {"success": True, "path": "test/file1.yaml", "sha": "sha1", "githubUrl": "url1"},
                requests.RequestException("API error")
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
            self.assertEqual(github_context["filesProcessed"], 2)
            self.assertEqual(len(github_context["results"]), 2)
            self.assertEqual(len(github_context["errors"]), 1)
            
    async def test_run_function_missing_file_fields(self) -> None:
        """Test function execution with missing required file fields."""
        req = fnv1.RunFunctionRequest(
            input=resource.dict_to_struct({
                "githubToken": "test_token",
                "files": [
                    {
                        "repository": "owner/repo",
                        "path": "test/file.yaml",
                        # Missing content and commitMessage
                    }
                ]
            }),
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
        self.assertEqual(len(github_context["errors"]), 1)
        self.assertIn("Missing required fields", github_context["errors"][0])


if __name__ == "__main__":
    unittest.main()
