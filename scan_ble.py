import asyncio
from bleak import BleakScanner

async def main():
    print("Scanning for Bluetooth Low Energy devices for 10 seconds...")
    devices = await BleakScanner.discover(timeout=10.0)
    
    orgbro_devices = []
    print("\nAll Discovered Devices:")
    for d in devices:
        name = d.name if d.name else "Unknown"
        print(f"  Address: {d.address} | Name: {name}")
        if d.name and "ORGBRO" in d.name.upper():
            orgbro_devices.append(d)
            
    print("\n--- ORGBRO Specific Devices ---")
    if orgbro_devices:
        for d in orgbro_devices:
            print(f"  FOUND: Name: {d.name} | Address: {d.address}")
    else:
        print("  No ORGBRO devices found. Make sure the printer is turned ON and is not currently connected to another device (like your phone).")

if __name__ == "__main__":
    asyncio.run(main())
