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

        mock_boto_client.assert_called_once_with(
            "s3",
            endpoint_url="https://mock.r2.cloudflarestorage.com",
            aws_access_key_id="test_access_key",
            aws_secret_access_key="test_secret_key",
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


if __name__ == "__main__":
    unittest.main()