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
import tempfile
from natsort import natsorted
from textblob import TextBlob
from textblob import Word
from textblob.en import Spelling
from build_dictionary import BuildDict

""" A class with the tools to translate a set of PDF files into a single CSV file using embedded text and OCR"""

class Arguments:

    def __init__(self, user_args):
        # Initialize parser
        parser = argparse.ArgumentParser()
        
        # Require path argument
        parser.add_argument("filepath", 
            help=("The path to the file or folder you would like to process. "
            "Must be verbatim and enclosed in quotes. See guide for details.")
        )
        
        # Arguments that augment the speed of the program
        speedGroup = parser.add_mutually_exclusive_group()
        # Accelerated (Ignore OCR pages)
        speedGroup.add_argument("-a", "--accelerated", 
            help=("Ignore any pages that require time-consuming OCR to process. "
            "The program will run very quickly, but might miss some text, "
            "depending on your source file formats."), 
            action="store_true"
        )
        # Thorough (OCR all pages)
        speedGroup.add_argument("-t", "--thorough", 
            help=("Force Optical Character Recognition (OCR) for all pages. "
            "This will be much slower than the default option, but is the most thorough."), 
            action="store_true"
        )

        # Arguments related to progress output
        progressGroup = parser.add_mutually_exclusive_group()
        # Quiet Mode (no progress updates)
        progressGroup.add_argument("-q", "--quiet", 
            help=("Supress progress updates about individual files. There can be "
            "a long period of time with no progress updates as the progam runs."), 
            action="store_true"
        )
        # Verbose Mode (progress update per page)
        progressGroup.add_argument("-v", "--verbose", 
            help=("Show detailed progress updates for each page. This can result "
            "in a lot of progress updates for larger files."), 
            action="store_true"
        )

        fieldGroup = parser.add_argument_group("Field Options", 
            ("This mode allows for the customization of the fields used "
            "for the CSV columns. See Guide for usage and syntax.")
        )
        class FieldAction(argparse.Action):
            def __call__(self, parser, namespace, values, option_string=None):
                fields = dict(
                    p="Source File Path", 
                    n="Source File Name", 
                    f="Page Number (File)", 
                    o="Page Number (Overall)", 
                    w="Word Count",
                    d="Page Processing Duration (s)", 
                    t="Text", 
                    s="Process Timestamp", 
                    r="Raw Text"
                )
                outputFields = list()
                fieldString = re.sub(r"[^pnfowdtscr]","",values.lower())
                if len(fieldString) < 1:
                    print(
                        ("No valid fields selected. Please refer to the Guide "
                        "for help on using this function. Default fields will be used.")
                    )
                    fieldString = "pfwtr"
                for c in fieldString:
                    outputFields.append(fields[c])           
                setattr(namespace, self.dest, outputFields)     

        fieldGroup.add_argument("-f", "--fields", 
            help=("The string of letters representing the fields required "
            "in the order desired. See Guide for details"), 
            default=[
                'Source File Path', 
                'Page Number (File)', 
                'Word Count', 
                'Text', 
                'Raw Text'
            ], 
            action=FieldAction, 
            metavar="Desired Field Order"
        )
        
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

        parser.add_argument("-p", "--pages", 
            help=("Only retrieve text from specified pages. "
            "List individual page numbers or page ranges in the format 1-10."), 
            nargs="+", 
            action=PageAction, 
            default=[], 
            metavar="Desired Page Numbers"
        )

        parser.add_argument("-s", "--split", 
            help=("Create a separate output CSV for every PDF file instead of "
            "the default of one comprehensive output CSV."), 
            action = "store_true"
        )
        
        reportGroup = parser.add_argument_group("Report Mode", 
            "Create a separate CSV with a report of frequency of each word present in the text."
        )
        reportGroupDetails = reportGroup.add_mutually_exclusive_group()
        reportGroupDetails.add_argument("-r", "--report", 
            help=("Create one report with cumulative counts for all words in all files. "
            "This will create a report per file if 'Split Mode' is also used."), 
            action="store_true"
        )
        reportGroupDetails.add_argument("-rp", "--reportPage", 
            help="Create a separate report for each page.", 
            action="store_true",
            dest="report_page"
        )
        reportGroupDetails.add_argument("-rf", "--reportFile", 
            help="Create a separate report for each file.", 
            action="store_true",
            dest="report_file"
        )
        reportGroup.add_argument("-rs", "--reportSort", 
            help="Sort the words by frequency in the report instead of alphabetically.", 
            action="store_true",
            dest="report_sort"
        )
        reportGroup.add_argument("-rl", "--reportLimit", 
            help=("Only include words above a certain frequency. "
            "Numbers alone represent minimum frequency, numbers with a percentage "
            "represent the upper given percentile."), 
            default="100%", 
            metavar="Desired Report Limit",
            dest="report_limit"
        )
        reportGroup.add_argument("-rpos", "--reportPOS", 
            help=("Count homonyms separately if they represent different parts of speech. "
            "Eg., without this option 'Can I have a can of juice?' would count "
            "two instances of 'can'. With this option, it would count once instance "
            "of 'can (noun)' and one of 'can (verb)'."), 
            action="store_true",
            dest="report_pos"
        )
        reportWordLists = reportGroup.add_mutually_exclusive_group()
        reportWordLists.add_argument("-ro", "--reportOnly", 
            help=("Report only specified words. Either list words here separated by a space, "
            "or modify the file 'options/ReportOnly.txt' as per instructions "
            "in that file and the Guide."), 
            nargs="*", 
            metavar="Only Report These Words",
            dest="report_only"
        )
        reportWordLists.add_argument("-ri", "--reportIgnore", 
            help=("Report all words except specified words to ignore. By default "
            "ignores the most common English words. For custom word lists, "
            "either list words here separated by a space, or modify the file "
            "'options/ReportIgnore.txt' as per instructions in that file and the Guide."), 
            nargs="*", 
            metavar="Ignore These Words",
            dest="report_ignore"
        )

        processGroup = parser.add_argument_group("Processing Options", 
            ("These options allow for common Natural Language Processing text "
            "processing operations to be performed on the source text before "
            "storing it in the CSV file.")
        )
        processGroup.add_argument("-ac", "--autocorrect", 
            help=("Apply an autocorrect alogorithm to the source text, correcting "
            "some of the errors from OCR or typos, approximately 70 percent accuracy. "
            "Use 'Process Raw' option to include original text in output as well."), 
            action="store_true"
        )
        processGroup.add_argument("-st", "--sourceText", 
            help=("Include the raw, unprocessed source text alongside "
            "the processed text in the output CSV."), 
            action="store_true",
            dest="source_text"
        )
        processGroup.add_argument("-c", "--corrections", 
            help=("Create a separate file that contains all of the words that were "
            "not found in the dictionary when using the 'Process Autocorrect' option, "
            "and whether it was corrected."), 
            action="store_true"
        )

        processGroup.add_argument("-d", "--dictionary", 
            help=("Create a custom dictionary specialized for a given subject matter, "
            "to be used by the 'Autocorrect' option. List topics here "
            "separated by a space, with multiple words surrounded by quotation marks. "
            "Topics should correspond to the titles of their respective articles "
            "on https://en.wikipedia.org. By default, uncommon words are removed "
            "for the sake of efficiency if the new dictionary is more than twice "
            "as large as the default dictionary. Disable this process by including "
            "the 'Dictioanry Large' option. This option needs to be run "
            "only once and all future 'Autocorrect' uses will use the new "
            "custom dictionary. Running this option again with new topics will "
            "replace the custom dictionary. Use the 'Dictionary Revert' "
            "option to delete the custom dictionary and revert to the default one."), 
            nargs="+", 
            metavar="Desired Dictionary Topic(s)"
        )
        processGroup.add_argument("-dl", "--dictionaryLarge", 
            help=("When used alongside the 'Dictionary' option, this "
            "includes all words added to the custom dictionary, regardless of frequency. "
            "Can result in long processing times when using the 'Process Autocorrect' option. "
            "If this option has been used, and you want to shrink the dictionary later, "
            "use 'build_dictionary.py -s', see 'build_dictionary.py -h' for "
            "details and further options."), 
            action="store_true",
            dest="dictionary_large"
        )
        processGroup.add_argument("-dr", "--dictionaryRevert", 
            help=("Delete the custom dictionary made using 'Process Dictionary' "
            "and revert to the default dictionary for all future 'Process Autocorrect' processes. "
            "To override a previous custom dictionary with a new one, use the "
            "'Process Dictionary' option again with new arguments."), 
            action="store_true",
            dest="dictionary_revert"
        )
        processGroup.add_argument("-daw", "--dictionaryAddWord", 
            help=("Add specific word(s) to the dictionary used by 'Process Autocorrect'. "
            "Separate individual words with a single space. " 
            "Alternatively, enter the path to a text file contianing a list of words. "
            "One word per line, otherwise only the first word from each line will be added. "
            "Frequency count separated by a space can be added on the same line "
            "for improved performance."), 
            nargs="+", 
            metavar="Words to Add",
            dest="dictionary_add_word"
        )
        processGroup.add_argument("-drw", "--dictionaryRemoveWord", 
            help=("Remove specific word(s) from the dictionary used by 'Process Autocorrect'. "
            "Separate individual words with a single space. "
            "Alternatively, enter the path to a text file contianing a list of words. "
            "One word per line, otherwise the first word from each line will be removed."), 
            nargs="+", 
            metavar="Words to Add",
            dest="dictionary_remove_word"
        )
        
        processGroup.add_argument("-l", "--lemmatize", 
            help=("Lemmatize all words for both text output and Frequency Report "
            "if 'Report' option is used. This converts words into their base form "
            "for easier analysis. Eg., 'went' and 'going' => 'go', 'leaf' and "
            "'leaves' => 'leaf', etc."), 
            action="store_true"
        )
        
        processTokenizers = processGroup.add_mutually_exclusive_group()
        processTokenizers.add_argument("-ts", "--tokenizeSentences", 
            help="Split the text into sentences and output a single sentence per CSV line.", 
            action = "store_true",
            dest="tokenize_sentences"
        )
        processTokenizers.add_argument("-tw", "--tokenizeWords", 
            help ="Split the text into individual words and output a single word per CSV line.", 
            action="store_true",
            dest="tokenize_words"
        )
        
        processWordLists = processGroup.add_mutually_exclusive_group()
        processWordLists.add_argument("-po", "--processOnly", 
            help=("Process only specified words. Either list words here separated "
            "by a space, or modify the file 'options/ProcessOnly.txt' as per "
            "instructions in that file and the Guide."), 
            nargs="*", 
            metavar="Only Process These Words",
            dest="process_only"
        )
        processWordLists.add_argument("-pi", "--processIgnore", 
            help=("Process all words except specified words to ignore. "
            "By default ignores the most common English words. For custom word lists, "
            "either list words here separated by a space, or modify the file "
            "'options/ProcessIgnore.txt' as per instructions in that file and the Guide."), 
            nargs="*", 
            metavar="Ignore These Words",
            dest="process_ignore"
        )

        processGroup.add_argument("-pp", "--processPunctuation", 
            help=("Remove all punctuation, excluding internal apostrphes and hypens. "
            "Retains all words and numbers, separated by a single space."), 
            action="store_true",
            dest="process_punctuation"
        )
        processGroup.add_argument("-pn", "--processNumbers", 
            help=("Remove all words containing numbers. Used in conjunction with "
            "the 'Process Punctuation' option, only words will be returned, "
            "separated with spaces. Used alone, punctuation will be preserved."), 
            action="store_true",
            dest="process_numbers"
        )
        processGroup.add_argument("-pw", "--processWords", 
            help=("Remove all words not found in the dictionary. "
            "If used in conjuction with the 'Process Autocorrect' option, "
            "an attempt will first be made to correct an unknown word to a known word, "
            "and only words that cannot be corrected would be removed. "
            "See the 'Process Dictionary' option for details on creating "
            "a custom dictionary to check words against. If a custom dictionary "
            "is not created, the default spell-check dictionary found at "
            "options/Dictionary.txt will be used. See Guide for more details."), 
            action="store_true",
            dest="process_words"
        )
        processGroup.add_argument("-lc", "--lowercase", 
            help="Convert all letters to lower-case for CSV output.", 
            action ="store_true"
        )
        
        if __name__ == "__main__":
            self.args=vars(parser.parse_args())
        else:
            args_split = [
                re.sub(r'"','', phrase) for phrase in 
                re.findall(r'([\w\-]+|".*?")', user_args)
            ]
            self.args = vars(parser.parse_args(args_split))

class ReadPDF:            

    # START STARTUP BLOCK
    def __init__(self, user_args=""):
        self.time_start_overall = time.perf_counter()
        self.args = Arguments(user_args).args
        self.path = self.args["filepath"]
        # Run basic setup to confirm input can be processed
        try:
            # Confirm that Tesseract OCR is properly installed right away
            self.find_tesseract()
            # Identify whether the input is a single file or a directory
            start_time = time.perf_counter()
            self.dialog = ProgressOutput(self)
            self.input_type = self.file_or_dir(self.args["filepath"])                
            # Compile list of all valid PDF files from input
            self.path_list = self.get_file_list(self.args["filepath"])
            self.tools = ProcessingTools()
            self.tools._dictionary_process(**self.args)
            self.dialog.start_container()
            self.files = self._read_files()
            self.text = " ".join(str(f.text) for f in self.files)
            self.word_count = sum(f.word_count for f in self.files)
            self.page_count = sum(f.page_count for f in self.files)
            self.page_count_active = self.page_count - sum(f.page_count_skipped for f in self.files)
            self._append_final_output_data()

            end_time = time.perf_counter()
            self.time = end_time-start_time


        except IOError as err:
            self.error_found(err)
            
    # Check to see if Tesseract OCR has been installed as per README
    def find_tesseract(self):

        # Identify default locations for Windows or Mac
        operating_system = sys.platform
        if operating_system == "win32":
            tesseract_path = r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe'
        elif operating_system == "darwin":
            tesseract_path = r'/usr/local/bin/tesseract'
        else:
            tesseract_path = r'neitherWin32NorMac'
        
        # If neither path exists, check the text file for a custom path, as per README
        if not os.path.isfile(tesseract_path):
            with open(os.path.join("options","tesseractPath.txt"), "r") as tesseract_path_file:
                tesseract_path = tesseract_path_file.readline().strip()
        
        # If the file still doesn't exist, raise the error
        if not os.path.isfile(tesseract_path):
            ex = IOError()
            ex.strerror = (
                "I could not find your Tesseract-OCR installation "
                "in the default location.\nThe program will attempt to read the "
                "file(s) if they are machine-readable, but will return an error "
                "if any pages require OCR.\nIf you have not installed Tesseract-OCR, "
                "please refer to the Guide to do so.\nIf you have installed it, "
                "please locate the executable file (\"tesseract.exe\" in Windows,"
                " \"tesseract\" in MacOS) and paste the full path as the first line "
                "of the file \"tesseractPath.txt\" in the same folder as this program"
            )
            raise ex
        else:
            # Point PyTesseract to Tesseract executable
            pytesseract.pytesseract.tesseract_cmd = tesseract_path

    # Check to see if the input is a valid file or a valid dir, return either or raise an error
    def file_or_dir(self, path):
        is_file = os.path.isfile(path)
        if not is_file:
            is_dir = os.path.isdir(path)
            if is_dir:
                return "dir"
            else:
                ex = IOError()
                ex.strerror = "Please enter a valid file or directory"
                raise ex
        else:
            return "file"   

    # Create a list of all valid PDF files in a given path
    def get_file_list(self, path):
        files = list()
        
        # Create a list of all files in a given path
        if self.input_type == "dir":
            dirs = [path]
            while len(dirs) > 0:
                for(dirpath, dirnames, filenames) in os.walk(dirs.pop()):
                    dirs.extend(dirnames)
                    files.extend(
                        map(
                            lambda n: os.path.join(*n), zip(
                                [dirpath] * len(filenames), filenames
                                )
                            )
                    )
        else:
            files.append(path)

        pdf_files = list()

        # Check all files in the file list, and create a new list with only valid PDF files (can be opened by MuPDF)
        for file in files:
            if os.path.splitext(file)[1].lower() == ".pdf" and os.path.basename(file)[0] != ".":
                try:
                    pdf = fitz.open(file)
                    pdf.close()
                    pdf_files.append(file)
                except:
                    pass

        # Ensure the list is in natural reading order (as would be seen in the file manager)
        pdf_files = natsorted(pdf_files)

        # Raise an error if there are no valid PDF files
        if len(pdf_files) == 0:
            ex = IOError()
            pdf_err = ("The {} you have entered {} PDF file{}. "
                "Please enter a PDF file or directory containing PDF files")
            if self.input_type == "file":
                ex.strerror = pdf_err.format("file", "is not a", "")
            else:
                ex.strerror = pdf_err.format("folder", "does not contain any", "s")
            raise ex

        return pdf_files

    def _read_files(self):
        return [File(path, self.dialog, **self.args) for path in self.path_list]

    def _append_final_output_data(self):
        counter_page = 1
        for f in self.files:
            for page in f.pages:
                page.output_data["Page Number (Overall)"] = counter_page
                counter_page += 1

    
    # END STARTUP BLOCK


    # Error dialog
    def error_found(self, e):
        print("Sorry! There's been a problem. {} and try again.".format(e.strerror))
    
class File:

    def __init__(self, file_path, dialog, **args):
        start_time = time.perf_counter()
        self.dialog = dialog
        self.dialog.file = self
        self.args = args
        self.path = file_path
        self.filename = os.path.basename(file_path)
        self.pdf = fitz.open(file_path)
        self.dialog.start_file()
        self.pages = self._read_pages()
        self.page_count_skipped = sum(1 for page in self.pages if page.skipped)
        self.page_count = len(self.pages)
        self.page_count_ocr = sum(1 for page in self.pages if page.method == "ocr")
        self.page_count_text =  self.page_count - self.page_count_ocr
        self.word_count = sum(page.word_count for page in self.pages)
        self.text = " ".join([str(page.text) for page in self.pages])
        self._append_file_output_data()
        end_time = time.perf_counter()
        self.time = end_time - start_time   

    def __repr__(self):
        return self.path
    
    def __str__(self):
        return self.filename

    def _read_pages(self):
        return [Page(page, self.pdf, self.dialog, **self.args) for page in self.pdf]

    def _append_file_output_data(self):

        for page in self.pages:

            page.output_data.update(
                {
                    "Source File Path" : self.path, 
                    "Source File Name" : self.filename, 
                    "Page Number (Overall)" : self.pages.index(page) + 1,
                    "Page Processing Duration (s)" : f"{round(page.time,3)}",
                }
            )

class Page:

    def __init__(self, page, pdf, dialog, **args):
        self.start_time = time.perf_counter()
        self.args = args
        self.dialog = dialog
        self.dialog.page = self
        self.page_number = page.number
        self.skipped = (len(self.args["pages"]) > 0 and self.page_number not in self.args["pages"])
        self.page = page
        self.method = "text"
        if not self.skipped:
            self.pdf = pdf
            self.text = self.read_page()
            self.text_whole = self.text
            self.word_count = len(self.text.words)
            self.sentence_count = len(self.text.sentences)
            self.output_data = self._build_output_dict()
        else: 
            self.text = TextBlob("")
            self.pdf = None
            self.word_count = 0
            self.sentence_count = 0
            self.dialog.page_skip()
        end_time = time.perf_counter()
        self.time = end_time-self.start_time
        self.dialog.page_read()

    def __repr__(self):
        return str(self.page.number)

    def __str__(self):
        return "Page {}".format(self.page_number)

    def read_page(self):
        # try to extract text
        if self.args["thorough"]:
            self.dialog.ocr_switch()
            self.method = "ocr"
            text = self.ocr_page()
        else:
            self.method = "text"
            text = self.page.getText()

            if len(text) < 1:   # OCR the page if there is no text or if forced
                self.method = "ocr"
                if self.args["accelerated"]:  # Skip if Accelerated option active
                    self.skipped = True
                    self.dialog.page_skip()
                else:
                    self.dialog.ocr_switch()
                    text = self.ocr_page()
                    
        text = self.clean_text(text) # Pass text through text cleaning processes
        return TextBlob(text)
    
    def ocr_page(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            zoom_matrix = fitz.Matrix(3.2,3.2)   # Set the optimal settings for OCR-readable images
            pix = self.page.getPixmap(matrix=zoom_matrix, colorspace=fitz.csGRAY, alpha=True) # Generate pixmap from PDF page
            img = os.path.join(temp_dir,"page-{}.png".format(self.page.number)) # find image in pixmap
            pix.writePNG(img)   # Grab image and save it
            
            text = self.ocr(img)                        
        return text
    
    def _build_output_dict(self):
        return {
            "Page Number (File)":self.page_number + 1, 
            "Word Count":self.word_count,
            "Text":self.text, 
            "Process Timestamp":time.asctime(), 
            "Raw Text":self.text_whole
        }

    # Use tesseract to get text via OCR
    def ocr(self, img):
        try:
            text = pytesseract.image_to_string(img, lang="eng", config="--psm 1")
        except:
            print(("\rSorry! There appears to be an issue with your Tesseract OCR installation. "
            "Please refer to the instruction manual for more details."))
            text = ""
        return text

    def clean_text(self, text_raw):

            # make all space (inluding line breaks) into standard spaces
            text_clean = re.sub(r"\s", " ", text_raw)

            # Strip accents and convert unicode symbols to ascii and transliterate non-latin characters
            text_clean = unidecode.unidecode(text_clean)

            # make all apostrophes the same
            text_clean = re.sub(r"[‘’‚‛′`']", r"'", text_clean)

            #connect hyphenated line breaks
            text_clean = re.sub(r"\S-\s+", lambda x: x.group(0)[0], text_clean)

            # Remove non-grammatical punctuation
            text_clean = re.sub(r'''[^a-zA-Z0-9' .;,"$/@!?&\-()_]''', r"", text_clean)

            # clean words split up by spaces
            text_clean = re.sub(r"(\b\w\s)+", self.strip_whitespace, text_clean)

            # fix spaces
            text_clean = re.sub(r"\s+", " ", text_clean)
            text_clean = re.sub(r"\s[.,;]", lambda x: x.group(0)[1], text_clean)

            # common splits
            text_clean = re.sub(
                r"(?i)\bt\s?h\s?e\b", 
                lambda x: x.group(0)[0]+"he", 
                text_clean
            )
            text_clean = re.sub(
                r"\ba\s?n\s?d\b", 
                lambda x: x.group(0)[0]+"nd", 
                text_clean
            )

            # remove leading and trailing spaces
            text_clean = text_clean.strip()

            return text_clean
    def strip_whitespace(self, text):
            text_new = ""
            for c in text.group(0):
                if not re.match(r"\s", c):
                    text_new += c
            text_new += " "
            return text_new
    
class ProcessPDF(ReadPDF):
    def __init__(self, user_args=""):

        super().__init__(user_args)

        self.time_read = self.time
        time_start = time.perf_counter()
        self.text_whole = " ".join([str(f.text_whole) for f in self.files])
        self.report = MergedFrequencyReport(
            [
                f.report for f in self.files if len(f.report.report) > 0
            ], 
            **self.args
        )
        time_end = time.perf_counter()
        self.time_process = sum([f.time_process for f in self.files]) + (time_end - time_start)
        self.time += self.time_process
        self.dialog.end_container()

    def _read_files(self):
        return [FileProcessed(path, self.dialog, **self.args) for path in self.path_list]
    
    def write(self):
        if self.args["split"]:
            outputs = self.files
        else:
            outputs = [self]
        for container in outputs:
            writer = CSVWriter(container)
            writer.write_content()
            if any([
                self.args["report"], 
                self.args["report_file"], 
                self.args["report_page"]
            ]):
                writer.write_report()
            if processed.args["corrections"]:
                writer.write_corrections()
class FileProcessed(File):
    def __init__(self, file_path, dialog, **args):
        super().__init__(file_path, dialog, **args)
        self.time_read = self.time
        time_start = time.perf_counter()
        self.text_whole = " ".join([str(page.text_whole) for page in self.pages])
        self.report = MergedFrequencyReport(
            [
                page.report for page in self.pages if hasattr(page, "report")
            ], 
            **self.args
        )
        time_end = time.perf_counter()
        self.time_process =  sum(page.time_process for page in self.pages) + (time_end - time_start)
        self.time = self.time_read + self.time_process
        self.dialog.end_file()
        

    def _read_pages(self):
        return [PageProcessed(page, self.pdf, self.dialog, **self.args) for page in self.pdf]

class PageProcessed(Page):
    def __init__(self, page, pdf, dialog, **args):
        super().__init__(page, pdf, dialog, **args)
        self.tools = ProcessingTools()
        self.dialog = dialog
        self.dialog.page = self
        self.time_read = self.time
        self.time_process = 0.0
        self.text_whole = self.text
        self.corrected_words = []
        start_time = time.perf_counter()
        if not self.skipped:
            self._process_page()
        end_time = time.perf_counter()
        self.time_process = end_time - start_time
        self.dialog.page_process()
        self.time = self.time_read + self.time_process
        self.dialog.page_complete()

    def _process_page(self):
        if not self.skipped:
            if self.args["autocorrect"]:
                if self.args["process_words"]:
                    self.correct_and_remove()
                else:
                    self.correct()
            elif self.args["process_words"]:
                self.remove_typos()
            
            if self.args["lemmatize"]:
                self.lemmatize()
            
            if self.args["process_punctuation"]:
                self.remove_punctuation()
            
            if self.args["process_numbers"]:
                self.remove_numbers()
            
            if self.args["lowercase"]:
                self.lowercase()
            if any([self.args["report"], self.args["report_page"], self.args["report_file"]]):
                self.report = FrequencyReport(self.text, **self.args)
            self.text_whole = self.text
            if self.args["process_only"] is not None:
                word_list = self.tools._get_word_list(
                    self.args["process_only"], 
                    self.tools.only_file
                )
                self.words_only(word_list)
            
            if self.args["process_ignore"] is not None:
                word_list = self.tools._get_word_list(
                    self.args["process_ignore"], 
                    self.tools.ignore_file
                )
                word_list = self.tools._default_stop_words(
                    word_list, 
                    self.tools.stop_words_file
                )
                self.words_ignore(word_list)
            self.output_data["Text"] = self.text

    def correct(self):
        correct = self.tools.autocorrect(self.text, "correct")
        self.text = correct[0]
        self.corrected_words = correct[1]

    def correct_and_remove(self):
        correct = self.tools.autocorrect(self.text, "correct+remove")
        self.text = correct[0]
        self.corrected_words = correct[1]

    def remove_typos(self):
        correct = self.tools.autocorrect(self.text, "remove")
        self.text = correct[0]
        self.corrected_words = correct[1]

    def lemmatize(self):
        self.text = self.tools.lemmatize(self.text)

    def remove_punctuation(self):
        self.text = self.tools.remove_punctuation(self.text)

    def remove_numbers(self):
        self.text = self.tools.remove_numbers(self.text)

    def lowercase(self):
        self.text = self.text.lower()

    def words_only(self, word_list):
        self.text_whole = self.text
        self.text = self.tools.words_only(self.text, word_list)
    
    def words_ignore(self, word_list):
        self.text_whole = self.text
        self.text = self.tools.words_ignore(self.text, word_list)

    def tokenize_sentences(self):
        self.output_data_whole = self.output_data.copy()
        self.output_data.update(
            {
                "Sentence Number" : [
                    i + 1 
                    for i in range(len(self.text.sentences))
                ],
                "Word Count" : [
                    len(sentence.words) for sentence in self.text.sentences
                ],
                "Text" : self.text.sentences,
                "Raw Text" : self.text_whole.sentences
            }
        )
    
    def tokenize_words(self):
        self.output_data_whole = self.output_data.copy()
        self.output_data.update(
            {
                "Word Number" : [
                    i + 1
                    for i in range(len(self.text.words))
                ],
                "Word Length" : [
                    len(word) for word in self.text.words
                ],
                "Text" : self.text.words,
                "Raw Text" : self.text_whole.words
            }
        )

    def detokenize(self):
        if hasattr(self, "output_data_whole"):
            self.output_data = self.output_data_whole

class ProcessingTools:

    def __init__(self):
        self._default_word_list_files()

    def _dictionary_process(self, **args):
        d = BuildDict()
        if args["dictionary_revert"]:
            try:
                os.remove(d.path_custom_dict)
                print("Custom dictionary removed, default dictionary now active.")
            except:
                print("Custom dictionary does not exist.")
        if args["dictionary_add_word"]:
            d.merge(
                d.path_custom_dict, 
                " ".join(args["dictionary_add_word"])
            )
        if args["dictionary_remove_word"]:
            d.remove(
                d.path_custom_dict, 
                " ".join(args["dictionary_remove_word"])
            )
        if args["dictionary"]:
            self.dictionary_new(args["dictionary"], args["dictionary_large"])

    def dictionary_new(self, terms, large=False):
        print("Building custom dictionary.")
        d = BuildDict()
        d.get(terms)
        d.train(d.path_custom_source)
        d.merge(d.path_custom_dict,d.path_ref_dict)
        if not large:
            limit = 1
            while len(open(d.path_custom_dict,"r").readlines()) > 70000:
                d.shrink(d.path_custom_dict,limit)
                limit += 1

    def _default_word_list_files(self, 
        ignore=os.path.join("options","ProcessIgnore.txt"), 
        only=os.path.join("options","ProcessOnly.txt"),
        stop=os.path.join("options", "StopWords.txt")
    ):
        self.ignore_file = ignore
        self.only_file = only
        self.stop_words_file = stop

    def _blobify(self, text):
        if type(text) != TextBlob:
            text = TextBlob(text)
        return text

    def _get_word_list(self, word_list, default_file):
        if type(word_list) is list and len(word_list) > 0:
            return word_list
        elif type(word_list) is str and os.path.isfile(word_list):
            return [word_list]
        else:
            return [default_file]

    def _default_stop_words(self, word_list, stop_words_file):
        if os.path.isfile(word_list[0]):
            with open(word_list[0], "r") as read_file:
                if len([line for line in read_file if line[0] !="#"]) == 0:
                    word_list = [stop_words_file]
        return word_list

    def autocorrect(self, text, mode="correct"):
        text = self._blobify(text)
        text_corrected = TextBlob("")
        words_corrected = list()
        spelling = Spelling(
            path=BuildDict.path_custom_dict if os.path.exists(BuildDict.path_custom_dict) 
            else BuildDict.path_ref_dict
        )
        
        for word in [p.split("/")[0] for p in re.sub(r"\n", " ", text.parse()).split(" ")]:
            word_lowercase = word.lower()
            if True not in [True if c.isalnum() else False for c in word]:
                check = [(word, -1)]
                separator = ""
            else:
                separator = " "
                if not word.isalpha():
                    check = [(word, -2)]
                else:
                    
                    check = spelling.suggest(word_lowercase)
            corrected = check[0][0]
            if word.isupper():
                corrected = corrected.upper()
            elif word.istitle():
                corrected = corrected.title()
            if "correct" in mode:
                if len(list(spelling._known([word.lower()]))) == 0 and check[0][1] > -1:
                    words_corrected.append(
                        [word, True if check[0][1]>0 else False, 
                        corrected if check[0][1]>0 else "", 
                        check[0][1] if check[0][1]>0 else ""]
                    )
                if mode == "correct+remove":
                    if check[0][1] > 0 or check[0][1] == -1:
                        text_corrected += separator + corrected
                else:
                    text_corrected += separator + corrected
            elif mode == "remove":
                if len(list(spelling._known([word.lower()]))) != 0 or check[0][1] == -1:
                    text_corrected += separator + corrected
        return (text_corrected.strip(), words_corrected)

    def lemmatize(self, text):
        
        blob = self._blobify(text)
        text = ""
        for w in re.sub(r"\n", " ", blob.parse()).split(" "):
            if "/" in w:
                if w.split("/")[1][:2] == "JJ":
                    pos = 'a'
                elif "RB" in w.split("/")[1]:
                    pos = 'r'
                elif w.split("/")[1][:2] == "VB":
                    pos = 'v'
                else:
                    pos = 'n'
                text += "{}".format(
                    " " if True in [True if c.isalnum() else False for c in w.split("/")[0]] else ""
                ) + Word(w.split("/")[0]).lemmatize(pos) 
            else:
                text += w
        return TextBlob(text.strip())

    def remove_punctuation(self, text):
        blob = self._blobify(text)
        text_new = " ".join(blob.words)
        text_new = re.sub(r"[^\w\s'-]|_|\^|\\", "", text_new)
        return TextBlob(text_new)

    def remove_numbers(self, text):
        text = str(text)
        text = re.sub(r"\d", "", text) 
        return TextBlob(text)

    def _get_pattern(self, pattern_list):

        # If there is a file name, get the list from the custom file source
        if os.path.isfile(pattern_list[0]):
                with open(pattern_list[0], "r") as pattern_file:
                    patterns = [
                        pattern.strip().lower() 
                        for pattern in pattern_file if pattern[0] != "#"
                    ]
        else:
            patterns = [pattern.lower() for pattern in pattern_list]

        # Catchall pattern if none specified
        if len(patterns) < 1:
            patterns.append(r"\w*")

        return patterns

    def words_only(self, text, word_list):
        patterns = self._get_pattern(word_list)
        text_old = str(text)
        text_new = ""
        # Only include specified words
        for pattern in patterns:
            matches  = re.findall(r"\b{}\b".format(pattern), text_old, flags=re.IGNORECASE)
            text_new += " " + " ".join(matches)
        text_new = re.sub(r"\s\s+", " ", text_new) # Fix double spaces
        text_new = text_new.strip()
        return TextBlob(text_new)
    
    def words_ignore(self, text, word_list):
        patterns = self._get_pattern(word_list)
        text = str(text)
        # Remove specified words
        for pattern in patterns:
            text = re.sub(r"\b{}\b".format(pattern), "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s\s+", " ", text) # Fix double spaces
        text = text.strip()
        return TextBlob(text)

class FrequencyReport:

    def __init__(self, source, user_args="", **args):
        if len(args) > 0:
            filepath = args["filepath"]
        else:
            filepath = "DEFAULT"
        self.args = Arguments(" ".join([filepath,user_args])).args
        self.args.update(args)
        if type(source) not in [ReadPDF, File, Page, ProcessPDF, FileProcessed, PageProcessed]:
            self.text = TextBlob(str(source))
        elif type(source) in [ReadPDF, ProcessPDF]:
            self.text = self._extractContainer(source)
        elif type(source) in [File, FileProcessed]:
            self.text = self._extractFile(source)
        elif type(source) in [Page, PageProcessed]:
            self.text = source.text
        if len(self.text) > 0:
            self.tools = ProcessingTools()
            self.tools._default_word_list_files(
                ignore=os.path.join("options", "ReportIgnore.txt"),
                only=os.path.join("options", "ReportOnly.txt")
            )

            self.report_words_raw = self.text.lower().word_counts

            if self.args["report_pos"]:
                self.report_raw = self.report_POS()
            else:
                self.report_raw = self.report_words_raw

            self.report = self.report_raw

            if self.args["report_only"] is not None:
                word_list = self.tools._get_word_list(
                    self.args["report_only"], 
                    self.tools.only_file
                )
                self.report = self.report_only(word_list)
            if self.args["report_ignore"] is not None:
                word_list = self.tools._get_word_list(
                    self.args["report_ignore"], 
                    self.tools.ignore_file
                )
                word_list = self.tools._default_stop_words(
                    word_list, 
                    self.tools.stop_words_file
                )
                self.report = self.report_ignore(word_list)

            self.report_unlimited = self.report

            if self.args["report_limit"]:
                self.report = self.report_limit(self.report, self.args["report_limit"])
                self.report_chron = {k:v for k,v in self.report_raw.items() if k in self.report.keys()}
            else:
                self.report_chron = self.report
            self.report_alpha = self._sort_alpha(self.report)
            self.report_freq = self._sort_freq(self.report)

            if self.args["report_sort"]:
                self.report = self.report_freq
            else:
                self.report = self.report_alpha
        else:
            self.report = {}

    def _extractFile(self, input_file):
        return TextBlob(" ".join([str(page.text_whole) for page in input_file.pages]))

    def _extractContainer(self, input_container):
        return TextBlob(" ".join([str(self._extractFile(input_file)) for input_file in input_container.files]))

    def _sort_alpha(self, report):
        if type(list(report)[0]) == str:
            return dict(sorted(report.items()))
        elif type(list(report)[0]) == tuple:
            return {pos : report[pos] for pos in sorted(report)}

    def _sort_freq(self, report):
        if type(list(report)[0]) == str:
            return dict(sorted(report.items(), reverse=True, key=lambda x: x[1]))
        elif type(list(report)[0]) == tuple:
            return {pos : report[pos] for pos in sorted(report, reverse=True, key=lambda x:report[x])}

    def report_POS(self):
        if type(self.text) != TextBlob:
            self.text = TextBlob(str(self.text))
        self.text = self.text.lower()
        return {
            self.text.tags.pop(self.text.tags.index(tag)) : self.text.tags.count(tag) 
            for tag in self.text.tags
        }
    
    def report_only(self, word_list):
        if type(list(self.report)[0]) == str:
            return {k:v for k,v in self.report.items() if k in word_list}
        elif type(list(self.report)[0]) == tuple:
            return {k:v for k,v in self.report if k[0] in word_list}

    def report_ignore(self, word_list):
        if type(list(self.report)[0]) == str:
            return {k:v for k,v in self.report.items() if k not in word_list}
        elif type(list(self.report)[0]) == tuple:
            return {k:v for k,v in self.report.items() if k[0] not in word_list}

    def report_limit(self, report, report_limit):
        count = sum(report.values())

        # get limit from arg, only numbers and %
        limit = re.sub(r"[^0-9%+]", "", report_limit)

        # default to 100% if input doesn't make sense
        if len(limit) < 1 or ("%" in limit and len(limit) < 2):
            limit = "100%"

        # get top percentile if % is present
        if "%" in limit:
            percentile = int(re.sub(r"[^0-9]", "", limit))

            # calculate percentile cutoff
            if percentile > 100:
                percentile = 100
            ceiling  = math.ceil((percentile/100) * count)

            # cutoff after instances have reached cutoff
            report_sorted = self._sort_freq(report)
            report_trimmed = dict()
            for k,v in report_sorted.items():
                if sum(report_trimmed.values()) < ceiling:
                    report_trimmed[k] = v
                else:
                    break 
        # if not a percentile, return top x words 
        
        
        elif "+" in limit:
            ceiling = int(re.sub(r"[^0-9]", "", limit))
            report_trimmed = {k:v for k,v in report.items() if v >= ceiling}

        else:
            ceiling = int(re.sub(r"[^0-9]", "", limit))
            report_sorted = self._sort_freq(report)
            report_trimmed = {k:report[k] for k in list(report_sorted.keys())[0:ceiling]}
        return report_trimmed

class MergedFrequencyReport(FrequencyReport):

    def __init__(self, reports, **args):
        self.args = args
        self.text = ""
        self.report = dict()
        if len(reports) > 0:
            
            self.text = " ".join(
                [str(report.text) for report in reports]
            )
            for report in reports:
                self.report.update(report.report)
            
            self.report_alpha = self._sort_alpha(self.report)
            self.report_freq = self._sort_freq(self.report)
            if self.args["report_limit"]:
                self.report = self.report_limit(self.report, self.args["report_limit"])
                self.report_chron = {k:v for k,v in self.report.items() if k in self.report.keys()}
            else:
                self.report_chron = self.report.copy()
            if self.args["report_sort"]:
                self.report = self.report_freq
            else:
                self.report = self.report_alpha

class CSVWriter:
    def __init__(self, input_container, user_args="", output_root_path="", output_file_basename=""):
        
        self.args = input_container.args
        if len(user_args) > 0:
            self.args = Arguments(" ".join([self.args["filepath"],user_args])).args
        self.input_container = input_container
        self.root_path = (
            os.path.split(input_container.path)[0] 
            if output_root_path == "" 
            else output_root_path
        )
        self.file_basename = (
            os.path.splitext(input_container.path)[0] 
            if output_file_basename == "" 
            else output_file_basename
        )
        if self.file_basename[-1] in ["/", "\\"]:
            self.file_basename = self.file_basename[:-1]

    
    def write_content(self):
        if type(self.input_container) in [ReadPDF,ProcessPDF,File,FileProcessed]:
            headers = self._get_content_headers()
            lines = self._build_lines()
            trimmed_lines = self._trim_lines(lines, headers)
            with open(
                f"{self.file_basename}.csv",
                "w+", 
                newline=''
            ) as output_file:
                writer = csv.DictWriter(output_file, fieldnames=headers, dialect='excel')
                writer.writeheader()
                writer.writerows(trimmed_lines)
            self.input_container.dialog.file_written(
                "content",
                self.input_container.path,
                f"{self.file_basename}.csv", 
                type(self.input_container)
            )

    def _trim_lines(self, lines, headers):
        for line in lines:
            keys_to_remove = [key for key in line.keys() if key not in headers]
            for key in keys_to_remove:
                del line[key]
        return lines

    def write_report(self):
        if type(self.input_container) in [ReadPDF,ProcessPDF,File,FileProcessed]:
            pos = type(list(self.input_container.report.report.items())[0][0]) == tuple
            
            if(all([
                self.args["report_file"], 
                type(self.input_container) in [ReadPDF, ProcessPDF]
            ])):
                lines = self._get_report_headers(self.input_container.path, pos)
                for f in self.input_container.files:
                    lines.extend(self._get_report_headers(f.filename, pos))
                    lines.extend(self._get_report_lines(f.report, pos))
            elif(self.args["report_page"]):
                lines = self._get_report_headers(self.input_container.path, pos)
                if type(self.input_container) in [File, FileProcessed]:
                    files = [self.input_container]
                else:
                    files = self.input_container.files 
                for f in files:
                    for page in f.pages:
                        if hasattr(page, "report"):
                            lines.extend(
                                self._get_report_headers(
                                    f"{f.filename} Page {page.page_number + 1}/{f.page_count}",
                                    pos
                                )
                            )
                            lines.extend(self._get_report_lines(page.report, pos))    
            else:
                lines = self._get_report_headers(self.input_container.path, pos)
                lines.extend(self._get_report_lines(self.input_container.report, pos))

            with open(
                f"{self.file_basename}-FR.csv",
                "w+",
                newline=''
            ) as output_file:
                writer = csv.writer(output_file, dialect='excel')
                writer.writerows(lines)
            self.input_container.dialog.file_written(
                "report",
                self.input_container.path,
                f"{self.file_basename}-FR.csv", 
                type(self.input_container)
            )

    def write_corrections(self):
        if type(self.input_container) in [ReadPDF,ProcessPDF,File,FileProcessed]:
            lines = [["Unknown Word","Correction Attempted","Correction","Confidence"]]
            pages = self._flatten_pages()
            lines.extend([line for page in pages for line in page.corrected_words if len(page.corrected_words) > 0])
            with open(
                f"{self.file_basename}-corrections.csv",
                "w+", 
                newline=''
            ) as output_file:
                writer = csv.writer(output_file, dialect='excel')
                writer.writerows(lines)
            self.input_container.dialog.file_written(
                "corrections",
                self.input_container.path,
                f"{self.file_basename}-corrections.csv", 
                type(self.input_container)
            )
            
    def _flatten_pages(self):
        if type(self.input_container) in [ReadPDF, ProcessPDF]:
            return [page for f in self.input_container.files for page in f.pages]
        else:
            return self.input_container.pages

    def _get_content_headers(self):
        headers = self.args["fields"]
        if "Raw Text" in headers and not self.args["source_text"]:
            headers.remove("Raw Text")
        if self.args["tokenize_sentences"] or self.args["tokenize_words"]:
            i=0
            for header in headers:
                if "Page Number" in header:
                    i = headers.index(header)
            if i > 0:
                if self.args["tokenize_sentences"]:
                    headers.insert(i+1, "Sentence Number")
                elif self.args["tokenize_words"]:
                    headers.insert(i+1, "Word Number")
                    if "Word Count" in headers:
                        j = headers.index("Word Count")
                        del headers[j]
                        headers.insert(j,"Word Length")
        
        return headers

    def _build_lines(self):
        pages = self._flatten_pages()
        lines = list()
        if not any([self.args["tokenize_sentences"], self.args["tokenize_words"]]):
            for page in pages:
                if type(page.output_data["Text"]) == list:
                    page.detokenize() 
            lines = [page.output_data for page in pages]
        else:
            expandable_fields = ["Text", "Raw Text"]
            if self.args["tokenize_sentences"]:
                for page in pages:
                    page.tokenize_sentences()
                expandable_fields.extend(["Word Count", "Sentence Number"])
            elif self.args["tokenize_words"]:
                for page in pages:
                    page.tokenize_words()
                expandable_fields.extend(["Word Length", "Word Number"])
            lines = [
                dict(
                    page.output_data.copy(),
                    **dict(
                        zip(expandable_fields,
                            [
                                page.output_data[field][i] 
                                for field in expandable_fields
                            ]
                        )
                    )
                )
                for page in pages
                for i in range(len(page.output_data["Text"]))
            ]
        
        return lines

    def _get_report_headers(self, source_path, pos):
        return [
            [f"Frequency Report for {source_path}"]
        ]
    
    def _get_report_lines(self, report, pos):
        lines = [["Word","POS","Frequency"] if pos else ["Word", "Frequency"]]
        lines.extend( [
            [line[0][0],line[0][1],line[1]] 
            if pos else [line[0],line[1]]
            for line in list(report.report.items())
        ])
        return lines

class ProgressOutput:

    def __init__(self, container, silent=False):
        self.container = container
        self.args = self.container.args
        self.file = None
        self.page = None
        self.silent = silent
        self.quiet = self.args["quiet"]
        self.verbose = self.args["verbose"]
        self.ocr_switch_notice = False
        self.five_percent = 0
        self.percent = 0 
        self.percent_count = 0
        self.counter_files = 0
        self.leader = "" if self.args["verbose"] else "\r"
        self.rtn = "\n" if self.args["verbose"] else ""

    def start_container(self):
        if not self.silent:
            if self.container.input_type == "dir":
                print("Processing all PDF files in folder {} ({} File{})".format(
                        self.container.path, 
                        len(self.container.path_list),
                        "s" if len(self.container.path_list) > 1 else ""
                    ))

    def end_container(self):
        if not any([self.silent, self.args["quiet"], not self.container.input_type == "dir"]):
            print(
                ("{} file{} ({} words) were processed in {} seconds. "
                "That is an average of {} seconds/file").format(
                    len(self.container.path_list), 
                    "s" if len(self.container.path_list) > 1 else "", 
                    self.container.word_count,
                    round(self.container.time,3), 
                    round(self.container.time/len(self.container.files)
                    if len(self.container.files) != 0 else 0,3)
                )
            )

    def start_file(self):
        self.counter_files += 1
        self.ocr_switch_notice = False
        if not self.silent:
            if not self.args["quiet"]:
                print("Processing {} ({} page{})".format(
                    self.file.filename,
                    len(self.file.pdf),
                    "s" if len(self.file.pdf) > 1 else ""
                ))
                if not any([self.args["verbose"], self.args["quiet"]]):
                    print("Progress: 0%|", end="", flush=True)
                self.five_percent = len(self.file.pdf)/20
                self.percent = self.five_percent
                self.ocr_switch_notice = False
            else:
                print(
                    f"\rProcessing file {self.counter_files}/{len(self.container.path_list)}",
                    end="" if self.counter_files < len(self.container.path_list) else "\n",
                    flush=True
                )

    def end_file(self):
        if not any([self.silent, self.args["quiet"]]):
            print(
                "Completed {} in {} seconds ({} page{}, {} words, {} seconds/page)".format(  
                    self.file.filename, 
                    round(self.file.time,3), 
                    self.file.page_count - self.file.page_count_skipped, 
                    "s" if (self.file.page_count - self.file.page_count_skipped) > 1 else "", 
                    self.file.word_count, 
                    round(self.file.time/(self.file.page_count-self.file.page_count_skipped)
                    if (self.file.page_count-self.file.page_count_skipped) != 0 
                    else 0,3)
                )
            )
            if self.file.page_count_skipped > 0:
                print(
                        ("Some pages were skipped because you chose {}. "
                        "See Guide for details.").format(
                            "Accelerated Mode" if self.args["accelerated"] 
                            else "to only process certain pages"
                        )
                    )
            
    def page_complete(self):
        if not any([self.silent, self.args["quiet"]]):
            if all([
                any([self.page.method == "ocr", self.args["verbose"]]),
                not self.page.skipped
            ]):
                print(
                        "{}Read and processed {} words from page {}/{} in {} seconds        ".format(
                            self.leader,
                            self.page.word_count, 
                            self.page.page_number + 1, 
                            len(self.file.pdf), 
                            round(self.page.time,3)
                        ), 
                        end=self.rtn, 
                        flush=True
                    )
            else:
                if all([self.page.page_number >= self.percent, not self.args["verbose"]]):    
                    print("=", end="", flush=True)
                    self.percent = self.percent + self.five_percent
            if all([
                self.page.page_number + 1 == len(self.file.pdf), 
                not self.args["verbose"]
            ]): 
                print("\rProgress: 0%|====================|100%                             ")

    def page_read(self):
        if all([self.args["verbose"], not self.page.skipped]):
            print(
                "Read {} words from page {}/{} in {} seconds".format(
                    self.page.word_count,
                    self.page.page_number + 1,
                    len(self.file.pdf),
                    round(self.page.time,3)
                )
            )

    def page_process(self):
        if all([self.args["verbose"], not self.page.skipped]):
            print(
                "Processed page {}/{} in {} seconds".format(
                    self.page.page_number + 1,
                    len(self.file.pdf), 
                    round(self.page.time_process,3)
                )
            )

    def page_skip(self):
        if not any([self.silent, self.args["quiet"], not self.page.method == "ocr"]): 
            print(
                "{}Page {}/{} skipped as {} specified.              ".format(
                    self.leader, 
                    self.page.page_number + 1, 
                    len(self.file.pdf),
                    "Accelerated Mode was" 
                    if self.container.args["accelerated"] 
                    else "it was not among those"
                ), 
                end=self.rtn if self.page.page_number + 1 < len(self.file.pdf) else "\n", 
                flush=True
            )

    def ocr_switch(self):
        if not self.ocr_switch_notice and not any([self.silent, self.args["quiet"]]):
            self.ocr_switch_notice = True
            print(
                ("\rThis file is being processed with OCR because {} "
                "\n(This may take a few seconds per page)").format(
                    "Thorough Mode has been chosen, see Guide for details."
                    if self.args["thorough"]
                    else "it contains non-machine readable text."
                )
            )

    def file_written(self, output_type, input_path, output_path, container_type):
        if not any([self.silent, self.args["quiet"]]):
            print(
                ("The file {} contains {} "
                "from {}{}.").format(
                    output_path,
                    "all of the text extracted" if output_type == "content" 
                    else (
                        "a frequency report of all words" if output_type == "report"
                        else "a list of all unknown words and corrections"
                    ),
                    "all PDF files in " if container_type in [ProcessPDF, ReadPDF] else "",
                    input_path
                )
            )

    def complete(self):
        if not self.silent:
            print(
                ("All input files have been read "
                "and all output files have been written in {} seconds.").format(
                    round(time.perf_counter() - self.container.time_start_overall, 3)
                )
            )

if __name__ == "__main__":
    processed = ProcessPDF()
    processed.write()
    processed.dialog.complete()