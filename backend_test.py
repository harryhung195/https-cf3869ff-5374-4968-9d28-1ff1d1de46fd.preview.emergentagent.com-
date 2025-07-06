#!/usr/bin/env python3
import requests
import json
import random
import string
import time
import sys
from typing import Dict, Any, Optional

# Backend URL from the frontend/.env file
BACKEND_URL = "https://cf3869ff-5374-4968-9d28-1ff1d1de46fd.preview.emergentagent.com/api"

# Test results tracking
test_results = {
    "total": 0,
    "passed": 0,
    "failed": 0,
    "tests": []
}

def random_string(length=8):
    """Generate a random string for test data"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=length))

def log_test(name: str, passed: bool, response: Optional[requests.Response] = None, error: str = ""):
    """Log test results"""
    test_results["total"] += 1
    
    if passed:
        test_results["passed"] += 1
        status = "✅ PASSED"
    else:
        test_results["failed"] += 1
        status = "❌ FAILED"
    
    test_data = {
        "name": name,
        "status": status,
        "error": error
    }
    
    if response:
        try:
            test_data["response"] = response.json()
        except:
            test_data["response"] = response.text
        
        test_data["status_code"] = response.status_code
    
    test_results["tests"].append(test_data)
    
    # Print test result to console
    print(f"{status} - {name}")
    if error:
        print(f"  Error: {error}")
    if response:
        print(f"  Status Code: {response.status_code}")
        try:
            print(f"  Response: {json.dumps(response.json(), indent=2)[:200]}...")
        except:
            print(f"  Response: {response.text[:200]}...")
    print()

def test_user_authentication():
    """Test user authentication endpoints"""
    print("\n=== Testing User Authentication System ===\n")
    
    # Generate random user data for testing
    test_user = {
        "email": f"test_{random_string()}@example.com",
        "name": f"Test User {random_string()}",
        "password": f"Password{random_string()}"
    }
    
    # Test user registration
    try:
        response = requests.post(
            f"{BACKEND_URL}/auth/register",
            json=test_user
        )
        
        if response.status_code == 200 and "access_token" in response.json():
            log_test("User Registration", True, response)
            # Save token for subsequent tests
            token = response.json()["access_token"]
            user_id = response.json()["user"]["id"]
        else:
            log_test("User Registration", False, response, 
                     f"Expected status 200 and access_token in response, got {response.status_code}")
            return None, None
    except Exception as e:
        log_test("User Registration", False, None, str(e))
        return None, None
    
    # Test user login
    try:
        login_data = {
            "email": test_user["email"],
            "password": test_user["password"]
        }
        
        response = requests.post(
            f"{BACKEND_URL}/auth/login",
            json=login_data
        )
        
        if response.status_code == 200 and "access_token" in response.json():
            log_test("User Login", True, response)
            # Update token in case it's different
            token = response.json()["access_token"]
        else:
            log_test("User Login", False, response, 
                     f"Expected status 200 and access_token in response, got {response.status_code}")
    except Exception as e:
        log_test("User Login", False, None, str(e))
    
    # Test invalid login
    try:
        invalid_login = {
            "email": test_user["email"],
            "password": "wrong_password"
        }
        
        response = requests.post(
            f"{BACKEND_URL}/auth/login",
            json=invalid_login
        )
        
        if response.status_code == 401:
            log_test("Invalid Login Credentials", True, response)
        else:
            log_test("Invalid Login Credentials", False, response, 
                     f"Expected status 401, got {response.status_code}")
    except Exception as e:
        log_test("Invalid Login Credentials", False, None, str(e))
    
    # Test get current user (protected route)
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(
            f"{BACKEND_URL}/auth/me",
            headers=headers
        )
        
        if response.status_code == 200 and "id" in response.json():
            log_test("Get Current User", True, response)
        else:
            log_test("Get Current User", False, response, 
                     f"Expected status 200 and user data in response, got {response.status_code}")
    except Exception as e:
        log_test("Get Current User", False, None, str(e))
    
    # Test invalid token
    try:
        headers = {"Authorization": "Bearer invalid_token"}
        
        response = requests.get(
            f"{BACKEND_URL}/auth/me",
            headers=headers
        )
        
        if response.status_code == 401:
            log_test("Invalid Token Validation", True, response)
        else:
            log_test("Invalid Token Validation", False, response, 
                     f"Expected status 401, got {response.status_code}")
    except Exception as e:
        log_test("Invalid Token Validation", False, None, str(e))
    
    return token, user_id

def test_product_management():
    """Test product management endpoints"""
    print("\n=== Testing Product Management API ===\n")
    
    # Test get all products
    try:
        response = requests.get(f"{BACKEND_URL}/products")
        
        if response.status_code == 200 and isinstance(response.json(), list):
            products = response.json()
            log_test("Get All Products", True, response)
            
            # Save a product ID for later tests
            if products:
                product_id = products[0]["id"]
            else:
                product_id = None
        else:
            log_test("Get All Products", False, response, 
                     f"Expected status 200 and list of products, got {response.status_code}")
            product_id = None
    except Exception as e:
        log_test("Get All Products", False, None, str(e))
        product_id = None
    
    # Test get product categories
    try:
        response = requests.get(f"{BACKEND_URL}/categories")
        
        if response.status_code == 200 and "categories" in response.json():
            categories = response.json()["categories"]
            log_test("Get Product Categories", True, response)
            
            # Save a category for filtering test
            if categories:
                test_category = categories[0]
            else:
                test_category = None
        else:
            log_test("Get Product Categories", False, response, 
                     f"Expected status 200 and categories list, got {response.status_code}")
            test_category = None
    except Exception as e:
        log_test("Get Product Categories", False, None, str(e))
        test_category = None
    
    # Test get products by category
    if test_category:
        try:
            response = requests.get(f"{BACKEND_URL}/products?category={test_category}")
            
            if response.status_code == 200 and isinstance(response.json(), list):
                filtered_products = response.json()
                # Verify all products have the correct category
                all_match = all(p["category"] == test_category for p in filtered_products)
                
                if all_match:
                    log_test(f"Filter Products by Category ({test_category})", True, response)
                else:
                    log_test(f"Filter Products by Category ({test_category})", False, response,
                             "Some products don't match the requested category")
            else:
                log_test(f"Filter Products by Category ({test_category})", False, response,
                         f"Expected status 200 and filtered list, got {response.status_code}")
        except Exception as e:
            log_test(f"Filter Products by Category ({test_category})", False, None, str(e))
    
    # Test product search
    try:
        # Use a common term that should be in some product descriptions
        search_term = "premium"
        response = requests.get(f"{BACKEND_URL}/products?search={search_term}")
        
        if response.status_code == 200 and isinstance(response.json(), list):
            search_results = response.json()
            log_test(f"Search Products (term: {search_term})", True, response)
        else:
            log_test(f"Search Products (term: {search_term})", False, response,
                     f"Expected status 200 and search results, got {response.status_code}")
    except Exception as e:
        log_test(f"Search Products (term: {search_term})", False, None, str(e))
    
    # Test get specific product
    if product_id:
        try:
            response = requests.get(f"{BACKEND_URL}/products/{product_id}")
            
            if response.status_code == 200 and "id" in response.json():
                log_test(f"Get Specific Product (ID: {product_id})", True, response)
            else:
                log_test(f"Get Specific Product (ID: {product_id})", False, response,
                         f"Expected status 200 and product data, got {response.status_code}")
        except Exception as e:
            log_test(f"Get Specific Product (ID: {product_id})", False, None, str(e))
        
        # Test invalid product ID
        try:
            invalid_id = "invalid_product_id"
            response = requests.get(f"{BACKEND_URL}/products/{invalid_id}")
            
            if response.status_code == 404:
                log_test("Invalid Product ID Handling", True, response)
            else:
                log_test("Invalid Product ID Handling", False, response,
                         f"Expected status 404, got {response.status_code}")
        except Exception as e:
            log_test("Invalid Product ID Handling", False, None, str(e))
    
    return product_id

def test_shopping_cart(token, product_id):
    """Test shopping cart endpoints"""
    print("\n=== Testing Shopping Cart API ===\n")
    
    if not token or not product_id:
        log_test("Shopping Cart Tests", False, None, 
                 "Skipping cart tests due to missing token or product ID")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test get cart (should be empty initially)
    try:
        response = requests.get(
            f"{BACKEND_URL}/cart",
            headers=headers
        )
        
        if response.status_code == 200 and "items" in response.json():
            log_test("Get Empty Cart", True, response)
        else:
            log_test("Get Empty Cart", False, response,
                     f"Expected status 200 and cart data, got {response.status_code}")
    except Exception as e:
        log_test("Get Empty Cart", False, None, str(e))
    
    # Test add item to cart
    try:
        cart_item = {
            "product_id": product_id,
            "quantity": 2
        }
        
        response = requests.post(
            f"{BACKEND_URL}/cart/add",
            headers=headers,
            json=cart_item
        )
        
        if response.status_code == 200 and "message" in response.json():
            log_test("Add Item to Cart", True, response)
        else:
            log_test("Add Item to Cart", False, response,
                     f"Expected status 200 and success message, got {response.status_code}")
    except Exception as e:
        log_test("Add Item to Cart", False, None, str(e))
    
    # Test get cart with items
    try:
        response = requests.get(
            f"{BACKEND_URL}/cart",
            headers=headers
        )
        
        if response.status_code == 200 and "items" in response.json():
            cart = response.json()
            if cart["items"] and len(cart["items"]) > 0:
                log_test("Get Cart with Items", True, response)
            else:
                log_test("Get Cart with Items", False, response,
                         "Cart should contain items but appears to be empty")
        else:
            log_test("Get Cart with Items", False, response,
                     f"Expected status 200 and cart with items, got {response.status_code}")
    except Exception as e:
        log_test("Get Cart with Items", False, None, str(e))
    
    # Test remove item from cart
    try:
        response = requests.delete(
            f"{BACKEND_URL}/cart/remove/{product_id}",
            headers=headers
        )
        
        if response.status_code == 200 and "message" in response.json():
            log_test("Remove Item from Cart", True, response)
        else:
            log_test("Remove Item from Cart", False, response,
                     f"Expected status 200 and success message, got {response.status_code}")
    except Exception as e:
        log_test("Remove Item from Cart", False, None, str(e))
    
    # Verify cart is empty after removal
    try:
        response = requests.get(
            f"{BACKEND_URL}/cart",
            headers=headers
        )
        
        if response.status_code == 200 and "items" in response.json():
            cart = response.json()
            if not cart["items"] or len(cart["items"]) == 0:
                log_test("Verify Cart Empty After Removal", True, response)
            else:
                log_test("Verify Cart Empty After Removal", False, response,
                         "Cart should be empty after item removal")
        else:
            log_test("Verify Cart Empty After Removal", False, response,
                     f"Expected status 200 and empty cart, got {response.status_code}")
    except Exception as e:
        log_test("Verify Cart Empty After Removal", False, None, str(e))

def test_database_models():
    """Test database models and setup"""
    print("\n=== Testing Database Models and Setup ===\n")
    
    # Test if sample products were initialized
    try:
        response = requests.get(f"{BACKEND_URL}/products")
        
        if response.status_code == 200 and isinstance(response.json(), list):
            products = response.json()
            if len(products) >= 9:  # We expect at least 9 sample products
                log_test("Sample Products Initialization", True, response)
            else:
                log_test("Sample Products Initialization", False, response,
                         f"Expected at least 9 sample products, found {len(products)}")
        else:
            log_test("Sample Products Initialization", False, response,
                     f"Expected status 200 and list of products, got {response.status_code}")
    except Exception as e:
        log_test("Sample Products Initialization", False, None, str(e))
    
    # Test if all product categories are present
    try:
        response = requests.get(f"{BACKEND_URL}/categories")
        
        if response.status_code == 200 and "categories" in response.json():
            categories = response.json()["categories"]
            expected_categories = {"Electronics", "T-Shirts", "Shoes"}
            found_categories = set(categories)
            
            if expected_categories.issubset(found_categories):
                log_test("Product Categories Setup", True, response)
            else:
                missing = expected_categories - found_categories
                log_test("Product Categories Setup", False, response,
                         f"Missing expected categories: {missing}")
        else:
            log_test("Product Categories Setup", False, response,
                     f"Expected status 200 and categories list, got {response.status_code}")
    except Exception as e:
        log_test("Product Categories Setup", False, None, str(e))

def print_summary():
    """Print test summary"""
    print("\n" + "="*50)
    print(f"TEST SUMMARY: {test_results['passed']}/{test_results['total']} tests passed")
    print("="*50)
    
    if test_results["failed"] > 0:
        print("\nFAILED TESTS:")
        for test in test_results["tests"]:
            if test["status"].startswith("❌"):
                print(f"- {test['name']}: {test.get('error', 'No error details')}")
    
    print("\n" + "="*50)
    success_rate = (test_results["passed"] / test_results["total"]) * 100
    print(f"Success Rate: {success_rate:.2f}%")
    print("="*50 + "\n")

def main():
    """Run all tests"""
    print("\n" + "="*50)
    print("STARTING E-COMMERCE BACKEND API TESTS")
    print("="*50 + "\n")
    
    # Run tests in sequence
    token, user_id = test_user_authentication()
    product_id = test_product_management()
    test_shopping_cart(token, product_id)
    test_database_models()
    
    # Print summary
    print_summary()
    
    # Return exit code based on test results
    return 0 if test_results["failed"] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())