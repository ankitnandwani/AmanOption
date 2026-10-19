import os
import sys
from unittest.mock import patch

# Set environment variables for the tests
os.environ["R2_ENDPOINT"] = "https://mock.r2.cloudflarestorage.com"
os.environ["R2_ACCESS_KEY_ID"] = "test_access_key"
os.environ["R2_SECRET_ACCESS_KEY"] = "test_secret_key"
os.environ["R2_BUCKET_NAME"] = "test-bucket"

# Add the project root to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

def test_simple_patch():
    # Test patching a built-in function
    with patch("builtins.open") as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = "test content"
        
        with open("test.txt", "r") as f:
            content = f.read()
        
        print(f"Content: {content}")
        if content == "test content":
            print("SUCCESS: Built-in patch is working")
        else:
            print("FAILURE: Built-in patch is not working")

if __name__ == "__main__":
    test_simple_patch()