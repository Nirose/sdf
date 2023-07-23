import time
import json
from multiprocessing.dummy import Pool as ThreadPool
import threading
from datetime import datetime
import re
from lxml import html
import requests
import dbc
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import traceback
import logging
from urllib.parse import urlparse
import os
import psycopg2
import cloudscraper

logging.basicConfig(filename='iapps.log', filemode='w',
format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

try:
    USER = os.getenv('A_U')
    PASSWORD = os.getenv('A_P')
    DEPLOYED = int(os.getenv('DEPLOYED'))
except:
    from secrets import A_U as USER, A_P as PASSWORD, DEPLOYED

class UniqueViolation(Exception):
    pass


class apptoForum:
    def __init__(self):
        # self.headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.90 Safari/537.36'}
        self.user = USER
        self.passw = PASSWORD
        self.unique = set()
        self.newApps = set()
        self.oldApps = self.getID()
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'firefox',
                'platform': 'windows',
                'mobile': False
            }
        )

    def chrome(self):
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--incognito")
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        # options.add_argument("user-data-dir=C:\\Users\\Administrator\\Desktop\\J\\Chrome\\profile");
        options.add_argument("log-level=0")
        if not DEPLOYED:
            s = Service(executable_path=os.getenv("CHROMEDRIVER"))
            self.d = webdriver.Chrome(service=s, options=options)
        else:
            from webdriver_manager.chrome import ChromeDriverManager
            from webdriver_manager.core.utils import ChromeType
            self.d = webdriver.Chrome(service=Service(ChromeDriverManager(chrome_type=ChromeType.BRAVE).install()))
        self.d.implicitly_wait(2)
        print("Chrome Browser Invoked")

    def login(self):
        self.chrome()
        driver = self.d
        driver.get("https://www.jucktion.com/f/help?type=rss")
        cookie = {"name": "jktn_selenium", "value": "apps", "domain": ".jucktion.com"}
        driver.add_cookie(cookie)
        driver.get("https://www.jucktion.com/f/login/")
        driver.find_elements(by=By.NAME, value="user")[1].send_keys(self.user)
        driver.find_elements(by=By.NAME, value="passwrd")[1].send_keys(self.passw)
        driver.find_elements(by=By.NAME, value="cookielength")[0].send_keys("360")

        time.sleep(2)
        ele = driver.find_element(by=By.CSS_SELECTOR, value=".login .button_submit")
        driver.execute_script(f"arguments[0].click()", ele)
        #
        # Exchange cookies from selenium to requests
        #
        request_cookies_browser = driver.get_cookies()
        s = requests.Session()
        c = [s.cookies.set(c["name"], c["value"]) for c in request_cookies_browser]

    def stop(self):
        driver = self.d
        driver.quit()

    # get all the ids from the sites

    def getAll(self):

        aad = "http://appaddict.net/price-drops"
        isn = "https://www.iosnoops.com/iphone-ipad-deals/all/free/all/"
        adv = "https://appadvice.com/apps-gone-free"
        t1 = threading.Thread(target=self.getAppAddict, args=(aad,))
        t2 = threading.Thread(target=self.iosSnoops, args=(isn,))
        t3 = threading.Thread(target=self.appadvice, args=(adv,))

        try:
            t1.start()
        except:
            print("Appaddict Failed")
        try:
            t2.start()
        except:
            print("iOSnopes Failed")
        try:
            t3.start()
        except:
            print("Appadvice failed")

        t1.join()
        t2.join()
        t3.join()

        return self.newApps

    # Get the apps from appaddict
    def getAppAddict(self, url):
        logging.info('Crawling App Addict')
        headers = {"Accept-Encoding":"deflate"}
        ar = self.scraper.get(url)
        tree = html.fromstring(ar.text)
        details = zip(
            tree.xpath(
                '//div[@class="td-container td-wrap-content"][1]//strong[@class="price"]//a[1]/@href'
            ),
            tree.xpath(
                '//div[@class="td-container td-wrap-content"][1]//strong[@class="price"]/a/text()'
            ),
        )
        for link, price in details:
            # print(link,price)
            id = re.findall(r"\d+", link.split("/")[-1])[0]
            price = (
                "0." + str(re.findall(r"\d+", price[:-8])[0])
                if ("\u00A2" in price)
                else re.findall(r"\$([\d.]{2,})", price[:-8])[0]
            )
            # test
            # print(id, price)
            if id not in self.unique:
                self.unique.add(id)
                self.newApps.add((int(id), price))
        #logging.info(f'Found (appaddict): {len(list(details))}')

    def iosSnoops(self, url):
        logging.info('Crawling iOSSnoops')
        ar = self.scraper.get(url)
        tree = html.fromstring(ar.text)
        details = zip(
            tree.xpath('//div[@class="post"]/h2/a/@href'),
            tree.xpath('//div[@class="post"]//p[@class="nav4"]/a/img/@src'),
        )
        
        for link, price in details:
            # print(link, price)
            id = link.split("/")[-1]
            format = str(re.findall(r"price-(\d+)-0.png", price)[0])
            # print(format)
            price = (
                "0" + "." + format[-2:]
                if (len(format) <= 2)
                else format[:-2] + "." + format[-2::]
            )
            # print(id, price)
            if id not in self.unique:
                self.unique.add(id)
                self.newApps.add((int(id), price))

        #logging.info(f'Found (iOSSnoops): {len(list(details))}')

    def appadvice(self, url):
        logging.info('Crawling appadvice')
        headers = {"Accept-Encoding":"deflate"}
        ar = self.scraper.get(url)
        tree = html.fromstring(ar.text)
        details = zip(
            tree.xpath(
                '//a[@class="aa_agf__main__btn aa_agf__main__btn--free aa_hide--touchdevice"]/@href'
            ),
            tree.xpath("//article//a[1]/span[1]/text()"),
        )
        
        # price = tree.xpath('//article//a[1]/span[1]/text()')
        for link, price in details:
            # print(urlparse(link[0]))
            # print(link, price)
            id = re.findall(r"\d+", urlparse(link).path)[0]
            price = re.findall(r"[\d.]{1,}", price)[0]
            if id not in self.unique:
                self.unique.add(id)
                self.newApps.add((int(id), price))
        #logging.info(f'Found (appadvice): {len(list(details))}')
    #
    # SQL STUFF
    #

    def addtoDB(self, id, price):
        # val = "('"+id + f"','https://apps.apple.com/us/app/id{id},{price}')"
        val = f"({id},'https://apps.apple.com/us/app/id{id}','{price}')"
        sql = f"INSERT INTO iapps(id,link,price) values {val}"
        try:
            self.sendSQL(sql)

        except UniqueViolation:
            raise Exception
        except Exception as e:
            logging.error(traceback.format_exc())
            print("Couldn't Add to DB!")

    # endpoint to send SQL
    def sendSQL(self, sql):
        send = dbc.connect()
        cur = send.cursor()
        try:
            cur.execute(sql)
            send.commit()
        except psycopg2.errors.UniqueViolation:
            raise UniqueViolation
            print("Duplicate Error!")
        except psycopg2.DatabaseError as e:
            print(sql)
            logging.error(traceback.format_exc())
            print("Could not execute insert command", e.pgcode)
            raise Exception
        finally:
            if send is not None:
                cur.close()
                send.close()

    def closeSQL(self):
        self.send.close()

    def getID(self):
        asin = set()
        try:
            # dbc.cur.execute('SELECT id,price from iapps')
            sql = "SELECT id,price from iapps"
            send = dbc.connect()
            cur = send.cursor()
            cur.execute(sql)
            for data in cur.fetchall():
                asin.add((data[0], data[1]))
            send.close()
        except:
            "Failed to get data!"
        return asin

    def deleteOld(self):
        # delete the ASINS older than 3 days
        delsql = f"DELETE FROM iapps where added < NOW()-INTERVAL'5 days'"
        try:
            self.sendSQL(delsql)
        except:
            print("Could not delete the older records")

    # SQL STUFF END

    # Cleanup
    def removegetAdd(self):
        self.deleteOld()
        newlist = None
        # new = set(x for x, y in self.newApps)
        # print('Old Apps:', self.oldApps)
        # print('New Apps:', self.newApps)
        newlist = list(self.newApps.difference(self.oldApps))

        if newlist:
            # convert set to a list
            newgen = ("https://apps.apple.com/us/app/id" + str(x) for x, y in newlist)
            final = ",".join(list(newgen))
            logging.info("New: " + str(len(newlist)))
            print("New: " + str(len(newlist)))
        else:
            print("Nothing new to add!")
        # pyperclip.copy(final)
        # self.addtoDB()

        return newlist

    def posttoForum(self, listB):
        # listofB = self.getData(
        #     "SELECT asin from kindle where added > NOW() - INTERVAL'1 day'")
        # final = ','.join(list(listofB))
        # print(final)
        # print(listB)
        for id, (appid, price) in enumerate(listB):
            logging.info(f'Posting: https://apps.apple.com/us/app/id{str(appid)}')
            link = "https://apps.apple.com/us/app/id" + str(appid)
            try:
                print(link)
                try:
                    self.addtoDB(appid, price)
                except:
                    print("Skipping, Database error Found")
                    continue
                re = self.scraper.get(link)
                if "<title>" in re.text:
                    tree = html.fromstring(re.text)
                    title = tree.xpath(
                        '//h1[@class="product-header__title app-header__title"]/text()'
                    )[0].strip()
                    ptitle = "[iOS] " + title + " ($" + price + " to Free)"
                    img = str(
                            tree.xpath(
                                '(//picture[contains(@class,"we-artwork--screenshot")]//source/@srcset)[1]'
                            )
                        )
                    #print(img)
                    img = img.split(" ")[-2]
                    # img = str(tree.xpath(
                    #     '//div[@class="we-screenshot-viewer__screenshots"]//source[@class="we-artwork__source"][1]/@srcset')).split(' ')[-5].split(",")[1]
                    # test image
                    # print(tree.xpath(
                    #     '//div[@class="we-screenshot-viewer__screenshots"]//source[@class="we-artwork__source"][1]/@srcset'))
                    # print(str(tree.xpath(
                    #     '//div[@class="we-screenshot-viewer__screenshots"]//source[@class="we-artwork__source"][1]/@srcset')).split(' ')[-5])
                    # print(str(tree.xpath(
                    #     '//div[@class="we-screenshot-viewer__screenshots"]//source[@class="we-artwork__source"][1]/@srcset')).split(' ')[-5].split(",")[1])
                    # print(img)
                    # break
                    description = tree.xpath(
                        '//div[@class="section__description"]//p/text()'
                    )
                    desc = "\n\n".join(description)
                    # dr.get(link)

                    # # dr.find_element_by_css_selector(
                    # #     '.we-truncate .we-truncate__button').click()
                    # desc = dr.find_element_by_css_selector(
                    #     '.we-truncate__button link').click()
                    # desc = dr.find_element_by_css_selector(
                    #     '.section__description').text
                    # desc = tree.xpath('//div[@class="section__description"]//div[@class="l-row"]/div/div/child::*/text()')
                    # print(id, title, ptitle, img, price)
                    # print(desc)

                    textform = """[img alt=App screenshot for {0}]{1}[/img]
[size=10pt][color=green][b]App Description:[/b][/color][/size]
{2}


[url={3}][img alt=Download {0} from the Appstore]https://www.jucktion.com/f/uploads/images/download-from-app-store.png[/img][/url]   [url=https://www.jucktion.com/f/apps-gone-free/?utm_campaign=moreapps][img alt=Download More Apps Gone Free]https://www.jucktion.com/f/uploads/images/see-more-apps.png[/img][/url]"""
                    copy = textform.format(title, img, desc, link)
                    dr = self.d
                    dr.get("https://www.jucktion.com/f/index.php?action=post&board=38")

                    time.sleep(2)

                    # scr = f"document.getElementsByName('message')[0].innerHTML = {json.dumps(desc)};"
                    # print(scr)
                    if dr.find_elements(by=By.NAME, value="subject"):
                        dr.execute_script(
                            f"document.getElementsByName('subject')[0].value = {json.dumps(ptitle)};document.getElementsByName('ogimage')[0].value = {json.dumps(img)};document.getElementsByName('description')[0].value = {json.dumps(desc[10:150])};document.getElementsByName('message')[0].innerHTML = {json.dumps(copy)};"
                        )
                    ele = dr.find_element(
                            by=By.CSS_SELECTOR,
                            value="#post_confirm_buttons .button_submit",
                        )
                    dr.execute_script(f"arguments[0].click()", ele)
                    print("Waiting half minutes...")
                    time.sleep(30)
                    # Add the ID to the db
                    # self.addtoDB(appid, price)
                    # break
                else:
                    print("Invalid Link, Skipped!")
                    continue
            except KeyboardInterrupt:
                break
            except Exception as e:
                logging.error(traceback.format_exc())
                print("Skipping ", link)

    @staticmethod
    def run():
        start = time.time()
        t = apptoForum()

        # TO RUN ONE BY ONE
        # t.getAppAddict('http://appaddict.net/price-drops')
        # t.appadvice('https://appadvice.com/apps-gone-free')
        # t.iosSnoops('https://www.iosnoops.com/iphone-ipad-deals/all/free/all/')
        # print(t.newApps)

        t.getAll()  # get all the IDs first

        # POST STARTER
        listed = t.removegetAdd()

        if listed:
            t.login()
            # msg.push('n', 'ct', "Automations",
            #          "Apps Posting Started", channel="nn")
            try:
                t.posttoForum(listed)
            except Exception as e:
                logging.error(traceback.format_exc())
            finally:
                t.stop()
            end = time.time()
        else:
            end = time.time()

        # CHECK THE DATA
        # print('Unique: ', t.unique)
        # print("new: ", t.newApps)
        # print("old: ", t.oldApps)
        # listed = t.removegetAdd()
        # print(listed)

        print(end - start)


if __name__ == "__main__":
    start = time.perf_counter()
    t = apptoForum()

    # TO RUN ONE BY ONE
    # t.getAppAddict('http://appaddict.net/price-drops')
    # t.appadvice('https://appadvice.com/apps-gone-free')
    # t.iosSnoops('https://www.iosnoops.com/iphone-ipad-deals/all/free/all/')
    # print(t.newApps)

    t.getAll()  # get all the IDs first

    # POST STARTER
    listed = t.removegetAdd()

    if listed:
        t.login()
        # msg.push('n', 'ct', "Automations",
        #          "Apps Posting Started", channel="nn")
        try:
            t.posttoForum(listed)
        except Exception as e:
            logging.error(traceback.format_exc())
        finally:
            t.stop()
        end = time.perf_counter()
    else:
        end = time.perf_counter()

    # CHECK THE DATA
    # print('Unique: ', t.unique)
    # print("new: ", t.newApps)
    # print("old: ", t.oldApps)
    # listed = t.removegetAdd()
    # print(listed)

    if not DEPLOYED:
        print(f'Completed: {round((end - start)/60,2)} minutes')
        logging.info(f'It took {round((end - start)/60,2)} minutes')
    else:
        logging.info(f'It took {round((end - start)/60,2)} minutes')