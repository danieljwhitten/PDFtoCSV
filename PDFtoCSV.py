import os
import re
import fitz
import pytesseract
import csv
import time
import sys
import unidecode
import argparse
import math
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
        
        self.reportText = ""
        if not self.args.split:
            self.createOutput(self.inputFilePath) # Create the output file
        self.completeWordCount = 0  # To keep track of all the words processed
        self.completePageCount = 0 # To keep track of all pages processed
        self.dialog("start") # Print starting dialog
        for path in self.pathList:
            self.completeWordCount += self.processFile(path) # Process file and update wordcount
        if self.args.report and not self.args.split:
            self.report()
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

        self.outputPath = os.path.join(outputDir,outputFilename)
        self.reportPath = self.outputPath[:-4] + "-FR" + self.outputPath[-4:]

        # Create blank file with headers
        with open(self.outputPath, "w+", newline='') as outputFile:
            outputCSVWriter = csv.writer(outputFile, dialect='excel')
            headers = self.args.fields
            while headers.count("Custom Text") > 0:
                i = headers.index("Custom Text")
                headers.remove("Custom Text")
                headers.insert(i,self.args.customTitle)
            outputCSVWriter.writerow(headers)
        
        if self.args.report or self.args.reportFile or self.args.reportPage:
            with open(self.reportPath, "w+", newline='') as outputFile:
                outputCSVWriter = csv.writer(outputFile, dialect='excel')     
    
    # Process each file in its entirety
    def processFile(self, filePath):
        self.filename = os.path.basename(filePath)

        if self.args.split:
            self.createOutput(filePath)

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
            
            if len(self.args.pages) == 0 or self.pageNum+1 in self.args.pages:  # Process unless not a specified page
                self.completePageCount += 1

                csvLine = list()

                # Get the text and word count from the page
                pageText = self.readPage(page) 
                self.pageWordCount = len(pageText.split())
                self.totalWordCount += self.pageWordCount # Update total file word count
                self.pageEnd = time.perf_counter()  # Record time page ends
                self.pageTime = self.pageEnd-self.pageStart

                if self.args.report or self.args.reportPage or self.args.reportFile:
                    self.reportText += pageText
                    if self.args.reportPage:
                        self.report()
            
                customData = re.sub("#", f"{self.pageNum+1}", self.args.customContent)
                customData = re.sub("\$", f"{self.completePageCount}", customData)
                customData = re.sub("@", self.filename, customData)

                data = {"Source File Path" : filePath, "Source File Name" : self.filename, "Page Number (File)" : self.pageNum+1, 
                                    "Page Number (Overall)" : self.completePageCount, "Page Word Count" : self.pageWordCount, 
                                    "Page Processing Duration" : f"{round(self.pageTime,3)} sec.", "Page Text" : pageText, "Process Timestamp" : time.asctime(),
                                    self.args.customTitle : customData}

                csvLine = list() # Build the output
                for f in self.args.fields:
                    csvLine.append(data[f])
                pages.append(csvLine) # Add it to the list of page outputs for the file
                self.dialog("page") # Update progress dialog
                
                
            else:
                self.skippedPages = True
                self.pageWordCount = 0
                self.dialog("pageskip")

        # Add each page from processed file to the output CSV as 1 line
        with open(self.outputPath, "a", newline='') as outputFile:
            outputCSVWriter = csv.writer(outputFile, dialect='excel')
            outputCSVWriter.writerows(pages)
        if self.args.reportFile or (self.args.split and self.args.report):
            self.report()

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

    def report(self):
        stats = {}
        text = re.sub(r"[^a-z '\-]", "", self.reportText.lower())
        text = re.sub(r"\B'|'\B", "", text)
        text = re.sub(r"\B\-|\-\B", "", text)
        for w in text.split():
            if w in stats:
                stats[w] += 1
            else:
                stats[w] = 1

        count = 0
        for c in stats.items():
            count += c[1]

        sortedStats = [(word,count) for (word, count) in sorted(stats.items(),reverse= True, key=lambda x: x[1])]


        trimmedStats = {}

        limit = re.sub(r"[^0-9%]", "", self.args.reportLimit)
        if len(limit) < 1 or ("%" in limit and len(limit) < 2):
            limit = "100%"

        if limit[-1] == "%":
            percentile = int(re.sub(r"[^0-9]", "", limit))
            if percentile > 100:
                percentile = 100
            cieling  = math.ceil((percentile/100) * count)

            counter = 0
            for w in sortedStats:
                counter += w[1]
                if counter <= cieling or counter == w[1]:
                    trimmedStats[w[0]]=w[1]            

        else:
            cieling = int(re.sub(r"[^0-9]", "", limit))
            for w in sortedStats:
                if w[1] >= cieling:
                    trimmedStats[w[0]]=w[1]

        finalStats = list()
        if not self.args.reportSort:
            finalStats = [(word, count) for (word,count) in sorted(trimmedStats.items())]
        else:
            finalStats = trimmedStats.items()


        with open(self.reportPath, "a", newline='') as outputFile:
            outputCSVWriter = csv.writer(outputFile, dialect='excel')
            if self.args.report and not self.args.split:
                src = self.inputFilePath
            else:
                src = self.filename
            outputCSVWriter.writerow(["Frequency Report of all words processed from {}".format(src)])   
            if self.args.reportPage:
                outputCSVWriter.writerow(["{} page {}/{}".format(self.filename, self.pageNum+1, len(self.pdf))])
            outputCSVWriter.writerow(["Word","Instances"])
            for w in finalStats:
                outputCSVWriter.writerow(w)
        self.reportText = ""

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
                if self.args.report or self.args.reportFile or self.args.reportPage:
                    out = "a report on the frequency of each word"
                else:
                    out = "all of the text extracted"
                print("The file {} contains {} from all PDF files in {}.".format(self.outputPath, out, self.inputFilePath))
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
                if len(self.args.pages) > 0:
                    pagesProcessed = len(self.args.pages)
                else:
                    pagesProcessed = len(self.pdf)
                if not self.args.quiet or self.inputType != "dir":
                    print("Completed {} in {} seconds ({} page{}, {} words, {} seconds/page)".format(self.filename, fileTime, pagesProcessed, plural, self.totalWordCount, round(fileTime/pagesProcessed,3)))
                if self.skippedPages and not self.args.quiet:
                    if self.args.accelerated:
                        reason = "Accellerated Mode"
                    if len(self.args.pages) > 0:
                        reason = "to only process certain pages"
                    print("Some pages were skipped because you chose {}. See Guide for details.".format(reason))
       
        if not self.args.quiet:
            if stage == "ocr":  # Explain to the user that we are now dealing with OCR and why
                if self.args.thorough:
                    reason = "Thorough Mode has been chosen, see Guide for details."
                else:
                    reason = "it contains non-machine readable text."
                print("\rThis file is being processed with OCR because {} \n(This may take a few seconds per page)".format(reason))

            if stage[:4] == "page":
                if self.pageNum >= self.percent:    # If we passed the next percentage marker, set a new one
                    self.percent = self.percent + self.fivePercent
                if self.fileMethod == "ocr" or self.args.verbose:    # Because OCR takes longer, give an update of time and words after each page
                    if self.args.verbose:
                        lead = ""
                        rtn = "\n"
                    else:
                        lead = "\r"
                        rtn = ""
                    if len(stage) == 4:
                        print("{}Read {} words from page {}/{} in {} seconds        ".format(lead,self.pageWordCount, self.pageNum+1, len(self.pdf), round(time.perf_counter()-self.pageStart,3)), end=rtn, flush=True)
                    else:
                        print("{}Page {}/{} skipped as it was not among those specified.    ".format(lead, self.pageNum+1, len(self.pdf)), end=rtn, flush=True)
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

        fieldGroup = parser.add_argument_group("Field Options", "This mode allows for the customization of the fields used for the CSV columns. See Guide for usage and syntax.")
        
        class FieldAction(argparse.Action):
            def __call__(self, parser, namespace, values, option_string=None):
                fields = dict(p="Source File Path", n="Source File Name", f="Page Number (File)", 
                                o="Page Number (Overall)", w="Page Word Count",d="Page Processing Duration", 
                                t="Page Text", s="Process Timestamp", c="Custom Text")
                outputFields = list()
                fieldString = re.sub(r"[^pnfowdtsc]","",values.lower())
                if len(fieldString) < 1:
                    print("No valid fields selected. Please refer to the Guide for help on using this function. Default fields will be used.")
                    fieldString = "pfwt"
                for c in fieldString:
                    outputFields.append(fields[c])           
                setattr(namespace, self.dest, outputFields)     

        fieldGroup.add_argument("-f", "--fields", help="The string of letters representing the fields required in the order desired. See Guide for details", default=['Source File Path', 'Page Number (File)', 'Page Word Count', 'Page Text'], action=FieldAction)
        customGroup = parser.add_argument_group("Custom Feild", "These options allow for the creation of a custom field in the CSV output. The indicator 'c' must be included in the field string for this field to be included. See Guide for details.")
        customGroup.add_argument("-ct", "--customTitle", help="Title of custom field. Default title is 'Custom' if not specified.", default="Custom")
        customGroup.add_argument("-cc", "--customContent", help="Content of custom field to be repeated for each page. Include @ for file name, # for file page number and $ for overall page number. Default is a blank cell if not specified.", default="")
        
        class PageAction(argparse.Action):
            def __call__(self, parser, namespace, values, option_string=None):
                pages = list()
                for p in values:
                    p = re.sub(r"[^0-9\-]","", p)
                    if "-" in p:
                        rng = range(int(p.split("-")[0]),int(p.split("-")[1])+1)
                        for i in rng:
                            pages.append(i)
                    elif len(p) > 0:
                        pages.append(int(p))
                setattr(namespace, self.dest, pages)

        parser.add_argument("-p", "--pages", help="Only retrieve text from specified pages. List individual page numbers or page ranges in the format 1-10.", nargs="+", action=PageAction, default=[])

        parser.add_argument("-s", "--split", help="Create a separate output CSV for every PDF file instead of the default of one comprehensive output CSV.", action = "store_true")
        
        reportGroup = parser.add_argument_group("Report Mode", "Create a separate CSV with a report of frequency of each word present in the text.")
        reportGroupDetails = reportGroup.add_mutually_exclusive_group()
        reportGroupDetails.add_argument("-r", "--report", help="Create one report with cumulative counts for all words in all files. This will create a report per file if 'Split Mode' is also used.", action="store_true")
        reportGroupDetails.add_argument("-rp", "--reportPage", help="Create a separate report for each page.", action="store_true")
        reportGroupDetails.add_argument("-rf", "--reportFile", help="Create a separate report for each file.", action="store_true")
        reportGroup.add_argument("-rs", "--reportSort", help="Sort the words by frequency in the report instead of alphabetically.", action="store_true")
        reportGroup.add_argument("-rl", "--reportLimit", help="Only include words above a certain frequency. Numbers alone represent minimum frequency, numbers with a percentage represent the upper given percentile.", default="100%")

        # Parse all args
        self.args = parser.parse_args()


test = PDFtoCSV()
test.run()