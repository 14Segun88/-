#!/usr/bin/env python3
"""
Декодирование FPTN VPN токена
"""

import base64
import json

# FPTN токен
token = "fptn:eyJ2ZXJzaW9uIjogMSwgInNlcnZpY2VfbmFtZSI6ICJGUFROLk9OTElORSIsICJ1c2VybmFtZSI6ICJ1c2VyNTk2NTM2MzAzNCIsICJwYXNzd29yZCI6ICJFVFpnQllqQSIsICJzZXJ2ZXJzIjogW3sibmFtZSI6ICJFc3RvbmlhIiwgImhvc3QiOiAiMTg1LjIxNS4xODcuMTY1IiwgIm1kNV9maW5nZXJwcmludCI6ICJkMDA5ZmQ5Y2ViMjgzNTI2ODMyZTVhZDNjZDUwMjM0YSIsICJwb3J0IjogNDQzfSwgeyJuYW1lIjogIkxhdHZpYS0xIiwgImhvc3QiOiAiMjE2LjE3My43MC43MyIsICJtZDVfZmluZ2VycHJpbnQiOiAiYTVmNGFjZTdmM2VhN2IxZDM1YWFmMDZiMzA4Zjc5ODIiLCAicG9ydCI6IDQ0M30sIHsibmFtZSI6ICJMYXR2aWEtMiIsICJob3N0IjogIjUuMzQuMjE0LjE0MCIsICJtZDVfZmluZ2VycHJpbnQiOiAiNzI1YmEyNDc4ODUyYmYyYWNiNGVkNTM1YzkwNDMyY2IiLCAicG9ydCI6IDQ0M30sIHsibmFtZSI6ICJOZXRoZXJsYW5kcy0xIiwgImhvc3QiOiAiMTQ3LjQ1LjEzNS42NyIsICJtZDVfZmluZ2VycHJpbnQiOiAiY2Q0ODM2NzE3MmY4NzBjMTcxNGZjZTJiZjg4ZTZlNzEiLCAicG9ydCI6IDQ0M30sIHsibmFtZSI6ICJVU0EtU2VhdHRsZSIsICJob3N0IjogIjE5Mi4zLjI1MS43OSIsICJtZDVfZmluZ2VycHJpbnQiOiAiNjU5MDFjMWM0MDlkMjAwYWM1YThkNGY5NDBlMjgzY2EiLCAicG9ydCI6IDQ0M30sIHsibmFtZSI6ICJKYXBhbi0xIiwgImhvc3QiOiAiMzguMTgwLjE0Ny4yMzgiLCAibWQ1X2ZpbmdlcnByaW50IjogIjZhZWUyMTExYjA5ZjQzNjQ2MzMxNDcwMTM0Y2I5Mzg5IiwgInBvcnQiOiA0NDN9XSwgImNlbnNvcmVkX3pvbmVfc2VydmVycyI6IFt7Im5hbWUiOiAiUnVzc2lhIChTYWludCBQZXRlcnNidXJnKSIsICJob3N0IjogIjk0LjI0Mi41MS4xODUiLCAibWQ1X2ZpbmdlcnByaW50IjogIjg5ZjY4ZWVlYTFmZWE2ZjI5MzhjMzc5NWYzZmY5MTBkIiwgInBvcnQiOiA0NDN9XX0"

# Удаляем префикс fptn:
encoded_data = token.replace("fptn:", "")

# Добавляем padding если нужно
missing_padding = len(encoded_data) % 4
if missing_padding:
    encoded_data += '=' * (4 - missing_padding)

# Декодируем base64
decoded_bytes = base64.b64decode(encoded_data)
decoded_str = decoded_bytes.decode('utf-8')

# Парсим JSON
vpn_data = json.loads(decoded_str)

print("=" * 60)
print("🔐 FPTN VPN CONFIGURATION")
print("=" * 60)
print(f"\n📧 Username: {vpn_data['username']}")
print(f"🔑 Password: {vpn_data['password']}")
print(f"🌐 Service: {vpn_data['service_name']}")

print("\n📡 Available Servers:")
print("-" * 40)
for server in vpn_data['servers']:
    print(f"\n📍 {server['name']}")
    print(f"   Host: {server['host']}")
    print(f"   Port: {server['port']}")
    print(f"   MD5: {server['md5_fingerprint'][:16]}...")

if 'censored_zone_servers' in vpn_data:
    print("\n🚫 Censored Zone Servers:")
    print("-" * 40)
    for server in vpn_data['censored_zone_servers']:
        print(f"\n📍 {server['name']}")
        print(f"   Host: {server['host']}")
        print(f"   Port: {server['port']}")

print("\n" + "=" * 60)
print("💡 RECOMMENDATIONS:")
print("=" * 60)
print("1. Use Japan-1 server for Asian exchanges (OKX, Huobi)")
print("2. Use USA-Seattle for American exchanges (Coinbase)")
print("3. Use Netherlands-1 for European access")
print("4. Estonia/Latvia servers for general use")

# Сохраняем конфигурацию в файл
with open('vpn_config.json', 'w') as f:
    json.dump(vpn_data, f, indent=2)
print("\n✅ VPN configuration saved to vpn_config.json")
