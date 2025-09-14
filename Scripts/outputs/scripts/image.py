from PIL import Image

def crop_image(src: str, dst: str):
    img = Image.open(src)
    
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    alpha = img.getchannel("A")
    bbox = alpha.getbbox()

    if not bbox:
        raise Exception("Frame is fully transparent!")
    
    img.crop(bbox).save(dst)


def make_gif(sources: list[str], dst: str, framerate: int = 10):
    images = [ Image.open(path).convert("RGBA") for path in sources ]
    
    # Work out the worst case bounding box
    union_bbox = None
    for img in images:
        alpha = img.getchannel("A")
        bbox = alpha.getbbox()
        if bbox:
            if union_bbox is None:
                union_bbox = bbox
            else:
                union_bbox = (
                    min(union_bbox[0], bbox[0]),
                    min(union_bbox[1], bbox[1]),
                    max(union_bbox[2], bbox[2]),
                    max(union_bbox[3], bbox[3]),
                )
    
    if not union_bbox:
        raise Exception("All frames are fully transparent!")
    
    images = [img.crop(union_bbox) for img in images]

    images[0].save(
        dst,
        save_all=True,
        append_images=images[1:],
        duration=int(1000 / framerate),
        loop=0,
        disposal=2
    )
