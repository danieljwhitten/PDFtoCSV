from textblob.en import Spelling
import requests
import re
import argparse
import unidecode
import os
from collections import Counter

class BuildDict:    
    
    customSourcePath = os.path.join("options", "CustomSource.txt")
    customDictPath = os.path.join("options", "CustomDictionary.txt")
    refDictPath = os.path.join("options","Dictionary.txt")

    def __init__(self):
        if __name__ == "__main__":
            self.arguments()
            if self.args.train:
                self.get(self.args.train)
                self.train(self.customSourcePath)
                self.merge(self.customDictPath,self.refDictPath)
            elif self.args.build:
                self.train(self.args.build)
            elif self.args.merge:
                self.merge(self.args.merge,self.refDictPath)
            elif self.args.shrink:
                self.shrink(self.args.shrink, 1)
    
    def arguments(self):
        parser = argparse.ArgumentParser()
        functionGroup = parser.add_mutually_exclusive_group()
        functionGroup.add_argument("-t", "--train", help="Enter the title of the main Wikipedia pages realted the topics of your specialized dictionary. For pages with multiple words in the title, use underscores (_) instead of spaces. Separate multiple articles with a single space between each. Eg. '-t Nigeria Economics Communism'.", nargs="+")
        functionGroup.add_argument("-b", "--build", help="Create a custom dictionary using a text file on your computer. Enter the full path to the text file in quotations. You must run the program again with the 'Merge' option to combine this custom dictionary with the entries from the standard dictionary. If you ran the 'Train' option and it crashed/stopped before creating a dictionary, run this option without specifying a file, and then run 'Merge' without specifying a file.", nargs="?", const=self.customSourcePath, default=False)
        functionGroup.add_argument("-m", "--merge", help="Combine a custom dictionary with the standard dictionary for the autocorrect function of PDFtoCSV. Enter the full path to the dictionary file in quotations. Dictionary must be in the format 'word count' on each line with no headers. If you ran the 'Train' option and it crashed/stopped before creating a dictionary, run the 'Build' option first without specifying a file, and then run this option without specifying a file.", nargs="?", const=self.customDictPath, default=False)
        functionGroup.add_argument("-s", "--shrink", help="For more effiency, remove all words from your dictionary that only occured once in the source text. By default, this will shrink the default custom dictionary. If you wish to shrink a custom dictionary, enter the full path to the dictionary file in quotations. Dictionary must be in the format 'word count' on each line with no headers.", nargs="?", const=self.customDictPath, default=False)
        
        self.args = parser.parse_args()

    def get(self, terms):
        print("Gathering text and links from Wikipedia pages for: ", end="")
        print(*terms, sep=", ")
        rootPage = self.getPage(terms,False)
        allLinks = list()
        with open(self.customSourcePath, "w") as f:
            for title, content in rootPage.items():
                f.write(content[0])
                for l in content[1]:
                    allLinks.append(l)

        print("Gathered links to {} related Wikipedia pages.".format(len(allLinks)))
        for i in range((len(allLinks)//25)+1):
            start =  i * 25
            if start < 0:
                start = 0
            end = (i+1) * 25
            if end >= len(allLinks)-1:
                end = len(allLinks)-1
            print("\rGathering text from pages {} to {} of {} total Wikipedia pages.".format(start+1, end+1, len(allLinks)), end="", flush=True)
            childPages = self.getPage(allLinks[start:end],False)
            with open(self.customSourcePath, "a+") as f:
                for title, content in childPages.items():
                    f.write(content[0])
        print()

    def train(self, sourcePath):
        with open(sourcePath, "r") as f:
            trainText = f.read()
        print("Building custom dictionary using {:,} total words gathered from Wikipedia.".format(len(trainText.split())))
        Spelling.train(trainText, path=self.customDictPath)
        if sourcePath == self.customSourcePath:
            os.remove(self.customSourcePath)
    
    def getPage(self, terms, redirect):
        processedPages = dict()

        requestURL = "https://en.wikipedia.org/w/index.php?title=Special:Export&pages="
        for term in terms:
            requestURL += re.sub(r" ", "_", term)
            requestURL += "%0A"
        requestURL = requestURL[:-3] + "&curonly=true&action=submit"
        try:
            req = requests.get(requestURL, timeout=3.05)
        except:
            try:
                req = requests.get(requestURL, timeout=3.05)
            except:
                return {"":["",[]]}
        rawXML = req.text
        pages = self.parsePages(rawXML)
        for page in pages.items():
            title = page[0]
            text = page[1]
            linkMatches = re.finditer(r"\[\[(?P<link>.*?)\]\]", text)
            links = [re.sub(r"[\|#].*","",l.group("link")) for l in linkMatches if ":" not in l.group("link")]
            body = re.sub(r"\s+", " ", re.sub(r"(&lt;ref.*?&lt;/ref&gt;)|(\{\{.*?\}\})|(\[\[.*?\]\])|(\{.*?\})|(\[.*?\])|(==+.*?==+)|(&lt;.*?&gt;)|(&.*?;)|(\b\w*?_\w*?\b)|[\W\d]", " ", text, flags=re.DOTALL)).strip()
            if body == "REDIRECT" and not redirect:
                if len(links) > 0:
                    redirected = self.getPage([links[0]],True)
                    k = list(redirected.keys())
                    if len(k) > 0:
                        processedPages[k[0]] = redirected[k[0]]
            else:
                processedPages[title] = [body,links]
        return processedPages

    def parsePages(self, xml):
        pages = re.findall(r"<page>.*?</page>",xml,flags=re.DOTALL)
        pageList = [re.search(r"<title>(?P<title>.*?)</title>.*?<text.*?>(?P<text>.*?)</text>", page, flags=re.DOTALL) for page in pages]
        return {page.group("title"):page.group("text").strip() for page in pageList}

    def merge(self, dictPath, refDictPath):
        if os.path.exists(dictPath):
            with open(dictPath, "r") as f:
                customDict = {line.split()[0]:int(line.split()[1]) for line in f}
        else:
            with open(self.refDictPath, "r") as f:
                customDict = {line.split()[0]:int(line.split()[1]) for line in f}
        if os.path.exists(refDictPath):
            with open(refDictPath, "r") as f:
                refDict = {line.split()[0]:int(line.split()[1]) if len(line.split()) == 2 and line.split()[1].isdigit() else 1 for line in f}
        else:
            refDict = {w:refDictPath.count(w) for w in refDictPath.split()}
        newDict = dict(Counter(customDict) + Counter(refDict))
        print("Merged {:,} unique words with {:,} unique words in the existing dictionary for a new dictionary of {:,} unique words.".format(len(customDict), len(refDict), len(newDict)))
        print("New custom dictionary is saved at {}.".format(os.path.abspath(dictPath)))
        dictList = ["{} {}\n".format(k,newDict[k]) for k in iter(newDict)]
        with open(dictPath, "w") as f:
            f.writelines(dictList)

    def shrink(self, dictPath, limit):
        print("Shrinking {}".format(dictPath))
        with open(dictPath, "r") as f:
            bigDict = {line.split()[0]:int(line.split()[1]) for line in f}
        smallDict = ["{} {}\n".format(k,bigDict[k]) for k in iter(bigDict) if bigDict[k] > limit]
        print("Dictionary has been shrunk {:.2%} from original size of {:,} unique words to new size of {:,} unique words.".format(1-(len(smallDict)/len(bigDict)), len(bigDict), len(smallDict)))
        with open(dictPath, "w+") as f:
            f.writelines(smallDict)

    def remove(self, dictPath, wordsSource):
        if os.path.exists(dictPath):
            with open(dictPath, "r") as f:
                customDict = {line.split()[0]:int(line.split()[1]) for line in f}
        else:
            with open(self.refDictPath, "r") as f:
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
        print("Successfully removed {:,} words from custom dictionary, {:,} words remaining.".format(len(words), len(customDict)))
        
        
test = BuildDict()
