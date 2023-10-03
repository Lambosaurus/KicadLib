import subprocess
import os, sys, shutil
import bom

# You may need to edit this
KICAD_ROOT = "C:/Program Files/KiCad/7.0/bin"

KICAD_CLI = os.path.join(KICAD_ROOT, "kicad-cli.exe")
KICAD_PYTHON = os.path.join(KICAD_ROOT, "python.exe")
IBOM_SCRIPT = os.path.expandvars("%USERPROFILE%/Documents/KiCad/7.0/3rdparty/plugins/org_openscopeproject_InteractiveHtmlBom/generate_interactive_bom.py")

SCRIPT_VERSION = "v1.2"

def get_layer_names(layers: int) -> list[str]:
    names = ["F.SilkS", "F.Paste", "F.Mask", "F.Cu", "B.Cu", "B.Mask", "B.Paste", "B.SilkS", "Edge.Cuts"]
    if layers > 2:
        for i in range(1, layers - 2):
            names.append(f"In{i}.Cu")
    return names

def run_command(args: list[str]):
    try:
        return subprocess.check_output(args).decode('ascii').strip()
    except subprocess.CalledProcessError as e:
        print(e.stdout.decode('ascii'))
        raise e

def clean_directory(dir: str):
    # Remove output directory (and its contents) and recreate it
    if (os.path.exists(dir)):
        shutil.rmtree(dir)
    os.makedirs(dir)

def export_sch_pdf(input_sch: str, output_pdf: str):
    # Create PDF from schematic
    run_command([
        KICAD_CLI, "sch", "export", "pdf",
        input_sch,
        "--output", output_pdf,
        ])

def export_sch_bom(input_sch: str, output_csv: str) -> list[str]:
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

def export_pcb_pos(input_pcb: str, output_file: str):
    run_command([
        KICAD_CLI, "pcb", "export", "pos",
        input_pcb,
        "--output", output_file,
        "--units", "mm",
        "--side", "both",
    ])


def export_pcb_step(input_pcb: str, output_file: str):
    run_command([
        KICAD_CLI, "pcb", "export", "step",
        input_pcb,
        "--output", output_file,
    ])

def export_pcb_ibom(input_pcb: str, output_file: str, dnf_list: list[str] = []):
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
    ])

def export_pcb_image(input_pcb: str, output_file: str):
    print("Currently image export is not supported")
    shutil.copyfile("scripts/template.png", output_file)
    run_command([
        "mspaint", output_file
    ])

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

    print("Generating schematic PDF")
    export_sch_pdf(INPUT_SCH, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".pdf"))

    print("Generating BOM")
    dnf_list = export_sch_bom(INPUT_SCH, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".csv"))

    print("Generating IBOM")
    export_pcb_ibom(INPUT_PCB, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".ibom.html"), dnf_list)

    print("Generating gerbers")
    export_pcb_gerbers(INPUT_PCB, os.path.join(OUTPUT_DIR, "Gerber"), get_layer_names(BOARD_LAYERS))

    print("Generating drill reports")
    export_pcb_ncdrill(INPUT_PCB, os.path.join(OUTPUT_DIR, "NC Drill"))

    print("Generating position report")
    export_pcb_pos(INPUT_PCB, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".pos"))

    print("Generating PCB Image")
    export_pcb_image(INPUT_PCB, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".png"))

    print("Generating step file")
    export_pcb_step(INPUT_PCB, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".step"))

    print("Generating zip file")
    zip_files(OUTPUT_DIR, os.path.join(OUTPUT_DIR, OUTPUT_NAME + ".zip"))

    input("Done")