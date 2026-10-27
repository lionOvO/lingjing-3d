"""Create a tall, detailed reference and intentionally incomplete mask for UI QA."""
from pathlib import Path
from PIL import Image, ImageDraw

directory = Path(__file__).resolve().parents[3] / 'tmp' / 'preprocess-ux-20261022'
directory.mkdir(parents=True, exist_ok=True)
image = Image.new('RGBA', (512, 1536), (35, 47, 63, 255))
draw = ImageDraw.Draw(image)
draw.rectangle((241, 140, 271, 1390), fill=(166, 182, 202, 255))
draw.polygon([(256, 45), (285, 125), (271, 165), (241, 165), (227, 125)], fill=(212, 225, 238, 255))
draw.ellipse((210, 1375, 302, 1465), fill=(164, 184, 205, 255))
draw.rectangle((225, 1450, 287, 1470), fill=(188, 205, 224, 255))
image.save(directory / 'source.png')
mask = Image.new('RGBA', image.size)
mask.paste(image.crop((209, 170, 303, 1480)), (209, 170))
mask.save(directory / 'mask.png')
