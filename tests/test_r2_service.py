import os
import unittest
from unittest.mock import patch, MagicMock

# Set environment variables for the tests
os.environ["R2_ENDPOINT"] = "https://mock.r2.cloudflarestorage.com"
os.environ["R2_ACCESS_KEY_ID"] = "test_access_key"
os.environ["R2_SECRET_ACCESS_KEY"] = "test_secret_key"

from services.r2_service import get_client, object_exists, get_object, put_object
import services.r2_service as r2_service


class TestR2Service(unittest.TestCase):
    @patch("services.r2_service.boto3.client")
    def test_get_client_creates_client(self, mock_boto_client):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        client = get_client()

        args, kwargs = mock_boto_client.call_args
        self.assertEqual(args[0], "s3")
        self.assertEqual(kwargs["endpoint_url"], "https://mock.r2.cloudflarestorage.com")
        self.assertEqual(kwargs["aws_access_key_id"], "test_access_key")
        self.assertEqual(kwargs["aws_secret_access_key"], "test_secret_key")
        # The client must not request a default CRC32 checksum: R2 does not
        # reliably accept the ChecksumAlgorithm parameter.
        self.assertEqual(
            kwargs["config"].request_checksum_calculation, "when_required"
        )
        self.assertEqual(client, mock_client)

    @patch("services.r2_service.boto3.client")
    def test_get_client_returns_same_instance(self, mock_boto_client):
        r2_service._s3_client = None
        with patch.dict(os.environ, {"R2_ENDPOINT": "https://mock.r2.cloudflarestorage.com", "R2_ACCESS_KEY_ID": "test_access_key", "R2_SECRET_ACCESS_KEY": "test_secret_key"}):
            print("Inside patch: R2_ENDPOINT=", os.environ.get("R2_ENDPOINT"), "R2_ACCESS_KEY_ID=", os.environ.get("R2_ACCESS_KEY_ID"), "R2_SECRET_ACCESS_KEY=", os.environ.get("R2_SECRET_ACCESS_KEY"))
            mock_client = MagicMock()
            mock_boto_client.return_value = mock_client

            client1 = get_client()
            client2 = get_client()

            mock_boto_client.assert_called_once()
            self.assertEqual(client1, client2)
            self.assertEqual(client1, mock_client)

    @patch("services.r2_service.get_client")
    def test_object_exists_true(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.head_object.return_value = {}

        result = object_exists("test-bucket", "test-key")

        mock_client.head_object.assert_called_once_with(
            Bucket="test-bucket", Key="test-key"
        )
        self.assertTrue(result)

    @patch("services.r2_service.get_client")
    def test_object_exists_false_404(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.head_object.side_effect = Exception("404")

        result = object_exists("test-bucket", "test-key")

        self.assertFalse(result)

    @patch("services.r2_service.get_client")
    def test_object_exists_exception_returns_false(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.head_object.side_effect = Exception("Some error")

        result = object_exists("test-bucket", "test-key")

        self.assertFalse(result)

    @patch("services.r2_service.get_client")
    def test_get_object_success(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_response = {"Body": MagicMock(read=MagicMock(return_value=b"data"))}
        mock_client.get_object.return_value = mock_response

        result = get_object("test-bucket", "test-key")

        mock_client.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="test-key"
        )
        self.assertEqual(result, b"data")

    @patch("services.r2_service.get_client")
    def test_get_object_not_found(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_object.side_effect = Exception("404")

        result = get_object("test-bucket", "test-key")

        self.assertIsNone(result)

    @patch("services.r2_service.get_client")
    def test_get_object_exception_returns_none(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.get_object.side_effect = Exception("Some error")

        result = get_object("test-bucket", "test-key")

        self.assertIsNone(result)

    @patch("services.r2_service.get_client")
    def test_put_object_success(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.put_object.return_value = {}

        result = put_object("test-bucket", "test-key", b"data")

        mock_client.put_object.assert_called_once_with(
            Bucket="test-bucket", Key="test-key", Body=b"data"
        )
        self.assertTrue(result)

    @patch("services.r2_service.get_client")
    def test_put_object_exception_returns_false(self, mock_get_client):
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        mock_client.put_object.side_effect = Exception("Some error")

        result = put_object("test-bucket", "test-key", b"data")

        self.assertFalse(result)

    @patch("services.r2_service.boto3.client")
    def test_get_client_missing_credentials(self, mock_boto_client):
        r2_service._s3_client = None
        with patch.dict(os.environ, {"R2_ENDPOINT": "", "R2_ACCESS_KEY_ID": "", "R2_SECRET_ACCESS_KEY": ""}):
            print("Inside patch: R2_ENDPOINT=", os.environ.get("R2_ENDPOINT"), "R2_ACCESS_KEY_ID=", os.environ.get("R2_ACCESS_KEY_ID"), "R2_SECRET_ACCESS_KEY=", os.environ.get("R2_SECRET_ACCESS_KEY"))
            client = get_client()
            self.assertIsNone(client)
            mock_boto_client.assert_not_called()


class TestR2ServiceApiContract(unittest.TestCase):
    """Validate the adapter against the real botocore API contract.

    These use a stubbed S3 client, so no network access and no credentials are
    needed, but the request shapes are checked by botocore itself.
    """

    def setUp(self):
        import boto3
        from botocore.stub import Stubber

        self.stubber_class = Stubber
        self.client = boto3.client(
            "s3",
            endpoint_url="https://mock.r2.cloudflarestorage.com",
            aws_access_key_id="test_access_key",
            aws_secret_access_key="test_secret_key",
            config=r2_service._build_client_config(),
        )
        # Save and restore the singleton instead of clearing it, so other test
        # modules keep whatever client state they already rely on.
        self._previous_client = r2_service._s3_client
        r2_service._s3_client = self.client
        self.addCleanup(setattr, r2_service, "_s3_client", self._previous_client)

    def test_head_object_returns_size_and_metadata(self):
        with self.stubber_class(self.client) as stub:
            stub.add_response(
                "head_object",
                {
                    "ContentLength": 1234,
                    "ETag": '"abc123"',
                    "Metadata": {"md5": "deadbeef"},
                },
                {"Bucket": "test-bucket", "Key": "historical_cache/2025-04-04.pkl"},
            )
            result = r2_service.head_object(
                "test-bucket", "historical_cache/2025-04-04.pkl"
            )

        self.assertEqual(result["size"], 1234)
        self.assertEqual(result["etag"], "abc123")
        self.assertEqual(result["metadata"]["md5"], "deadbeef")

    def test_head_object_missing_returns_none(self):
        from botocore.exceptions import ClientError

        with self.stubber_class(self.client) as stub:
            stub.add_client_error(
                "head_object",
                service_error_code="404",
                service_message="Not Found",
                http_status_code=404,
                expected_params={
                    "Bucket": "test-bucket",
                    "Key": "historical_cache/missing.pkl",
                },
            )
            result = r2_service.head_object(
                "test-bucket", "historical_cache/missing.pkl"
            )

        self.assertIsNone(result)

    def test_list_objects_handles_pagination(self):
        with self.stubber_class(self.client) as stub:
            stub.add_response(
                "list_objects_v2",
                {
                    "Contents": [
                        {"Key": "historical_cache/a.pkl", "Size": 10, "ETag": '"e1"'}
                    ],
                    "IsTruncated": True,
                    "NextContinuationToken": "token",
                },
                {"Bucket": "test-bucket", "Prefix": "historical_cache/"},
            )
            stub.add_response(
                "list_objects_v2",
                {
                    "Contents": [
                        {"Key": "historical_cache/b.pkl", "Size": 20, "ETag": '"e2"'}
                    ],
                    "IsTruncated": False,
                },
                {
                    "Bucket": "test-bucket",
                    "Prefix": "historical_cache/",
                    "ContinuationToken": "token",
                },
            )
            objects = r2_service.list_objects("test-bucket", "historical_cache/")

        self.assertEqual(len(objects), 2)
        self.assertEqual(objects[0]["key"], "historical_cache/a.pkl")
        self.assertEqual(objects[1]["size"], 20)

    def test_put_file_sends_metadata_without_default_checksum(self):
        import tempfile
        from unittest.mock import ANY

        with tempfile.NamedTemporaryFile(suffix=".pkl", delete=False) as handle:
            handle.write(b"payload")
            path = handle.name
        self.addCleanup(os.unlink, path)

        with self.stubber_class(self.client) as stub:
            stub.add_response(
                "put_object",
                {"ETag": '"x"'},
                {
                    "Bucket": "test-bucket",
                    "Key": "historical_cache/2025-04-04.pkl",
                    "Body": ANY,
                    "Metadata": {"md5": "abc", "sha256": "def"},
                },
            )
            result = r2_service.put_file(
                "test-bucket",
                "historical_cache/2025-04-04.pkl",
                path,
                metadata={"md5": "abc", "sha256": "def"},
            )

        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()