import subprocess
import os, sys, shutil, platform, json, argparse, glob, contextlib
import bom, image, pdfmerge, bundle

SCRIPT_VERSION = "v1.25"
KICAD_VERSION = "9.0"

if platform.platform().startswith("Windows"):
    # You may need to edit this
    KICAD_ROOT = f"C:/Program Files/KiCad/{KICAD_VERSION}/bin"
    KICAD_CLI = os.path.join(KICAD_ROOT, "kicad-cli.exe")
    KICAD_PYTHON = os.path.join(KICAD_ROOT, "python.exe")
    IBOM_SCRIPT = os.path.expandvars(f"%USERPROFILE%/Documents/KiCad/{KICAD_VERSION}/3rdparty/plugins/org_openscopeproject_InteractiveHtmlBom/generate_interactive_bom.py")
else:
    KICAD_CLI = "kicad-cli"
    KICAD_PYTHON = "python3"
    IBOM_SCRIPT = os.path.expanduser(f"~/.local/share/kicad/{KICAD_VERSION}/3rdparty/plugins/org_openscopeproject_InteractiveHtmlBom/generate_interactive_bom.py")


def get_layer_names(layers: int) -> list[str]:
    names = ["F.Fab", "F.SilkS", "F.Paste", "F.Mask", "F.Cu", "B.Cu", "B.Mask", "B.Paste", "B.SilkS", "B.Fab", "Edge.Cuts"]
    if layers > 2:
        for i in range(layers - 2):
            names.append(f"In{i + 1}.Cu")
    return names

def run_command(args: list[str], silent: bool = False) -> str:
    try:
        stderr = subprocess.DEVNULL if silent else None
        return subprocess.check_output(args, stderr=stderr).decode().strip()
    except subprocess.CalledProcessError as e:
        print_color(f"Command failed with code {e.returncode}!", "r")
        print_color(' '.join(args), "r")
        print_color(e.stdout.decode().strip(), "r")
        print("Aborting...")
        exit()

def print_color(text: str, color: str = "r"):
    colors = {
        "r": "\033[91m",
        "g": "\033[92m",
        "y": "\033[93m",
        "b": "\033[94m",
    }
    print(colors[color] + text + "\033[0m")

def clean_directory(dir: str):
    # Remove output directory (and its contents) and recreate it
    if (os.path.exists(dir)):
        shutil.rmtree(dir)
    os.makedirs(dir)

@contextlib.contextmanager
def temp_directory(base: str, name: str = "tmp", preserve: bool = False):
    path = os.path.join(base, name)
    os.makedirs(path, exist_ok=True)
    try:
        yield path
    finally:
        if not preserve:
            shutil.rmtree(path)

def report_errors(title: str, errors: list[dict[str, str]]) -> dict[str, int]:
    groups = {}
    for error in errors:
        severity = error["severity"]
        if severity not in groups:
            groups[severity] = 0
        groups[severity] += 1

    if groups:
        msg = f"{title}: " + ", ".join([f"{count} {type}s" for type, count in groups.items()])
        color = "r" if "error" in groups else "y"
        print_color(msg, color)


def run_sch_erc(input_sch: str, output_dir: str):
    # Run schematic ERC check
    outfile = os.path.join(output_dir, "sch-erc.json")
    run_command([
        KICAD_CLI, "sch", "erc",
        input_sch,
        "--output", outfile,
        "--format", "json",
        "--severity-warning",
        "--severity-error",
    ])
    
    with open(outfile, "r") as f:
        report = json.load(f)
        report_errors("ERC report", sum((sheet["violations"] for sheet in report["sheets"]),[]))

    os.remove(outfile)

def run_pcb_drc(input_pcb: str, output_dir: str):
    # Run PCB DRC check
    outfile = os.path.join(output_dir, "pcb-drc.json")
    run_command([
        KICAD_CLI, "pcb", "drc",
        input_pcb,
        "--output", outfile,
        "--format", "json",
        "--severity-warning",
        "--severity-error",
        "--schematic-parity",
    ])
    
    with open(outfile, "r") as f:
        report = json.load(f)
        report_errors("Schematic parity", report["schematic_parity"])
        report_errors("Unconnected items", report["unconnected_items"])
        report_errors("DRC report", report["violations"])

    os.remove(outfile)


def export_sch_pdf(input_sch: str, output_pdf: str):
    # Create PDF from schematic
    run_command([
        KICAD_CLI, "sch", "export", "pdf",
        input_sch,
        "--output", output_pdf,
    ])

def export_sch_bom(input_sch: str, output_csv: str) -> list[str]:
    os.makedirs( os.path.dirname(output_csv) )
    output_xml = output_csv.replace(".csv", ".xml")
    run_command([
        KICAD_CLI, "sch", "export", "python-bom",
        input_sch,
        "--output", output_xml,
    ])
    components = bom.load_components(output_xml)
    bom.create_bom(components, output_csv)
    dnf_list = bom.get_dnf_list(components)
    os.remove(output_xml)
    return dnf_list

def export_pcb_gerbers(input_pcb: str, output_dir: str, layers: list[str]):
    os.makedirs(output_dir)
    run_command([
        KICAD_CLI, "pcb", "export", "gerbers",
        input_pcb,
        "--output", output_dir,
        "--layers", ",".join(layers),
    ])

def export_pcb_ncdrill(input_pcb: str, output_dir: str):
    os.makedirs(output_dir)
    run_command([
        KICAD_CLI, "pcb", "export", "drill",
        input_pcb,
        "--output", output_dir + "/",
        "--format", "excellon",
        "--excellon-zeros-format", "suppressleading",
        "--excellon-units", "mm",
        "--drill-origin", "absolute",
        "--excellon-separate-th",
        "--excellon-min-header",
        "--generate-map",
        "--map-format", "gerberx2",
    ])

def fix_pos_header(header: str):
    header = header.replace("Ref", "Designator")
    header = header.replace("PosX", "Mid X")
    header = header.replace("PosY", "Mid Y")
    header = header.replace("Rot", "Rotation")
    header = header.replace("Side", "Layer")
    return header

def export_pcb_pos(input_pcb: str, output_file: str):
    run_command([
        KICAD_CLI, "pcb", "export", "pos",
        input_pcb,
        "--output", output_file,
        "--units", "mm",
        "--side", "both",
        "--format", "csv",
    ])

    with open(output_file, "r+") as f:
        f.seek(0)
        lines = f.readlines()
        lines[0] = fix_pos_header(lines[0])
        f.seek(0)
        f.writelines(lines)
        f.truncate()


def export_pcb_step(input_pcb: str, output_file: str):
    run_command([
        KICAD_CLI, "pcb", "export", "step",
        input_pcb,
        "--output", output_file,
        "--no-dnp",
    ])

def export_pcb_ibom(input_pcb: str, output_file: str, dnf_list: list[str] = []):

    if not os.path.exists(IBOM_SCRIPT):
        print_color(f"IBOM plugin not found", "y")
        return

    os.environ['INTERACTIVE_HTML_BOM_NO_DISPLAY'] = "1"
    run_command([
        KICAD_PYTHON, IBOM_SCRIPT, input_pcb,
        "--no-browser",
        "--dest-dir", os.path.dirname(output_file),
        "--dark-mode",
        "--show-fabrication",
        "--include-tracks",
        "--include-nets",
        "--name-format", os.path.basename(output_file).replace(".html", ""),
        "--blacklist", ",".join(dnf_list)
    ], silent=True)

def export_pcb_image(input_pcb: str, output_file: str, side: str = "top", zoom: float = 0.9, resolution: int = 2000):
    resolution = [str(resolution), str(resolution)]
    run_command([
        KICAD_CLI, "pcb", "render",
        input_pcb,
        "--output", output_file,
        "--quality", "user",
        "--perspective",
        "--zoom", f"{zoom:.2f}",
        "--width", resolution[0],
        "--height", resolution[1],
        "--background", "transparent",
        "--side", side,
    ])
    image.crop_image(output_file, output_file)

def export_pcb_gif(input_pcb: str, output_file: str, direction: str = "left", zoom: float = 0.7, framerate: int = 20, duration: float = 3.0, resolution: int = 640):

    rotate_str = {
        "up":       lambda a: f"{-a:.03f},0,0",
        "down":     lambda a: f"{a:.03f},0,0",
        "left":     lambda a: f"0,{a:.03f},0",
        "right":    lambda a: f"0,{-a:.03f},0",
    }[direction]

    frames = int(duration * framerate)
    resolution = [str(resolution), str(resolution)]

    with temp_directory(os.path.dirname(output_file), "gif-tmp") as tmpdir:
        images = []
        for f in range(frames):
            angle = 360.0 * f / frames
            path = os.path.join(tmpdir, f"{f:04d}.png")
            images.append(path)
            run_command([
                KICAD_CLI, "pcb", "render",
                input_pcb,
                "--output", path,
                "--quality", "user",
                "--perspective",
                "--zoom", f"{zoom:.2f}",
                "--width", resolution[0],
                "--height", resolution[1],
                "--background", "transparent",
                "--side", "top",
                "--rotate", rotate_str(angle)
            ])
        
        image.make_gif(images, output_file, framerate)

def export_pcb_drawings(input_pcb: str, output_file: str, layers: int, extra_layers: list[str] = None):

    if not pdfmerge.get_backend():
        print_color("No PDF merging backend available. Skipping PCB drawings", "y")
        return

    with temp_directory(os.path.dirname(output_file), "pdf-tmp") as tmpdir:
        plots = [
            {
                "name": "Top Fabrication",
                "layers": ["F.Fab", "Edge.Cuts"],
            },
            {
                "name": "Bottom Fabrication",
                "layers": ["B.Fab", "Edge.Cuts"],
            },
            {
                "name": "Top",
                "layers": ["F.Cu", "F.Paste", "F.SilkS", "Edge.Cuts"],
            },
            {
                "name": "Bottom",
                "layers": ["B.Cu", "B.Paste", "B.SilkS", "Edge.Cuts"],
            },
        ]

        if layers > 2:
            # Put the internal layers between the top and bottom layers
            bottom = plots.pop(-1)
            for i in range(layers - 2):
                plots.append({
                    "name": f"Inner Layer {i + 1}",
                    "layers": [f"In{i + 1}.Cu", "Edge.Cuts"]
                })
            plots.append(bottom)

        if extra_layers:
            for layer in extra_layers:
                plots.append({
                    "name": f"Layer {layer}",
                    "layers": [layer, "Edge.Cuts"]
                })

        for plot in plots:
            result = run_command([
                KICAD_CLI, "pcb", "export", "pdf",
                input_pcb,
                "--layers", plot["layers"][0],
                "--common-layers", ",".join(plot["layers"][1:]),
                "--output", tmpdir,
                "--include-border-title",
                "--drill-shape-opt", "2",
                "--define-var", f"LAYER_NAME={plot['name']}",
                "--mode-separate",
            ])
            # Result format: "Plotted to 'outputs/pdf-tmp/pcb_name-F_Fab.pdf'."
            plot["filename"] = result.split("'")[-2]

        pages = [ plot["filename"] for plot in plots ]
        pdfmerge.merge_pdf(pages, output_file)

def run_git_check() -> str:
    if not shutil.which("git"):
        print_color("Git not found. Skipping git check.", "y")
        return None

    try:
        output = run_command(["git", "status"], silent=True)
    except subprocess.CalledProcessError:
        print_color("Not a git repository.", "y")
        return None
    
    git_commit = run_command(["git", "rev-parse", "--short", "HEAD"], silent=True)

    if not "nothing to commit, working tree clean" in output:
        print_color("Git repository has uncommitted changes.", "y")
    else:
        print(f"Git commit: {git_commit}")

    return git_commit

def zip_files(input_path: str, output_file: str, files: list[str] = None):
    bundle.bundle(input_path, output_file, files)

def zip_release_pack(input_path: str, output_file: str, format: str):
    if format == "jlc":
        zip_files(input_path, output_file, [
            "Assembly",
            "Gerber",
            "NC Drill",
        ])
    else:
        raise ValueError(f"Unknown release format: {format}.")

def glob_single(input_pattern: str) -> str:
    files = glob.glob(input_pattern)
    if len(files) == 0:
        raise FileNotFoundError(f"No files match \"{input_pattern}\"")
    if len(files) > 1:
        raise ValueError(f"Multiple files match \"{input_pattern}\".")
    return files[0]

if __name__ == "__main__":

    sys.argv[-1] = sys.argv[-1].strip()  # Remove trailing carriage return for *nix/win compat.
    argparser = argparse.ArgumentParser(description="Output generator for kicad projects")
    argparser.add_argument("--input", "-i", type=str, help="Kicad project", default="*.kicad_pro")
    argparser.add_argument("--output", "-o", type=str, help="Output directory", default="outputs")
    argparser.add_argument("--layers", "-l", type=int, help="Number of layers in the PCB design.", default=2)
    argparser.add_argument("--extra-layer", action="append", default=[], help="Additional PCB layers to add to gerbers and drawings")
    argparser.add_argument("--render-side", type=str, help="Side of the board to render.", default="top", choices=["top", "bottom", "left", "right", "front", "back"])
    argparser.add_argument("--render-zoom", type=float, help="Zoom used for rendering.", default=0.9)
    argparser.add_argument("--render-resolution", type=int, help="Render resolution (before cropping)", default=2000)
    argparser.add_argument("--gif", action="store_true", help="Enables gif generation")
    argparser.add_argument("--gif-zoom", type=float, help="Zoom used for gif rendering.", default=0.7)
    argparser.add_argument("--gif-duration", type=float, help="Duration of the gif in seconds.", default=3.0)
    argparser.add_argument("--gif-framerate", type=int, help="Framerate of the gif.", default=20)
    argparser.add_argument("--gif-resolution", type=int, help="Gif resolution (before cropping)", default=640)
    argparser.add_argument("--gif-direction", type=str, help="Rotation direction of the gif", default="left", choices=["up", "down", "left", "right"])
    argparser.add_argument("--name", type=str, help="Output name", default=None)
    argparser.add_argument("--wait-on-done", action="store_true", help="Wait to hold the terminal open when done.")
    argparser.add_argument("--format", type=str, help="Manufacturer specific output options", default=None, choices=["jlc"])
    argparser.add_argument("--compression", type=str, help="Compression format", default="zip", choices=bundle.SUPPORTED_FORMATS)
    args = argparser.parse_args()

    # Strip file extention
    input_file = glob_single(args.input)
    input_file = os.path.splitext(input_file)[0]
    
    INPUT_SCH = input_file + ".kicad_sch"
    INPUT_PCB = input_file + ".kicad_pcb"
    OUTPUT_DIR = args.output
    OUTPUT_NAME = args.name if args.name else os.path.basename(input_file)

    print("Running output generator {}".format(SCRIPT_VERSION))

    clean_directory(OUTPUT_DIR)

    print("Checking git status")
    run_git_check()

    print("Running schematic ERC")
    run_sch_erc(INPUT_SCH, OUTPUT_DIR)

    print("Generating schematic PDF")
    export_sch_pdf(INPUT_SCH, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".schematics.pdf"))

    print("Running PCB DRC")
    run_pcb_drc(INPUT_PCB, OUTPUT_DIR)

    print("Generating BOM")
    dnf_list = export_sch_bom(INPUT_SCH, os.path.join(OUTPUT_DIR, "Assembly" , OUTPUT_NAME + ".bom.csv"))

    print("Generating IBOM")
    export_pcb_ibom(INPUT_PCB, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".ibom.html"), dnf_list)

    print("Generating gerbers")
    export_pcb_gerbers(INPUT_PCB, os.path.join(OUTPUT_DIR, "Gerber"), get_layer_names(args.layers) + args.extra_layer)

    print("Generating drill reports")
    export_pcb_ncdrill(INPUT_PCB, os.path.join(OUTPUT_DIR, "NC Drill"))

    print("Generating position report")
    export_pcb_pos(INPUT_PCB, os.path.join(OUTPUT_DIR, "Assembly", OUTPUT_NAME + ".pos.csv"))

    print("Generating PCB drawings")
    export_pcb_drawings(INPUT_PCB, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".drawings.pdf"), args.layers, args.extra_layer)

    print("Generating PCB render")
    export_pcb_image(INPUT_PCB, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".png"),
            side = args.render_side,
            zoom = args.render_zoom,
            resolution = args.render_resolution
        )

    if args.gif:
        print("Generating PCB gif")
        export_pcb_gif(INPUT_PCB, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".gif"),
            direction = args.gif_direction,
            zoom = args.gif_zoom,
            framerate = args.gif_framerate,
            duration = args.gif_duration,
            resolution = args.gif_resolution
        )

    print("Generating step file")
    export_pcb_step(INPUT_PCB, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".step"))

    print(f"Generating {args.compression} file")
    zip_files(OUTPUT_DIR, os.path.join(OUTPUT_DIR, f"{OUTPUT_NAME}.{args.compression}"))

    if args.format != None:
        print(f"Generating {args.format} release pack")
        zip_release_pack(OUTPUT_DIR, os.path.join(OUTPUT_DIR, f"{OUTPUT_NAME}.{args.format}.{args.compression}"), args.format)

    print("Done!")
    if args.wait_on_done:
        input("Press enter to exit...")
