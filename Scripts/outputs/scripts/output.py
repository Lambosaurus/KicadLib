import subprocess
import os, sys, shutil, platform, json
import bom, image

SCRIPT_VERSION = "v1.16"
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
    names = ["F.SilkS", "F.Paste", "F.Mask", "F.Cu", "B.Cu", "B.Mask", "B.Paste", "B.SilkS", "Edge.Cuts"]
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

def export_pcb_image(input_pcb: str, output_file: str):
    run_command([ KICAD_CLI, "pcb", "render",
        input_pcb,
        "--output", output_file,
        "--quality", "user",
        "--perspective",
        "--zoom", "0.9",
        "--width", "2000",
        "--height", "2000",
        "--background", "transparent",
    ])
    image.crop_image(output_file, output_file)

def zip_files(input_path: str, output_file: str):
    run_command([
        "tar",
        "-C", input_path,
        "-acf", output_file,
    ] + os.listdir(input_path)
    )

if __name__ == "__main__":
    BOARD_NAME = sys.argv[1]
    BOARD_LAYERS = int(sys.argv[2])

    INPUT_SCH = BOARD_NAME + ".kicad_sch"
    INPUT_PCB = BOARD_NAME + ".kicad_pcb"
    OUTPUT_DIR = "outputs"
    OUTPUT_NAME = BOARD_NAME

    print("Running output generator {}".format(SCRIPT_VERSION))

    clean_directory(OUTPUT_DIR)

    print("Running schematic ERC")
    run_sch_erc(INPUT_SCH, OUTPUT_DIR)

    print("Generating schematic PDF")
    export_sch_pdf(INPUT_SCH, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".pdf"))

    print("Running PCB DRC")
    run_pcb_drc(INPUT_PCB, OUTPUT_DIR)

    print("Generating BOM")
    dnf_list = export_sch_bom(INPUT_SCH, os.path.join(OUTPUT_DIR, "Assembly" , OUTPUT_NAME + "_bom.csv"))

    print("Generating IBOM")
    export_pcb_ibom(INPUT_PCB, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".ibom.html"), dnf_list)

    print("Generating gerbers")
    export_pcb_gerbers(INPUT_PCB, os.path.join(OUTPUT_DIR, "Gerber"), get_layer_names(BOARD_LAYERS))

    print("Generating drill reports")
    export_pcb_ncdrill(INPUT_PCB, os.path.join(OUTPUT_DIR, "NC Drill"))

    print("Generating position report")
    export_pcb_pos(INPUT_PCB, os.path.join(OUTPUT_DIR, "Assembly", OUTPUT_NAME + "_pos.csv"))

    print("Generating PCB render")
    export_pcb_image(INPUT_PCB, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".png"))

    print("Generating step file")
    export_pcb_step(INPUT_PCB, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".step"))

    print("Generating zip file")
    zip_files(OUTPUT_DIR, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".zip"))

    input("Done")