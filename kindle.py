import time
import json
from multiprocessing.dummy import Pool as ThreadPool
import threading
import re
from lxml import html, etree
import requests
import random
import psycopg
from psycopg import sql as query
import cloudscraper

# import pyperclip
import dbc
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import traceback
import logging
import os
from amazon_paapi import AmazonApi

try:
    AMZKEY = os.getenv("AMZKEY")
    AMZSECRET = os.getenv("AMZSECRET")
    THROTTLE = os.getenv("THROTTLE")
    DEPLOYED = int(os.getenv("DEPLOYED"))
    USER = os.getenv("K_U")
    PASSWORD = os.getenv("K_P")
    DEBUG = int(os.environ["DEBUG"])
    PULL = os.environ["PULL"]
except Exception:
    from secrets import (
        K_U as USER,
        K_P as PASSWORD,
        AMZKEY,
        AMZSECRET,
        THROTTLE,
        DEPLOYED,
        DEBUG,
        PULL,
    )

if DEBUG:
    logging.basicConfig(
        filename="kindle.log",
        filemode="w",
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

amazon = AmazonApi(AMZKEY, AMZSECRET, "arnz-20", "US", throttling=int(THROTTLE))
# from pushbullet import PB as pb

# # Create database.
# try:
#     cur.execute("CREATE TABLE kindle(asin varchar primary key not null,link varchar (255) not null,added DATE NOT NULL DEFAULT CURRENT_DATE )")
#     conn.commit()
# except:
#     print('Could not execute command')


# add row
def cleanDir(folder):
    logging.info(f"Deleting contents of folder {folder}")
    for f in os.listdir(folder):
        os.remove(os.path.join(folder, f))
        # print(os.path.join(dir, f))


class UniqueViolation(Exception):
    pass


class booktoForum:
    def __init__(self):
        # AWS location r"C:\Users\Administrator\Desktop\J\Chrome\bin\chrome.exe"
        self.conn = dbc.connect_pool()
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6729.1 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
        }
        self.scraper = cloudscraper.create_scraper(
            browser={"browser": "firefox", "platform": "windows", "mobile": False}
        )

        self.user = USER
        self.passw = PASSWORD
        self.newAsins = set()
        self.oldAsins = self.getASIN()
        with requests.get(
            "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"
        ) as f:
            self.driver = json.loads(f.text)["channels"]["Stable"]["version"]

    def chrome(self):
        mobile_emulation = {
            "deviceMetrics": {"width": 390, "height": 844, "pixelRatio": 3.0},
            "userAgent": "Mozilla/5.0 (Linux; Android 10; SM-A205U) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.5735.196 Mobile Safari/537.36",
        }
        options = Options()
        # options.binary_location = os.getenv('CHROME')
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--incognito")
        # options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_experimental_option(
            "excludeSwitches", ["enable-automation"]
        )  # hide top bar
        options.add_experimental_option("mobileEmulation", mobile_emulation)
        # options.add_argument("--auto-open-devtools-for-tabs") # open devtools
        # options.add_argument("user-data-dir=C:\\Users\\Administrator\\Desktop\\J\\Chrome\\profile");
        options.add_argument("log-level=1")
        if not DEPLOYED:
            options.binary_location = os.getenv("CHROME")
            s = Service(executable_path=os.getenv("CHROMEDRIVER"))
            self.d = webdriver.Chrome(service=s, options=options)
        else:
            options.binary_location = "/usr/bin/chromium-browser"
            s = Service(executable_path=os.getenv("CHROMEWEBDRIVER/chromedriver"))
            self.d = webdriver.Chrome(service=s, options=options)
        self.d.implicitly_wait(2)
        print("Chrome Browser Invoked")

    def stop(self):
        driver = self.d
        driver.quit()

    def login(self):
        # Init Chrome
        self.chrome()
        driver = self.d
        driver.get("https://www.jucktion.com/f/login?type=auto")
        cookie = {"name": "jktn_selenium", "value": "kindle", "domain": ".jucktion.com"}
        driver.add_cookie(cookie)
        driver.find_elements(by=By.NAME, value="user")[1].send_keys(self.user)
        driver.find_elements(by=By.NAME, value="passwrd")[1].send_keys(self.passw)
        driver.find_elements(by=By.NAME, value="cookielength")[0].send_keys("360")
        time.sleep(2)

        ele = driver.find_element(by=By.CSS_SELECTOR, value=".login .button_submit")
        driver.execute_script("arguments[0].click()", ele)
        time.sleep(2)
        # Switch cookies
        # request_cookies_browser = driver.get_cookies()
        # s = requests.Session()
        # c = [s.cookies.set(c["name"], c["value"]) for c in request_cookies_browser]

    def sendSQL(self, sql: str, val=None):
        try:
            # send = self.conn.getconn()
            with self.conn.getconn() as send, send.cursor() as cur:
                try:
                    if val:
                        cur.execute(
                            query.SQL(sql).format(query.Identifier("udemy")), val
                        )
                    else:
                        cur.execute(sql)
                        send.commit()
                except psycopg.errors.UniqueViolation:
                    print("Duplicate Error!")
                    raise UniqueViolation
                except psycopg.DatabaseError as e:
                    print(sql)
                    logging.error(traceback.format_exc())
                    print("Could not execute command", e.pgcode)
                    raise Exception
                finally:
                    cur.close()
        finally:
            self.conn.putconn(send)

    def addtoDB(self, asin, title, image, desc, price, sale):
        val = f"('{asin}','https://www.amazon.com/dp/{asin}','{title.replace("'", '')}','{image}','{desc.replace("'", '')}','{price}','{sale}')"
        sql = f"INSERT INTO kindle(asin,link, title, image, description, price, sale) values {val}"
        if DEBUG:
            logging.info(f"{sql}")
        try:
            self.sendSQL(sql)
        except Exception:
            print("Couldn't Add to DB!")

    def closeSQL(self):
        dbc.conn.close()

    def getASIN(self):
        asin = set()
        try:
            # dbc.cur.execute('SELECT id,price from iapps')
            sql = "SELECT asin from kindle"
            send = dbc.connect()
            cur = send.cursor()
            cur.execute(sql)
            for data in cur.fetchall():
                asin.add(data[0])
            send.close()
            return asin
        except Exception:
            "Failed to get data!"

    def getData(self, query):
        data = set()
        try:
            dbc.cur.execute(query)
        except Exception:
            "Failed to get data!"
        for d in dbc.cur.fetchall():
            data.add(d[0])
        return list(data)

    def deleteOld(self):
        # delete the ASINS older than 3 days
        delsql = "DELETE FROM kindle where added < NOW()-INTERVAL'5 days'"
        try:
            self.sendSQL(delsql)
        except Exception:
            print("Could not delete the older ASINs")

    # amazon method

    def amazon(self, url):
        ar = self.scraper.get(url)

        # Test the source
        if DEBUG and not DEPLOYED:
            with open("debug/amazon.html", "w", encoding="utf-8") as f:
                f.write(str(ar.content))

        links = 0

        # tree = html.fromstring(str(ar.content))
        # search = tree.xpath(
        #     '//div[starts-with(@id, "B")]/a[contains(@class,"a-link-normal")]'
        # )
        # if len(search) == 0:
        #     search = tree.xpath(
        #         '//div[@class="zg-grid-general-faceout"]/div/a[@class="a-link-normal"][1]'
        #     )

        asins = re.findall(r"(?<=dp/)B[A-Z0-9]{9}(?=/?)", str(ar.content))

        for asin in asins:
            self.newAsins.add(asin)
            links += 1

        # for elm in search:
        #     asin = re.findall(r"B[0-9A-Z]{9,9}", str(elm.xpath("@href")[0]))[0]
        #     # link = "https://www.amazon.com" + re.sub(
        #     #     r"\/ref.+", "", str(elm.xpath("@href")[0])
        #     # )
        #     # print(asin)
        #     self.newAsins.add(asin)
        #     links += 1
        if DEPLOYED:
            logging.info((f"Amazon: {links} found"))
        else:
            print(f"Amazon: {links} found")
        # sql = f"INSERT INTO kindle(asin,link) VALUES('{asin}','{link}')"
        # sendSQL(sql)

    def zio(self, run):
        f = requests.get(run, headers=self.headers)

        amz = html.fromstring(f.text)
        asin = re.findall(
            r"B[0-9A-Z]{9,9}", amz.xpath('//div/a[text()="Amazon USA"]/@href')[0]
        )[0]
        logging.info(f"{run}, {asin}")
        self.newAsins.add(asin)
        # for elm in amz.xpath('//div/a[text()="Amazon USA"]/@href'):
        #     ar = self.scraper.get(elm).url
        #     if DEBUG:
        #         logging.info(f"{elm},{ar}")
        #     asin = re.findall(r"B[0-9A-Z]{9,9}", ar)[0]
        #     # link = elm.xpath("@href")[0]
        #     # print(asin)
        #     self.newAsins.add(asin)

    # bookzio

    def bookzio(self, url):
        # pass
        br = requests.get(url, headers=self.headers)
        # Test the source
        if DEBUG and not DEPLOYED:
            with open("debug/bookzio.html", "w", encoding="utf-8") as f:
                f.write(br.text)

        tree = html.fromstring(br.text)
        links = tree.xpath('//h2[@class="df-post-title"]/a/@href')
        if DEPLOYED:
            logging.info((f"Bookzio: {len(links)} found"))
        else:
            print(f"Bookzio: {len(links)} found")
        pool = ThreadPool(15)
        pool.starmap(self.zio, zip(links))

    # HUKD
    def hukd(self, id):
        url = str("https://www.hotukdeals.com/visit/thread/" + id)
        try:
            ar = self.scraper.get(url).url
            try:
                asin = re.findall(r"B[0-9A-Z]{9,9}", ar)[0]
                if DEBUG:
                    logging.info(f"{ar}, {asin}")
                self.newAsins.add(asin)
            except IndexError:
                print("Skipping (HUKD): ", ar)
        except Exception:
            logging.error(traceback.format_exc())

    def getHUKD(self, url):
        hr = self.scraper.get(url)
        if DEBUG and not DEPLOYED:
            with open("debug/hukd.html", "w", encoding="utf-8") as f:
                f.write(hr.text)
        # Using regex
        # matches = re.findall(
        #     r"(?<=amazon.co.uk\/dp\/).+?(?=\#customerReviews)", hr.text
        # )

        # if DEPLOYED:
        #     logging.info(f"HUKD: {len(matches)} found")
        # else:
        #     print(f"HUKD: {len(matches)} found")

        # for m in matches:
        #     try:
        #         # print(ar, asin)
        #         self.newAsins.add(m)
        #     except IndexError:
        #         print("Skipping: ", m)

        root = etree.fromstring(hr.text.encode("utf-8"))

        links = []
        for item in root.findall(".//item"):
            title = item.find("title").text
            if (
                "kindle" in title.lower()
            ):  # Check if "kindle" is in the title (case insensitive)
                link = item.find("link").text
                links.append(link)
        # Using HTML (old)
        # tree = html.fromstring(hr.text)
        # links = tree.xpath(
        #     '//a[contains(@class,"thread-title--list")][contains(@title,"kindle")]/@href|//a[contains(@class,"thread-title--list")][contains(@title,"Kindle")]/@href'
        # )
        if DEPLOYED:
            logging.info(f"HUKD: {len(links)} found")
        else:
            print(f"HUKD: {len(links)} found")
        threads = list()  # make a thread list
        for i in links:
            # start the threading with external function parse
            x = threading.Thread(target=self.hukd, args=(i.split("-")[-1],))
            threads.append(x)  # count the threads
            x.start()  # start the threads

        for t in threads:
            t.join()  # loop through all the threads and wait for them to finish

    def removegetAdd(self):
        self.deleteOld()
        amz = f"{PULL}https://www.amazon.com/amz-books/book-deals"
        burl = "https://www.bookzio.com/latest-book-deals/"
        hurl = "https://www.hotukdeals.com/rss/tag/freebies"
        # open('books.txt', 'w').close()

        t1 = threading.Thread(target=self.amazon, args=(amz,))
        t2 = threading.Thread(target=self.bookzio, args=(burl,))
        t3 = threading.Thread(target=self.getHUKD, args=(hurl,))
        t1.start()
        t2.start()
        t3.start()
        t1.join()
        t2.join()
        t3.join()

        # print(self.oldAsins)
        # print(self.newAsins)
        newlist = list(self.newAsins.difference(self.oldAsins))

        # convert set to a list
        # newgen = ("https://www.amazon.com/dp/" + x for x in newlist)
        # final = ",".join(list(newgen))
        # print("New: " + str(final))

        # pyperclip.copy(final)
        # self.addtoDB()

        return newlist

    def getProxy(self, link):
        driver = self.d
        driver.get("https://kproxy.com")
        driver.find_element(by=By.ID, value="maintextfield").clear()
        driver.find_element(by=By.ID, value="maintextfield").send_keys(link)
        driver.find_elements(by=By.CLASS_NAME, value="boton")[3].click()
        return driver

    def getwoProxy(self, link):
        driver = self.d
        driver.get(link)
        return driver

    def posttoForum(self, listB):
        # listofB = self.getData(
        #     "SELECT asin from kindle where added > NOW() - INTERVAL'1 day'")
        # final = ','.join(list(listofB))
        # print(final)
        # print(listB)
        # wait for login
        # time.sleep(120)
        for i, asin in enumerate(listB):
            if asin not in self.oldAsins:
                try:
                    logging.info(f"https://www.amazon.com/dp/{str(asin)}")
                    link = "https://www.amazon.com/dp/" + str(asin)
                    logging.info(f"{i + 1} of {len(listB)}: {link}")

                    print(f"{i + 1} of {len(listB)}: ", link)
                    # driver = getProxy(link)  # Use proxy to get Amazon content
                    # pyperclip.copy(driver.page_source)
                    driver = self.getwoProxy(link)
                    time.sleep(1)

                    # Debug source
                    if not DEPLOYED:
                        with open(f"debug/{asin}.html", "w", encoding="utf-8") as f:
                            f.write(driver.page_source)

                    if (
                        "All titles below are free to borrow with a Kindle Unlimited subscription"
                        in driver.page_source
                    ):
                        continue

                    if 'id="collection_description"' in driver.page_source:
                        print("Collection is found")
                        tree = html.fromstring(driver.page_source)
                        links = tree.xpath('//a[contains(@id,"itemBookTitle_")]/@href')
                        for i in links:
                            asin = re.findall(r"B[0-9A-Z]{9,9}", i)[0]
                            listB.append(asin)
                    else:
                        try:
                            item = amazon.get_items(asin)[0]
                        except Exception:
                            print("Cannot get data from API, using alternative")
                            item = False
                            # print(traceback.format_exc())

                        if item:
                            price = item.offers.listings[0].price.display_amount
                        else:
                            try:
                                price = (
                                    driver.find_element(
                                        by=By.CSS_SELECTOR,
                                        value=".slot-price .ebook-price-value",
                                    ).text
                                    if (
                                        driver.find_elements(
                                            by=By.CSS_SELECTOR,
                                            value=".slot-price .ebook-price-value",
                                        )
                                    )
                                    else driver.find_element(
                                        by=By.CSS_SELECTOR,
                                        value=".kindleExtraMessage .a-color-price",
                                    ).text
                                    if (
                                        driver.find_elements(
                                            by=By.CSS_SELECTOR,
                                            value=".kindleExtraMessage .a-color-price",
                                        )
                                    )
                                    else driver.find_element(
                                        by=By.CSS_SELECTOR,
                                        value=".centralizedApexPricePriceToPayMargin",
                                    ).text
                                    if (
                                        driver.find_elements(
                                            by=By.CSS_SELECTOR,
                                            value=".centralizedApexPricePriceToPayMargin",
                                        )
                                    )
                                    else driver.find_element(
                                        by=By.CSS_SELECTOR, value="#price-to-pay"
                                    ).text
                                )
                            except Exception:
                                print("Could not find price element in source code")
                                # price = False
                                # wait = random.randint(60, 120)
                                # print(f"Waiting {wait} seconds...")
                                # time.sleep(wait)
                                continue
                            price = ".".join(price.strip().split())
                            try:
                                ogprice = (
                                    driver.find_element(
                                        by=By.CSS_SELECTOR,
                                        value="#basis-price",
                                    ).text
                                    if (
                                        driver.find_elements(
                                            by=By.CSS_SELECTOR,
                                            value="#basis-price",
                                        )
                                    )
                                    else driver.find_element(
                                        by=By.CSS_SELECTOR,
                                        value="#digital-list-price.a-text-strike",
                                    ).text
                                    if (
                                        driver.find_elements(
                                            by=By.CSS_SELECTOR,
                                            value="#digital-list-price.a-text-strike",
                                        )
                                    )
                                    else driver.find_element(
                                        by=By.CSS_SELECTOR,
                                        value="#print-list-price .a-text-strike",
                                    ).text
                                    if driver.find_elements(
                                        by=By.CSS_SELECTOR,
                                        value="#print-list-price .a-text-strike",
                                    )
                                    else driver.find_element(
                                        by=By.CSS_SELECTOR,
                                        value=".a-price.a-text-price",
                                    ).text
                                    if driver.find_elements(
                                        by=By.CSS_SELECTOR,
                                        value=".a-price.a-text-price",
                                    )
                                    else driver.find_element(
                                        by=By.CSS_SELECTOR,
                                        value=".a-color-base.a-align-bottom.a-text-strike",
                                    ).text
                                )
                            except Exception:
                                if DEPLOYED:
                                    logging.info(
                                        f"Couldnt find original price for {link}"
                                    )
                                else:
                                    print(f"Couldnt find original price for {link}")
                                continue
                        # FREE
                        # if price and "$0.00" in str(price):
                        if DEBUG:
                            logging.info(
                                f"OG: {ogprice.strip()}, New: {price.strip()}\nAFTER \nOG: {ogprice.strip().split('$')[1]}, New: {price.strip().split('$')[1]}"
                            )
                        if price and float(ogprice.strip().split("$")[1]) > float(
                            price.strip().split("$")[1]
                        ):
                            time.sleep(1)
                            if item:
                                title = item.item_info.title.display_value

                            else:
                                title = (
                                    driver.find_element(
                                        by=By.XPATH, value='//h1[@id="ebooksTitle"]'
                                    ).text
                                    if (
                                        driver.find_elements(
                                            by=By.CSS_SELECTOR, value="#ebooksTitle"
                                        )
                                    )
                                    else driver.find_element(
                                        by=By.XPATH, value='//span[@id="productTitle"]'
                                    ).text
                                )
                            cleantitle = title

                            rating = (
                                driver.find_element(
                                    by=By.CSS_SELECTOR, value="span#acrPopover"
                                ).get_attribute("title")
                                if driver.find_elements(
                                    by=By.CSS_SELECTOR, value="span#acrPopover"
                                )
                                else driver.find_element(
                                    by=By.CSS_SELECTOR,
                                    value="#acrCustomerReviewLink span.a-color-base",
                                ).text
                                + " out of 5"
                                if driver.find_elements(
                                    by=By.ID, value="acrCustomerReviewLink"
                                )
                                else ""
                            )
                            revnum = (
                                driver.find_element(
                                    by=By.CSS_SELECTOR,
                                    value="span#acrCustomerReviewText",
                                ).text
                                if driver.find_elements(
                                    by=By.CSS_SELECTOR,
                                    value="span#acrCustomerReviewText",
                                )
                                else driver.find_element(
                                    by=By.CSS_SELECTOR,
                                    value="a#acrCustomerReviewLink > span:nth-child(3)",
                                ).text
                                + " Reviews"
                                if driver.find_elements(
                                    by=By.ID, value="acrCustomerReviewLink"
                                )
                                else ""
                            )
                            revnum = (
                                revnum.strip().split("(")[1].split(")")[0]
                                if ("(" in revnum)
                                else revnum
                            )

                            if item:
                                img = item.images.primary.large.url
                            else:
                                img = (
                                    driver.find_element(
                                        by=By.ID, value="ebooksImgBlkFront"
                                    ).get_attribute("src")
                                    if driver.find_elements(
                                        by=By.ID, value="ebooksImgBlkFront"
                                    )
                                    else driver.find_element(
                                        by=By.CSS_SELECTOR,
                                        value="#landing-image-wrapper img",
                                    ).get_attribute("src")
                                )
                            try:
                                author = " ".join(
                                    reversed(
                                        item.item_info.by_line_info.contributors[
                                            0
                                        ].name.split(",")
                                    )
                                )
                            except Exception:
                                author = (
                                    driver.find_element(
                                        by=By.CSS_SELECTOR, value="a#bylineContributor"
                                    ).text
                                    if driver.find_elements(
                                        by=By.ID, value="bylineContributor"
                                    )
                                    else driver.find_element(
                                        by=By.CSS_SELECTOR, value=".author a"
                                    ).text
                                    if driver.find_elements(
                                        by=By.CLASS_NAME, value="author"
                                    )
                                    else driver.find_element(
                                        by=By.CSS_SELECTOR, value="#contributorLink"
                                    ).text
                                    if driver.find_elements(
                                        by=By.ID, value="contributorLink"
                                    )
                                    else ""
                                )

                            price = "FREE" if ("$0.00" in price) else price
                            title += " (" + str(ogprice) + " to " + str(price) + ")"

                            desc = (
                                driver.find_element(
                                    by=By.CSS_SELECTOR,
                                    value="#drengr_MobileTabbedDescriptionOverviewContent_feature_div",
                                ).text
                                if driver.find_elements(
                                    by=By.ID,
                                    value="drengr_MobileTabbedDescriptionOverviewContent_feature_div",
                                )
                                else driver.find_element(
                                    by=By.CSS_SELECTOR,
                                    value="#bookDescription_feature_div .a-expander-content",
                                ).text
                                if driver.find_elements(
                                    by=By.ID, value="bookDescription_feature_div"
                                )
                                else ""
                            )
                            # driver.switch_to.default_content()

                            # print(title)
                            # print(ogprice)
                            # print(rating)
                            # print(revnum)
                            # print(img)
                            # print(author)
                            # print(desc)
                            textform = """[img alt=Cover Image for {0}]{1}[/img]

[b]Author: [color=green]{2}[/color].

Rating:[color=maroon] {3} ({4} Reviews)[/color][/b]

[size=10pt][color=green][b]Book Description:[/b][/color][/size]

{5}


[url={6}?tag=jucktion-20][img alt=Download {0} for Kindle]https://www.jucktion.com/f/uploads/amzbtn.png[/img][/url]   [url=https://g.ootl.in/kindleunlimited][img alt=Download More Amazon Books]https://www.jucktion.com/f/uploads/amazonbooks.png[/img][/url]
\n\n\n[sub]Please note: As an affiliate partner with Amazon, this post includes affiliate links. Purchasing items on Amazon through these links may earn me a commission, but please buy only if it aligns with your needs. Thanks for your support![/sub]"""
                            copy = textform.format(
                                cleantitle, img, author, rating, revnum, desc, link
                            )
                            # print(textform.format(title,img,author,rating,revnum,desc,link,title))
                            # pyperclip.copy(copy)

                            driver.get(
                                "https://www.jucktion.com/f/index.php?action=post&board=43"
                            )

                            time.sleep(2)
                            self.addtoDB(
                                asin=asin,
                                title=cleantitle,
                                image=img,
                                desc=desc,
                                price=ogprice,
                                sale=price,
                            )
                            # scr = f"document.getElementsByName('message')[0].innerHTML = {json.dumps(desc)};"
                            # print(scr)
                            if driver.find_elements(by=By.NAME, value="subject"):
                                driver.execute_script(
                                    f"document.getElementsByName('subject')[0].value = {json.dumps(title)};document.getElementsByName('ogimage')[0].value = {json.dumps(img)};document.getElementsByName('description')[0].value = {json.dumps(desc[:150])};document.getElementsByName('message')[0].innerHTML = {json.dumps(copy)};"
                                )
                                ele = driver.find_element(
                                    by=By.CSS_SELECTOR,
                                    value="#post_confirm_buttons .button_submit",
                                )
                                driver.execute_script("arguments[0].click()", ele)
                            # driver.get('https://www.amazon.com/gp/goldbox?ref_=nav_cs_gb')
                            wait = random.randint(60, 120)
                            print(f"Posted! Waiting {wait} seconds...")
                            time.sleep(wait)
                            # Add the ASIN to the db
                    # break
                except KeyboardInterrupt:
                    break
                except Exception:
                    logging.error(traceback.format_exc())
                    print("Skipping ", link)

    @staticmethod
    def run():
        start = time.time()
        # msg = pb()
        # msg.push('n', 'ct', "Automations", "Book Posting Started", channel="nn")
        task = booktoForum()
        listed = task.removegetAdd()

        # CHECK DATA
        # print('OLD: ', task.oldAsins)
        # print('NEW: ', task.newAsins)
        # print(listed)

        # TASK DONE HERE
        logging.info(f"New found: {len(listed)}")
        print(f"New found: {len(listed)}")
        if listed > 0:
            task.login()

            try:
                task.posttoForum(listed)
            except Exception:
                logging.error(traceback.format_exc())
        else:
            pass
        task.stop()
        end = time.time()
        # msg.push('l', 'ct', "Automations", f"Book posting completed in {round((end-start)/60,2)} minutes",
        #          link="https://www.jucktion.com/f/kindle-free-books/", channel='nn')
        print(end - start)


if __name__ == "__main__":
    start = time.time()
    if not DEPLOYED:
        cleanDir("debug")

    task = booktoForum()
    listed = task.removegetAdd()

    # CHECK DATA
    # print('OLD: ', task.oldAsins)
    # print('NEW: ', task.newAsins)
    # print(listed)

    # TASK DONE HERE
    logging.info(f"New found: {len(listed)}")
    if DEBUG:
        print(f"New found {len(listed)}")

    from pyvirtualdisplay import Display

    if not DEPLOYED:
        if len(listed) > 0:
            task.login()
            try:
                task.posttoForum(listed)
            except Exception:
                logging.error(traceback.format_exc())
            except KeyboardInterrupt:
                task.stop()
            finally:
                task.stop()
        else:
            pass
    else:
        with Display(visible=0, size=(1024, 768)) as disp:
            if len(listed) > 0:
                task.login()
                try:
                    task.posttoForum(listed)
                except Exception:
                    logging.error(traceback.format_exc())
                except KeyboardInterrupt:
                    task.stop()
                finally:
                    task.stop()
            else:
                pass

    end = time.time()
    # msg.push('l', 'ct', "Automations", f"Book posting completed in {round((end-start)/60,2)} minutes",
    #          link="https://www.jucktion.com/f/kindle-free-books/", channel='nn')
    print(round((end - start) / 60, 2), "minutes")
