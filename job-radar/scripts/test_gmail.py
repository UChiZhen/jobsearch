#!/usr/bin/env python3
"""
Test Gmail API authentication.
First run will open browser for OAuth authorization.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.emailer import get_gmail_client


def main():
    print("🔐 Testing Gmail API authentication...")
    print("   (First run will open browser for authorization)")
    print()
    
    client = get_gmail_client()
    
    if client.authenticate():
        print()
        print("🎉 Gmail API ready!")
        print(f"   Email: {client.user_email}")
        print()
        
        # Ask if user wants to send a test email
        response = input("Send a test email to yourself? (y/n): ").strip().lower()
        
        if response == 'y':
            result = client.send_email(
                to=client.user_email,
                subject="🧪 Job Radar Test Email",
                body_html="""
                <div style="font-family: sans-serif; padding: 20px;">
                    <h1>✅ Gmail API Working!</h1>
                    <p>Your Job Radar email integration is configured correctly.</p>
                    <p>You'll receive weekly job reports at this address.</p>
                </div>
                """,
                body_text="Gmail API Working! Your Job Radar is configured correctly."
            )
            
            if result['success']:
                print(f"✅ Test email sent! Message ID: {result['message_id']}")
            else:
                print(f"❌ Failed to send: {result['error']}")
        else:
            print("Skipped test email.")
    else:
        print("❌ Authentication failed. Please check your credentials.json")
        sys.exit(1)


if __name__ == "__main__":
    main()
