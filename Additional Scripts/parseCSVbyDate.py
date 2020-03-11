#!/usr/bin/env python3.7

import csv

inputFileName = "DT 2014"
outputFileName = "DT 2014 (clean)"
newYearsDay = "Wednesday"
year = 2014


weekDays = ["Monday","Tuesday", "Wednesday", "Thursday","Friday","Saturday","Sunday"]
monthsOfTheYear = tuple(("January", "February", "March", "April","May", "June", "July", "August", "September", "October", "November", "December"))


inRows = []
outRows = []
with open("../Active/Raw/" + inputFileName + ".csv") as csvRawData:
	csvReader = csv.reader(csvRawData, delimiter="|")
	for row in csvReader:
		if row[0] != "":
#			pull page, text, source
			inRows.append([row[2],row[3],row[4]])
day = weekDays.index(newYearsDay)
date = 1
month = 1
page = 0
dateStart = 0
dateFound = False
dayPages = []

with open("../Active/Clean/" +inputFileName + " (clean).csv", "w") as csvCleanData:
	csvWriter = csv.writer(csvCleanData, delimiter = ",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
	csvWriter.writerow(["Page", "Text",  "Page Number", "Day", "Month", "Year"])
	for row in inRows:
		if day == 6:
			tomorrow = 0
		else:
			tomorrow = day+1
		page += 1
		rowText = row[1]
#		if it is the header or footer		
		if "Vol." in rowText:
#			if tomorrow's day is on the page			
			if weekDays[tomorrow] in rowText:
				textDay = weekDays[tomorrow]
				dayPos = rowText.find(textDay)
# 				Get month
				shortMonth = rowText[dayPos + len(textDay): dayPos + len(textDay)+5].strip()
				if textDay[0:3] in shortMonth:
					dayPos = rowText.find(textDay,dayPos+1)
					shortMonth = rowText[dayPos + len(textDay): dayPos + len(textDay)+5].strip()
# 				Is it this month or next month?
				if shortMonth in monthsOfTheYear[month-1] or (month != 12 and shortMonth in monthsOfTheYear[month]):
					if shortMonth in monthsOfTheYear[month-1]:
						textMonth = month
					else:
						textMonth = month+1
					monthPos = rowText.find(monthsOfTheYear[textMonth-1],dayPos)
# 					Get date
					textDate = rowText[monthPos + len(monthsOfTheYear[textMonth-1]) : monthPos + len(monthsOfTheYear[textMonth-1])+105].strip()
					print(textDate)
# 					One or two digits
					if date < 9:
						textDate = textDate[0]
					elif date > 27 and textDate[0] == "1" and not textDate[1].isnumeric():
						textDate = textDate[0]
					else:
						textDate = textDate[0:2]
# 					If it is likely tomorrow's date 
					if textDate.isnumeric():
						if int(textDate) == date + 1 or (int(textDate) == 1 and date > 27):
							print("YES")
							dayPages.append([str(date) + "-" + str(month), page-1])
							day = tomorrow
							date = int(textDate)
							month = textMonth
							page = 1
							print(textDay + " " + monthsOfTheYear[textMonth-1] + " " +  textDate)
		csvWriter.writerow([row[0],row[1], row[2], page,date,month,year])		
dayPages.append([str(date) + "-" + str(month), page-1])

with open("../Active/Clean/" +inputFileName + " (count).csv", "w") as csvCountData:
	csvCountWriter = csv.writer(csvCountData, delimiter = ",", quotechar='"', quoting=csv.QUOTE_MINIMAL)
	csvCountWriter.writerow(["Date", "Page Count"])
	for d in dayPages:
		print(d[0] + ": " + str(d[1]))
		csvCountWriter.writerow([d[0], d[1]])	

	
	
		
			
		

		