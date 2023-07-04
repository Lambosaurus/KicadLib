# Output generation script
This automates kicad output generation

# Installation
1. Install python
2. Install the HTMLBom plugin for Kicad
3. Place `output.bat` and `scripts` in your projects root directory
4. Edit `output.bat` to contain your correct project settings. 
   * The command format is `python "scripts/output.py" "<project-name>" <pcb-layers>`
   * The project name should be the same as the `.kicad_pro`, `.kicad_sch`, and `.kicad_pcb` files (without the file extention) 
5. Confirm the Kicad install directory is correct. This is referenced at the top of `output.py`

# Using

Just run the `output.bat` (or equivilent shell command)
Output generation will be automatic, with the exception of the image

