import sys
from importlib import util
from importlib import import_module
from subprocess import run
dependencies = [("PyMuPDF","fitz"),"pytesseract","unidecode","natsort"]
successCount = 0
for package in dependencies:
    if len(package) == 2:
        lib = package[1]
        dep = package[0]
    else:
        lib = package
        dep = package
    if util.find_spec(lib) is None:
        run([sys.executable, "-m", "pip", "install", dep])
    if util.find_spec(lib) is not None:
    	successCount += 1
    run([sys.executable, "-m", "textblob.download_corpora"])
if successCount == len(dependencies):
	print("All packages are installed")
else:
	print("Some packages were not sucessfully installed. Please exit and try again later.")
