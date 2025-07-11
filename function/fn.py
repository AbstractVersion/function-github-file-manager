"""GitHub File Manager Function for Crossplane.

A Crossplane composition function that commits files directly to GitHub repositories
using either personal access tokens or GitHub App authentication.
"""

import base64
import json
import time

import grpc.aio
import jwt
import requests
from crossplane.function import logging
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from google.protobuf import json_format
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Constants for HTTP status codes
HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NOT_FOUND = 404

# Security: timeout for requests
REQUEST_TIMEOUT = 30


def resolve_secret_value(secret_ref: dict, logger) -> str | None:
    """Resolve a Kubernetes secret reference to its actual value.
    
    Args:
        secret_ref: Dictionary with 'name', 'namespace', and 'key' fields
        logger: Logger instance
        
    Returns:
        The secret value as a string, or None if not found
    """
    try:
        # Load Kubernetes config (in-cluster config for function pods)
        try:
            config.load_incluster_config()
        except config.ConfigException:
            # Fallback to local config for development
            config.load_kube_config()
            
        v1 = client.CoreV1Api()
        
        name = secret_ref.get("name")
        namespace = secret_ref.get("namespace", "default")
        key = secret_ref.get("key")
        
        if not all([name, key]):
            logger.error(f"Invalid secret reference: {secret_ref}")
            return None
            
        logger.info(f"Resolving secret {namespace}/{name} key {key}")
        
        # Get the secret
        secret = v1.read_namespaced_secret(name=name, namespace=namespace)
        
        if key not in secret.data:
            logger.error(f"Key '{key}' not found in secret {namespace}/{name}")
            return None
            
        # Decode from base64
        value = base64.b64decode(secret.data[key]).decode('utf-8')
        logger.info(f"Successfully resolved secret {namespace}/{name} key {key}")
        return value
        
    except ApiException as e:
        logger.error(f"Kubernetes API error resolving secret: {e}")
        return None
    except Exception as e:
        logger.error(f"Error resolving secret reference: {e}")
        return None


def resolve_credential_value(cred_value, logger) -> str | None:
    """Resolve a credential value that might be a direct string or secret reference.
    
    Args:
        cred_value: Either a string value or a dict with 'secretRef'
        logger: Logger instance
        
    Returns:
        The resolved credential value as a string
    """
    if isinstance(cred_value, str):
        # Direct string value
        return cred_value
    elif isinstance(cred_value, dict) and "secretRef" in cred_value:
        # Secret reference
        return resolve_secret_value(cred_value["secretRef"], logger)
    else:
        logger.error(f"Invalid credential value format: {cred_value}")
        return None


class GitHubFileManager:
    """GitHub API client for file operations."""

    def __init__(
        self,
        logger,
        github_token: str | None = None,
        github_app: dict | None = None,
    ):
        """Initialize with GitHub authentication and logger.

        Args:
            logger: Logger instance
            github_token: GitHub personal access token (optional)
            github_app: GitHub App credentials dict with appId,
                        installationId, privateKey (optional)
        """
        self.logger = logger
        self.github_token = github_token
        self.github_app = github_app
        self.access_token = None
        self.token_expires_at = None

        # Validate authentication
        if not github_token and not github_app:
            msg = "Either github_token or github_app credentials must be provided"
            raise ValueError(msg)

        if github_token and github_app:
            msg = (
                "Cannot use both github_token and github_app "
                "authentication simultaneously"
            )
            raise ValueError(msg)

        # Initialize headers
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Crossplane-GitHub-Function",
        }

    def _generate_jwt_token(self) -> str:
        """Generate a JWT token for GitHub App authentication."""
        if not self.github_app:
            msg = "GitHub App credentials not provided"
            raise ValueError(msg)

        # JWT payload
        now = int(time.time())
        payload = {
            "iat": now - 60,  # issued 1 minute ago to account for clock skew
            "exp": now + 600,  # expires in 10 minutes
            "iss": self.github_app["appId"],
        }

        # Generate JWT token using the private key
        jwt_token = jwt.encode(
            payload,
            self.github_app["privateKey"],
            algorithm="RS256",
        )
        return jwt_token

    def _get_installation_access_token(self) -> str:
        """Get an installation access token using GitHub App authentication."""
        if not self.github_app:
            msg = "GitHub App credentials not provided"
            raise ValueError(msg)

        # Check if we have a valid token
        if (
            self.access_token
            and self.token_expires_at
            and time.time() < self.token_expires_at
        ):
            return self.access_token

        jwt_token = self._generate_jwt_token()
        installation_id = self.github_app["installationId"]
        url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"

        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github.v3+json",
        }

        self.logger.info(
            f"Getting installation access token for installation {installation_id}"
        )
        response = requests.post(url, headers=headers, timeout=REQUEST_TIMEOUT)

        if response.status_code != HTTP_CREATED:
            error_msg = (
                f"Failed to get installation access token: "
                f"{response.status_code} - {response.text}"
            )
            self.logger.error(error_msg)
            raise requests.RequestException(error_msg)

        token_data = response.json()
        self.access_token = token_data["token"]

        # Parse expiration time (subtract 5 minutes for safety)
        import datetime

        expires_at = datetime.datetime.fromisoformat(
            token_data["expires_at"].replace("Z", "+00:00")
        )
        self.token_expires_at = expires_at.timestamp() - (5 * 60)

        self.logger.info(
            f"Successfully obtained installation access token "
            f"(expires at {token_data['expires_at']})"
        )
        return self.access_token

    def _get_auth_headers(self) -> dict:
        """Get authentication headers based on configured method."""
        headers = self.headers.copy()

        if self.github_token:
            headers["Authorization"] = f"token {self.github_token}"
        elif self.github_app:
            access_token = self._get_installation_access_token()
            headers["Authorization"] = f"token {access_token}"
        else:
            msg = "No authentication method configured"
            raise ValueError(msg)

        return headers

    def commit_file(
        self,
        repository: str,
        path: str,
        content: str,
        message: str,
        branch: str = "main",
    ) -> dict:
        """Commit a file to a GitHub repository.

        Args:
            repository: GitHub repository in format "owner/repo"
            path: File path within repository
            content: File content as string
            message: Commit message
            branch: Target branch (default: main)

        Returns:
            dict: GitHub API response with commit info

        Raises:
            requests.RequestException: If GitHub API request fails
        """
        url = f"https://api.github.com/repos/{repository}/contents/{path}"
        auth_headers = self._get_auth_headers()

        # Encode content as base64
        encoded_content = base64.b64encode(content.encode()).decode("ascii")

        # Check if file exists to get SHA for update
        current_sha = None
        try:
            get_response = requests.get(
                url,
                headers=auth_headers,
                params={"ref": branch},
                timeout=REQUEST_TIMEOUT,
            )
            if get_response.status_code == HTTP_OK:
                current_sha = get_response.json().get("sha")
                self.logger.info(
                    f"File {path} exists, will update with SHA: {current_sha}"
                )
            elif get_response.status_code == HTTP_NOT_FOUND:
                self.logger.info(f"File {path} does not exist, will create new file")
            else:
                self.logger.warning(
                    f"Unexpected response checking file existence: "
                    f"{get_response.status_code}"
                )
        except Exception as e:
            self.logger.warning(f"Error checking file existence: {e}")

        # Prepare commit data
        commit_data = {
            "message": message,
            "content": encoded_content,
            "branch": branch,
        }

        if current_sha:
            commit_data["sha"] = current_sha

        # Commit the file
        self.logger.info(f"Committing file {path} to {repository}/{branch}")
        commit_response = requests.put(
            url,
            json=commit_data,
            headers=auth_headers,
            timeout=REQUEST_TIMEOUT,
        )

        if commit_response.status_code in [HTTP_OK, HTTP_CREATED]:
            result = commit_response.json()
            self.logger.info(
                f"Successfully committed {path} with SHA: {result['content']['sha']}"
            )
            return {
                "success": True,
                "path": path,
                "sha": result["content"]["sha"],
                "githubUrl": f"https://github.com/{repository}/blob/{branch}/{path}",
            }
        else:
            error_msg = (
                f"Failed to commit {path}: "
                f"{commit_response.status_code} - {commit_response.text}"
            )
            self.logger.error(error_msg)
            raise requests.RequestException(error_msg)


class FunctionRunner:
    """Main function runner for Crossplane composition function."""

    def __init__(self):
        """Initialize the function runner."""
        self.log = logging.get_logger()

    async def RunFunction(  # noqa: PLR0915, C901
        self, req: fnv1.RunFunctionRequest, _: grpc.aio.ServicerContext
    ) -> fnv1.RunFunctionResponse:
        """Run the GitHub file manager function."""
        log = self.log
        log.info("Starting GitHub file manager function")

        # Initialize response
        rsp = fnv1.RunFunctionResponse()

        try:
            # Extract input data from protobuf struct
            if not req.input:
                msg = "No input provided"
                raise ValueError(msg)

            # Convert protobuf struct to dictionary
            input_dict = json_format.MessageToDict(req.input)
            log.info(f"Input received: {json.dumps(input_dict, indent=2)}")

            # Extract required parameters
            github_token_raw = input_dict.get("githubToken")
            github_app_raw = input_dict.get("githubApp")
            files = input_dict.get("files", [])

            # Resolve credentials (handle secret references)
            github_token = None
            github_app = None

            if github_token_raw:
                github_token = resolve_credential_value(github_token_raw, log)
                if not github_token:
                    msg = "Failed to resolve GitHub token"
                    raise ValueError(msg)

            if github_app_raw:
                log.info("Resolving GitHub App credentials...")
                app_id = resolve_credential_value(github_app_raw.get("appId"), log)
                installation_id = resolve_credential_value(github_app_raw.get("installationId"), log)
                private_key = resolve_credential_value(github_app_raw.get("privateKey"), log)

                if not all([app_id, installation_id, private_key]):
                    missing = []
                    if not app_id: missing.append("appId")
                    if not installation_id: missing.append("installationId")
                    if not private_key: missing.append("privateKey")
                    msg = f"Failed to resolve GitHub App credentials: {', '.join(missing)}"
                    raise ValueError(msg)

                github_app = {
                    "appId": app_id,
                    "installationId": installation_id,
                    "privateKey": private_key
                }

            # Validate authentication
            if not github_token and not github_app:
                msg = "Either githubToken or githubApp authentication must be provided"
                raise ValueError(msg)

            if github_token and github_app:
                msg = (
                    "Cannot use both githubToken and githubApp "
                    "authentication simultaneously"
                )
                raise ValueError(msg)

            if not files:
                msg = "At least one file must be specified"
                raise ValueError(msg)

            # Log authentication method
            if github_token:
                log.info("Using personal access token authentication")
            else:
                app_id = github_app.get("appId")
                log.info(f"Using GitHub App authentication (App ID: {app_id})")

            # Initialize GitHub manager
            github_manager = GitHubFileManager(
                logger=log, github_token=github_token, github_app=github_app
            )

            # Process files
            results = []
            errors = []

            for i, file_spec in enumerate(files):
                try:
                    # Extract file details
                    repository = file_spec.get("repository")
                    path = file_spec.get("path")
                    content = file_spec.get("content")
                    commit_message = file_spec.get("commitMessage")
                    branch = file_spec.get("branch", "main")

                    # Validate required fields
                    if not all([repository, path, content, commit_message]):
                        msg = f"Missing required fields for file {path}"
                        raise ValueError(msg)

                    # Commit the file
                    result = github_manager.commit_file(
                        repository=repository,
                        path=path,
                        content=content,
                        message=commit_message,
                        branch=branch,
                    )
                    results.append(result)
                    log.info(f"Successfully processed file {i + 1}: {path}")

                except Exception as e:
                    error_msg = (
                        f"Failed to process file {file_spec.get('path', 'unknown')}: "
                        f"{e!s}"
                    )
                    errors.append(error_msg)
                    log.error(error_msg)

            # Create context with results
            context = {
                "github-file-manager": {
                    "success": len(errors) == 0,
                    "filesProcessed": len(results),
                    "results": results,
                    "errors": errors,
                }
            }

            # Set context in response
            rsp.context.CopyFrom(json_format.ParseDict(context, rsp.context))

            # Add appropriate result message
            if len(errors) == 0:
                success_msg = f"Successfully committed {len(results)} files to GitHub"
                rsp.results.append(
                    fnv1.Result(
                        severity=fnv1.SEVERITY_NORMAL,
                        message=success_msg,
                    )
                )
            else:
                rsp.results.append(
                    fnv1.Result(
                        severity=fnv1.SEVERITY_WARNING,
                        message=(
                            f"GitHub file manager completed with {len(errors)} errors. "
                            "Check context for details."
                        ),
                    )
                )

        except Exception as e:
            # Handle any unexpected errors
            error_msg = f"Function execution failed: {e!s}"
            log.error(error_msg)

            # Set error context
            context = {"github-file-manager": {"success": False, "error": error_msg}}
            rsp.context.CopyFrom(json_format.ParseDict(context, rsp.context))

            rsp.results.append(
                fnv1.Result(severity=fnv1.SEVERITY_FATAL, message=error_msg)
            )

        log.info("GitHub file manager function completed")
        return rsp
