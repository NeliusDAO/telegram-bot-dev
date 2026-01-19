import requests
import json
import time
import os
from typing import List, Dict, Optional
from datetime import datetime
from urllib.parse import urlencode

from settings import BLEEPRS_API_KEY


def get_network_from_prefix(phone_number: str) -> Optional[str]:
    """
    Get carrier from phone number prefix (local lookup).
    
    Args:
        phone_number: Phone number to look up
        
    Returns:
        Carrier name or None if unknown
    """
    # Normalize number: remove spaces, dashes, +234
    number = phone_number.replace(' ', '').replace('-', '')
    
    if number.startswith('+234'):
        number = '0' + number[4:]
    
    prefix = number[:4]
    
    networks = {
        'MTN': ['0803', '0806', '0703', '0706', '0813', '0816', '0810', '0814', '0903', '0906', '0913'],
        'Airtel': ['0802', '0808', '0708', '0812', '0701', '0902', '0907', '0901'],
        'Glo': ['0805', '0807', '0705', '0815', '0811', '0905'],
        '9mobile': ['0809', '0817', '0818', '0909', '0908']
    }
    
    for network, prefixes in networks.items():
        if prefix in prefixes:
            return network
    
    return None


def get_network_from_api(phone_number: str) -> Optional[str]:
    """
    Get carrier from phone number using apilayer API.
    
    Args:
        phone_number: Phone number to look up
        
    Returns:
        Carrier name (first word, lowercase) or None if error
    """
    try:
        base_url = 'http://apilayer.net/api/validate'
        access_key = os.getenv('PHONEVERIFY_API_KEY', '')
        
        if not access_key:
            return None
        
        params = {
            'access_key': access_key,
            'number': phone_number,
            'country_code': 'NG'
        }
        
        url = f"{base_url}?{urlencode(params)}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        # Extract carrier (robust against different API shapes)
        carrier_raw = None
        if data:
            if isinstance(data.get('carrier'), str):
                carrier_raw = data['carrier']
            elif isinstance(data.get('carrier'), dict):
                carrier_raw = data['carrier'].get('name') or data['carrier'].get('provider')
            elif isinstance(data.get('provider'), str):
                carrier_raw = data['provider']
            elif isinstance(data.get('carrier_name'), str):
                carrier_raw = data['carrier_name']
        
        if carrier_raw:
            carrier_first_word = carrier_raw.strip().split()[0].lower()
            return carrier_first_word
        
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error calling apilayer API: {e}")
        return None
    except Exception as e:
        print(f"Error getting carrier from API: {e}")
        return None


def get_carrier_from_phone(phone_number: str) -> Optional[str]:
    """
    Get the carrier for a phone number using API lookup.
    
    Args:
        phone_number: Phone number to look up
        
    Returns:
        Carrier name (lowercase) or None if error
    """
    # Use API lookup
    carrier = get_network_from_api(phone_number)
    if carrier:
        return carrier
    
    return None


class BleeprsAirtimeClient:
    """Client for sending bulk airtime using Bleeprs API"""
    
    def __init__(self, api_key: str):
        self.base_url = "https://api.bleeprs.com"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.rate_limit_delay = 0.05  # 20 requests per second max
    
    def get_account_balance(self) -> Dict:
        """Get current account balance"""
        url = f"{self.base_url}/api-reference/endpoint/accountbalance"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
    
    def list_airtime_networks(self) -> Dict:
        """Get list of available airtime networks"""
        url = f"{self.base_url}/api-reference/endpoint/airtimelist"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
    
    def purchase_airtime(self, phone: str, amount: int, network: str | None = None) -> Dict:
        """Purchase airtime for a single number"""
        url = f"{self.base_url}/api/purchaseAirtime"

        if not network:
            phone = "234" + phone[1:]
            network = get_carrier_from_phone(phone)
            print(network)

        # Bleeprs expects an array of objects with keys: phoneNumber, network, amount
        payload = [
            {
                "phoneNumber": phone,
                "network": (network.lower() if isinstance(network, str) else network),
                "amount": amount
            }
        ]
        
        try:
            response = requests.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            # Include response text when available for easier debugging
            err = str(e)
            try:
                err_text = getattr(e, 'response').text if getattr(e, 'response', None) is not None else None
                if err_text:
                    err = f"{err} - {err_text}"
            except Exception:
                pass
            return {"error": err, "phone": phone, "amount": amount}
    
    def purchase_bulk_airtime(self, recipients: List[Dict], batch_size: int = 10) -> List[Dict]:
        """
        Purchase airtime for multiple recipients
        
        Args:
            recipients: List of dicts with 'phone', 'amount', 'network' keys
            batch_size: Number of requests to send before pausing
        
        Returns:
            List of results for each transaction
        """
        results = []
        total = len(recipients)
        
        print(f"Starting bulk airtime purchase for {total} recipients...")
        print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        for idx, recipient in enumerate(recipients, 1):
            phone = recipient.get('phone')
            amount = recipient.get('amount')
            # Use provided network, or auto-detect via getNetwork.js
            network = recipient.get('network')
            if not network:
                network = get_carrier_from_phone(phone)
            if not network:
                network = 'MTN'  # Default fallback
            
            print(f"[{idx}/{total}] Processing {phone} - ₦{amount} ({network})...")
            
            result = self.purchase_airtime(phone, amount, network)
            result['phone'] = phone
            result['amount'] = amount
            result['network'] = network
            results.append(result)
            
            # Check result
            if 'error' in result:
                print(f"  ✗ Failed: {result['error']}")
            else:
                print(f"  ✓ Success")
            
            # Rate limiting: respect 20 requests/second
            time.sleep(self.rate_limit_delay)
            
            # Longer pause after each batch
            if idx % batch_size == 0 and idx < total:
                print(f"\nCompleted batch. Pausing for 2 seconds...\n")
                time.sleep(2)
        
        return results
    
    def view_vending_logs(self, limit: Optional[int] = 50) -> Dict:
        """View vending transaction logs"""
        url = f"{self.base_url}/api-reference/endpoint/vendinglogs"
        params = {"limit": limit} if limit else {}
        
        try:
            response = requests.get(url, headers=self.headers, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
    
    def view_statistics(self) -> Dict:
        """View vending statistics"""
        url = f"{self.base_url}/api-reference/endpoint/vendingstatistics"
        try:
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
    
    def generate_report(self, results: List[Dict]) -> Dict:
        """Generate summary report from bulk purchase results"""
        total = len(results)
        successful = sum(1 for r in results if 'error' not in r)
        failed = total - successful
        total_amount = sum(r['amount'] for r in results if 'error' not in r)
        
        report = {
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "total_transactions": total,
            "successful": successful,
            "failed": failed,
            "success_rate": f"{(successful/total*100):.2f}%",
            "total_amount_sent": total_amount,
            "failed_transactions": [
                {
                    "phone": r['phone'],
                    "amount": r['amount'],
                    "network": r['network'],
                    "error": r.get('error', 'Unknown error')
                }
                for r in results if 'error' in r
            ]
        }
        
        return report

def main():
    """Example usage of the Bleeprs bulk airtime client"""
    
    # Initialize client with your API key
    API_KEY = BLEEPRS_API_KEY
    client = BleeprsAirtimeClient(API_KEY)
    
    # Check account balance first
    print("Checking account balance...")
    # balance = client.get_account_balance()
    # print(f"Balance: {json.dumps(balance, indent=2)}\n")
    
    # # List available networks
    # print("Fetching available networks...")
    # networks = client.list_airtime_networks()
    # print(f"Networks: {json.dumps(networks, indent=2)}\n")
    
    # Define recipients for bulk airtime purchase
    recipients = [
        {"phone": "07035262610", "amount": 100},
        {"phone": "08074235470", "amount": 100},
    ]
    
    # Send bulk airtime
    print("=" * 60)
    # results = client.purchase_airtime("07035262610", 100, "mtn")
    results = client.purchase_bulk_airtime(recipients)
    print(results)
    print("=" * 60)
    
    # Generate and display report
    # print("\n\nBULK AIRTIME PURCHASE REPORT")
    # print("=" * 60)
    # report = client.generate_report(results)
    # print(json.dumps(report, indent=2))
    
    # # View statistics
    # print("\n\nVENDING STATISTICS")
    # print("=" * 60)
    # stats = client.view_statistics()
    # print(json.dumps(stats, indent=2))
    
    # # Save results to file
    # output_file = f"airtime_bulk_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    # with open(output_file, 'w') as f:
    #     json.dump({
    #         "report": report,
    #         "detailed_results": results
    #     }, f, indent=2)
    
    # print(f"\n\nResults saved to: {output_file}")


if __name__ == "__main__":
    # main()
    pass
