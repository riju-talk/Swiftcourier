import requests

def get_access_token(base_url, email, password):
    """
    Generate an access token from LastMiles API and print raw response
    """
    url = f"{base_url}/login"
    headers = {
        "Content-Type": "application/json",
    }
    payload = {
        "email": email,
        "password": password
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        print("Raw Response Text:", response.text)   # ✅ Print raw text
        print("Raw Response JSON:", response.json()) # ✅ Print parsed JSON

        response.raise_for_status()
        data = response.json()
        
        if data.get("status") and "data" in data:
            return data["data"]["access_token"]
        else:
            print("Login failed:", data.get("message"))
            return None
    except Exception as e:
        print("Error during login:", e)
        return None


# Example usage
if __name__ == "__main__":
    BASE_URL = "https://api.lastmiles.co"  # Replace with actual API base URL
    EMAIL = "shipnick11@gmail.com"
    PASSWORD = "SH@whs860"

    token = get_access_token(BASE_URL, EMAIL, PASSWORD)
    print("Extracted Access Token:", token)


# Example usage:
if __name__ == "__main__":

    print("Access Token:", token)
