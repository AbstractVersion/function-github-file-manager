"""A Crossplane composition function that commits files to GitHub repositories."""

import base64
import grpc
import requests
from crossplane.function import logging, response
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from crossplane.function.proto.v1 import run_function_pb2_grpc as grpcv1


class GitHubFileManager:
    """GitHub API client for file operations."""
    
    def __init__(self, token: str, logger):
        """Initialize with GitHub token and logger."""
        self.token = token
        self.logger = logger
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "kubecore-function-github-file-manager"
        }
    
    def commit_file(self, repository: str, path: str, content: str, 
                   message: str, branch: str = "main") -> dict:
        """
        Commit a file to a GitHub repository.
        
        Args:
            repository: GitHub repository in format "owner/repo"
            path: File path within the repository
            content: File content to commit
            message: Commit message
            branch: Target branch (default: main)
            
        Returns:
            dict: GitHub API response with commit info
            
        Raises:
            requests.RequestException: If GitHub API request fails
        """
        url = f"https://api.github.com/repos/{repository}/contents/{path}"
        
        # Check if file exists (to get SHA for updates)
        current_sha = None
        try:
            get_response = requests.get(url, headers=self.headers, params={"ref": branch})
            if get_response.status_code == 200:
                current_sha = get_response.json().get("sha")
                self.logger.info(f"File {path} exists, will update with SHA: {current_sha}")
            elif get_response.status_code == 404:
                self.logger.info(f"File {path} does not exist, will create new file")
            else:
                self.logger.warning(f"Unexpected response checking file existence: {get_response.status_code}")
        except Exception as e:
            self.logger.warning(f"Error checking file existence: {e}")
        
        # Prepare commit data
        commit_data = {
            "message": message,
            "content": base64.b64encode(content.encode('utf-8')).decode('ascii'),
            "branch": branch
        }
        
        # Add SHA if updating existing file
        if current_sha:
            commit_data["sha"] = current_sha
        
        # Commit the file
        self.logger.info(f"Committing file {path} to {repository}/{branch}")
        commit_response = requests.put(url, json=commit_data, headers=self.headers)
        
        if commit_response.status_code in [200, 201]:
            result = commit_response.json()
            self.logger.info(f"Successfully committed {path} with SHA: {result['content']['sha']}")
            return {
                "success": True,
                "path": path,
                "sha": result['content']['sha'],
                "githubUrl": result['content']['html_url']
            }
        else:
            error_msg = f"Failed to commit {path}: {commit_response.status_code} - {commit_response.text}"
            self.logger.error(error_msg)
            raise requests.RequestException(error_msg)


class FunctionRunner(grpcv1.FunctionRunnerService):
    """A FunctionRunner handles gRPC RunFunctionRequests."""

    def __init__(self):
        """Create a new FunctionRunner."""
        self.log = logging.get_logger()

    async def RunFunction(
        self, req: fnv1.RunFunctionRequest, _: grpc.aio.ServicerContext
    ) -> fnv1.RunFunctionResponse:
        """Run the GitHub file manager function."""
        log = self.log.bind(tag=req.meta.tag)
        log.info("Running GitHub file manager function")

        rsp = response.to(req)
        
        try:
            # Extract input data from protobuf struct
            if not req.input:
                raise ValueError("No input provided")
            
            # Convert protobuf struct to dictionary
            from google.protobuf import json_format
            input_dict = json_format.MessageToDict(req.input)
            
            # Get GitHub token and files from input
            github_token = input_dict.get("githubToken")
            files = input_dict.get("files", [])
            
            if not github_token:
                raise ValueError("GitHub token is required")
            
            if not files:
                raise ValueError("At least one file must be specified")
            
            log.info(f"Processing {len(files)} files")
            
            # Initialize GitHub client
            github_client = GitHubFileManager(github_token, log)
            
            # Process each file
            results = []
            errors = []
            
            for file_spec in files:
                try:
                    # Validate required fields
                    repository = file_spec.get("repository")
                    path = file_spec.get("path")
                    content = file_spec.get("content")
                    commit_message = file_spec.get("commitMessage")
                    branch = file_spec.get("branch", "main")
                    
                    if not all([repository, path, content, commit_message]):
                        raise ValueError(f"Missing required fields for file {path}")
                    
                    # Commit the file
                    result = github_client.commit_file(
                        repository=repository,
                        path=path,
                        content=content,
                        message=commit_message,
                        branch=branch
                    )
                    
                    results.append(result)
                    log.info(f"Successfully processed file: {path}")
                    
                except Exception as e:
                    error_msg = f"Failed to process file {file_spec.get('path', 'unknown')}: {str(e)}"
                    errors.append(error_msg)
                    log.error(error_msg)
                    
                    # Add failed result
                    results.append({
                        "success": False,
                        "path": file_spec.get("path", "unknown"),
                        "error": str(e)
                    })
            
            # Create response context with results
            response_context = {
                "github-file-manager": {
                    "success": len(errors) == 0,
                    "filesProcessed": len(files),
                    "results": results,
                    "errors": errors
                }
            }
            
            # Add context to response
            rsp.context.update(response_context)
            
            if errors:
                log.warning(f"Function completed with {len(errors)} errors")
                # Set function result to indicate partial failure
                rsp.results.append(
                    fnv1.Result(
                        severity=fnv1.SEVERITY_WARNING,
                        message=f"GitHub file manager completed with {len(errors)} errors. Check context for details."
                    )
                )
            else:
                log.info("All files processed successfully")
                rsp.results.append(
                    fnv1.Result(
                        severity=fnv1.SEVERITY_NORMAL,
                        message=f"Successfully committed {len(files)} files to GitHub"
                    )
                )
            
        except Exception as e:
            error_msg = f"Function failed: {str(e)}"
            log.error(error_msg)
            
            # Add error context
            rsp.context.update({
                "github-file-manager": {
                    "success": False,
                    "error": error_msg
                }
            })
            
            # Add fatal error result
            rsp.results.append(
                fnv1.Result(
                    severity=fnv1.SEVERITY_FATAL,
                    message=error_msg
                )
            )

        return rsp
