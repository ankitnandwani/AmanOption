import os
import pickle
import sys
from unittest.mock import patch, MagicMock

# Set environment variables for the tests
os.environ["R2_ENDPOINT"] = "https://mock.r2.cloudflarestorage.com"
os.environ["R2_ACCESS_KEY_ID"] = "test_access_key"
os.environ["R2_SECRET_ACCESS_KEY"] = "test_secret_key"
os.environ["R2_BUCKET_NAME"] = "test-bucket"

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from services.r2_service import get_object

def test_mock():
    with patch("services.r2_service.get_client") as mock_get_client:
        # Setup mocks
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        test_data = pickle.dumps({"key": "value"})
        # Configure the mock client's get_object method to return a response-like object
        mock_response = {"Body": MagicMock(read=MagicMock(return_value=test_data))}
        mock_client.get_object.return_value = mock_response
        
        print(f"mock_client.get_object.return_value = {mock_client.get_object.return_value}")
        print(f"type(mock_client.get_object.return_value) = {type(mock_client.get_object.return_value)}")
        
        result = get_object("test-bucket", "test-key")
        print(f"result = {result}")
        print(f"type(result) = {type(result)}")
        
        if result == test_data:
            print("SUCCESS: Mock is working correctly")
        else:
            print("FAILURE: Mock is not returning the expected value")
            print(f"get_client was called: {mock_get_client.called}")
            if mock_get_client.called:
                print(f"get_client returned: {mock_get_client.return_value}")
                print(f"get_client().get_object was called: {mock_client.get_object.called}")

if __name__ == "__main__":
    test_mock()