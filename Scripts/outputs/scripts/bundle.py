import os
import subprocess


def zip_files(input_path: str, output_file: str, files: list[str]):
    subprocess.check_call([
            "zip",
            "-rq",
            os.path.abspath(output_file),
        ] + files,
        cwd=input_path
    )

def tar_files(input_path: str, output_file: str, files: list[str]):
    subprocess.check_call([
            "tar",
            "-C", input_path,
            "-acf", output_file,
        ] + files
    )

BUNDLERS = {
    ".zip": zip_files,
    ".tar.gz": tar_files,
}

SUPPORTED_FORMATS = [ extn[1:] for extn in BUNDLERS.keys() ]


def bundle(input_path: str, output_file: str, files: list[str] = None):
    _, extn = os.path.splitext(output_file)

    if files is None:
        files = os.listdir(input_path)

    for extn in BUNDLERS.keys():
        if output_file.endswith(extn):
            BUNDLERS[extn](input_path, output_file, files)
            return
    raise Exception(f"Unknown compression format: \"{extn}\"")
    
