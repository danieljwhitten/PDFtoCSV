#!/usr/bin/env python3.7

import csv
from pip._internal import main as pipmain
pipmain(['install', "unidecode"])
import unidecode
import re
import time
from multiprocessing import Pool

# specify the files to process
inputFiles = ["DT 2012-2", "DT 2012-3", "DT 2012-4", "DT 2012-5","DT 2012-6", "DT 2012-7", "DT 2012-8", "DT 2012-9", "DT 2012-10", "DT 2012-11", "DT 2012-12",
	"DT 2013-2", "DT 2013-3", "DT 2013-4", "DT 2013-5","DT 2013-6", "DT 2013-7", "DT 2013-8", "DT 2013-9", "DT 2013-10", "DT 2013-11", "DT 2013-12",
	"DT 2014-2", "DT 2014-3", "DT 2014-4", "DT 2014-5","DT 2014-6", "DT 2014-7", "DT 2014-8", "DT 2014-9", "DT 2014-10", "DT 2014-11", "DT 2014-12",
	"DT 2015-2", "DT 2015-3", "DT 2015-4", "DT 2015-5","DT 2015-6", "DT 2015-7", "DT 2015-8", "DT 2015-9", "DT 2015-10", "DT 2015-11", "DT 2015-12",
	"DT 2016-2", "DT 2016-3", "DT 2016-4", "DT 2016-5","DT 2016-6", "DT 2016-7", "DT 2016-8", "DT 2016-9", "DT 2016-10", "DT 2016-11", "DT 2016-12",
	"DT 2017-2", "DT 2017-3", "DT 2017-4", "DT 2017-5","DT 2017-6", "DT 2017-7", "DT 2017-8", "DT 2017-9", "DT 2017-10", "DT 2017-11", "DT 2017-12",
	"Guardian 2015-1", "Guardian 2015-2", "Guardian 2015-3", "Guardian 2015-4", "Guardian 2015-5", "Guardian 2015-6", "Guardian 2015-7", "Guardian 2015-8", "Guardian 2015-9", "Guardian 2015-10", "Guardian 2015-11", "Guardian 2015-12",
	"Guardian 2016-1", "Guardian 2016-2", "Guardian 2016-3", "Guardian 2016-4", "Guardian 2016-5", "Guardian 2016-6", "Guardian 2016-7", "Guardian 2016-8", "Guardian 2016-9", "Guardian 2016-10", "Guardian 2016-11", "Guardian 2016-12", 
	"Guardian 2017-1", "Guardian 2017-2", "Guardian 2017-3", "Guardian 2017-4", "Guardian 2017-5", "Guardian 2017-6", "Guardian 2017-7", "Guardian 2017-8", "Guardian 2017-9", "Guardian 2017-10", "Guardian 2017-11", "Guardian 2017-12",
	"Guardian 2018-1", "Guardian 2018-2", "Guardian 2018-3", "Guardian 2018-4", "Guardian 2018-5", "Guardian 2018-6", "Guardian 2018-7", "Guardian 2018-8", "Guardian 2018-9", "Guardian 2018-10", "Guardian 2018-11", "Guardian 2018-12"]	
inputFileName = ""

# Time tracking
fileTime = []
pageTime = []

# Strip the input to be processed
def stripRaw(rawLine):
	
	# Strip accents
	unaccented = unidecode.unidecode(rawLine)
	
	# make all hyphens and apostrophes the same
	apostropheFix = re.sub(r"[‘’‚‛′`']", r"'", rawLine) 

	# make all chars lowercase
	lowercase = apostropheFix.lower()
	
	# remove all non alphanum chars, except ' - and spaces
	stripped = re.sub(r"[^a-z0-9' ]", r"", lowercase)
	
	# remove multiple spaces
	for i in range(5):
		stripped = re.sub(r"  ", r" ", stripped)

	# return stripped line
	return stripped

# add an array of strings together into one string
def concat(words):
	con = ""
	for word in words:
		con += word
	return con

# Check to see if the word is in the dictionary, if not, check combinations with words before and after	
def checkWords(words):
	
	prev = ""
	current = ""
	next = ""
	concatStart = 0
	concatEnd = 2
	
	# Lookup word
	if lookupWord(words[1]):
		prev = "+"
		current = words[1]
		next = "+"
	# Lookup combos 
	else:
		for i in range(2):
			if lookupWord(concat(words[concatStart:3])):
				concatEnd = 3
				break
			else:
				if lookupWord(concat(words[concatStart:2])):
					concatEnd = 2
					break
				else:
					if concatStart > 0:
						# if the word doesn't contain a number, report it to the missing words log
						if not re.search(r"[0-9]",words[1]):
							reportWords(words)
					else:
						concatStart += 1
						
		# determine whether to keep (+) or skip (*) previous words, depending on whether or not they are incorporated into a new word
		current = concat(words[concatStart:concatEnd])
		if concatStart == 0:
			prev = "*"
		else:
			prev = "+"
		if concatEnd == 3:
			next = "*"
		else:
			next = "+"
	
	# return the current word with the indicators for previous and next
	return [prev, current, next]
	
# is this word in the dictionary	
def lookupWord(word):

	#open the dictionary for that letter
	wordCounter = 0
	#if the word contain non-letters, it won't be in the dictionary
	if re.search(r"[0-9]", word) or not re.search(r"[a-z]", word):
		found = False
	else:
		#handle if the first letter is non-alpha
		while not re.match(r"[a-z]",word[wordCounter]):
			wordCounter += 1
		first = word[wordCounter]
		if len(word[wordCounter:]) == 1 or (len(word[wordCounter:]) > 1 and not re.match(r"[a-z]", word[wordCounter+1])):
			second = "_"
		else:
			second = word[wordCounter+1]
		#get a wordlist from the dictionary
		try:
			with open("../Dictionary/dict-" + first + second + ".txt", "r") as dictFile:
				wordList = []		
				for line in dictFile:
					wordList.append(re.sub(r"\n", r"", line))
				dictFile.close()
		except:
			wordList = []
			
		# check if the word is in the dictionary
		found = word in wordList
		wordList = []
	
	return found
		

#report words that are not in the dictionary so we can see if there are any patterns that need to be added
def reportWords(words):
	# append to report csv, main word, followed by previous and next words for context
	with open("../Active/Clean/Stripped/Reports/unknownWords.csv", "a+") as reportFile:
		reportWriter = csv.writer(reportFile, delimiter = ",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
		reportWriter.writerow([words[1],words[0],words[2]])
	reportFile.close()
	
# Write the clean row to the new file	
def writeCleanRow(cleanLine):
	with open("../Active/Clean/Stripped/Output/" + inputFileName + " (stripped).csv", "a+") as csvOutput:
		csvOutputWriter = csv.writer(csvOutput, delimiter = ",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
		csvOutputWriter.writerow(cleanLine)
	csvOutput.close()

def processRow(row):
	pageTimeStart = round(time.perf_counter(), 4)
	
	# set aside everything besides the text cell (varying number of columns between DT and G)
	nonText = []
	nonText.append(row[0])
	for cell in row[-4:len(row)]:
		nonText.append(cell)

	# set aside the text
	inputText = row[1]

	# strip the text so that it's just alphanum, internal punctuation and spaces
	strippedText = stripRaw(inputText)

	# split the text into words
	words = strippedText.split()
	
	# Set defaults
	cleanText = ""
	wordCount = 0
	prevWord = ""
	skipNext = False
	
	wordTime = []
	
	#process each word
	for currentWord in words:
	
		wordTimeStart = round(time.perf_counter(),4)
						
		# If this word was incorporated into the previous word, skip it
		if skipNext:
			skipNext = False
		else:
			# Get the next word
			# if its the last word, next word is null
			if wordCount + 2 > len(words):
				nextWord = ""
			else:
				nextWord = words[wordCount+1]
			# array with previous word, current word, next word
			wordsToCheck = [prevWord, currentWord, nextWord]
			# Check the words and combos against the dictionary
			checkedWords = checkWords(wordsToCheck)
	
			# If required, add the previous word
			if checkedWords[0] == "+":
				cleanText += " " + prevWord
	
			# New previous word is the current word or combo
			prevWord = checkedWords[1]
	
			# Do we need to skip the next word, because it was combined with the current?
			skipNext = checkedWords[2] == "*"
			
			# If it's the last word, add it
			if wordCount + 2 >len(words):
				cleanText += currentWord + " "
			
		wordTimeEnd = round(time.perf_counter(),4)
		wordTime.append(round(wordTimeEnd - wordTimeStart,4))
			
	
	
	#rebuild clean row
	cleanRow = []
	cleanRow.append(nonText[0])
	cleanRow.append(cleanText)
	for cell in nonText[1:len(nonText)]:
		cleanRow.append(cell)

	pageTimeEnd = round(time.perf_counter(),4)
	pageTime.append(round(pageTimeEnd - pageTimeStart,4))
	
	#finish progress tracker
	print("Completed " + str(row[-3]) + "-" + str(row[-2]) + "-" + str(row[-1]) + ": page " + str(row[-4]))
	print("Words:		" + str(len(words)))
	print("Seconds:	" + str(round(pageTimeEnd-pageTimeStart,4)))
	try:
		avgWord = str(round(sum(wordTime)/len(wordTime),4))
	except:
		avgWord = "Error"
	print("Avg/word:	" + avgWord + " seconds")
	try:
		avgPage = str(round(sum(pageTime)/len(pageTime),4))
	except:
		avgPage = "Error"	
	print("Avg/page:	" + avgPage + " seconds ")
	print()	
	
	#write new line to output
	return cleanRow

# process all the words in a file
def processFile():
	# Open input file with raw data
	with open("../Active/Clean/Stripped/Input/" + inputFileName + ".csv", "r") as csvInput:
		csvInputReader = csv.reader(csvInput, delimiter=",", quotechar='"')
		
		#create output file 
		with open("../Active/Clean/Stripped/Output/" + inputFileName + " (stripped).csv", "w") as outputFile:
			csvOutputWriter = csv.writer(outputFile, delimiter = ",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
			csvOutputWriter.writerow(["Page", "Words","Page Number","Day","Month","Year"])
		outputFile.close()
		
				
		# Create 4 processes to process the rows
		with Pool(processes=4) as pool:
			rowsForOutput = pool.map(processRow, csvInputReader)
	
		# Output the collected results
		for row in rowsForOutput:
			writeCleanRow(row)
			print(str(row[0]) + " written to file.")
			
# run the program for every file specified
for fileName in inputFiles:
	inputFileName = fileName
	print("Now processing " + fileName + ".csv")
	fileTimeStart = round(time.perf_counter(),4)
	processFile()
	fileTimeEnd = round(time.perf_counter(),4)
	fileTime.append(round(fileTimeEnd - fileTimeStart,4))
	print("Finished processing " + fileName + " in " + str(round(fileTimeEnd-fileTimeStart,4)) + " seconds. Average is " + str(round(sum(fileTime)/len(fileTime),4)) + " seconds.")
		
		
		
		
		
		
	
	
	