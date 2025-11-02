"""
Simple test script to verify the TruthScope backend API is working.
Tests both the health check endpoint and the analyze endpoint.
"""

import requests
import json

# Backend URL
BASE_URL = "http://127.0.0.1:8080"

def test_health_check():
    """Test the root endpoint to check if server is running."""
    print("\n" + "="*60)
    print("TEST 1: Health Check (GET /)")
    print("="*60)
    
    try:
        response = requests.get(f"{BASE_URL}/")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("✅ Health check passed!")
            return True
        else:
            print("❌ Health check failed!")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_analyze_endpoint():
    """Test the /analyze endpoint with a sample article."""
    print("\n" + "="*60)
    print("TEST 2: Analyze Endpoint (POST /analyze)")
    print("="*60)
    
    # Sample article data
    test_data = {
        "url": "https://www.bbc.com/news/world-asia-india-12345678",
        "article_text": """
        Breaking News: New Climate Agreement Reached
        
        World leaders gathered today to sign a historic climate agreement aimed at 
        reducing carbon emissions by 50% over the next decade. The agreement includes 
        commitments from over 150 countries and establishes a new global fund for 
        renewable energy projects.
        
        Scientists have praised the agreement as a significant step forward in 
        combating climate change. "This is exactly what we need," said Dr. Jane Smith, 
        a climate researcher at Oxford University.
        """
    }
    
    # Note: This endpoint requires authentication
    # You'll need to add your Google OAuth token here
    print("\n⚠️  Note: /analyze endpoint requires authentication")
    print("To test this endpoint, you need to:")
    print("1. Get a Google OAuth access token")
    print("2. Add it to the headers as 'Authorization: Bearer <token>'")
    print("\nSkipping authenticated endpoint test for now...")
    
    return None


def test_analyze_with_auth(access_token):
    """Test the /analyze endpoint with authentication."""
    print("\n" + "="*60)
    print("TEST 2: Analyze Endpoint WITH AUTH (POST /analyze)")
    print("="*60)
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    
    test_data = {
        "url": "https://www.bbc.com/news/world-asia-india-12345678",
        "article_text": """
        Breaking News: New Climate Agreement Reached
        
        World leaders gathered today to sign a historic climate agreement aimed at 
        reducing carbon emissions by 50% over the next decade.
        """
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/analyze",
            headers=headers,
            json=test_data,
            timeout=60
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 200:
            print("✅ Analysis completed successfully!")
            return True
        else:
            print("❌ Analysis failed!")
            return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "="*60)
    print("TruthScope Backend API Tests")
    print("="*60)
    print(f"Testing backend at: {BASE_URL}")
    print("Make sure the backend is running first!")
    print("="*60)
    
    # Test 1: Health check
    health_ok = test_health_check()
    
    # Test 2: Analyze endpoint (requires auth)
    test_analyze_endpoint()
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    if health_ok:
        print("✅ Backend is running and accessible")
        print("✅ Configuration looks good")
        print("\n📝 Next steps:")
        print("1. Get a Google OAuth token from your frontend")
        print("2. Call test_analyze_with_auth(token) to test analysis")
        print("3. Or use the browser extension to test end-to-end")
    else:
        print("❌ Backend health check failed")
        print("Make sure the backend is running: python check_text.py")
    print("="*60)
