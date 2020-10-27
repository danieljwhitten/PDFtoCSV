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
from shutil import rmtree
from textblob import TextBlob
from textblob import Word
from textblob.en import Spelling
from build_dictionary import BuildDict

""" A class with the tools to translate a set of PDF files into a single CSV file using embedded text and OCR"""
class PDFtoCSV:            
    
    class Arguments:

        def __init__(self, user_args=""):

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
                        d="Page Processing Duration", 
                        t="Text", 
                        s="Process Timestamp", 
                        c="Custom Text", 
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
            customGroup = parser.add_argument_group("Custom Feild", 
                ("These options allow for the creation of a custom field in the CSV output. "
                "The indicator 'c' must be included in the field string for this field to be included. "
                "See Guide for details.")
            )
            customGroup.add_argument("-ct", "--customTitle", 
                help="Title of custom field. Default title is 'Custom' if not specified.", 
                default="Custom", 
                metavar="Desired Custom Title",
                dest="custom_title"
            )
            customGroup.add_argument("-cc", "--customContent", 
                help=("Content of custom field to be repeated for each page. "
                "Include @ for file name, # for file page number and $ for overall page number. "
                "Default is a blank cell if not specified."), 
                default="", 
                metavar="Desired Custom Content",
                dest="custom_content"
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

            # Parse all args
            if __name__ == "__main__":
                args_parsed = parser.parse_args()
            else:
                args_split = [
                    re.sub(r'"','', phrase) for phrase in 
                    re.findall(r'([\w\-]+|".*?")', user_args)
                ]
                args_parsed = parser.parse_args(args_split)
            self.args = vars(args_parsed)

    # START STARTUP BLOCK
    def __init__(self, user_args=""):

        self.args = self.Arguments(user_args).args
        self.input_filepath = os.path.realpath(self.args["filepath"])

        # Identify the execution path right away
        self.homepath = os.path.dirname(os.path.realpath(__file__))

        # Run basic setup to confirm input can be processed
        try:
            # Confirm that Tesseract OCR is properly installed right away
            self.find_tesseract()
            # Identify whether the input is a single file or a directory
            self.input_type = self.file_or_dir(self.input_filepath)
            # Compile list of all valid PDF files from input
            self.path_list = self.get_file_list(self.input_filepath, self.input_type)

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
            with open(os.path.join(self.homepath,"tesseractPath.txt"), "r") as tesseract_path_file:
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
    def get_file_list(self, path, inputType):
        files = list()
        
        # Create a list of all files in a given path
        if inputType == "dir":
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
            if inputType == "file":
                ex.strerror = pdf_err.format("file", "is not a", "")
            else:
                ex.strerror = pdf_err.format("folder", "does not contain any", "s")
            raise ex

        return pdf_files
    # END STARTUP BLOCK

    # Process the files
    def run(self):
        if self.args["dictionary_revert"]:
            try:
                os.remove(BuildDict.path_custom_dict)
                print("Custom dictionary removed, default dictionary now active.")
            except:
                print("Custom dictionary does not exist.")
        if self.args["dictionary_add_word"]:
            BuildDict().merge(
                BuildDict().path_custom_dict, " ".join(self.args["dictionary_add_word"])
            )
        if self.args["dictionary_remove_word"]:
            BuildDict().remove(
                BuildDict().path_custom_dict, " ".join(self.args["dictionary_remove_word"])
            )
        if self.args["dictionary"]:
            self.dictionary()
        self.report_text = ""
        if not self.args["split"]:
            self.create_output(self.input_filepath) # Create the output file
        self.complete_wordcount = 0  # To keep track of all the words processed
        self.pagecount_complete = 0 # To keep track of all pages processed
        self.dialog("start") # Print starting dialog
        self.words_corrected = list()
        for path in self.path_list:
            self.complete_wordcount += self.process_file(path) # Process file and update wordcount
        if self.args["report"] and not self.args["split"]:
            self.report()
        if self.args["autocorrect"] and self.args["corrections"] and not self.args["split"]:
            self.corrections()
        self.dialog("end") # Print ending dialogue

    def dictionary(self):
        print("Building custom dictionary.")
        d = BuildDict()
        d.get(self.args["dictionary"])
        d.train(d.path_custom_source)
        d.merge(d.path_custom_dict,d.path_ref_dict)
        if not self.args["dictionary_large"]:
            limit = 1
            while len(open(d.path_custom_dict,"r").readlines()) > 70000:
                d.shrink(d.path_custom_dict,limit)
                limit += 1

    # Crete a CSV file for the output, given the same name as the input path, and in the same location
    def create_output(self, path):

        # Remove trailing / or \
        if path[-1] == "/" or path[-1] == r"\\":
            path = path[:-1]

        # Create the file in the same location as the input path    
        output_dir = os.path.dirname(path)

        # Give the output file the same name as the input path
        output_filename = os.path.splitext(os.path.basename(path))[0] + ".csv"

        self.output_path = os.path.join(output_dir,output_filename)
        self.report_path = self.output_path[:-4] + "-FR" + self.output_path[-4:]
        self.corrections_path = self.output_path[:-4] + "-Corrections" + self.output_path[-4:]

        # Create blank file with headers
        with open(self.output_path, "w+", newline='') as output_file:
            output_CSV_writer = csv.writer(output_file, dialect='excel')
            headers = self.args["fields"]
            if "Raw Text" in headers and not self.args["source_text"]:
                headers.remove("Raw Text")
            if self.args["tokenize_sentences"] or self.args["tokenize_words"]:
                i=0
                for header in headers:
                    if "Page Number" in header:
                        i = headers.index(header)
                if i > 0:
                    headers.insert(i+1, "Sentence Number")
                    if self.args["tokenize_words"]:
                        headers.insert(i+2, "Word Number")
                        if "Word Count" in headers:
                            j = headers.index("Word Count")
                            del headers[j]
                            headers.insert(j,"Word Length")
                    
            while headers.count("Custom Text") > 0:
                i = headers.index("Custom Text")
                headers.remove("Custom Text")
                headers.insert(i,self.args["custom_title"])
            output_CSV_writer.writerow(headers)
        
        if self.args["report"] or self.args["report_file"] or self.args["report_page"]:
            with open(self.report_path, "w+", newline='') as output_file:
                output_CSV_writer = csv.writer(output_file, dialect='excel')
        if self.args["autocorrect"] and self.args["corrections"]:
            with open(self.corrections_path, "w+", newline='') as output_file:
                output_CSV_writer = csv.writer(output_file, dialect='excel')
                output_CSV_writer.writerow(["Original Word","Corrected","Correction","Confidence"])
    
    # Process each file in its entirety
    def process_file(self, filePath):
        self.filename = os.path.basename(filePath)

        if self.args["split"]:
            self.create_output(filePath)

        self.pdf = fitz.open(filePath)   # Open the PDF with MuPDF
        self.skipped_pages = False   # Reset
        self.dialog("fileStart")
        
        pages = list()
        self.wordcount_total = 0 # Keep track of all the words processed in the file
        
        self.fivePercent = len(self.pdf)/20 # Determine the 5% intervals for the progress bar
        self.percent = self.fivePercent   # Next percentage marker
        self.percent_count = 0    # How many 5% intervals have passed
        
        self.file_method = "text"  # Assume machine readable text, will change to OCR if OCR detected

        for page in self.pdf:   # process one page at a time
            self.page_start = time.perf_counter()    # Record time page started (OCR pages can take a long time)
            self.page_num = page.number
            
            if len(self.args["pages"]) == 0 or self.page_num+1 in self.args["pages"]:  # Process unless not a specified page
                self.pagecount_complete += 1

                csv_line = list()

                # Get the text and word count from the page
                page_text = self.read_page(page)
                page_blob = TextBlob(page_text)
                sentences_blob = page_blob.sentences
                words_blob = list()
                for s in sentences_blob:
                    words_blob += s.words
                self.wordcount_page = len(page_text.split())
                self.wordcount_total += self.wordcount_page # Update total file word count

                if self.args["autocorrect"]:
                    text_correct = self.autocorrect(page_blob,"correct")
                    page_text = text_correct

                if self.args["lemmatize"]:
                    page_text = self.lemmatize(page_text)

                if self.args["tokenize_sentences"] or self.args["tokenize_words"]:
                    sentences = TextBlob(page_text).sentences

                if self.args["process_punctuation"]:
                    page_text = " ".join(TextBlob(page_text).words)
                    page_text = re.sub(r"[^\w\s'-]|_|\^|\\", "", page_text)
                if self.args["process_numbers"]:
                    page_text = re.sub(r"\d", "", page_text)
                if self.args["process_words"]:
                    page_text = self.autocorrect(TextBlob(page_text), "remove")
                if self.args["lowercase"]:
                    page_text = page_text.lower()
                if self.args["report"] or self.args["report_page"] or self.args["report_file"]:
                    self.report_text += page_text + " "
                    if self.args["report_page"]:
                        self.report()

                page_text = self.edit_words(page_text,"process") # Remove words as specified

                self.page_end = time.perf_counter()  # Record time page ends
                self.page_time = self.page_end-self.page_start

                custom_data = re.sub(r"#", f"{self.page_num+1}", self.args["custom_content"])
                custom_data = re.sub(r"\$", f"{self.pagecount_complete}", custom_data)
                custom_data = re.sub(r"@", self.filename, custom_data)

                data = {
                    "Source File Path" : filePath, 
                    "Source File Name" : self.filename, 
                    "Page Number (File)" : self.page_num+1, 
                    "Page Number (Overall)" : self.pagecount_complete, 
                    "Word Count" : [self.wordcount_page], 
                    "Page Processing Duration" : f"{round(self.page_time,3)} sec.", 
                    "Text" : [page_text], "Raw Text" : [page_blob], 
                    "Process Timestamp" : time.asctime(),
                    self.args["custom_title"] : custom_data
                }
                if self.args["tokenize_sentences"] or self.args["tokenize_words"]:
                    sentence_count = [i+1 for i in range(len(sentences))]
                    wordcount_sentence = [len(s.words) for s in sentences]
                    data["Sentence Number"] = sentence_count
                    if self.args["tokenize_sentences"]:
                        data["Word Count"] = wordcount_sentence
                    data["Text"] = sentences
                    data["Raw Text"] = sentences_blob
                    if self.args["tokenize_words"]:
                        word_index = list()
                        words = list()
                        sentence_counts = list()
                        i = 1
                        for s in sentences:
                            word_index += [i+1 for i in range(len(s.words))]
                            words += s.words
                            sentence_counts += [i] * len(s.words)
                            i += 1

                        word_length = [len(w) for w in words]
                        data["Word Length"] = word_length
                        data["Text"] = words
                        data["Raw Text"] = words_blob
                        data["Sentence Number"] = sentence_counts
                        data["Word Number"] = word_index
                    

                for i in range(len(data["Text"])):
                    csv_line = list() # Build the output
                    for f in self.args["fields"]:
                        if f == "Raw Text":
                            if self.args["source_text"]:
                                csv_line.append(data[f][i])
                        else:
                            if type(data[f]) is list:
                                csv_line.append(data[f][i])
                            else:
                                csv_line.append(data[f])
                    pages.append(csv_line) # Add it to the list of page outputs for the file
                self.dialog("page") # Update progress dialog
                
                
            else:
                self.skipped_pages = True
                self.wordcount_page = 0
                self.dialog("pageskip")

        # Add each page from processed file to the output CSV as 1 line
        with open(self.output_path, "a", newline='') as outputFile:
            outputCSVWriter = csv.writer(outputFile, dialect='excel')
            outputCSVWriter.writerows(pages)
        if self.args["report_file"] or (self.args["split"] and self.args["report"]):
            self.report()
        if self.args["autocorrect"] and self.args["corrections"] and self.args["split"]:
            self.corrections()

        self.dialog("fileEnd")  # Show user statistics for completed file
        self.pdf.close()    # Close the PDF

        return self.wordcount_total

    # return an autocorrected version of source text
    def autocorrect(self, text, mode):
        text_corrected = ""
        spelling = Spelling(
            path=BuildDict.path_custom_dict if os.path.exists(BuildDict.path_custom_dict) 
            else BuildDict.path_ref_dict
        )
        
        for w in [p.split("/")[0] for p in re.sub(r"\n", " ", text.parse()).split(" ")]:
            if True not in [True if c.isalnum() else False for c in w]:
                check = [(w, -1)]
                separator = ""
            else:
                separator = " "
                if not w.isalpha():
                    check = [(w, -2)]
                else:
                    word_lowercase = w.lower()
                    check = spelling.suggest(word_lowercase)
            corrected = check[0][0]
            if w.isupper():
                corrected = corrected.upper()
            elif w.istitle():
                corrected = corrected.title()
            if mode == "correct":
                text_corrected += separator + corrected
                if len(list(spelling._known([w.lower()]))) == 0 and check[0][1] > -1:
                    self.words_corrected.append(
                        [w, True if check[0][1]>0 else False, 
                        corrected if check[0][1]>0 else "", 
                        check[0][1] if check[0][1]>0 else ""]
                    )
            elif mode == "remove":
                if self.args["autocorrect"]:
                    if check[0][1] > 0 or check[0][1] == -1:
                        text_corrected += separator + corrected
                else:
                    if len(list(spelling._known([w.lower()]))) != 0 or check[0][1] == -1:
                        text_corrected += separator + corrected
            
        return text_corrected.strip()

    def corrections(self):
        with open(self.corrections_path, "a+", newline='') as output_file:
            output_csv_writer = csv.writer(output_file, dialect='excel')
            output_csv_writer.writerows(self.words_corrected)

    # Get the text from a single page
    def read_page(self, page):
        # try to extract text
        if self.args["thorough"]:
            text = self.thorough_page(page)
        else:
            text = page.getText()

            if len(text) < 1:   # OCR the page if there is no text or if forced
                if self.args["accelerated"]:  # Skip if Accelerated option active
                    self.skipped_pages = True
                else:
                    text = self.ocr_page(page)
                    if self.file_method == "text":    # If this is the first OCR page, tell the user what's going on
                        self.dialog("ocr")
                    self.file_method = "ocr" # Once one page is OCR, change the file method to OCR
        text = self.clean_text(text) # Pass text through text cleaning processes
        return text

    def thorough_page(self,page):
        if self.file_method == "text":    # If this is the first OCR page, tell the user what's going on
            self.dialog("ocr")
        self.file_method = "ocr" # Once one page is OCR, change the file method to OCR
        blocks = page.getText("dict", 0)["blocks"]
        img_list = page.getImageList(full=True)
        for i in img_list:
            img_bbox = page.getImageBbox(i)
            self.tem_image_path()
            img_dict = self.pdf.extractImage(i[0])
            img = os.path.join(self.img_path,"{}.{}".format(i[0], img_dict["ext"]))
            img_out = open(img, "wb")
            img_out.write(img_dict["image"])
            img_out.close()
            img_text = self.ocr(img)
            if len(img_text) > 0 :
                blocks.append(
                    {"type": 1, "bbox": img_bbox, "lines": 
                        [{"bbox":img_bbox, "spans": 
                            [{"bbox": img_bbox, "text":img_text}]
                        }]
                    }
                )
        try:
            rmtree(self.img_path)
        except:
            pass
        spans = list()
        for block in blocks:
            for line in block["lines"]:
                for span in line["spans"]:
                    spans.append({"bbox":span["bbox"], "text":span["text"]})
        text = ""
        for s in spans:
            text += s["text"]
        return text
   
    def tem_image_path(self):
        # Create a temporary folder for the images used in OCR
        self.img_path = os.path.join(self.homepath,"tempImages")
        try:
            os.mkdir(self.img_path)
        except:
            pass

    # Read a page using OCR
    def ocr_page(self, page):
        self.tem_image_path()
        zoom_matrix = fitz.Matrix(3.2,3.2)   # Set the optimal settings for OCR-readable images
        pix = page.getPixmap(matrix=zoom_matrix, colorspace=fitz.csGRAY, alpha=True) # Generate pixmap from PDF page
        img = os.path.join(self.img_path,"page-%i.png" % page.number) # find image in pixmap
        pix.writePNG(img)   # Grab image and save it
        
        text = self.ocr(img)

        rmtree(self.img_path) # Delete the temp folder for the pics
                
        return text
    
    # Use tesseract to get text via OCR
    def ocr(self, img):
        try:
            text = pytesseract.image_to_string(img, lang="eng", config="--psm 1")
        except:
            print(("\rSorry! There appears to be an issue with your Tesseract OCR installation. "
            "Please refer to the instruction manual for more details."))
            text = ""
        return text

    # create a frequency report
    def report(self):
        stats = {}
        # Clean the text for analysis
        blob = TextBlob(self.report_text)
        wordlist = blob.words.lower()
        text = " ".join(wordlist)
        
        text = self.edit_words(text, "report")

        blob = TextBlob(text)
        pos_list = blob.tags

        # Add words to the dictionary with a count of 1 or add one to count if word already counted
        for w in pos_list:
            if self.args["report_pos"]:
                word = w
            else:
                word = w[0]
            if word in stats:
                stats[word] += 1
            else:
                stats[word] = 1

        # get count of all words
        count = 0
        for c in stats.items():
            count += c[1]

        # sort stats alphabetically
        stats_sorted = [
            (word,count) for (word, count) in 
            sorted(stats.items(),reverse= True, key=lambda x: x[1])
        ]

        # trim words included based on the Report Limit argument
        stats_trimmed = {}

        # get limit from arg, only numbers and %
        limit = re.sub(r"[^0-9%]", "", self.args["report_limit"])

        # default to 100% if input doesn't make sense
        if len(limit) < 1 or ("%" in limit and len(limit) < 2):
            limit = "100%"

        # get top percentile if % is present
        if "%" in limit:
            percentile = int(re.sub(r"[^0-9]", "", limit))

            # calculate percentile cutoff
            if percentile > 100:
                percentile = 100
            cieling  = math.ceil((percentile/100) * count)

            # cutoff after instances have reached cutoff
            counter = 0
            for w in stats_sorted:
                counter += w[1]
                if counter <= cieling or counter == w[1]:
                    stats_trimmed[w[0]]=w[1]            
        
        # if not a percentile, return top x words 
        else:
            cieling = int(re.sub(r"[^0-9]", "", limit))
            for w in stats_sorted:
                if w[1] >= cieling:
                    stats_trimmed[w[0]]=w[1]

        stats_final = list()

        # Sort words by frequency if Report Sort arg active, alphabetically if not
        if not self.args["report_sort"]:
            stats_final = [
                (word[0],word[1], count) if type(word) is tuple 
                else (word, count) for (word,count) in sorted(stats_trimmed.items())
            ]
        else:
            stats_final = stats_trimmed.items()

        # Write FR to file
        with open(self.report_path, "a", newline='') as output_file:
            output_csv_writer = csv.writer(output_file, dialect='excel')

            # Source changes based on if it is split or not
            if self.args["report"] and not self.args["split"]:
                src = self.input_filepath
            else:
                src = self.filename
            
            # Header
            output_csv_writer.writerow(["Frequency Report of all words processed from {}".format(src)])  

            # Secondary header if reporting by each page 
            if self.args["report_page"]:
                output_csv_writer.writerow(["{} page {}/{}".format(
                    self.filename, 
                    self.page_num+1, 
                    len(self.pdf))]
                )
            
            # Column headers
            headers = ["Word","Instances"]
            if self.args["report_pos"]:
                headers.insert(1,"POS")
            output_csv_writer.writerow(headers)

            # Write output
            for w in stats_final:
                output_csv_writer.writerow(w)
        
        # Reset report text
        self.report_text = ""

    # Edit the text for the Ignore or Only options of either the Report or Process functions
    def edit_words(self, text, purpose):
        stopwords_path = os.path.join(self.homepath, "options", "StopWords.txt")
        report_ignore_path = os.path.join(self.homepath, "options", "ReportIgnore.txt")
        report_only_path = os.path.join(self.homepath, "options", "ReportOnly.txt")
        process_ignore_path = os.path.join(self.homepath, "options", "ProcessIgnore.txt")
        process_only_path = os.path.join(self.homepath, "options", "ProcessOnly.txt")
        if purpose == "report":
            ignore_path = report_ignore_path
            only_path = report_only_path
            ignore_list = self.args["report_ignore"]
            only_list = self.args["report_only"]
        elif purpose == "process":
            ignore_path = process_ignore_path
            only_path = process_only_path
            ignore_list = self.args["process_ignore"]
            only_list = self.args["process_only"]

        # Remove all but specified words if Report Only arg is used
        if only_list is not None:
            # If no words given, pull from file
            if len(only_list) < 1:
                only_list.append(only_path)
            
            # Turn strings from CL or file into regex patterns
            patterns = self.get_pattern(only_list)
            text_old = text
            text = ""
            # Only include specified words
            for pattern in patterns:
                matches  = re.findall(r"\b{}\b".format(pattern), text_old, flags=re.IGNORECASE)
                for match in matches:
                    text += match + " "

        # Remove specified words if Report Ignore arg is used
        if ignore_list is not None:

            # If no words given, pull from file
            if len(ignore_list) < 1:
                with open(ignore_path, "r") as f:
                    if len([line for line in f if line[0] !="#"]) == 0:
                        ignore_list = [stopwords_path] 
                    else:
                        ignore_list = [ignore_path]
    

            # Turn strings from CL or file into regex patterns
            patterns = self.get_pattern(ignore_list)

            # Remove specified words
            for pattern in patterns:
                text = re.sub(r"\b{}\b".format(pattern), "", text, flags=re.IGNORECASE)

        text = re.sub(r"\s\s+", " ", text) # Fix double spaces

        return text

    # Convert list of strings to regex patterns
    def get_pattern(self, patternList):

        # If there is a file name, get the list from the custom file source
        if os.path.isfile(patternList[0]):
                with open(patternList[0], "r") as reportOnlyFile:
                    patterns = [pattern.strip().lower() for pattern in reportOnlyFile if pattern[0] != "#"]
        else:
            patterns = [pattern.lower() for pattern in patternList]

        # Catchall pattern if none specified
        if len(patterns) < 1:
            patterns.append(r"\w*")

        return patterns

    # Strip unneceesary whitespace
    def strip_whitespace(self, text):
        text_new = ""
        for c in text.group(0):
            if not re.match(r"\s", c):
                text_new += c
        text_new += " "
        return text_new

    # Process text to format it to be human-readable on one CSV line and fix common OCR errors
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
        text_clean = re.sub(r"(?i)\bt\s?h\s?e\b", lambda x: x.group(0)[0]+"he", text_clean)
        text_clean = re.sub(r"\ba\s?n\s?d\b", lambda x: x.group(0)[0]+"nd", text_clean)

        # remove leading and trailing spaces
        text_clean = text_clean.strip()

        return text_clean

    def lemmatize(self, text):
        blob = TextBlob(text)
        text = ""
        for w in re.sub(r"\n", " ", blob.parse()).split(" "):
            if w.split("/")[1][:2] == "JJ":
                pos = 'a'
            elif "RB" in w.split("/")[1]:
                pos = 'r'
            elif w.split("/")[1][:2] == "VB":
                pos = 'v'
            else:
                pos = 'n'
            text += "{}".format(" " if True in [True if c.isalnum() else False for c in w.split("/")[0]] else "") + Word(w.split("/")[0]).lemmatize(pos) 
        return text.strip()     

    # Various dialogues to keep the user informed of progress
    def dialog(self, stage):

        # Only show beginning and ending dialog if it is a dir (otherwise the file beginning and ending dialoge is enough)
        if self.input_type == "dir":

            # Determine plural ending
            if len(self.path_list) == 1:
                plural = ""
            else:
                plural = "s"
            
            if stage == "start":    # Starting dialogue
                if not self.args["quiet"]:
                    print("Processing all PDF files in folder {} ({} File{})".format(
                        self.input_filepath, 
                        len(self.path_list), plural
                    ))
                self.dirTimeStart = time.perf_counter() # Record starting time
            elif stage == "end":    # Ending dialogue
                dirTimeEnd = time.perf_counter()   # Record ending time
                dir_time = round(dirTimeEnd-self.dirTimeStart, 3)  # Calculate processing time
                if not self.args["quiet"]:
                    print()
                    if not self.args["split"]:
                        print(
                            ("The file {} contains all of the text extracted "
                            "from from all PDF files in {}.").format(
                                self.output_path, 
                                self.input_filepath
                            )
                        )
                        if (self.args["report"] or 
                            self.args["report_file"] or 
                            self.args["report_page"]):
                            print(
                                ("The file {} contains a frequency report "
                                "of all words processed.").format(self.report_path))
                    else:
                        print(
                            ("Each file in {} has breen processed and "
                            "the extracted text is contained in the "
                            "accompanying CSV file.").format(self.input_filepath)
                        )
                        if (self.args["report"] or 
                            self.args["report_file"] or 
                            self.args["report_page"]):
                            print(
                                ("Each file also contains an accompanying "
                                "CSV file with a frequency report of each word processed.")
                            )
                    print(
                        ("{} file{} ({} words) were processed in {} seconds. "
                        "That is an average of {} seconds/file").format(
                            len(self.path_list), 
                            plural, 
                            self.complete_wordcount, 
                            dir_time, 
                            round(dir_time/len(self.path_list),3)
                        )
                    )
        
        if stage[:4] == "file":    # The dialog relates to the processing of the file
            if len(self.pdf) == 1:  # Determine plural ending
                plural = ""
            else:
                plural = "s"
            if stage == "fileStart":    # File start dialogue
                if not self.args["quiet"]:
                    print ()
                    print("Processing {} ({} page{})".format(self.filename,len(self.pdf),plural))
                    if not self.args["verbose"]:
                        print("Progress: 0%|", end="", flush=True)  # Set up progress bar
                self.fileStartTime = time.perf_counter()    # Record file start time
            elif stage == "fileEnd":    # File completed dialogue
                fileEndTime = time.perf_counter()   # Record file end time
                fileTime = round(fileEndTime - self.fileStartTime, 3)
                if len(self.args["pages"]) > 0:
                    pagesProcessed = len(self.args["pages"])
                else:
                    pagesProcessed = len(self.pdf)
                if not self.args["quiet"] or self.input_type != "dir":
                    print(
                        "Completed {} in {} seconds ({} page{}, {} words, {} seconds/page)".format(
                            self.filename, 
                            fileTime, 
                            pagesProcessed, 
                            plural, 
                            self.wordcount_total, 
                            round(fileTime/pagesProcessed,3)
                        )
                    )
                if self.skipped_pages and not self.args["quiet"]:
                    if self.args["accelerated"]:
                        reason = "Accellerated Mode"
                    if len(self.args["pages"]) > 0:
                        reason = "to only process certain pages"
                    print(
                        ("Some pages were skipped because you chose {}. "
                        "See Guide for details.").format(reason)
                    )
       
        if not self.args["quiet"]:
            if stage == "ocr":  # Explain to the user that we are now dealing with OCR and why
                if self.args["thorough"]:
                    reason = "Thorough Mode has been chosen, see Guide for details."
                else:
                    reason = "it contains non-machine readable text."
                print(
                    ("\rThis file is being processed with OCR because {} "
                    "\n(This may take a few seconds per page)").format(reason)
                )

            if stage[:4] == "page":
                if self.page_num >= self.percent:    # If we passed the next percentage marker, set a new one
                    self.percent = self.percent + self.fivePercent
                if self.file_method == "ocr" or self.args["verbose"]:    # Because OCR takes longer, give an update of time and words after each page
                    if self.args["verbose"]:
                        lead = ""
                        rtn = "\n"
                    else:
                        lead = "\r"
                        rtn = ""
                    if len(stage) == 4:
                        print(
                            "{}Read {} words from page {}/{} in {} seconds        ".format(
                                lead,
                                self.wordcount_page, 
                                self.page_num+1, 
                                len(self.pdf), 
                                round(time.perf_counter()-self.page_start,3)
                            ), 
                            end=rtn, 
                            flush=True
                        )
                    else:
                        print(
                            "{}Page {}/{} skipped as it was not among those specified.    ".format(
                                lead, 
                                self.page_num+1, 
                                len(self.pdf)
                            ), 
                            end=rtn, 
                            flush=True
                        )
                else:   # For text, just update the progress bar
                    if self.page_num >= self.percent:    # If we passed the next percentage marker, print a marker set a new one
                        print("=", end="", flush=True)
                        self.percent = self.percent + self.fivePercent
                if self.page_num+1 == len(self.pdf) and not self.args["verbose"]: # If we are at the end of the file, ensure there is a full progress bar
                    print("\rProgress: 0%|====================|100%                ")

    # Error dialog
    def error_found(self, e):
        print("Sorry! There's been a problem. {} and try again.".format(e.strerror))



if __name__ == "__main__":
    test = PDFtoCSV()
    test.run()