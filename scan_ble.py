import asyncio
from bleak import BleakScanner

async def main():
    print("Scanning for Bluetooth Low Energy devices for 10 seconds...")
    print("Only displaying named devices and highlighting ORGBRO printers to reduce noise...\n")
    
    orgbro_devices = []
    
    def callback(device, advertising_data):
        name = device.name if device.name else ""
        if not name:
            return
            
        is_printer = "ORGBRO" in name.upper() or name.upper() == "X3"
        prefix = "⭐️ [PRINTER] " if is_printer else "             "
        print(f"  {prefix}Address: {device.address} | Name: {name} | RSSI: {device.rssi}dBm")
        
        if is_printer and device.address not in [d.address for d in orgbro_devices]:
            orgbro_devices.append(device)

    scanner = BleakScanner(callback)
    await scanner.start()
    await asyncio.sleep(10.0)
    await scanner.stop()
            
    print("\n--- Summary ---")
    if orgbro_devices:
        print(f"Found {len(orgbro_devices)} ORGBRO printer(s):")
        for d in orgbro_devices:
            print(f"  FOUND: Name: {d.name} | Address: {d.address}")
    else:
        print("  No ORGBRO devices found. Make sure the printer is turned ON, has battery, and is not currently connected to another device (like your phone).")

if __name__ == "__main__":
    asyncio.run(main())
