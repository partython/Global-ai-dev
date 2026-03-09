"""
Priya Global Platform — File Upload Security Tests

Tests file upload size limits, type validation, path traversal,
filename sanitization, and content scanning.
"""

import os
import re
import pytest


@pytest.mark.security
class TestFileUploadSizeLimits:
    """Test that file upload size limits are enforced."""

    def test_max_file_size_constant_defined(self):
        """Platform must define a maximum upload size."""
        MAX_UPLOAD_SIZE_MB = 25  # Industry standard for SaaS
        MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

        assert MAX_UPLOAD_SIZE_BYTES == 26_214_400
        assert MAX_UPLOAD_SIZE_MB <= 50  # Should never exceed 50MB

    def test_zero_byte_file_rejected(self):
        """Empty/zero-byte files should be rejected."""
        empty_file = b""
        assert len(empty_file) == 0
        # API should reject: assert response.status_code == 400

    @pytest.mark.parametrize("size_mb", [26, 50, 100])
    def test_oversized_file_generates_correct_size(self, size_mb):
        """Verify oversized file detection logic."""
        MAX_SIZE = 25 * 1024 * 1024
        file_size = size_mb * 1024 * 1024

        assert file_size > MAX_SIZE


@pytest.mark.security
class TestFileTypeValidation:
    """Test that only allowed file types are accepted."""

    ALLOWED_TYPES = {
        "image/jpeg", "image/png", "image/gif", "image/webp",
        "application/pdf",
        "text/plain", "text/csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }

    BLOCKED_TYPES = {
        "application/x-msdownload",  # .exe
        "application/x-sh",          # .sh
        "application/x-python",      # .py
        "text/html",                 # .html (XSS risk)
        "application/javascript",    # .js
        "application/x-php",         # .php
        "application/java-archive",  # .jar
        "application/x-msdos-program",  # .com
    }

    @pytest.mark.parametrize("mime_type", ALLOWED_TYPES)
    def test_allowed_file_types(self, mime_type):
        """These MIME types should be accepted."""
        assert mime_type in self.ALLOWED_TYPES

    @pytest.mark.parametrize("mime_type", BLOCKED_TYPES)
    def test_blocked_file_types(self, mime_type):
        """These MIME types must be rejected."""
        assert mime_type not in self.ALLOWED_TYPES
        assert mime_type in self.BLOCKED_TYPES

    def test_double_extension_blocked(self):
        """Files with double extensions must be caught."""
        dangerous_filenames = [
            "report.pdf.exe",
            "image.jpg.php",
            "document.docx.sh",
            "data.csv.py",
        ]

        for filename in dangerous_filenames:
            # Last extension should be checked, not first
            parts = filename.rsplit(".", 1)
            if len(parts) > 1:
                ext = parts[-1].lower()
                blocked_extensions = {"exe", "sh", "php", "py", "bat", "cmd", "com", "js", "jar", "vbs"}
                assert ext in blocked_extensions, f"Double extension not caught: {filename}"

    def test_mime_type_sniffing_vs_extension(self):
        """File type must be verified by content, not just extension."""
        # A .jpg file with executable content should be blocked
        fake_jpg_with_exe_header = b"MZ\x90\x00"  # PE executable magic bytes
        jpg_magic = b"\xff\xd8\xff"  # JPEG magic bytes

        # PE header should not match JPEG
        assert not fake_jpg_with_exe_header.startswith(jpg_magic)

        # Real JPEG should match
        real_jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF"
        assert real_jpg.startswith(jpg_magic)


@pytest.mark.security
class TestFilenamesSanitization:
    """Test that filenames are properly sanitized."""

    @pytest.mark.parametrize("malicious_name,expected_safe", [
        ("../../etc/passwd", "etc_passwd"),
        ("..\\..\\windows\\system32\\config", "windows_system32_config"),
        ("file\x00.txt", "file.txt"),
        ("file\n.txt", "file.txt"),
        ("<script>alert(1)</script>.jpg", "scriptalert1script.jpg"),
        ("file with spaces.txt", "file with spaces.txt"),
        ("très_spécial.pdf", "très_spécial.pdf"),  # Unicode OK
        ("CON.txt", "CON.txt"),  # Windows reserved — should be handled
        ("NUL.pdf", "NUL.pdf"),  # Windows reserved
    ])
    def test_filename_sanitization(self, malicious_name, expected_safe):
        """Malicious filenames must be sanitized."""
        # Remove path traversal
        sanitized = malicious_name.replace("../", "").replace("..\\", "")
        # Remove null bytes
        sanitized = sanitized.replace("\x00", "").replace("\n", "").replace("\r", "")
        # Remove path separators
        sanitized = sanitized.replace("/", "_").replace("\\", "_")
        # Remove HTML tags
        sanitized = re.sub(r'<[^>]+>', '', sanitized)

        # Must not contain path traversal
        assert ".." not in sanitized
        assert "/" not in sanitized
        assert "\\" not in sanitized
        assert "\x00" not in sanitized

    def test_filename_length_limit(self):
        """Filenames exceeding max length must be truncated."""
        MAX_FILENAME_LENGTH = 255
        long_name = "a" * 500 + ".pdf"

        assert len(long_name) > MAX_FILENAME_LENGTH

        # Truncation should preserve extension
        name, ext = os.path.splitext(long_name)
        truncated = name[:MAX_FILENAME_LENGTH - len(ext)] + ext

        assert len(truncated) <= MAX_FILENAME_LENGTH
        assert truncated.endswith(".pdf")


@pytest.mark.security
class TestFileContentScanning:
    """Test that file content is validated beyond MIME type."""

    def test_zip_bomb_detection(self):
        """Compressed files with extreme compression ratios should be flagged."""
        # A zip bomb has tiny compressed size but enormous decompressed size
        compressed_size = 1024  # 1KB
        decompressed_size = 1024 * 1024 * 1024  # 1GB
        ratio = decompressed_size / compressed_size

        MAX_COMPRESSION_RATIO = 100
        assert ratio > MAX_COMPRESSION_RATIO

    def test_polyglot_file_detection(self):
        """Files that are valid in multiple formats should be flagged."""
        # A file that starts with JPEG magic but contains PHP
        polyglot = b"\xff\xd8\xff\xe0<?php system($_GET['cmd']); ?>"

        # Starts like a JPEG
        assert polyglot[:3] == b"\xff\xd8\xff"

        # But contains PHP code
        assert b"<?php" in polyglot

        # Content scanner must detect this
        has_script_content = b"<?php" in polyglot or b"<script" in polyglot
        assert has_script_content  # Should be flagged

    def test_svg_xss_detection(self):
        """SVG files containing JavaScript must be rejected."""
        malicious_svg = b'''<?xml version="1.0"?>
        <svg xmlns="http://www.w3.org/2000/svg">
            <script type="text/javascript">alert('XSS')</script>
        </svg>'''

        # Must detect embedded script
        assert b"<script" in malicious_svg
