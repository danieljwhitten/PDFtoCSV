import os
import re
import fitz
import pytesseract
import csv
import time
import sys
import unidecode
import argparse
from natsort import natsorted
from subprocess import run
from shutil import rmtree

""" A class with the tools to translate a set of PDF files into a single CSV file using embedded text and OCR"""
class PDFtoCSV:
    
    # START STARTUP BLOCK
    def __init__(self):

        self.arguments()

        self.inputFilePath = self.args.filepath

        # Identify the execution path right away
        self.homePath = os.path.dirname(os.path.realpath(__file__))

        # Run basic setup to confirm input can be processed
        try:
            # Confirm that Tesseract OCR is properly installed right away
            self.findTesseract()
            # Identify whether the input is a single file or a directory
            self.inputType = self.fileOrDir(self.inputFilePath)
            # Compile list of all valid PDF files from input
            self.pathList = self.getFileList(self.inputFilePath, self.inputType)

        except IOError as e:
            self.errorFound(e)
            
    # Check to see if Tesseract OCR has been installed as per README
    def findTesseract(self):

        # Identify default locations for Windows or Mac
        operatingSystem = sys.platform
        if operatingSystem == "win32":
            tesseractPath = r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'
        elif operatingSystem == "darwin":
            tesseractPath = r'/usr/local/bin/tesseract'
        else:
            tesseractPath = r'neitherWin32NorMac'
        
        # If neither path exists, check the text file for a custom path, as per README
        if not os.path.isfile(tesseractPath):
            with open(os.path.join(self.homePath,"tesseractPath.txt"), "r") as tesseractPathFile:
                tesseractPath = tesseractPathFile.readline().strip()
        
        # If the file still doesn't exist, raise the error
        if not os.path.isfile(tesseractPath):
            ex = IOError()
            ex.strerror = "I could not find your Tesseract-OCR installation in the default location.\nThe program will attempt to read the file(s) if they are machine-readable, but will return an error if any pages require OCR.\nIf you have not installed Tesseract-OCR, please refer to the Guide to do so.\nIf you have installed it, please locate the executable file (\"tesseract.exe\" in Windows, \"tesseract\" in MacOS) and paste the full path as the first line of the file \"tesseractPath.txt\" in the same folder as this program"
            raise ex
        else:
            # Point PyTesseract to Tesseract executable
            pytesseract.pytesseract.tesseract_cmd = tesseractPath

    # Check to see if the input is a valid file or a valid dir, return either or raise an error
    def fileOrDir(self, path):
        isFile = os.path.isfile(path)
        if not isFile:
            isDir = os.path.isdir(path)
            if isDir:
                return "dir"
            else:
                ex = IOError()
                ex.strerror = "Please enter a valid file or directory"
                raise ex
        else:
            return "file"   

    # Create a list of all valid PDF files in a given path
    def getFileList(self, path, inputType):
        files = list()
        
        # Create a list of all files in a given path
        if inputType == "dir":
            dirs = [path]
            while len(dirs) > 0:
                for(dirpath, dirnames, filenames) in os.walk(dirs.pop()):
                    dirs.extend(dirnames)
                    files.extend(map(lambda n: os.path.join(*n), zip([dirpath] * len(filenames), filenames)))
        else:
            files.append(path)

        pdfFiles = list()

        # Check all files in the file list, and create a new list with only valid PDF files (can be opened by MuPDF)
        for file in files:
            if os.path.splitext(file)[1].lower() == ".pdf" and os.path.basename(file)[0] != ".":
                try:
                    pdf = fitz.open(file)
                    pdf.close()
                    pdfFiles.append(file)
                except:
                    pass

        # Ensure the list is in natural reading order (as would be seen in the file manager)
        pdfFiles = natsorted(pdfFiles)

        # Raise an error if there are no valid PDF files
        if len(pdfFiles) == 0:
            ex = IOError()
            pdfErr = "The {} you have entered {} PDF file{}. Please enter a PDF file or directory containing PDF files"
            if inputType == "file":
                ex.strerror = pdfErr.format("file", "is not a", "")
            else:
                ex.strerror = pdfErr.format("folder", "does not contain any", "s")
            raise ex

        return pdfFiles
    # END STARTUP BLOCK

    # Process the files
    def run(self):
        
        self.outputPath = self.createOutput(self.inputFilePath) # Create the output file
        self.completeWordCount = 0  # To keep track of all the words processed
        self.dialog("start") # Print starting dialog
        for path in self.pathList:
            self.completeWordCount += self.processFile(path) # Process file and update wordcount
        self.dialog("end") # Print ending dialogue
        
    # Crete a CSV file for the output, given the same name as the input path, and in the same location
    def createOutput(self, path):

        # Remove trailing / or \
        if path[-1] == "/" or path[-1] == r"\\":
            path = path[:-1]

        # Create the file in the same location as the input path    
        outputDir = os.path.dirname(path)

        # Give the output file the same name as the input path
        outputFilename = os.path.splitext(os.path.basename(path))[0] + ".csv"

        outputPath = os.path.join(outputDir,outputFilename)

        # Create blank file with headers
        with open(os.path.join(outputDir,outputFilename), "w+", newline='') as outputFile:
            outputCSVWriter = csv.writer(outputFile, dialect='excel')
            outputCSVWriter.writerow(["Source File", "Page", "Word Count", "Text"])
        
        return outputPath
    
    # Process each file in its entirety
    def processFile(self, filePath):
        self.filename = os.path.basename(filePath)
        self.pdf = fitz.open(filePath)   # Open the PDF with MuPDF
        self.skippedPages = False   # Reset
        self.dialog("fileStart")
        
        pages = list()
        self.totalWordCount = 0 # Keep track of all the words processed in the file
        
        self.fivePercent = len(self.pdf)/20 # Determine the 5% intervals for the progress bar
        self.percent = self.fivePercent   # Next percentage marker
        self.percentCount = 0    # How many 5% intervals have passed
        
        self.fileMethod = "text"  # Assume machine readable text, will change to OCR if OCR detected

        for page in self.pdf:   # process one page at a time
            self.pageStart = time.perf_counter()    # Record time page started (OCR pages can take a long time)
            self.pageNum = page.number

            csvLine = list()

            # Get the text and word count from the page
            pageText = self.readPage(page) 
            self.pageWordCount = len(pageText.split())

            csvLine = [filePath, self.pageNum+1, self.pageWordCount, pageText] # Build the output
            pages.append(csvLine) # Add it to the list of page outputs for the file
            
            self.totalWordCount += self.pageWordCount # Update total file word count
            self.dialog("page") # Update progress dialog
        
        # Add each page from processed file to the output CSV as 1 line
        with open(self.outputPath, "a", newline='') as outputFile:
            outputCSVWriter = csv.writer(outputFile, dialect='excel')
            outputCSVWriter.writerows(pages)

        self.dialog("fileEnd")  # Show user statistics for completed file
        self.pdf.close()    # Close the PDF

        return self.totalWordCount

    # Get the text from a single page
    def readPage(self, page):
        # try to extract text
        text = page.getText()

        if len(text) < 1 or self.args.thorough:   # OCR the page if there is no text or if forced
            if self.args.accelerated:  # Skip if Accelerated option active
                self.skippedPages = True
            else:
                text = self.ocrPage(page)
                if self.fileMethod == "text":    # If this is the first OCR page, tell the user what's going on
                    self.dialog("ocr")
                self.fileMethod = "ocr" # Once one page is OCR, change the file method to OCR
        text = self.cleanText(text) # Pass text through text cleaning processes
        return text

    # Read a page using OCR
    def ocrPage(self, page):

        # Create a temporary folder for the images used in OCR
        imgPath = os.path.join(self.homePath,"tempImages")
        try:
            os.mkdir(imgPath)
        except:
            pass

        zoomMatrix = fitz.Matrix(3.2,3.2)   # Set the optimal settings for OCR-readable images
        pix = page.getPixmap(matrix=zoomMatrix, colorspace=fitz.csGRAY) # Generate pixmap from PDF page
        img = os.path.join(imgPath,"page-%i.png" % page.number) # find image in pixmap
        pix.writePNG(img)   # Grab image and save it
        
        # Use tesseract to get text via OCR
        try:
            text = pytesseract.image_to_string(img, lang="eng", config="--psm 1")
        except:
            print("\rSorry! There appears to be an issue with your Tesseract OCR installation. Please refer to the instruction manual for more details.")
            sys.exit(1)

        rmtree(imgPath) # Delete the temp folder for the pics
                
        return text

    # Strip unneceesary whitespace
    def stripWhite(self, text):
        newText = ""
        for c in text.group(0):
            if not re.match(r"\s", c):
                newText += c
        newText += " "
        return newText

    # Process text to format it to be human-readable on one CSV line and fix common OCR errors
    def cleanText(self, rawText):

        # make all space (inluding line breaks) into standard spaces
        cleanText = re.sub(r"\s", " ", rawText)

        # Strip accents and convert unicode symbols to ascii and transliterate non-latin characters
        cleanText = unidecode.unidecode(cleanText)

        # make all apostrophes the same
        cleanText = re.sub(r"[‘’‚‛′`']", r"'", cleanText)

        #connect hyphenated line breaks
        cleanText = re.sub(r"\S-\s+", lambda x: x.group(0)[0], cleanText)

        # Remove non-grammatical punctuation
        cleanText = re.sub(r'''[^a-zA-Z0-9' .;,"$/@!?&\-()_]''', r"", cleanText)

        # clean words split up by spaces
        cleanText = re.sub(r"(\b\w\s)+", self.stripWhite, cleanText)

        # fix spaces
        cleanText = re.sub(r"\s+", " ", cleanText)
        cleanText = re.sub(r"\s[.,;]", lambda x: x.group(0)[1], cleanText)

        # common splits
        cleanText = re.sub(r"(?i)\bt\s?h\s?e\b", lambda x: x.group(0)[0]+"he", cleanText)
        cleanText = re.sub(r"\ba\s?n\s?d\b", lambda x: x.group(0)[0]+"nd", cleanText)

        # remove leading and trailing spaces
        cleanText = cleanText.strip()

        return cleanText

    # Various dialogues to keep the user informed of progress
    def dialog(self, stage):

        # Only show beginning and ending dialog if it is a dir (otherwise the file beginning and ending dialoge is enough)
        if self.inputType == "dir":

            # Determine plural ending
            if len(self.pathList) == 1:
                plural = ""
            else:
                plural = "s"
            
            if stage == "start":    # Starting dialogue
                print("Processing all PDF files in folder {} ({} File{})".format(self.inputFilePath, len(self.pathList), plural))
                self.dirTimeStart = time.perf_counter() # Record starting time
            elif stage == "end":    # Ending dialogue
                dirTimeEnd = time.perf_counter()   # Record ending time
                dirTime = round(dirTimeEnd-self.dirTimeStart, 3)  # Calculate processing time
                print()
                print("The file {} contains all of the text extracted from all PDF files in {}".format(self.outputPath, self.inputFilePath))
                if not self.args.quiet:
                    print("{} file{} ({} words) were processed in {} seconds. That is an average of {} seconds/file".format(len(self.pathList), plural, self.completeWordCount, dirTime, round(dirTime/len(self.pathList),3)))
        
        if stage[:4] == "file":    # The dialog relates to the processing of the file
            if len(self.pdf) == 1:  # Determine plural ending
                plural = ""
            else:
                plural = "s"
            if stage == "fileStart":    # File start dialogue
                if not self.args.quiet:
                    print ()
                    print("Processing {} ({} page{})".format(self.filename,len(self.pdf),plural))
                    if not self.args.verbose:
                        print("Progress: 0%|", end="", flush=True)  # Set up progress bar
                self.fileStartTime = time.perf_counter()    # Record file start time
            elif stage == "fileEnd":    # File completed dialogue
                fileEndTime = time.perf_counter()   # Record file end time
                fileTime = round(fileEndTime - self.fileStartTime, 3)
                if not self.args.quiet or self.inputType != "dir":
                    print("Completed {} in {} seconds ({} page{}, {} words, {} seconds/page)".format(self.filename, fileTime, len(self.pdf), plural, self.totalWordCount, round(fileTime/len(self.pdf),3)))
                if self.skippedPages and not self.args.quiet:
                    print("Some pages were skipped because you chose Accelerated Mode. See Guide for details.")
       
        if not self.args.quiet:
            if stage == "ocr":  # Explain to the user that we are now dealing with OCR and why
                if self.args.thorough:
                    reason = "Thorough Mode has been chosen, see Guide for details."
                else:
                    reason = "it contains non-machine readable text."
                print("\rThis file is being processed with OCR because {} \n(This may take a few seconds per page)".format(reason))

            if stage == "page":
                if self.pageNum >= self.percent:    # If we passed the next percentage marker, set a new one
                    self.percent = self.percent + self.fivePercent
                if self.fileMethod == "ocr" or self.args.verbose:    # Because OCR takes longer, give an update of time and words after each page
                    if self.args.verbose:
                        lead = ""
                        rtn = "\n"
                    else:
                        lead = "\r"
                        rtn = ""
                    print("{}Read {} words from page {}/{} in {} seconds        ".format(lead,self.pageWordCount, self.pageNum+1, len(self.pdf), round(time.perf_counter()-self.pageStart,3)), end=rtn, flush=True)
                else:   # For text, just update the progress bar
                    if self.pageNum >= self.percent:    # If we passed the next percentage marker, print a marker set a new one
                        print("=", end="", flush=True)
                        self.percent = self.percent + self.fivePercent
                if self.pageNum+1 == len(self.pdf) and not self.args.verbose: # If we are at the end of the file, ensure there is a full progress bar
                    print("\rProgress: 0%|====================|100%                ")

    # Error dialog
    def errorFound(self, e):
        print("Sorry! There's been a problem. {} and try again.".format(e.strerror))

    # Argument processing
    def arguments(self):

        # Initialize parser
        parser = argparse.ArgumentParser()
        
        # Require path argument
        parser.add_argument("filepath", help="The path to the file or folder you would like to process. Must be verbatim and enclosed in quotes. See guide for details.")

        # Arguments that augment the speed of the program
        speedGroup = parser.add_mutually_exclusive_group()
        # Accelerated (Ignore OCR pages)
        speedGroup.add_argument("-a", "--accelerated", help="Ignore any pages that require time-consuming OCR to process. The program will run very quickly, but might miss some text, depending on your source file formats.", action="store_true")
        # Thorough (OCR all pages)
        speedGroup.add_argument("-t", "--thorough", help="Force Optical Character Recognition (OCR) for all pages. This will be much slower than the default option, but is the most thorough.", action="store_true")

        # Arguments related to progress output
        progressGroup = parser.add_mutually_exclusive_group()
        # Quiet Mode (no progress updates)
        progressGroup.add_argument("-q", "--quiet", help="Supress progress updates about individual files. There can be a long period of time with no progress updates as the progam runs.", action="store_true")
        # Verbose Mode (progress update per page)
        progressGroup.add_argument("-v", "--verbose", help="Show detailed progress updates for each page. This can result in a lot of progress updates for larger files.", action="store_true")

        # Parse all args
        self.args = parser.parse_args()



test = PDFtoCSV()
test.run()