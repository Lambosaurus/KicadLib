from PIL import Image
import subprocess, os

def crop_image(src: str, dst: str):
    img = Image.open(src)
    
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    alpha = img.getchannel("A")
    bbox = alpha.getbbox()

    if not bbox:
        raise Exception("Frame is fully transparent!")
    
    img.crop(bbox).save(dst)


def find_bounding_box(images: list[Image.Image|str] ):
    # Work out the worst case bounding box
    union_bbox = None
    for img in images:

        # Images may be PIL image or path.
        if type(img) is str:
            img = Image.open(img).convert("RGBA")

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
    return union_bbox

ANIMATION_FORMATS = [ "gif", "webp" ]

def make_animation(sources: list[str], dst: str, framerate: int = 10):
    images = [ Image.open(path).convert("RGBA") for path in sources ]
    bbox = find_bounding_box(images)
    images = [img.crop(bbox) for img in images]

    images[0].save(
        dst,
        save_all=True,
        append_images=images[1:],
        duration=int(1000 / framerate),
        loop=0,
        disposal=2
    )

def make_wepm(sources: list[str], dst: str, framerate: int = 10):

    x0, y0, x1, y1 = find_bounding_box(sources)

    frame_info_path = os.path.join(os.path.dirname(dst), "ffmpeg-frames.txt")
    with open(frame_info_path, 'w') as f:
        for path in sources:
            f.write(f"file '{os.path.abspath(path)}'\n")

    subprocess.check_output([
        "ffmpeg",
        "-f", "concat",
        "-safe", "0",
        "-r", str(framerate),
        "-i", frame_info_path,
        "-c:v", "libvpx-vp9",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-vf", f"crop={x1-x0}:{y1-y0}:{x0}:{y0},pad=ceil(iw/2)*2:ceil(ih/2)*2",
        dst
    ])

    os.remove(frame_info_path)