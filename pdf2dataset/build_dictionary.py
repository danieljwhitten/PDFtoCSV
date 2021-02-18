#     datasets-from-pdfs - Convert single or mass PDFs to datasets
#     Copyright (C) 2021  Daniel Whitten - danieljwhitten@gmail.com

#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.

#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU General Public License for more details.

#     You should have received a copy of the GNU General Public License
#     along with this program.  If not, see <https://www.gnu.org/licenses/>.

from textblob.en import Spelling
import requests
import re
import argparse
import unidecode
import os
from collections import Counter

class BuildDict:    
    
    path_custom_source = os.path.join("options", "CustomSource.txt")
    path_custom_dict = os.path.join("options", "CustomDictionary.txt")
    path_ref_dict = os.path.join("options","Dictionary.txt")

    def __init__(self):
        if __name__ == "__main__":
            self.arguments()
            if self.args.train:
                self.get(self.args.train)
                self.train(self.path_custom_source)
                self.merge(self.path_custom_dict,self.path_ref_dict)
            elif self.args.build:
                self.train(self.args.build)
            elif self.args.merge:
                self.merge(self.args.merge,self.path_ref_dict)
            elif self.args.shrink:
                self.shrink(self.args.shrink, 1)
    
    def arguments(self):
        parser = argparse.ArgumentParser()
        function_group = parser.add_mutually_exclusive_group()
        function_group.add_argument("-t", "--train", 
            help=("Enter the title of the main Wikipedia pages realted the topics "
            "of your specialized dictionary. For pages with multiple words in the title, "
            "use underscores (_) instead of spaces. Separate multiple articles with "
            "a single space between each. Eg. '-t Nigeria Economics Communism'."), 
            nargs="+"
        )
        function_group.add_argument("-b", "--build", 
            help=("Create a custom dictionary using a text file on your computer. "
            "Enter the full path to the text file in quotations. You must run "
            "the program again with the 'Merge' option to combine this custom dictionary "
            "with the entries from the standard dictionary. If you ran the 'Train' option "
            "and it crashed/stopped before creating a dictionary, run this option "
            "without specifying a file, and then run 'Merge' without specifying a file."), 
            nargs="?", 
            const=self.path_custom_source, 
            default=False
        )
        function_group.add_argument("-m", "--merge", 
            help=("Combine a custom dictionary with the standard dictionary for "
            "the autocorrect function of PDFtoCSV. Enter the full path to the "
            "dictionary file in quotations. Dictionary must be in the format "
            "'word count' on each line with no headers. If you ran the 'Train' option "
            "and it crashed/stopped before creating a dictionary, run the 'Build' option "
            "first without specifying a file, and then run this option without specifying a file."), 
            nargs="?", 
            const=self.path_custom_dict, 
            default=False
        )
        function_group.add_argument("-s", "--shrink", 
            help=("For more effiency, remove all words from your dictionary "
            "that only occured once in the source text. By default, this will "
            "shrink the default custom dictionary. If you wish to shrink a "
            "custom dictionary, enter the full path to the dictionary file in quotations. "
            "Dictionary must be in the format 'word number' on each line with no headers."), 
            nargs="?", 
            const=self.path_custom_dict, 
            default=False
        )
        
        self.args = parser.parse_args()

    def get(self, terms):
        print("Gathering text and links from Wikipedia pages for: ", end="")
        print(*terms, sep=", ")
        rootpage = self.get_page(terms,False)
        links_all = list()
        with open(self.path_custom_source, "w") as f:
            for title, content in rootpage.items():
                f.write(content[0])
                for l in content[1]:
                    links_all.append(l)

        print("Gathered links to {} related Wikipedia pages.".format(len(links_all)))
        for i in range((len(links_all)//25)+1):
            start =  i * 25
            if start < 0:
                start = 0
            end = (i+1) * 25
            if end >= len(links_all)-1:
                end = len(links_all)-1
            print(
                "\rGathering text from pages {} to {} of {} total Wikipedia pages.".format(
                    start+1, 
                    end+1, 
                    len(links_all)
                ), 
                end="", 
                flush=True
            )
            child_pages = self.get_page(links_all[start:end],False)
            with open(self.path_custom_source, "a+") as f:
                for title, content in child_pages.items():
                    f.write(content[0])
        print()

    def train(self, path_source):
        with open(path_source, "r") as f:
            text_training = f.read()
        print(
            "Building custom dictionary using {:,} total words gathered from Wikipedia.".format(
                len(text_training.split())
            )
        )
        Spelling.train(text_training, path=self.path_custom_dict)
        if path_source == self.path_custom_source:
            os.remove(self.path_custom_source)
    
    def get_page(self, terms, redirect):
        pages_processed = dict()

        request_url = "https://en.wikipedia.org/w/index.php?title=Special:Export&pages="
        for term in terms:
            request_url += re.sub(r" ", "_", term)
            request_url += "%0A"
        request_url = request_url[:-3] + "&curonly=true&action=submit"
        try:
            req = requests.get(request_url, timeout=3.05)
        except:
            try:
                req = requests.get(request_url, timeout=3.05)
            except:
                return {"":["",[]]}
        rawXML = req.text
        pages = self.parse_pages(rawXML)
        for page in pages.items():
            title = page[0]
            text = page[1]
            linkMatches = re.finditer(r"\[\[(?P<link>.*?)\]\]", text)
            links = [re.sub(r"[\|#].*","",l.group("link")) for l in linkMatches if ":" not in l.group("link")]
            body = re.sub(
                r"\s+", 
                " ", 
                re.sub(
                    (
                        r"(&lt;ref.*?&lt;/ref&gt;)|"
                        r"(\{\{.*?\}\})|"
                        r"(\[\[.*?\]\])|"
                        r"(\{.*?\})|"
                        r"(\[.*?\])|"
                        r"(==+.*?==+)|"
                        r"(&lt;.*?&gt;)|"
                        r"(&.*?;)|"
                        r"(\b\w*?_\w*?\b)|"
                        r"[\W\d]"
                    ), 
                    " ", 
                    text, 
                    flags=re.DOTALL
                )
            ).strip()
            if body == "REDIRECT" and not redirect:
                if len(links) > 0:
                    redirected = self.get_page([links[0]],True)
                    k = list(redirected.keys())
                    if len(k) > 0:
                        pages_processed[k[0]] = redirected[k[0]]
            else:
                pages_processed[title] = [body,links]
        return pages_processed

    def parse_pages(self, xml):
        pages = re.findall(r"<page>.*?</page>",xml,flags=re.DOTALL)
        pageList = [
            re.search(
                r"<title>(?P<title>.*?)</title>.*?<text.*?>(?P<text>.*?)</text>", 
                page, 
                flags=re.DOTALL
            ) for page in pages
        ]
        return {page.group("title"):page.group("text").strip() for page in pageList}

    def merge(self, dictPath, refDictPath):
        if os.path.exists(dictPath):
            with open(dictPath, "r") as f:
                customDict = {line.split()[0]:int(line.split()[1]) for line in f}
        else:
            with open(self.path_ref_dict, "r") as f:
                customDict = {line.split()[0]:int(line.split()[1]) for line in f}
        if os.path.exists(refDictPath):
            with open(refDictPath, "r") as f:
                refDict = {
                    line.split()[0]:int(line.split()[1]) 
                    if len(line.split()) == 2 and line.split()[1].isdigit() 
                    else 1 for line in f
                }
        else:
            refDict = {w:refDictPath.count(w) for w in refDictPath.split()}
        newDict = dict(Counter(customDict) + Counter(refDict))
        print(
            ("Merged {:,} unique words with {:,} unique words in the existing "
            "dictionary for a new dictionary of {:,} unique words.").format(
                len(customDict), 
                len(refDict), 
                len(newDict)
            )
        )
        print("New custom dictionary is saved at {}.".format(os.path.abspath(dictPath)))
        dictList = ["{} {}\n".format(k,newDict[k]) for k in iter(newDict)]
        with open(dictPath, "w") as f:
            f.writelines(dictList)

    def shrink(self, dictPath, limit):
        print("Shrinking {}".format(dictPath))
        with open(dictPath, "r") as f:
            bigDict = {line.split()[0]:int(line.split()[1]) for line in f}
        smallDict = ["{} {}\n".format(k,bigDict[k]) for k in iter(bigDict) if bigDict[k] > limit]
        print(
            ("Dictionary has been shrunk {:.2%} from original size of {:,} "
            "unique words to new size of {:,} unique words.").format(
                1-(len(smallDict)/len(bigDict)), 
                len(bigDict), 
                len(smallDict)
            )
        )
        with open(dictPath, "w+") as f:
            f.writelines(smallDict)

    def remove(self, dictPath, wordsSource):
        if os.path.exists(dictPath):
            with open(dictPath, "r") as f:
                customDict = {line.split()[0]:int(line.split()[1]) for line in f}
        else:
            with open(self.path_ref_dict, "r") as f:
                customDict = {line.split()[0]:int(line.split()[1]) for line in f}
        if os.path.exists(wordsSource):
            with open(wordsSource, "r") as f:
                words = [line.split()[0] for line in f]
        else:
            words = wordsSource.split()
        for w in words:
            if w in customDict:
                del customDict[w]
        dictList = ["{} {}\n".format(k,customDict[k]) for k in iter(customDict)]
        with open(dictPath, "w") as f:
            f.writelines(dictList)
        print(
            ("Successfully removed {:,} words from custom dictionary, "
            "{:,} words remaining.").format(
                len(words), 
                len(customDict)
            )
        )
        
        
test = BuildDict()
