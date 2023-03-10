import requests
from lxml import html, etree
from selenium import webdriver
import os
from selenium.webdriver.chrome.options import Options
import re as regex
import threading
from urllib.parse import urlparse, parse_qs
import json
import traceback
import logging
import dbc
import psycopg2
import time
from datetime import datetime, timedelta

logging.basicConfig(filename='udemy.log', filemode='w',
                    format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)


class UniqueViolation(Exception):
    pass


class Udemy:
    def __init__(self):
        self.rss_head, self.rss_foot, self.html_head, self.html_foot = tuple(
            '' for _ in range(4))
        self.xmlitems, self.htmlitems = [], []
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.84 Safari/537.36 Vivaldi/3.3.2022.39'
        }
        self.conn = dbc.connect_pool()
        self.oldcourses = self.getID()
        self.foundcourses, self.newcourses = set(), set()

    def chrome(self):
        options = Options()
        options.binary_location = os.getenv('CHROME')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--incognito')
        options.add_argument('--headless')
        options.add_argument("--disable-gpu")
        # options.add_argument("user-data-dir=C:\\Users\\Administrator\\Desktop\\J\\Chrome\\profile");
        options.add_argument('log-level=2')
        d = webdriver.Chrome(
            options=options, executable_path=os.getenv('CHROMEDRIVER'))

        # d.implicitly_wait(2)
        # print("Chrome Browser Invoked")
    #
    # SQL STUFF
    #

    def addtoDB(self, idprice):
        # val = "('"+id + f"','https://apps.apple.com/us/app/id{id},{price}')"
        val = f"({idprice[0]},'{idprice[1]}','{idprice[2]}')"
        sql = f"INSERT INTO udemy(id,link,price) values {val}"
        try:
            self.sendSQL(sql)

        except UniqueViolation:
            raise Exception
        except Exception as e:
            logging.error(traceback.format_exc())
            print('Couldn\'t Add to DB!')

    # endpoint to send SQL
    def sendSQL(self, sql):
        send = self.conn.getconn()
        try:
            cur = send.cursor()
        except Exception as e:
            print('Exception: ', e)

        try:
            cur.execute(sql)
            send.commit()
        except psycopg2.errors.UniqueViolation:
            raise UniqueViolation
            print("Duplicate Error!")
        except psycopg2.DatabaseError as e:
            print(sql)
            logging.error(traceback.format_exc())
            print('Could not execute insert command', e.pgcode)
            raise Exception
        finally:
            cur.close()
            self.conn.putconn(send)

    def closeSQL(self):
        if self.conn is not None:
            self.conn.closeall()

    def getID(self):
        asin = set()
        try:
            # dbc.cur.execute('SELECT id,price from iapps')
            sql = 'SELECT id from udemy'
            send = dbc.connect()
            cur = send.cursor()
            cur.execute(sql)
            for data in cur.fetchall():
                asin.add(data[0])
        except:
            print('Failed to get data!')
        finally:
            send.close()
            cur.close()
        return asin

    def deleteOld(self):
        # delete the ASINS older than 3 days
        delsql = f"DELETE FROM udemy where added < NOW()-INTERVAL'3 days'"
        try:
            self.sendSQL(delsql)
        except Exception as e:
            print('Could not delete the older records', e)

    def getUdeId(self, url):
        parseurl = urlparse(url)
        uurl = 'https://www.udemy.com/api-2.0/courses/' + \
            parseurl.path.split('/')[2]
        try:
            coupon = parse_qs(parseurl.query)['couponCode'][0]
        except KeyError:
            coupon = ''
        ar = requests.get(uurl)
        data = json.loads(ar.text)
        return {'id': str(data['id']), 'link': 'https://www.udemy.com/course/'+parseurl.path.split('/')[2]+'/?couponCode='+coupon, 'title': data['title'], 'price': str(data['price'].strip('$')), 'coupon': coupon}

    # SQL STUFF END

    def csq(self, url):
        re = requests.get(url)
        q = regex.findall('''(?<=sf_offer_url = ')(.*)(?=';)''', re.text)
        try:
            query = 'https://couponscorpion.com/scripts/udemy/out.php?go='+q[0]
            # print(query)
            try:
                re = requests.get(query, headers=self.headers)
                if self.verifyUdemy(re.url):
                    logging.info(f'FREE: {re.url}')
                    self.createPages(re.url, 'both')
                else:
                    logging.info(f'NOT: {re.url}')

            except Exception as e:
                print('Failed: ', query)
                logging.error(traceback.format_exc())
        except IndexError:
            logging.info(
                f'IndexError Failure:{re.url}')

    def createPages(self, url, kind):
        # get course details for the current url
        details = self.getUdeId(url)
        if int(details['id']) not in self.oldcourses and int(details['id']) not in self.foundcourses:
            # add new course id to the list
            self.foundcourses.add(int(details['id']))
        # add the new items to db
            self.addtoDB(
                [details['id'], details['link'], details['price']])
            now = datetime.utcnow()
            rss = now.strftime("%a, %d %b %Y %H:%M:%S +0000")
            if kind == 'xml' or kind == 'both':
                self.xmlitems.append('''
    <item>
        <title><![CDATA[''' + details['title'] + ' ' + details['price']+''']]></title>
        <description><![CDATA[''' + details['title']+''']]></description>
        <link>''' + details['link'] + '''</link>
        <guid>https://www.udemy.com/course/''' + details['id'] + '''</guid>
        <pubDate>''' + rss + '''</pubDate>
    </item>''')

            if kind == 'html' or kind == 'both':
                self.htmlitems.append('''
                    <li><a target="_blank" href="''' + details['link'] + '''">''' + details['title'] + details['price'] + '''</a></li>
                ''')

    def cs(self, page):
        linklist = []
        logging.info('Crawling couponscorpion...')
        url = 'https://couponscorpion.com'
        for p in range(1, page+1):
            curl = url + '/page/' + str(p) + '/'
            re = requests.get(curl)
            # file = open('source.txt', 'w')
            # file.write(re.text)
            # file.close()
            tree = html.fromstring(re.content)
            logging.info(f'Page: {p}')
            # for e in tree.xpath('//span[contains(text(),"100% OFF")]/following-sibling::a/@href'):
            for x in tree.xpath('//span[contains(text(),"100% OFF")]/following-sibling::a/@href'):
                linklist.append(x)
                logging.info(x)
        logging.info(f'{len(linklist)} links found in couponscorpion')
        logging.info("Udemy links from couponscorpion tracking links:")
        threads = list()
        for e in reversed(linklist):
            x = threading.Thread(target=self.csq, args=(e,))
            threads.append(x)
            x.start()

        for t in threads:
            t.join()

    def fg(self):
        url = 'https://freebiesglobal.com/tag/udemy-100-off/feed'
        logging.info('Crawling freebiesglobal...')
        re = requests.get(url)
        collection = []
        tree = etree.fromstring(bytes(re.text, encoding='utf-8'))
        for e in tree.xpath('//item/link'):
            re = requests.get(e.text)
            try:
                tree = html.fromstring(re.text).xpath(
                    '//div/a[contains(@href,"couponCode")]/@href')
            except:
                print('Failed:', re.url)
                logging.error(traceback.format_exc())
            if tree:
                collection.append(tree[0])
                logging.info(tree[0])
        logging.info(f'{len(collection)} links found in freebiesglobal')
        threads = list()
        for item in reversed(collection):
            if self.verifyUdemy(item):
                logging.info(f'FREE: {item}')
                x = threading.Thread(
                    target=self.createPages, args=(item, 'both',))
                threads.append(x)
                x.start()
            else:
                logging.info(f'NOT: {item}')
        for x in threads:
            x.join()
        # for item in tree:
        #     if self.verifyUdemy(item):
        #         print(item)

    def verifyUdemy(self, url):
        parseurl = urlparse(url)
        uurl = 'https://www.udemy.com/api-2.0/courses/' + \
            parseurl.path.split('/')[2]
        try:
            coupon = parse_qs(parseurl.query)['couponCode'][0]
        except KeyError:
            coupon = ''
        # print(uurl)
        ar = requests.get(uurl)

        # print(ar.text)  # initial course data
        data = json.loads(ar.text)
        if 'detail' not in data.keys():
            uuurl = 'https://www.udemy.com/api-2.0/course-landing-components/' + \
                str(data['id']) + '/me/?couponCode=' + \
                str(coupon) + '&components=buy_button'
            # print(uuurl) #check for the coupons validity
            ar = requests.get(uuurl)
            data = json.loads(ar.text)
            # print(data)
            return data['buy_button']['button']['is_free_with_discount']
        else:
            return False

    # Get and manage data

    def writeXML(self):
        self.rss_head = '''<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"
	xmlns:content="http://purl.org/rss/1.0/modules/content/"
	xmlns:wfw="http://wellformedweb.org/CommentAPI/"
	xmlns:dc="http://purl.org/dc/elements/1.1/"
	xmlns:atom="http://www.w3.org/2005/Atom"
	xmlns:sy="http://purl.org/rss/1.0/modules/syndication/"
	xmlns:slash="http://purl.org/rss/1.0/modules/slash/"
	>

<channel>
	<title>Freebies Global</title>
	<atom:link href="https://freebiesglobal.com/feed" rel="self" type="application/rss+xml" />
	<link>https://freebiesglobal.com</link>
	<description>Free Udemy, BitDegree, Skillshare &#38; More Online Courses</description>
	<lastBuildDate>Mon, 07 Sep 2020 14:35:10 +0000</lastBuildDate>
	<language>en-US</language>
	<sy:updatePeriod>hourly</sy:updatePeriod>
	<sy:updateFrequency>1</sy:updateFrequency>
	

<image>
        <url>https://media.freebiesglobal.com/2019/01/FreebiesGlobalIcon-1-150x150.png</url>
        <title>Freebies Global</title>
        <link>https://freebiesglobal.com</link>
        <width>32</width>
        <height>32</height>
</image> 
    '''

        self.rss_foot = '''
</channel>
</rss>'''
        files = open('feed.xml', 'w')
        content = self.rss_head + \
            str(''.join(reversed(self.xmlitems))) + self.rss_foot
        files.write(content)
        files.close()

    def writeHTML(self):
        self.html_head = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Document</title>
    <style>
    html {
        background-color: #1d1919;
        color: blanchedalmond;
    }
    a {
        color: darkgray;
    }
    a:visited {
        color: coral;
    }
    </style>
</head>
<body>
    <div class="container">
        <ol>'''
        self.html_foot = '''
        </ol>
    </div>
</body>
</html>'''
        files = open('feed.html', 'w')
        content = self.html_head + \
            str(''.join(reversed(self.htmlitems))) + self.html_foot
        files.write(content)
        files.close()

    def manageID(self):
        # self.deleteOld()
        self.couponscorpion(2, 'both')
        self.newcourses = list(self.foundcourses.difference(self.oldcourses))


if __name__ == "__main__":
    start = time.time()
    ud = Udemy()
    ud.deleteOld()
    # ud.couponscorpion(7, 'both')
    # ud.writeXML()
    # print(len(ud.oldcourses))
    ud.cs(7)
    ud.fg()
    # print(ud.foundcourses)
    ud.newcourses = ud.foundcourses.difference(ud.oldcourses)
    # print(ud.newcourses)
    ud.writeHTML()
    # ud.writeXML()
    ud.closeSQL()
    end = time.time()
    print(len(ud.newcourses), 'course id found in',
          round((end-start)/60, 2), 'minutes')
