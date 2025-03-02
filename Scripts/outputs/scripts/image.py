from PIL import Image

def crop_image(src: str, dst: str):
    img = Image.open(src)
    
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    alpha = img.split()[3]
    bbox = alpha.getbbox()
    
    if bbox:
        img.crop(bbox).save(dst)
    else:
        print("Warning, image is fully transparent!")