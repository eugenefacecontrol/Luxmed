import requests
import re
import json

def debug_brokul_login():
    """Debug script to analyze Brokul login page structure"""
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    })
    
    try:
        # Get the login page
        print("Getting login page...")
        response = session.get("https://dietyodbrokula.pl/customer/account/login/")
        response.raise_for_status()
        
        html_content = response.text
        
        # Find forms using regex
        form_pattern = r'<form[^>]*action="([^"]*)"[^>]*>'
        forms = re.findall(form_pattern, html_content)
        print(f"Found forms with actions: {forms}")
        
        # Find all input fields
        input_pattern = r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"[^>]*>'
        inputs = re.findall(input_pattern, html_content)
        print(f"\nFound {len(inputs)} input fields:")
        
        form_data = {}
        for name, value in inputs:
            print(f"  Name: {name}, Value: {value}")
            form_data[name] = value
        
        print(f"\nForm data: {json.dumps(form_data, indent=2)}")
        
        # Look for CSRF tokens specifically
        print("\nLooking for CSRF tokens...")
        csrf_patterns = [
            r'name="form_key"\s+value="([^"]+)"',
            r'name="csrf_token"\s+value="([^"]+)"',
            r'name="token"\s+value="([^"]+)"',
            r'<input[^>]*name="[^"]*key[^"]*"[^>]*value="([^"]+)"',
            r'<meta[^>]*name="csrf-token"[^>]*content="([^"]+)"',
            r'window\.csrf_token\s*=\s*["\']([^"\']+)["\']',
            r'window\.form_key\s*=\s*["\']([^"\']+)["\']',
        ]
        
        for i, pattern in enumerate(csrf_patterns):
            matches = re.findall(pattern, html_content, re.IGNORECASE)
            if matches:
                print(f"  Pattern {i+1} found: {matches}")
        
        # Look for JavaScript that might set tokens
        script_pattern = r'<script[^>]*>(.*?)</script>'
        scripts = re.findall(script_pattern, html_content, re.DOTALL | re.IGNORECASE)
        print(f"\nFound {len(scripts)} script tags")
        for i, script_content in enumerate(scripts):
            if 'csrf' in script_content.lower() or 'token' in script_content.lower() or 'form_key' in script_content.lower():
                print(f"  Script {i+1} contains token-related content:")
                print(f"    {script_content[:200]}...")
        
        # Save the full HTML for manual inspection
        with open("debug_login_page.html", "w", encoding="utf-8") as f:
            f.write(response.text)
        print("\nFull HTML saved to debug_login_page.html")
        
    except Exception as e:
        print(f"Debug failed: {e}")

if __name__ == "__main__":
    debug_brokul_login() 