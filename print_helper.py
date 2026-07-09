import os
import sys
import argparse
import asyncio
import qrcode
from PIL import Image, ImageDraw, ImageFont

# Resolve paths dynamically relative to this script's directory
kiosk_dir = os.path.dirname(os.path.abspath(__file__))

def find_orgbro_dir():
    """Locate the Orgbro directory on both development and kiosk machines."""
    home_dir = os.path.expanduser("~")
    candidates = [
        # Sibling CitizensTrack (Dev machine)
        os.path.join(kiosk_dir, "..", "CitizensTrack", "Orgbro"),
        # Sibling directly
        os.path.join(kiosk_dir, "..", "Orgbro"),
        os.path.join(kiosk_dir, "..", "orgbro"),
        os.path.join(kiosk_dir, "..", "orgbro_printer"),
        # Home directory candidates
        os.path.join(home_dir, "orgbro"),
        os.path.join(home_dir, "orgbro_printer"),
        os.path.join(home_dir, "CitizensTrack", "Orgbro"),
        os.path.join(home_dir, "Documents", "ConnectedByData", "CitizensTrack", "Orgbro"),
        # Hardcoded target paths
        "/home/admin/orgbro_printer",
        "/home/admin/orgbro",
        "/home/admin/CitizensTrack/Orgbro",
        "/Users/admin/Documents/ConnectedByData/CitizensTrack/Orgbro"
    ]
    for c in candidates:
        abs_path = os.path.abspath(c)
        py_path = os.path.join(abs_path, "venv", "bin", "python")
        if os.path.exists(py_path):
            return abs_path
            
    # Fallback to dev path
    return os.path.abspath(os.path.join(kiosk_dir, "..", "CitizensTrack", "Orgbro"))

# Add Orgbro directory to path so we can import print_image
ORGBRO_DIR = find_orgbro_dir()
sys.path.append(ORGBRO_DIR)

try:
    from print_image import print_job, get_default_font
except ImportError as e:
    print(f"Error importing from print_image: {e}", file=sys.stderr)
    sys.exit(1)

def generate_teaser(episode_idx, output_path):
    print(f"Generating teaser for episode {episode_idx}...")
    
    # Map episode index to cover image and public URL
    # Episode 0: Media
    # Episode 1: Education
    # Episode 2: Bus stop / How We Use It
    covers = [
        os.path.join(kiosk_dir, "sites", "site4", "toons", "assets", "img", "lets-talk-ai-media-1-carousel.webp"),
        os.path.join(kiosk_dir, "sites", "site4", "toons", "assets", "img", "lets-talk-ai-education-1-carousel.webp"),
        os.path.join(kiosk_dir, "sites", "site4", "toons", "assets", "img", "lets-talk-ai-bus-stop-1-carousel.webp")
    ]
    urls = [
        "https://www.letstalkai.org.uk/toons/media.html",
        "https://www.letstalkai.org.uk/toons/education.html",
        "https://www.letstalkai.org.uk/toons/how_you_use_it.html"
    ]
    
    if episode_idx < 0 or episode_idx >= len(covers):
        raise ValueError(f"Invalid episode index: {episode_idx}")
        
    cover_path = covers[episode_idx]
    target_url = urls[episode_idx]
    
    if not os.path.exists(cover_path):
        raise FileNotFoundError(f"Cover image not found at {cover_path}")
        
    # Load cover image, convert to grayscale
    cover = Image.open(cover_path).convert("L")
    w, h = cover.size
    aspect = h / w
    cover_w = 864
    cover_h = int(cover_w * aspect)
    cover = cover.resize((cover_w, cover_h), Image.Resampling.LANCZOS)
    
    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(target_url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("L")
    
    # Resize QR code to standard size
    qr_size = 220
    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)
    
    # Render URL text: https://www.letstalkai.org in bold
    font_path = get_default_font()
    bold_font_path = None
    if font_path:
        bold_paths = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            font_path
        ]
        for bp in bold_paths:
            if os.path.exists(bp):
                bold_font_path = bp
                break
                
    font_size = 36
    try:
        if bold_font_path:
            font = ImageFont.truetype(bold_font_path, font_size)
        else:
            font = ImageFont.load_default(size=font_size)
    except Exception:
        font = ImageFont.load_default()
        
    # Create blank canvas
    # Height: cover height + QR height + text height + padding
    padding = 30
    canvas_h = cover_h + qr_size + font_size + (padding * 4)
    canvas = Image.new("1", (864, canvas_h), 1)
    
    # Paste cover (converted to 1-bit monochrome)
    canvas.paste(cover.convert("1"), (0, 0))
    
    # Paste QR code (centered horizontally)
    qr_x = (864 - qr_size) // 2
    qr_y = cover_h + padding
    canvas.paste(qr_img.convert("1"), (qr_x, qr_y))
    
    # Draw URL text
    draw = ImageDraw.Draw(canvas)
    text = "https://www.letstalkai.org"
    
    # Measure text width to center it
    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_w = bbox[2] - bbox[0]
    except Exception:
        text_w = len(text) * 20
        
    text_x = (864 - text_w) // 2
    text_y = qr_y + qr_size + padding
    draw.text((text_x, text_y), text, font=font, fill=0)
    
    canvas.save(output_path)
    print(f"Teaser image saved to {output_path}")

async def run_print(image_path):
    class MockArgs:
        def __init__(self, img_path):
            self.image = img_path
            self.text = None
            self.font = None
            self.font_size = 48
            self.height = 500
            self.address = "auto"
            self.invert = False
            self.chunk_size = 120
            self.chunk_delay = 0.008
            
    args = MockArgs(image_path)
    await print_job(args)

def main():
    parser = argparse.ArgumentParser(description="Print helper for Let's Talk AI Kiosk.")
    parser.add_argument("--type", required=True, choices=["teaser", "full"], help="Print type: teaser or full scroll")
    parser.add_argument("--episode", required=True, type=int, help="Episode index (0, 1, 2)")
    args = parser.parse_args()
    
    temp_dir = os.path.join(kiosk_dir, "static")
    os.makedirs(temp_dir, exist_ok=True)
    temp_path = os.path.join(temp_dir, "temp_print_job.png")
    
    if args.type == "teaser":
        try:
            generate_teaser(args.episode, temp_path)
        except Exception as e:
            print(f"Error generating teaser: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        # Full scroll
        full_scrolls = [
            os.path.join(ORGBRO_DIR, "images", "lets-talk-ai-media.png"),
            os.path.join(ORGBRO_DIR, "images", "lets-talk-ai-education.png"),
            os.path.join(ORGBRO_DIR, "images", "lets-talk-ai-bus-stop.png")
        ]
        if args.episode < 0 or args.episode >= len(full_scrolls):
            print(f"Error: Invalid episode index {args.episode}", file=sys.stderr)
            sys.exit(1)
            
        temp_path = full_scrolls[args.episode]
        if not os.path.exists(temp_path):
            print(f"Error: Full scroll image not found at {temp_path}", file=sys.stderr)
            sys.exit(1)
            
    # Run the print job
    try:
        asyncio.run(run_print(temp_path))
        print("Print job completed successfully.")
    except Exception as e:
        print(f"Error during printing: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        # Clean up teaser temp file
        if args.type == "teaser" and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass

if __name__ == "__main__":
    main()
