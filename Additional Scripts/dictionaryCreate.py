#!/usr/bin/env python3.7
import csv
import string
import re
import os	



with open("../Dictionary/wordlist_small.csv", "r") as inputFile:
	reader = csv.reader(inputFile, delimiter=",", quotechar='"')
	
	for row in reader:
		word = row[0]
		word = word.lower()
		word = re.sub(r"[^a-z']", "", word)
		first = word[0]
		if len(word) == 1 or (len(word) > 1 and not re.match(r"[a-z]", word[1])):
			second = "_"
		else:
			second = word[1]
		with open("../Dictionary/dict-" + first + second + ".txt", "a+") as f:
			f.write(word+"\n")
			print(".", end="", flush=True)
			