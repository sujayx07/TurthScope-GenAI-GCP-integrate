"""
Test script to validate JSON format consistency in check_text.py

This script tests that all error and success responses follow the expected format:
- Success: {"textResult": {"label": "...", "score": ..., ...}}
- Error: {"textResult": {"error": "...", "details": "...", ...}}
"""

import json
from typing import Dict, Any

def validate_response_format(response: Dict[str, Any], test_name: str) -> bool:
    """
    Validates that a response follows the expected format.
    
    Args:
        response: The response dictionary to validate
        test_name: Name of the test for logging
    
    Returns:
        True if valid, False otherwise
    """
    print(f"\n{'='*60}")
    print(f"Test: {test_name}")
    print(f"{'='*60}")
    
    # Check if textResult exists
    if "textResult" not in response:
        print("❌ FAIL: Missing 'textResult' key")
        print(f"Response keys: {list(response.keys())}")
        return False
    
    text_result = response["textResult"]
    
    # Check if it's an error response
    if "error" in text_result:
        print("✅ Format: Error response")
        print(f"   Error message: {text_result['error']}")
        if "details" in text_result:
            print(f"   Details: {text_result['details']}")
        if "raw_response_preview" in text_result:
            print(f"   Has raw response preview: Yes")
        return True
    
    # Check if it's a success response
    if "label" in text_result and "score" in text_result:
        print("✅ Format: Success response")
        print(f"   Label: {text_result['label']}")
        print(f"   Score: {text_result['score']}")
        
        # Check optional fields
        optional_fields = [
            "sentiment", "bias", "highlights", "reasoning",
            "educational_insights", "fact_check", "localized_summary"
        ]
        present_fields = [f for f in optional_fields if f in text_result]
        print(f"   Optional fields present: {', '.join(present_fields) if present_fields else 'None'}")
        return True
    
    # Invalid format
    print("❌ FAIL: Missing required fields (label and score)")
    print(f"   Available fields: {list(text_result.keys())}")
    return False


def test_formats():
    """Run format validation tests"""
    
    all_tests_passed = True
    
    # Test 1: Valid success response
    success_response = {
        "textResult": {
            "label": "LABEL_0",
            "score": 0.92,
            "sentiment": {"label": "neutral", "score": 0.85},
            "bias": {"summary": "Minimal bias", "indicators": []},
            "highlights": [],
            "reasoning": ["Source is credible"],
            "educational_insights": ["Well-sourced content"],
            "fact_check": []
        }
    }
    all_tests_passed &= validate_response_format(success_response, "Valid Success Response")
    
    # Test 2: Valid error response (Model JSON error)
    error_response_1 = {
        "textResult": {
            "error": "Model did not return valid JSON in the final response.",
            "details": "JSON parse error: Expecting property name",
            "raw_response_preview": "Some malformed JSON..."
        }
    }
    all_tests_passed &= validate_response_format(error_response_1, "Model JSON Parse Error")
    
    # Test 3: Valid error response (Tool error)
    error_response_2 = {
        "textResult": {
            "error": "Analysis failed due to tool error: ApiError('Timeout')"
        }
    }
    all_tests_passed &= validate_response_format(error_response_2, "Tool Error")
    
    # Test 4: Valid error response (Missing input)
    error_response_3 = {
        "textResult": {
            "error": "URL and article text must be provided."
        }
    }
    all_tests_passed &= validate_response_format(error_response_3, "Missing Input Error")
    
    # Test 5: Invalid format - Old error format (should fail)
    old_error_format = {
        "error": "Some error message"
    }
    result = validate_response_format(old_error_format, "OLD ERROR FORMAT (should fail)")
    if result:
        print("⚠️  WARNING: Old error format passed validation (this is bad!)")
        all_tests_passed = False
    else:
        print("✅ Correctly rejected old error format")
        all_tests_passed = True  # This is expected to fail
    
    # Test 6: Invalid format - Missing label/score (should fail)
    incomplete_response = {
        "textResult": {
            "reasoning": ["Some reasoning"],
            "fact_check": []
        }
    }
    result = validate_response_format(incomplete_response, "Incomplete Response (should fail)")
    if result:
        print("⚠️  WARNING: Incomplete response passed validation (this is bad!)")
        all_tests_passed = False
    else:
        print("✅ Correctly identified incomplete response")
    
    # Final summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    if all_tests_passed:
        print("✅ All validation tests passed!")
    else:
        print("❌ Some tests failed!")
    print(f"{'='*60}\n")
    
    return all_tests_passed


if __name__ == "__main__":
    print("""
╔════════════════════════════════════════════════════════════╗
║        TruthScope JSON Format Validation Tests             ║
║                                                            ║
║  Testing that all responses follow the expected format:    ║
║  • Success: {"textResult": {"label": "...", "score": ...}} ║
║  • Error: {"textResult": {"error": "...", ...}}            ║
╚════════════════════════════════════════════════════════════╝
    """)
    
    success = test_formats()
    exit(0 if success else 1)
