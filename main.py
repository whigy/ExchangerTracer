# -*- coding: utf-8 -*-
"""
Created on Sat Jul  7 13:04:35 2018

@author: whigy
"""

import logging
import time
import os
import pandas as pd
import pickle
import sys

from datetime import date, timedelta, datetime
from selenium import webdriver

logging.basicConfig(stream=sys.stdout, level=logging.INFO)
TIME_FORMAT = "%Y-%m-%d"


def openBrowser(url):
    browser = webdriver.Chrome(executable_path=os.path.join(os.getcwd(), 'chromedriver'))
    time.sleep(3)

    logging.info("Get URL {:s}".format(url))
    browser.get(url)
    logging.info("Brower ready.")
    return browser


def get_exchange(url, currency, startTime=None, endTime=None):
    browser = openBrowser(url)

    logging.info("Parsing BOC Webpage...")
    time.sleep(4)

    ########################## Search ################################
    # Send dates
    def clickCalendar(date):
        d = date.split("-")
        browser.find_element_by_xpath("//select[@id='calendarYear']/option[@value='{:s}']".format(d[0])).click()
        browser.find_element_by_xpath(
            "//select[@id='calendarMonth']/option[@value='{:d}']".format(int(d[1]) - 1)).click()
        browser.find_element_by_xpath("//table[@id='calendarTable']/tbody/tr/td[text()={:d}]".format(int(d[2]))).click()

    # End time
    if endTime == None:
        browser.find_element_by_name("nothing").click()
        browser.find_element_by_name("calendarToday").click()
        endTime = date.today().strftime(TIME_FORMAT)
    else:
        browser.find_element_by_name("nothing").click()
        clickCalendar(endTime)
    logging.info("end time: {}".format(endTime))

    # Start time
    if startTime == None:  # if none: one day before end time
        startTime = (datetime.strptime(endTime, TIME_FORMAT) - timedelta(1)).strftime(TIME_FORMAT)
    logging.info("start time: {}".format(startTime))
    browser.find_element_by_name("erectDate").click()

    clickCalendar(startTime)

    # Send currency
    browser.find_element_by_xpath("//select[@id='pjname']/option[@value='{:s}']".format(currency)).click()
    browser.find_elements_by_class_name("search_btn")[1].click()

    logging.info("Searching {:s} from {:s} to {:s}.....".format(currency, startTime, endTime))

    time.sleep(3)

    ############################ Saving Information #######################################
    # Get pages
    try:
        pageSize = int(browser.find_element_by_class_name("turn_page").find_element_by_tag_name("li").text[1:-1])
    except Exception:
        logging.info("Page size regarded as less then 1.")
        pageSize = 1

    def turnPage(pageSize):
        curr = browser.find_element_by_class_name("turn_page").find_element_by_class_name("current").text
        if int(curr) < pageSize:
            browser.find_element_by_class_name("turn_page").find_elements_by_tag_name("li")[-1].click()
            time.sleep(0.3)
            return True
        else:
            return False

    def findRows():
        def parseRow(row):
            tds = row.find_elements_by_tag_name("td")
            strList = [tds[3].text] + tds[6].text.split(" ") #3: 现汇卖出价; 6: 发布时间
            return ','.join(strList) + '\n'

        rows = browser \
            .find_element_by_class_name("BOC_main") \
            .find_element_by_tag_name("table") \
            .find_elements_by_tag_name("tr")
        rowsText = [parseRow(row) for row in rows[1:-1]]
        return rowsText

    allRows = []
    if pageSize == 1:
        allRows = findRows()
    else:
        tag = True
        while(tag):
            allRows += findRows()
            tag = turnPage(pageSize)

    logging.info("Collected {:d} rows data!".format(len(allRows)))

    header = "out_exc,date,time\n"
    
    # MakeDir 'meta'
    directory = 'meta'
    if not os.path.exists(directory):
        os.makedirs(directory)
    filename = 'meta/{:s}_meta_{:s}.csv'.format(currency, datetime.now().strftime("%Y%m%d_%H%M%S"))
    with open(filename, 'w') as csvfile:
        csvfile.writelines(header)
        csvfile.writelines(allRows)
        csvfile.close()

    return filename


def calculateData(filename, output="output/output.txt"):
    # MakeDir 'output'
    directory = 'output'
    if not os.path.exists(directory):
        os.makedirs(directory)

    with open(filename, 'rb') as file:
        df = pd.read_csv(file)

    histData = 'meta/history.pkl'
    if os.path.exists(histData):
        logging.info("Reading history data from {:s}".format(histData))
        try:
            with open(histData, 'rb') as f:
                data = pickle.load(f)
        except Exception as e:
            print('Unable to load data ', histData, ':', e)
            data = {}
    else:
        "History data not exist! Calculating from scratch!"
        data = {}

    group = df.sort_values(["date", "time"]) \
        .groupby("date")['out_exc'] \
        .aggregate({'opening': lambda x: x.iloc[0],
                    'max': 'max',
                    'min': 'min',
                    'closing': lambda x: x.iloc[-1]})
    data = {**data, **group.T.to_dict()}  # Update history
    with open(histData, 'wb') as f:
        pickle.dump(data, f, pickle.HIGHEST_PROTOCOL)

    updated = pd.DataFrame.from_dict(data).T.reset_index()
    updated["date"] = updated["index"].apply(lambda x: x.replace(".", '/'))

    # read existing csv
    with open(output, 'rb') as file:
        origin = pd.read_csv(file, " ",
            names = ["date", "opening", "max", "min", "closing"])

    origin = origin[origin["date"] < updated['date'].min()]
    updated = origin.append(updated, ignore_index=True)

    updated[["date", "opening", "max", "min", "closing"]]\
        .sort_values("date")\
        .to_csv(output, index=False, header=False, sep=" ")

def readConfig():
    parameters = {}
    try:
        with open("Config.txt", 'r') as f:
            for line in f:
                p = line.strip("\n").split("=")
                parameters[p[0]] = p[1]

    except Exception as e:
        print('Unable to load Configuration!')
        print("""
        Please create 'Congig.txt', with template:
            URL=http://srh.bankofchina.com/search/whpj/search_cn.jsp
            CURRENCY=1320
            START=YESTERDAY
            END=TODAY
        """)
    if parameters["START"] == "YESTERDAY":
        parameters["START"] = (date.today() - timedelta(1)).strftime(TIME_FORMAT)
    if parameters["END"] == "TODAY":
        parameters["END"] = date.today().strftime(TIME_FORMAT)

    return parameters

def readConfig2():
    parameters = {}
    try:
        with open("Config.txt", 'r') as f:
            for line in f:
                p = line.strip("\n").split("=")
                parameters[p[0]] = p[1]

    except Exception as e:
        print('Unable to load Configuration!')
        print("""
        Please create 'Congig.txt', with template:
            URL=http://srh.bankofchina.com/search/whpj/search.jsp
            CURRENCY=瑞典克朗
            START=YESTERDAY
            END=TODAY
        """)

    try:
        with open("./output/output.txt", 'r') as f:
            d = f.readlines()[-1].strip("\n").split(" ")
    except Exception as e:
        logging.info("No output data exist!")
        d = [(date.today() - timedelta(1)).strftime(TIME_FORMAT)]
    if parameters["START"] == "YESTERDAY":
        parameters["START"] = (date.today() - timedelta(1)).strftime(TIME_FORMAT)
    elif parameters["START"] == "AUTO":
        parameters["START"] = d[0].replace("/", "-")
    if parameters["END"] == "TODAY":
        parameters["END"] = date.today().strftime(TIME_FORMAT)

    return parameters

if __name__ == "__main__":
    logging.info("Start!")
    p = readConfig2()
    filename = get_exchange(p["URL"], p["CURRENCY"], p["START"], p["END"])
    calculateData(filename)
    logging.info("The end of the script!")
