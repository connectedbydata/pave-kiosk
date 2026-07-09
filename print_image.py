import asyncio
import sys
import argparse
import platform
import os
from bleak import BleakClient, BleakScanner
from PIL import Image, ImageOps, ImageDraw, ImageFont

# Default BLE printer details for Orgbro X3
if platform.system() == "Darwin":
    DEFAULT_ADDRESS = "8BAC0268-BE53-F740-7877-32C3490B6F75"
elif platform.system() == "Linux":
    DEFAULT_ADDRESS = "05:04:00:00:B6:98"
else:
    DEFAULT_ADDRESS = "auto"

PRINTER_SERVICE_UUID = "0000ff00-0000-1000-8000-00805f9b34fb"
PRINTER_WRITE_CHAR_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
PRINTER_NOTIFY1_CHAR_UUID = "0000ff01-0000-1000-8000-00805f9b34fb"
PRINTER_NOTIFY2_CHAR_UUID = "0000ff03-0000-1000-8000-00805f9b34fb"

DOT_PER_LINE = 864
BYTE_PER_LINE = DOT_PER_LINE // 8  # 108 bytes
LINES_PER_PACKET = 4  # 108 bytes * 4 lines = 432 bytes per packet

def get_default_font():
    system = platform.system()
    if system == "Darwin":
        paths = [
            "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf"
        ]
    elif system == "Linux":
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    else:
        paths = []
    
    for p in paths:
        if os.path.exists(p):
            return p
    return None

DEFAULT_FONT = get_default_font()

# Global state for flow control
credits_available = 0
credits_event = asyncio.Event()

handshake_f1_event = asyncio.Event()
handshake_f2_event = asyncio.Event()

def notify_handler_1(sender, data):
    # print(f"[Notification ff01]: {data.hex()}")
    if len(data) >= 2 and data[0] == 0x64:
        cmd = data[1]
        if cmd == 0xf1:
            handshake_f1_event.set()
        elif cmd == 0xf2:
            handshake_f2_event.set()

def notify_handler_2(sender, data):
    global credits_available
    # print(f"[Notification ff03]: {data.hex()}")
    if len(data) >= 2 and data[0] == 0x01:
        new_credits = data[1]
        credits_available += new_credits
        credits_event.set()

def wrap_sent_packet(cmd, seq, payload):
    header = b'\x64'
    cmd_byte = bytes([cmd])
    seq_byte = bytes([seq])
    length = len(payload).to_bytes(2, 'little')
    suffix = b'\x00\x00\x00\x00\x9b'
    return header + cmd_byte + seq_byte + length + payload + suffix

def prepare_image(image_path, invert=False):
    print(f"Loading image: {image_path}")
    img = Image.open(image_path)
    
    # Convert to grayscale first
    img = img.convert("L")
    
    # Invert colors if requested (thermal prints black on white, so default is no invert)
    if invert:
        img = ImageOps.invert(img)
        
    # Resize keeping aspect ratio to fit print width
    w, h = img.size
    aspect_ratio = h / w
    new_height = int(DOT_PER_LINE * aspect_ratio)
    
    print(f"Resizing image from {w}x{h} to {DOT_PER_LINE}x{new_height}...")
    img = img.resize((DOT_PER_LINE, new_height), Image.Resampling.LANCZOS)
    
    # Convert to 1-bit monochrome using Floyd-Steinberg dithering for high quality
    img = img.convert("1")
    return img

def text_to_image(text, font_path, font_size, width=864, min_height=500):
    print(f"Generating dithered text image using font: {font_path}...")
    # Load font
    font = None
    if font_path:
        try:
            font = ImageFont.truetype(font_path, font_size)
        except Exception as e:
            print(f"Error loading font {font_path}: {e}. Falling back to default font.")
            
    if font is None:
        try:
            # Pillow >= 10.1.0 supports size parameter in load_default
            font = ImageFont.load_default(size=font_size)
        except TypeError:
            font = ImageFont.load_default()
        
    # Wrap text to fit margins
    margin = 60
    max_text_width = width - (margin * 2)
    
    # Parse paragraphs and wrap words
    paragraphs = text.split("\n")
    lines = []
    
    # Use a dummy context to measure text layout
    dummy_img = Image.new("1", (1, 1), 1)
    dummy_draw = ImageDraw.Draw(dummy_img)
    
    for para in paragraphs:
        if not para.strip():
            lines.append("")
            continue
        words = para.split(" ")
        current_line = []
        for word in words:
            test_line = " ".join(current_line + [word])
            bbox = dummy_draw.textbbox((0, 0), test_line, font=font)
            w = bbox[2] - bbox[0]
            if w <= max_text_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    lines.append(word)
                    current_line = []
        if current_line:
            lines.append(" ".join(current_line))
            
    # Calculate vertical spacing and dimensions
    line_heights = []
    for line in lines:
        if not line:
            # Empty line height
            line_heights.append(font_size)
        else:
            bbox = dummy_draw.textbbox((0, 0), line, font=font)
            line_heights.append(bbox[3] - bbox[1])
            
    max_line_height = max(line_heights) if line_heights else font_size
    line_spacing = int(max_line_height * 0.3)
    
    total_text_height = sum(line_heights) + line_spacing * (len(lines) - 1) if lines else 0
    
    # Ensure min_height is respected (for post-it like dimensions)
    height = max(min_height, total_text_height + margin * 2)
    
    # Create white canvas (1 = white)
    img = Image.new("1", (width, height), 1)
    draw = ImageDraw.Draw(img)
    
    # Render centered text
    y = (height - total_text_height) // 2
    for line, lh in zip(lines, line_heights):
        if line:
            bbox = draw.textbbox((0, 0), line, font=font)
            w = bbox[2] - bbox[0]
            x = (width - w) // 2
            draw.text((x, y - bbox[1]), line, font=font, fill=0)
        y += lh + line_spacing
        
    return img

def image_to_raster_lines(img):
    # Invert the bits of the 1-bit image data
    # (Pillow uses 0 for black, 1 for white; thermal printer uses 1 for black, 0 for white)
    raw_data = bytes(~b & 0xFF for b in img.tobytes())
    # Split into lines of BYTE_PER_LINE (108 bytes)
    lines = [raw_data[i:i+BYTE_PER_LINE] for i in range(0, len(raw_data), BYTE_PER_LINE)]
    return lines

async def send_packet_with_credit(client, write_char, cmd, seq, payload, chunk_size=120, chunk_delay=0.008):
    global credits_available
    while credits_available <= 0:
        credits_event.clear()
        try:
            await asyncio.wait_for(credits_event.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            raise TimeoutError("Timeout waiting for printer credit notification.")
        
    credits_available -= 1
    packet = wrap_sent_packet(cmd, seq, payload)
    
    # Split the packet into chunks (default 120 bytes) to prevent BLE UART buffer overflow.
    # We use response=False (Write Without Response) to eliminate roundtrip latency.
    for offset in range(0, len(packet), chunk_size):
        chunk = packet[offset:offset+chunk_size]
        await client.write_gatt_char(write_char, chunk, response=False)
        await asyncio.sleep(chunk_delay)

async def discover_printer(timeout=8.0):
    print("Scanning for ORGBRO thermal printer...")
    found_address = None
    event = asyncio.Event()

    def callback(device, advertising_data):
        nonlocal found_address
        name = device.name if device.name else ""
        if "ORGBRO" in name.upper() or name.upper() == "X3":
            found_address = device.address
            print(f"Discovered ORGBRO printer: {name} [{device.address}]")
            event.set()

    scanner = BleakScanner(callback)
    await scanner.start()
    try:
        # Wait up to the timeout for discovery event
        await asyncio.wait_for(event.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        pass
    finally:
        await scanner.stop()
        
    return found_address

async def print_job(args):
    global credits_available, credits_event, handshake_f1_event, handshake_f2_event
    
    # Re-initialize the events in the current event loop context to prevent loop binding issues
    credits_event = asyncio.Event()
    handshake_f1_event = asyncio.Event()
    handshake_f2_event = asyncio.Event()
    
    # Reset credits
    credits_available = 0
    
    # Prepare the image from file or render from text input
    if args.text:
        img = text_to_image(args.text, args.font, args.font_size, DOT_PER_LINE, args.height)
    elif args.image:
        img = prepare_image(args.image, invert=args.invert)
    else:
        print("Error: You must provide either --image or --text.", file=sys.stderr)
        sys.exit(1)
        
    lines = image_to_raster_lines(img)
    
    # Pad to multiple of LINES_PER_PACKET
    while len(lines) % LINES_PER_PACKET != 0:
        lines.append(b'\x00' * BYTE_PER_LINE)
        
    total_lines = len(lines)
    print(f"Total lines to print: {total_lines}")
    
    address = args.address
    if address.lower() == "auto":
        discovered = await discover_printer()
        if discovered:
            address = discovered
            # Add a small delay to let the adapter settle after scanning
            await asyncio.sleep(1.0)
        else:
            print("Error: Auto-discovery failed. Could not find any ORGBRO devices on BLE.", file=sys.stderr)
            sys.exit(1)
            
    print(f"Connecting to BLE device at {address}...")
    
    # We use a retry loop to enter the context manager and execute printing
    connected = False
    for attempt in range(1, 4):
        try:
            print(f"Connection attempt {attempt}/3...")
            async with BleakClient(address, timeout=12.0) as client:
                print("Connected successfully!")
                connected = True
                
                await client.start_notify(PRINTER_NOTIFY1_CHAR_UUID, notify_handler_1)
                await client.start_notify(PRINTER_NOTIFY2_CHAR_UUID, notify_handler_2)
                print("Subscribed to notifications.")
                
                write_char = client.services.get_service(PRINTER_SERVICE_UUID).get_characteristic(PRINTER_WRITE_CHAR_UUID)
                
                # Wait for initial credits
                print("Waiting for printer ready (credits)...")
                for _ in range(50):
                    if credits_available > 0:
                        break
                    await asyncio.sleep(0.1)
                    
                if credits_available == 0:
                    print("Warning: Did not receive initial credits. Assuming 8 credits.")
                    credits_available = 8
                    
                print(f"Printer ready. Initial credits: {credits_available}")
                seq = 3
                
                # 1. Send Handshake 0x11
                print("Sending handshake 1/2...")
                handshake_f1_event.clear()
                await send_packet_with_credit(client, write_char, 0x11, seq, b'', args.chunk_size, args.chunk_delay)
                seq = (seq + 1) % 64
                
                try:
                    await asyncio.wait_for(handshake_f1_event.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    print("Warning: Handshake 1 response timeout. Continuing.")
                    
                # 2. Send Handshake 0x12
                print("Sending handshake 2/2...")
                handshake_f2_event.clear()
                await send_packet_with_credit(client, write_char, 0x12, seq, b'', args.chunk_size, args.chunk_delay)
                seq = (seq + 1) % 64
                
                try:
                    await asyncio.wait_for(handshake_f2_event.wait(), timeout=3.0)
                except asyncio.TimeoutError:
                    print("Warning: Handshake 2 response timeout. Continuing.")
                    
                # 3. Send Configuration packets 0x0a and 0x09
                print("Sending printer configuration...")
                await send_packet_with_credit(client, write_char, 0x0a, seq, b'\x55', args.chunk_size, args.chunk_delay)
                seq = (seq + 1) % 64
                
                await send_packet_with_credit(client, write_char, 0x09, seq, b'\x0c', args.chunk_size, args.chunk_delay)
                seq = (seq + 1) % 64
                
                # 4. Send print data packets
                print("Printing...")
                last_progress = 0
                for k in range(0, total_lines, LINES_PER_PACKET):
                    chunk = lines[k:k+LINES_PER_PACKET]
                    payload = b"".join(chunk)
                    await send_packet_with_credit(client, write_char, 0x00, seq, payload, args.chunk_size, args.chunk_delay)
                    seq = (seq + 1) % 64
                    
                    # Print progress percentage
                    progress = int((k + LINES_PER_PACKET) / total_lines * 100)
                    if progress != last_progress:
                        print(f"Progress: {progress}%", end="\r")
                        last_progress = progress
                    
                print("\nPrinting complete. Finishing print job...")
                # 5. Send print end packet (Cmd: 0x02, Payload: feed length 200)
                await send_packet_with_credit(client, write_char, 0x02, seq, b'\xc8\x00', args.chunk_size, args.chunk_delay)
                
                print("Waiting for printer to finish feeding...")
                await asyncio.sleep(3.0)
                
                await client.stop_notify(PRINTER_NOTIFY1_CHAR_UUID)
                await client.stop_notify(PRINTER_NOTIFY2_CHAR_UUID)
                print("Done!")
                break
        except Exception as e:
            print(f"Connection attempt {attempt} failed: {e}")
            if attempt < 3:
                print("Retrying in 3 seconds...")
                await asyncio.sleep(3.0)
                
    if not connected:
        print("Error: Failed to connect to printer after 3 attempts.", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Print images or text to the Orgbro X3 Mini Thermal Printer via BLE.")
    
    # Main sources
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--image", help="Path to the PNG or JPEG image to print.")
    group.add_argument("--text", help="Text to render and print in a handwriting style.")
    
    # Text rendering options
    parser.add_argument("--font", default=DEFAULT_FONT, help=f"TrueType/OpenType font path (default: {DEFAULT_FONT})")
    parser.add_argument("--font-size", type=int, default=48, help="Font size for rendered text (default: 48)")
    parser.add_argument("--height", type=int, default=500, help="Minimum height of the sticker in dots/lines (default: 500, ~1.66 inches)")
    
    # Connection / BLE details
    parser.add_argument("--address", default=DEFAULT_ADDRESS, help=f"BLE MAC Address of the printer (default: {DEFAULT_ADDRESS})")
    parser.add_argument("--invert", action="store_true", help="Invert image colors before printing (only applies to --image).")
    parser.add_argument("--chunk-size", type=int, default=120, help="Size of BLE write chunks (default: 120)")
    parser.add_argument("--chunk-delay", type=float, default=0.008, help="Delay between BLE chunks in seconds (default: 0.008)")
    
    args = parser.parse_args()
    asyncio.run(print_job(args))


