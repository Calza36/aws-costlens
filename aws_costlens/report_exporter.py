"""Export handling for AWS CostLens reports - Local and S3."""

import os
from io import BytesIO
from typing import Optional

from rich.console import Console

console = Console()


def upload_to_s3(
    content: bytes,
    bucket: str,
    key: str,
    profile: Optional[str] = None,
    content_type: str = "application/octet-stream",
) -> bool:
    """
    Upload content to S3 bucket.

    Args:
        content: Bytes to upload
        bucket: S3 bucket name
        key: S3 object key
        profile: Optional AWS profile
        content_type: MIME type

    Returns:
        True if successful
    """
    import boto3

    try:
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        s3 = session.client("s3")
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        console.print(f"[green]✓ Uploaded to s3://{bucket}/{key}[/]")
        return True
    except Exception as e:
        console.print(f"[bold red]Error uploading to S3: {str(e)}[/]")
        return False


class ExportHandler:
    """Handles exporting reports to various destinations."""

    def __init__(
        self,
        output_dir: Optional[str] = None,
        s3_bucket: Optional[str] = None,
        s3_prefix: Optional[str] = None,
        profile: Optional[str] = None,
    ):
        """
        Initialize export handler.

        Args:
            output_dir: Local directory for output
            s3_bucket: Optional S3 bucket
            s3_prefix: Optional S3 prefix/folder
            profile: AWS profile for S3 access
        """
        self.output_dir = output_dir or os.getcwd()
        self.s3_bucket = s3_bucket
        self.s3_prefix = s3_prefix or ""
        self.profile = profile

        # Ensure output directory exists
        if self.output_dir:
            os.makedirs(self.output_dir, exist_ok=True)

    def save(
        self,
        content: bytes,
        filename: str,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Save content to configured destination(s).

        Args:
            content: Bytes to save
            filename: Name of the file
            content_type: MIME type

        Returns:
            Path or URL where content was saved
        """
        saved_path = ""

        # Save locally
        local_path = self._save_to_local(content, filename)
        saved_path = local_path

        # Upload to S3 if configured
        if self.s3_bucket:
            s3_key = f"{self.s3_prefix}/{filename}" if self.s3_prefix else filename
            s3_key = s3_key.lstrip("/")
            if upload_to_s3(content, self.s3_bucket, s3_key, self.profile, content_type):
                saved_path = f"s3://{self.s3_bucket}/{s3_key}"

        return saved_path

    def _save_to_local(self, content: bytes, filename: str) -> str:
        """Save content to local filesystem."""
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "wb") as f:
            f.write(content)
        console.print(f"[green]✓ Saved to {filepath}[/]")
        return filepath

    def save_text(self, content: str, filename: str) -> str:
        """Save text content."""
        return self.save(content.encode("utf-8"), filename, "text/plain")

    def save_csv(self, content: str, filename: str) -> str:
        """Save CSV content."""
        return self.save(content.encode("utf-8"), filename, "text/csv")

    def save_json(self, content: str, filename: str) -> str:
        """Save JSON content."""
        return self.save(content.encode("utf-8"), filename, "application/json")

    def save_pdf(self, content: bytes, filename: str) -> str:
        """Save PDF content."""
        return self.save(content, filename, "application/pdf")


def get_pdf_output() -> BytesIO:
    """Get a BytesIO buffer for PDF output."""
    return BytesIO()


def finalize_pdf(buffer: BytesIO) -> bytes:
    """Finalize PDF and return bytes."""
    buffer.seek(0)
    return buffer.read()
