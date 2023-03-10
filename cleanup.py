import os
import re
import time
import json
import requests
import logging
import traceback
from urllib.parse import urlparse, parse_qs
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.by import By
from env import *
from amazon_paapi import AmazonApi

try:
    USER = os.getenv('C_U')
    PASSWORD = os.getenv('C_P')
    DEPLOYED = int(os.getenv('DEPLOYED'))
except:
    from secrets import C_U as USER, C_P as PASSWORD, DEPLOYED

# import warnings

# warnings.filterwarnings("ignore", category=DeprecationWarning)

amazon = AmazonApi(AMZKEY, AMZSECRET, "arnz-20", "US",throttling=THROTTLE)


class Cleanup:
    def __init__(self):
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--incognito")
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        # options.add_argument("user-data-dir=C:\\Users\\Administrator\\Desktop\\J\\Chrome\\profile");
        options.add_argument("log-level=1")
        s = Service(executable_path=os.getenv("CHROMEDRIVER"))
        self.d = webdriver.Chrome(service=s, options=options)
        self.d.implicitly_wait(2)
        # print("Chrome Browser Invoked")
        self.headers = {
            "authority": "www.amazon.com",
            "pragma": "no-cache",
            "cache-control": "no-cache",
            "dnt": "1",
            "upgrade-insecure-requests": "1",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/81.0.4044.123 Safari/537.36",
            "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "sec-fetch-site": "none",
            "sec-fetch-mode": "navigate",
            "sec-fetch-dest": "document",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",
        }
        self.jeaders = {
            "user-agent": "Jucktion/1.0 (Language=Python; Host=jucktion.com)",
        }

    def stop(self):
        driver = self.d
        driver.quit()

    def login(self):
        print("Loggin in...")
        driver = self.d
        driver.get("https://www.jucktion.com/f/login/")
        driver.find_elements(by=By.NAME, value="user")[1].send_keys(PASSWORD)
        driver.find_elements(by=By.NAME, value="passwrd")[1].send_keys(PASSWORD)
        driver.find_element(by=By.NAME, value="cookieneverexp").click()

        driver.find_element(by=By.CSS_SELECTOR, value=".login .button_submit").click()

        # pass cookies on to requests session
        request_cookies_browser = driver.get_cookies()
        self.r = requests.Session()
        [self.r.cookies.set(c["name"], c["value"]) for c in request_cookies_browser]
        # ar = self.r.get('https://www.jucktion.com/f/')
        # print(ar.text)

    def delete(self, url):
        driver = self.d
        try:
            # print(url)
            driver.get(url)
            # requests didn't work because of session missmatch
            # re = self.r.get(url)
            # print(re.text)
            print("Deleted!")
        except Exception as e:
            logging.error(traceback.format_exc())
            print("Skipped!")

    def getlastPage(self, url):
        driver = self.d
        driver.get(url)
        return int(
            driver.find_element(
                by=By.CSS_SELECTOR, value=".pagelinks a.navPages:nth-last-child(2)"
            ).text
        )

    def getallLinks(self, url):
        startcrawl = time.time()
        booklist = []
        lastpage = 20 * self.getlastPage(url)
        # for i in range(lastpage, -1, -20):
        lastcheck = 0
        print("Getting links until... ", lastcheck)
        # go reverse up to 250th
        for i in range(lastpage, lastcheck, -20):
            page = url + str(i)
            driver = self.d
            driver.get(page)

            books = driver.find_elements(
                by=By.CSS_SELECTOR, value="span[id^=msg_]:not(.exclamation) a"
            )
            # print(len(books))
            for b in reversed(books):
                try:
                    booklist.append(str(b.get_attribute("href")))
                except:
                    pass
            # print(len(booklist))
            # break #break after scraping links on the last page
        # driver.quit()
        endcrawl = time.time()
        print(round((endcrawl - startcrawl) / 60, 2), "minutes")
        return booklist

    def checkbookLinkProxy(self):
        bookstoCheck = self.getallLinks("https://www.jucktion.com/f/kindle-free-books/")
        print("Validation Started...")
        for i, book in enumerate(bookstoCheck):
            driver = self.d
            print(book)  # print the post link
            driver.get(book)
            amz = driver.find_element(
                by=By.CSS_SELECTOR, value="a.bbc_link[href*=amazon\.com]"
            ).get_attribute("href")
            try:
                de = driver.find_element(
                    by=By.CSS_SELECTOR, value="li.remove_button a"
                ).get_attribute("href")
            except:
                print("Skipped, could'nt find deletion link")
                continue
            print(amz)
            driver.get("https://kproxy.com")
            driver.find_element(by=By.ID, value="maintextfield").clear()
            driver.find_element(by=By.ID, value="maintextfield").send_keys(amz)
            driver.find_elements(by=By.CLASS_NAME, value="boton")[3].click()
            time.sleep(5)
            if bool(re.search("Save \$[0-9.]{0,}\s.*\(100\%\)", driver.page_source)):
                print("Still Free!")
            else:
                try:
                    # driver.execute_script("window.history.go(-1)")
                    # time.sleep(3)
                    self.delete(de)
                except WebDriverException:
                    print("Couldn't go back!")
                    print("Skipping ", amz)
                    pass
            # break #only check the last link

    def checkbookLink(self):
        w = 1 #wait time
        bookstoCheck = self.getallLinks("https://www.jucktion.com/f/kindle-free-books/")
        print("Validation Started...")
        for i, book in enumerate(bookstoCheck):
            driver = self.d
            print(i + 1, "of", len(bookstoCheck), book)  # print the post link
            driver.get(book)
            amz = driver.find_element(
                by=By.CSS_SELECTOR, value="a.bbc_link[href*=amazon\.com]"
            ).get_attribute("href")
            try:
                de = driver.find_element(
                    by=By.CSS_SELECTOR, value="li.remove_button a"
                ).get_attribute("href")
                ed = driver.find_element(
                    by=By.CSS_SELECTOR, value="li.modify_button a"
                ).get_attribute("href")
            except:
                print("Skipped, could'nt find deletion link")
                continue

            # print(amz)
            asin = re.findall(r"B[0-9A-Z]{9,9}", amz)[0]

            # print(asin)
            try:
                item = amazon.get_items(asin)[0]
                price = item.offers.listings[0].price.display_amount
            except Exception as e:
                #print('Error 196:', traceback.format_exc())
                #self.delete(de)
                continue

            # req = requests.get(amz, headers=self.headers)

            # TO CHECK SOURCE to FILE
            # file = open('file.txt','w')
            # file.write(req.text)
            # file.close()
            # print(req.text)
            # using selenium? driver.page_source
            # if 'To discuss automated access to Amazon data please contact' not in req.text:

            if str(price) == "$0.00":
                print("Still Free!")
            else:
                try:
                    # driver.execute_script("window.history.go(-1)")
                    # time.sleep(3)
                    self.expire(ed, type="")
                    # break #test a delete
                except WebDriverException:
                    print("Couldn't go back!")
                    print("Skipping ", amz)
                    pass
            # else:
            #     logging.error('Blockade!')
            # break #only check the last link

    def expire(self, url, type):
        driver = self.d
        replace = (
            "https://www.jucktion.com/f/uploads/enroll-udemy.png"
            if (type == "udemy")
            else "https://www.jucktion.com/f/uploads/amzbtn.png"
        )
        replacement = (
            "https://www.jucktion.com/f/uploads/expired-udemy-coupon.png"
            if (type == "udemy")
            else "https://www.jucktion.com/f/uploads/amz-expired-button.webp"
        )
        try:
            print("Marking Expired.")
            driver.get(url)
            select = Select(driver.find_element(by=By.ID, value="icon"))
            select.select_by_visible_text("Exclamation point")
            message = driver.find_element(by=By.ID, value="message").get_attribute(
                "value"
            )
            message = message.replace(replace, replacement)
            if driver.find_elements(by=By.NAME, value="message"):
                driver.execute_script(
                    f"document.querySelector('#message').innerHTML = {json.dumps(message)};"
                )
                driver.find_element(
                    by=By.CSS_SELECTOR, value='input[value="Save"]'
                ).click()
        except Exception as e:
            print("This is not working", traceback.format_exc())

    def checkudemyLink(self):
        coursetoCheck = self.getallLinks("https://www.jucktion.com/f/udemy-coupon/")
        print("Validation Started...")
        for i, course in enumerate(coursetoCheck):
            driver = self.d
            # time.sleep(3)
            print(i + 1, "of", len(coursetoCheck), course)  # print the post link

            driver.get(course)
            try:
                de = driver.find_element(
                    by=By.CSS_SELECTOR, value="li.remove_button a"
                ).get_attribute("href")
                ed = driver.find_element(
                    by=By.CSS_SELECTOR, value="li.modify_button a"
                ).get_attribute("href")
            except:
                print("Skipped, could'nt find deletion link")
                continue
            # print(de)
            try:
                # driver.get(driver.find_element_by_css_selector(
                #     'a.bbc_link[href*=udemy\.com]').get_attribute('href'))
                # time.sleep(5)
                ud = driver.find_element(
                    by=By.CSS_SELECTOR, value='a.bbc_link[href*="udemy\.com"]'
                ).get_attribute("href")
                print(ud)
            except:
                print("Malformed: ", course)
            if bool(self.verifyUdemy(ud)):
                print("Still Free!")
            else:
                # driver.execute_script("window.history.go(-1)")
                # time.sleep(1)
                try:
                    self.expire(ed, "udemy")
                    print('Expired')
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    logging.error(traceback.format_exc())
                # break #only check the last link

    def verifyUdemy(self, url):
        parseurl = urlparse(url)
        uurl = "https://www.udemy.com/api-2.0/courses/" + parseurl.path.split("/")[2]
        try:
            coupon = parse_qs(parseurl.query)["couponCode"][0]
        except KeyError:
            coupon = ""
        # print(uurl)
        ar = requests.get(uurl)

        #print(ar.text) #initial course data
        data = json.loads(ar.text)
        if "detail" not in data.keys():
            uuurl = (
                "https://www.udemy.com/api-2.0/course-landing-components/"
                + str(data["id"])
                + "/me/?couponCode="
                + str(coupon)
                + "&components=buy_button"
            )
            #print(uuurl) #check for the coupons validity
            ar = requests.get(uuurl)
            data = json.loads(ar.text)
            #print(data)
            return data["buy_button"]["button"]["is_free_with_discount"]
        else:
            return False

    @staticmethod
    def udemy():
        start = time.time()
        # msg = pb()
        # msg.push('n', "ct", "Automations", "Cleanup Started", channel="nn")
        task = Cleanup()
        try:
            task.login()
            task.checkudemyLink()
            # task.checkbookLink()
        except Exception as e:
            logging.error(traceback.format_exc())
        finally:
            task.stop()
        # print(driver.page_source)
        # driver.quit()
        end = time.time()
        # msg.push('n', 'ct', "Automations", f"Course cleanup completed in {round((end-start)/60,2)} minutes",channel="nn")
        print(end - start)

    @staticmethod
    def books():
        start = time.time()
        # msg = pb()
        # msg.push('n', "ct", "Automations", "Cleanup Started", channel="nn")
        task = Cleanup()
        try:
            task.login()
            # task.checkudemyLink()
            task.checkbookLink()
        except Exception as e:
            logging.error(traceback.format_exc())
        finally:
            task.stop()
        # print(driver.page_source)
        # driver.quit()
        end = time.time()
        # msg.push('n', 'ct', "Automations", f"Course cleanup completed in {round((end-start)/60,2)} minutes",channel="nn")
        print(end - start)


if __name__ == "__main__":
    start = time.time()
    # msg = pb()
    # msg.push('n', "ct", "Automations", "Cleanup Started", channel="nn")
    task = Cleanup()
    try:
        task.login()
        task.checkudemyLink()
        #task.checkbookLink()
    except Exception as e:
        logging.error(traceback.format_exc())
    finally:
        task.stop()
    # print(driver.page_source)
    # driver.quit()
    end = time.time()
    # msg.push('n', 'ct', "Automations", f"Course cleanup completed in {round((end-start)/60,2)} minutes",channel="nn")
    print(end - start)
