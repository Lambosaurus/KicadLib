import shutil

BACKEND = None

if not BACKEND:
    if shutil.which("pdfunite"):
        BACKEND = "pdfunite"

if not BACKEND:
    try: 
        from pypdf import PdfMerger
        BACKEND = "pypdf"
    except ImportError:
        pass


def get_backend() -> str | None:
    return BACKEND


def merge_pdf(pdf_files: list[str], output_file: str):

    if BACKEND == "pdfunite":
        return merge_pdf_pdfunite(pdf_files, output_file)
    
    elif BACKEND == "pypdf":
        return merge_pdf_pypdf(pdf_files, output_file)
    
    else:
        raise Exception("No PDF merging backend available. Please install 'pypdf' or ensure 'pdfunite' is available in your PATH.")


def merge_pdf_pypdf(pdf_files: list[str], output_file: str):
    merger = PdfMerger()
    for pdf in pdf_files:
        merger.append(pdf)
    merger.write(output_file)
    merger.close()


def merge_pdf_pdfunite(pdf_files: list[str], output_file: str):
    import subprocess
    command = ["pdfunite"] + pdf_files + [output_file]
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        raise Exception(f"pdfunite failed: {result.stderr.decode()}")
