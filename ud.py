import os
from lxml import html, etree
import re as regex
import threading
from urllib.parse import urlparse, parse_qs, quote
import json
import traceback
import logging
import dbc
import psycopg
from psycopg import sql as query
import time
from datetime import datetime
import concurrent.futures
import cloudscraper
import random as rand


# print(os.environ)
PUBOLD = "1 hour"
try:
    # INTERVAL = int(os.environ['INTERVAL'])
    DEPLOYED = int(os.environ["DEPLOYED"])
    BOT = os.environ["BOT"]
    CHATID = os.environ["CHATID"]
    # PUBOLD = os.environ['PUBOLD']
    UD_CS = os.environ["UD_CS"]
    UD_FG = os.environ["UD_FG"]
    UD_IH = os.environ["UD_IH"]
    UD_DU = os.environ["UD_DU"]
    UD_AF = os.environ["UD_AF"]
    UD_FA = os.environ["UD_FA"]
    DEBUG = int(os.environ["DEBUG"])
    PRXY = os.environ["PRXY"]
    USE_PRXY = int(os.environ["USE_PRXY"])
    THREADS = int(os.environ["THREADS"])
    HIDE = int(os.environ["HIDE"])
except KeyError:
    INTERVAL = 3600
    BOT = ""
    CHATID = ""
    from secrets import (
        DEBUG,
        DEPLOYED,
        UD_CS,
        UD_IH,
        UD_FG,
        UD_DU,
        PRXY,
        USE_PRXY,
        THREADS,
        UD_AF,
        UD_FA,
        HIDE,
    )

if DEBUG:
    logging.basicConfig(
        filename="udemy.log",
        filemode="w",
        format="%(asctime)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )


class UniqueViolation(Exception):
    pass


class Udemy:
    def __init__(self):
        self.rss_head, self.rss_foot, self.html_head, self.html_foot = tuple(
            "" for _ in range(4)
        )
        self.xmlitems, self.htmlitems = [], []
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.84 Safari/537.36 Vivaldi/3.3.2022.39"
        }
        self.conn = dbc.connect_pool()
        self.foundcourses, self.newcourses, self.rsscourses = set(), set(), set()
        self.oldcourses = self.getID()
        self.oldlinks = self.getLinks()
        self.tags = set()
        print(DEPLOYED, BOT, CHATID)
        session = cloudscraper.create_scraper()
        self.scraper = cloudscraper.create_scraper(
            browser={"browser": "firefox", "platform": "windows", "mobile": False},
            interpreter="nodejs",
            sess=session,
        )
        self.proxy = {"http": PRXY, "https": PRXY}
        self.threads = THREADS

    #
    # SQL STUFF
    #

    def addtoDB(self, idprice: list):
        # val = "('"+id + f"','https://apps.apple.com/us/app/id{id},{price}')"
        # format cid[0],price[1],image[2],title[3],desc[4],pub[5],link[6]
        sql = """INSERT INTO {}(cid,price,image,title,des,pub,link,source) values(%s,%s,%s,%s,%s,%s,%s,%s)"""
        try:
            self.sendSQL(sql, idprice)
        except UniqueViolation:
            raise Exception
        except Exception as e:
            logging.error(traceback.format_exc(), e)
            print("Couldn't Add to DB!")

    # endpoint to send SQL
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

    def closeSQL(self):
        if self.conn is not None:
            self.conn.close()

    def getID(self):
        asin = set()
        try:
            # dbc.cur.execute('SELECT id,price from iapps')
            sql = "SELECT cid from udemy"
            send = dbc.connect()
            cur = send.cursor()
            cur.execute(sql)
            for data in cur.fetchall():
                asin.add(data[0])
        except Exception:
            print("Failed to get data!")
        finally:
            send.close()
            cur.close()
        return asin

    def getLinks(self):
        links = set()
        try:
            # dbc.cur.execute('SELECT id,price from iapps')
            sql = "SELECT source from udemy"
            send = dbc.connect()
            cur = send.cursor()
            cur.execute(sql)
            for data in cur.fetchall():
                links.add(data[0])
        except Exception:
            print("Failed to get data!")
        finally:
            send.close()
            cur.close()
        return links

    def deleteOld(self):
        # delete the ASINS older than 3 days
        delsql = "delete from udemy where pdate < NOW()-INTERVAL'3 days'"
        try:
            self.sendSQL(delsql)
        except Exception as e:
            print("Could not delete the older records", e)

    def updateOld(self):
        # update old post to published after 30 minutes
        delsql = f"UPDATE udemy SET pub = 1 WHERE pdate < NOW()-INTERVAL'{PUBOLD}' AND pub = 0"
        try:
            self.sendSQL(delsql)
        except Exception as e:
            print("Could not update the older records", e)

    def cleanDesc(self, title: str, des: str, img: str, link: str):
        import re

        alt = re.sub(r"\[.*?\]", "", title)
        alt = alt.strip()
        desc = (
            des.replace("<li>", "-")
            .replace("<strong>", "[b]")
            .replace("</strong>", "[/b]")
        )
        sdesc = desc.split("</p>")
        clean = []
        for p in sdesc:
            a = re.sub(r"<.*?>", "", p, flags=re.M)
            b = re.sub(r"[\s]{2,}", "", a, flags=re.M)
            clean.append(b)
        desc = "\n\n".join(clean)

        hide_string = "[hide]" if HIDE else ""
        hide_end_string = "[/hide]" if HIDE else ""

        cdesc = f"[img alt={alt}]{img}[/img]\n\n{desc}\
\n\n\
{hide_string}\
[url=#][img alt=Button to link to the udemy course]https://www.jucktion.com/forum/uploads/enroll-udemy.png[/img][/url][url=https://www.jucktion.com/forum/udemy-coupon/?utm_source=forum&utm_campaign=more-udemy-coupons][img alt=Button to check more free udemy coupons]https://www.jucktion.com/forum/uploads/more-udemy-coupons.png[/img][/url]\
{hide_end_string}\
[html]<script>var linko='{rand.choice([UD_AF, UD_FA])}{quote(link)}';document.querySelector('.bbc_link').href=linko;</script>[/html]\
\n\n\n[sub]Please note: As an affiliate partner with Udemy, this post includes affiliate links. Purchasing any course through these links may earn me a commission, but please buy only if it aligns with your needs. Thanks for your support![/sub]"

        return cdesc

    def getUdeId(self, url: str):
        cname = urlparse(url).path.split("/")[2]
        uurl = (
            "https://www.udemy.com/api-2.0/courses/"
            + cname
            + "?fields[course]=price,title,image_480x270,description"
        )
        try:
            coupon = parse_qs(urlparse(url).query)["couponCode"][0]
        except KeyError:
            coupon = ""
        data = json.loads(self.scraper.get(uurl).text)
        link = "https://www.udemy.com/course/" + cname + "/?couponCode=" + coupon
        desc = self.cleanDesc(
            data["title"], data["description"], data["image_480x270"], link
        )
        return {
            "id": str(data["id"]),
            "price": (data["price"]),
            "image": str(data["image_480x270"]),
            "title": str(data["title"]),
            "desc": str(desc),
            "pub": str(1),
            "link": str(link),
            "coupon": str(coupon),
        }

    # SQL STUFF END

    # Add to DB without creating html or xml pages
    def addNew(self, url: str, source: str):
        # get course details for the current url
        details = self.getUdeId(url)
        notneeded = self.oldcourses.union(self.foundcourses)
        if int(details["id"]) not in notneeded:
            # add new course id to the list
            self.foundcourses.add(int(details["id"]))
            # add the new items to db
            newtitle = (
                f"{details['title'].replace('&', 'and')} ({details['price']} to FREE)"
            )
            # format cid,price,image,title,desc,pub,link
            data = [
                details["id"],
                details["price"],
                details["image"],
                newtitle,
                details["desc"],
                details["pub"],
                details["link"],
                source,
            ]
            # print(data)
            self.addtoDB(data)

    def createPages(self, url: str, kind: str):
        # get course details for the current url
        details = self.getUdeId(url)
        notneeded = self.oldcourses.union(self.foundcourses)
        if int(details["id"]) not in notneeded:
            # add new course id to the list
            self.foundcourses.add(int(details["id"]))
            # add the new items to db
            # format cid,price,image,title,desc,pub,link
            data = [
                details["id"],
                details["price"],
                details["image"],
                details["title"],
                details["desc"],
                details["pub"],
                details["link"],
            ]
            # print(data)
            self.addtoDB(data)
            now = datetime.utcnow()
            rss = now.strftime("%a, %d %b %Y %H:%M:%S +0000")
            if kind == "xml" or kind == "both":
                self.xmlitems.append(
                    """
    <item>
        <title><![CDATA["""
                    + details["title"]
                    + " "
                    + details["price"]
                    + """]]></title>
        <description><![CDATA["""
                    + details["title"]
                    + """]]></description>
        <link>"""
                    + details["link"]
                    + """</link>
        <guid>https://www.udemy.com/course/"""
                    + details["id"]
                    + """</guid>
        <pubDate>"""
                    + rss
                    + """</pubDate>
    </item>"""
                )

            if kind == "html" or kind == "both":
                self.htmlitems.append(
                    '''
                    <li><a target="_blank" href="'''
                    + details["link"]
                    + """">"""
                    + details["title"]
                    + details["price"]
                    + """</a></li>
                """
                )

    def checkAdd(self, url: str, source: str):
        if self.unique(url):
            try:
                if self.verifyUdemy(url):
                    if not DEPLOYED:
                        logging.info(f"FREE: {url}")
                    self.addNew(url, source)
                else:
                    logging.info(f"NOT: {url}")
            except Exception as e:
                logging.error("Exception logged", e)
        else:
            logging.info("Coupon already checked! ")

    def multiThread(self, threads: int, collection: list, function):
        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(function, url): url for url in collection}
            for future in concurrent.futures.as_completed(futures):
                try:
                    url = futures[future]
                except Exception as exc:
                    print("%r generated an exception: %s" % (url, exc))

    def cs(self, page: int):
        collection = []
        logging.info("Crawling CS...")
        logging.info(f"Using Proxy: {USE_PRXY}")
        for p in range(1, page + 1):
            curl = UD_CS + "/page/" + str(p) + "/"
            re = (
                self.scraper.get(curl, proxies=self.proxy)
                if USE_PRXY
                else self.scraper.get(curl)
            )
            # with open('source.txt', 'w') as file:
            #     file.write(re.text)
            # break
            tree = html.fromstring(re.content)
            logging.info(f"Page: {p}")
            # for e in tree.xpath('//span[contains(text(),"100% OFF")]/following-sibling::a/@href'):
            for x in tree.xpath(
                '//div[@class="newsdetail newstitleblock rh_gr_right_sec"]/h2/a/@href'
            ):
                collection.append(x)
                if DEBUG:
                    logging.info(x)
        logging.info(f"{len(collection)} links found in CS")
        logging.info("Udemy links from CS tracking links:")
        collection = reversed(collection)
        self.multiThread(self.threads, collection, self.csq)
        # threads = list()
        # for e in reversed(linklist):
        #     x = threading.Thread(target=self.csq, args=(e,))
        #     threads.append(x)
        #     x.start()

        # for t in threads:
        #     t.join()

    def csq(self, source: str):
        if source not in self.oldlinks:
            rq = (
                self.scraper.get(source, headers=self.headers, proxies=self.proxy).text
                if USE_PRXY
                else self.scraper.get(source, headers=self.headers).text
            )
            q = regex.findall("""(?<=sf_offer_url = ')(.*)(?=';)""", rq)
            try:
                query = f"{UD_CS}/scripts/udemy/out.php?go=" + q[0]
                # print(query)
                try:
                    re = self.scraper.get(query, headers=self.headers)
                    self.checkAdd(re.url, source)

                except Exception as e:
                    print("Failed: ", query)
                    logging.error(traceback.format_exc(), e)
            except IndexError:
                logging.info(f"IndexError Failure:{re.url}")
        else:
            logging.info("CS link already checked, skipping")

    def du(self, page: int):
        logging.info("Crawling DU")
        collection = []
        for p in range(1, page):
            re = self.scraper.get(f"{UD_DU}/all/{str(p)}")
            if DEBUG:
                logging.info(f"{UD_DU}/all/{str(p)}")
            tree = html.fromstring(bytes(re.text, encoding="utf-8"))
            for e in tree.xpath(
                "//span[contains(@style,'text-decoration: line-through;color: rgb(33, 186, 69);')]/ancestor::div/div/a[contains(@class,'card-header')]/@href"
            ):
                collection.append(e)
        logging.info(f"DU Links found: {len(collection)}")
        self.multiThread(self.threads, collection, self.duq)

    def duq(self, source: str):
        if source not in self.oldlinks:
            if DEBUG:
                logging.info(f"Crawling: {source}")
            re = self.scraper.get(f"{UD_DU}/go/{source.split('/')[-1]}")
            tree = html.fromstring(bytes(re.text, encoding="utf-8"))
            url = tree.xpath('//a[contains(@href,"couponCode=")]/@href')[0]
            logging.info(f"Found: {url}")
            self.checkAdd(url, source)
        else:
            logging.info("DU link already checked, skipping")

    def iv(self):
        logging.info("Crawling IH")
        re = self.scraper.get(f"{UD_IH}/fetchdata?filter=latest")
        # logging.info(re.text)
        collection = []
        tree = html.fromstring(bytes(re.text, encoding="utf-8"))
        for e in tree.xpath('//a[contains(text(),"Enroll Now")]/@href'):
            url = e.split("murl=")[1]
            collection.append(f"{url}")
        logging.info(f"IH Links found: {len(collection)}")

        self.multiThread(self.threads, collection, self.ivq)

    def ivq(self, source: str):
        if source not in self.oldlinks:
            if not DEPLOYED:
                logging.info(f"Crawling: {source}")
            self.checkAdd(source, source)
        else:
            logging.info("IV link already checked, skipping")

    def fg(self):
        logging.info("Crawling FG...")
        re = self.scraper.get(UD_FG)
        collection = []
        tree = etree.fromstring(bytes(re.text, encoding="utf-8"))
        for e in tree.xpath("//item/link"):
            collection.append(e.text)
            if not DEPLOYED:
                logging.info(e.text)
        logging.info(f"{len(collection)} links found in FG")
        threads = list()
        for item in reversed(collection):
            x = threading.Thread(target=self.fgq, args=(item,))
            threads.append(x)
            x.start()
        for x in threads:
            x.join()
        # for item in tree:
        #     if self.verifyUdemy(item):
        #         print(item)

    def fgq(self, source: str):
        if source not in self.oldlinks:
            re = self.scraper.get(source)
            try:
                tree = html.fromstring(re.text).xpath(
                    '//div/a[contains(@href,"couponCode")]/@href'
                )
            except Exception:
                print("Failed:", re.url)
                logging.error(traceback.format_exc())
            if tree:
                url = tree[0]
                self.checkAdd(url, source)
        else:
            logging.info("FG link already checked, skipping")

    def unique(self, url: str):
        tag = urlparse(url).path.split("/")[2]
        try:
            coupon = parse_qs(urlparse(url).query)["couponCode"][0]
            check = f"{tag},{coupon}"
            if check not in self.tags:
                self.tags.add(check)
                return True
            else:
                return False
        except Exception:
            return False

    def verifyUdemy(self, url):
        uurl = (
            "https://www.udemy.com/api-2.0/courses/" + urlparse(url).path.split("/")[2]
        )
        try:
            coupon = parse_qs(urlparse(url).query)["couponCode"][0]
        except KeyError:
            coupon = ""
        # logging.info(uurl)
        try:
            response = (
                self.scraper.get(uurl, proxies=self.proxy).text
                if USE_PRXY
                else self.scraper.get(uurl).text
            )
            if DEBUG:
                logging.info(f"First Response: {response}")
            data = json.loads(response)
            if "detail" not in data.keys():
                uuurl = (
                    "https://www.udemy.com/api-2.0/course-landing-components/"
                    + str(data["id"])
                    + "/me/?couponCode="
                    + str(coupon)
                    + "&components=buy_button"
                )
                logging.info(uuurl)  # check for the coupons validity
                response = (
                    self.scraper.get(uuurl, proxies=self.proxy).text
                    if USE_PRXY
                    else self.scraper.get(uuurl).text
                )
                if DEBUG:
                    logging.info(f"Second Response: {response}")
                try:
                    data = json.loads(response)
                    logging.info(data)
                    return data["buy_button"]["button"]["is_free_with_discount"]
                except Exception as e:
                    logging.error(
                        f"Response is not formatted: {response}, Exception: {e}"
                    )
                    return False

            else:
                logging.info(data)
                return False
        except Exception as e:
            logging.error(f"Exception occured while trying to verify {e}")

    def manageID(self):
        # self.deleteOld()
        self.cs(2)
        self.newcourses = list(self.foundcourses.difference(self.oldcourses))


if __name__ == "__main__":
    start = time.perf_counter()
    ud = Udemy()
    ud.deleteOld()
    ud.updateOld()
    # ud.writeXML()
    # print(len(ud.oldcourses))
    # print(ud.oldcourses)
    # print(ud.rsscourses)

    if DEPLOYED:
        try:
            ud.du(5)
        except Exception as e:
            logging.error("DU website has failed", e)
        try:
            ud.iv()
        except Exception as e:
            logging.error("IH website has failed", e)
        # try:
        #     ud.fg()
        # except Exception as e:
        #     logging.error("FG website has failed", e)
    else:
        try:
            ud.cs(5)
        except Exception as e:
            logging.error("CS website has failed", e)

    # print(ud.foundcourses)
    ud.newcourses = ud.foundcourses.difference(ud.oldcourses)
    # print(ud.newcourses)
    # ud.writeHTML()
    # ud.writeXML()
    ud.closeSQL()
    end = time.perf_counter()
    print(
        len(ud.newcourses),
        "courses id found in",
        round((end - start) / 60, 2),
        "minutes",
    )

    if len(ud.newcourses) > 0:
        tg = (
            "https://api.telegram.org/bot"
            + BOT
            + "/sendMessage?chat_id="
            + CHATID
            + "&text="
        )
        msg = f"{len(ud.newcourses)} courses found in {round((end - start) / 60, 2)} minutes"
        ud.scraper.get(tg + msg)
    # if DEPLOYED == 1:
    #     print(f'waiting for: {str(round(INTERVAL/60,2))} minutes')
    #     time.sleep(INTERVAL)
