import os
import requests
from lxml import html, etree
import re as regex
import threading
from urllib.parse import urlparse, parse_qs
import json
import traceback
import logging
import dbc
import psycopg2
from psycopg2 import sql as query
import time
from datetime import datetime, timedelta
import concurrent.futures
import cloudscraper


#print(os.environ)
PUBOLD ='1 hour'
try:
    #INTERVAL = int(os.environ['INTERVAL'])
    DEPLOYED = int(os.environ['DEPLOYED'])
    BOT = os.environ['BOT']
    CHATID = os.environ['CHATID']
    #PUBOLD = os.environ['PUBOLD']
    UD_CS = os.environ['UD_CS']
    UD_FG = os.environ['UD_FG']
    UD_IH = os.environ['UD_IH']
    UD_DU = os.environ['UD_DU']
    DEBUG = int(os.environ['DEBUG'])
    PRXY = os.environ['PRXY']
    THREADS = int(os.environ['THREADS'])
except KeyError:
    INTERVAL = 3600
    BOT = ''
    CHATID = ''
    from secrets import DEBUG, DEPLOYED, UD_CS, UD_IH, UD_FG, UD_DU, PRXY, THREADS

if DEBUG:
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
        self.foundcourses, self.newcourses, self.rsscourses = set(), set(), set()
        self.oldcourses = self.getID()
        self.oldlinks = self.getLinks()
        self.tags = set()
        print(DEPLOYED,BOT,CHATID)
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'firefox',
                'platform': 'windows',
                'mobile': False
            }
        )
        self.proxy = {
            'http': PRXY,
            'https': PRXY
        }
        self.threads = THREADS
    #
    # SQL STUFF
    #

    def addtoDB(self, idprice: list):
        # val = "('"+id + f"','https://apps.apple.com/us/app/id{id},{price}')"
        #format cid[0],price[1],image[2],title[3],desc[4],pub[5],link[6]
        sql = '''INSERT INTO {}(cid,price,image,title,des,pub,link,source) values(%s,%s,%s,%s,%s,%s,%s,%s)'''
        try:
            self.sendSQL(sql, idprice)
        except UniqueViolation:
            raise Exception
        except Exception as e:
            logging.error(traceback.format_exc(),e)
            print('Couldn\'t Add to DB!')

    # endpoint to send SQL
    def sendSQL(self, sql: str, val=None):
        try:
            # send = self.conn.getconn()
            with self.conn.getconn() as send, send.cursor() as cur:
                # try:
                #     cur = send.cursor()

                # except Exception as e:
                #     print('Exception: ', e)
                try:
                    if val:
                        #sqlr = query.SQL(sql).format(query.Identifier('data'))
                        #print(sqlr.as_string(send))
                        cur.execute(query.SQL(sql).format(query.Identifier('udemy')),val)
                    else:
                        cur.execute(sql)
                        send.commit()
                except psycopg2.errors.UniqueViolation:
                    print("Duplicate Error!")
                    raise UniqueViolation
                except psycopg2.DatabaseError as e:
                    print(sql)
                    logging.error(traceback.format_exc())
                    print('Could not execute command', e.pgcode)
                    raise Exception
                finally:
                    cur.close()
        finally:
            self.conn.putconn(send)

    def closeSQL(self):
        if self.conn is not None:
            self.conn.closeall()

    def getID(self):
        asin = set()
        try:
            # dbc.cur.execute('SELECT id,price from iapps')
            sql = 'SELECT cid from udemy'
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
    
    def getLinks(self):
        links = set()
        try:
            # dbc.cur.execute('SELECT id,price from iapps')
            sql = 'SELECT source from udemy'
            send = dbc.connect()
            cur = send.cursor()
            cur.execute(sql)
            for data in cur.fetchall():
                links.add(data[0])
        except:
            print('Failed to get data!')
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
            print('Could not delete the older records', e)

    def updateOld(self):
        #update old post to published after 30 minutes
        delsql = f"UPDATE udemy SET pub = 1 WHERE pdate < NOW()-INTERVAL'{PUBOLD}' AND pub = 0"
        try:
            self.sendSQL(delsql)
        except Exception as e:
            print('Could not update the older records', e)

    def cleanDesc(self,title: str,des: str,img: str,link: str):
        import re
        alt = re.sub(r'\[.*?\]','', title)
        alt = alt.strip()
        desc = des.replace('<li>', '-').replace('<strong>', '[b]').replace('</strong>', '[/b]')
        sdesc = desc.split('</p>')
        clean = []
        for p in sdesc:
            a = re.sub(r'<.*?>','',p,flags=re.M)
            b = re.sub(r'[\s]{2,}','',a,flags=re.M)
            clean.append(b)
        desc = '\n\n'.join(clean)
        
        cdesc = f'[img alt={alt}]{img}[/img]\n\n{desc}\n\n[hide][url={link}&utm_source=jucktion&utm_medium=forum&utm_campaign=udemy%20coupon][img alt=Enroll button]https://www.jucktion.com/forum/uploads/enroll-udemy.png[/img][/url][url=https://www.jucktion.com/forum/udemy-coupon/?utm_source=forum&utm_campaign=more-udemy-coupons][img alt=Check more free udemy coupons]https://www.jucktion.com/forum/uploads/more-udemy-coupons.png[/img][/url][/hide]'
        return cdesc

    def getUdeId(self, url: str):
        cname = urlparse(url).path.split('/')[2]
        uurl = 'https://www.udemy.com/api-2.0/courses/' + cname +'?fields[course]=price,title,image_480x270,description'
        try:
            coupon = parse_qs(urlparse(url).query)['couponCode'][0]
        except KeyError:
            coupon = ''
        data = json.loads(requests.get(uurl).text)
        link = 'https://www.udemy.com/course/'+cname+'/?couponCode='+coupon
        desc = self.cleanDesc(data['title'],data['description'],data['image_480x270'],link)
        return {'id': str(data['id']), 'price': (data['price']), 'image': str(data['image_480x270']),'title': str(data['title']),'desc': str(desc),'pub':str(1),'link': str(link), 'coupon': str(coupon)}

    # SQL STUFF END

    #Add to DB without creating html or xml pages
    def addNew(self, url: str, source: str):
        
        # get course details for the current url
        details = self.getUdeId(url)
        notneeded = self.oldcourses.union(self.foundcourses)
        if int(details['id']) not in notneeded:
            # add new course id to the list
            self.foundcourses.add(int(details['id']))
            # add the new items to db
            newtitle = f"{details['title'].replace('&', 'and')} ({details['price']} to FREE)"
            #format cid,price,image,title,desc,pub,link
            data = [details['id'],details['price'],details['image'],newtitle,details['desc'],details['pub'],details['link'], source]
            #print(data)
            self.addtoDB(data)

    def createPages(self, url: str, kind: str):
        # get course details for the current url
        details = self.getUdeId(url)
        notneeded = self.oldcourses.union(self.foundcourses)
        if int(details['id']) not in notneeded:
            # add new course id to the list
            self.foundcourses.add(int(details['id']))
        # add the new items to db
        #format cid,price,image,title,desc,pub,link
            data = [details['id'],details['price'],details['image'],details['title'],details['desc'],details['pub'],details['link']]
            #print(data)
            self.addtoDB(data)
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
    def checkAdd(self, url: str, source: str):
        if self.unique(url):
            if self.verifyUdemy(url):
                if not DEPLOYED:
                    logging.info(f'FREE: {url}')
                self.addNew(url,source)
            else:
                logging.info(f'NOT: {url}')
        else:
            logging.info(f'Already checked! ')
    
    def multiThread(self, threads: int, collection: list, function):
        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as executor:
            futures = {executor.submit(function, url): url for url in collection}
            for future in concurrent.futures.as_completed(futures):
                try:
                    url = futures[future]
                except Exception as exc:
                    print('%r generated an exception: %s' % (url, exc))

    def cs(self, page: int):
        collection = []
        logging.info('Crawling CS...')
        for p in range(1, page+1):
            curl = UD_CS + '/page/' + str(p) + '/'
            re = self.scraper.get(curl, proxies= self.proxy)
            # with open('source.txt', 'w') as file:
            #     file.write(re.text)
            # break
            tree = html.fromstring(re.content)
            logging.info(f'Page: {p}')
            # for e in tree.xpath('//span[contains(text(),"100% OFF")]/following-sibling::a/@href'):
            for x in tree.xpath('//span[contains(text(),"100% OFF")]/following-sibling::a/@href'):
                collection.append(x)
                if not DEPLOYED:
                    logging.info(x)
        logging.info(f'{len(collection)} links found in CS')
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
            q = regex.findall('''(?<=sf_offer_url = ')(.*)(?=';)''', self.scraper.get(source, headers=self.headers, proxies=self.proxy).text)
            try:
                query = f'{UD_CS}/scripts/udemy/out.php?go='+q[0]
                # print(query)
                try:
                    re = requests.get(query, headers=self.headers)
                    self.checkAdd(re.url, source)

                except Exception as e:
                    print('Failed: ', query)
                    logging.error(traceback.format_exc(),e)
            except IndexError:
                logging.info(
                    f'IndexError Failure:{re.url}')
        else:
            logging.info('Link already checked, skipping')
        
    def du(self,page: int):
        logging.info('Crawling DU')
        collection = []
        for p in range(1, page):
            re = self.scraper.get(UD_DU + str(p))
            if DEBUG:
                logging.info(f'{UD_DU + str(p)}')
            tree = html.fromstring(bytes(re.text, encoding='utf-8'))
            for e in tree.xpath("//span[contains(@style,'text-decoration: line-through;color: rgb(33, 186, 69);')]/ancestor::div/div/a[contains(@class,'card-header')]/@href"):
                collection.append(e)
        logging.info(f'DU Links found: {len(collection)}')
        self.multiThread(self.threads, collection, self.duq)
    
    def duq(self, source: str):
        if source not in self.oldlinks:
            if not DEPLOYED:
                logging.info(f'Crawling: {source}')
            re = self.scraper.get("https://www.discudemy.com/go/"+source.split("/")[-1])
            tree = html.fromstring(bytes(re.text, encoding='utf-8'))
            url = tree.xpath('//a[contains(@id,"couponLink")]/@href')[0]

            self.checkAdd(url,source)
        else:
            logging.info('Link already checked, skipping')


    def iv(self):
        logging.info('Crawling IH')
        re = self.scraper.get(f'{UD_IH}/course')
        collection = []
        tree = html.fromstring(bytes(re.text, encoding='utf-8'))
        for e in tree.xpath('//a[contains(@class,"btndarkgrid")]/@href'):
            collection.append(f'{UD_IH}/{e}')
        logging.info(f'IH Links found: {len(collection)}')

        self.multiThread(self.threads, collection, self.ivq)
    
    def ivq(self, source: str):
        if source not in self.oldlinks:
            re = self.scraper.get(source)
            if not DEPLOYED:
                logging.info(f'Crawling: {source}')
            tree = html.fromstring(bytes(re.text, encoding='utf-8'))
            link = tree.xpath("(//a[contains(@id,'couponval')])[1]/@href")
            url = link[0].split('murl=')[1]
            if not DEPLOYED:
                logging.info(f'Checking: {url}')
            self.checkAdd(url, source)
        else:
            logging.info('Link already checked, skipping')

    def fg(self):
        logging.info('Crawling FG...')
        re = requests.get(UD_FG)
        collection = []
        tree = etree.fromstring(bytes(re.text, encoding='utf-8'))
        for e in tree.xpath('//item/link'):
            collection.append(e.text)
            if not DEPLOYED:
                logging.info(e.text)
        logging.info(f'{len(collection)} links found in FG')
        threads = list()
        for item in reversed(collection):
                x = threading.Thread(
                    target=self.fgq, args=(item,))
                threads.append(x)
                x.start()
        for x in threads:
            x.join()
        # for item in tree:
        #     if self.verifyUdemy(item):
        #         print(item)
    def fgq(self, source: str):
        if source not in self.oldlinks:
            re = requests.get(source)
            try:
                tree = html.fromstring(re.text).xpath(
                    '//div/a[contains(@href,"couponCode")]/@href')
            except:
                print('Failed:', re.url)
                logging.error(traceback.format_exc())
            if tree:
                url = tree[0]
                self.checkAdd(url,source)
        else:
            logging.info('Link already checked, skipping')

    def unique(self, url: str):
        tag = urlparse(url).path.split('/')[2]
        try:
            coupon = parse_qs(urlparse(url).query)['couponCode'][0]
            check = f'{tag},{coupon}'
            if check not in self.tags:
                self.tags.add(check)
                return True
            else:
                return False
        except:
            return False

    def verifyUdemy(self, url):
        uurl = 'https://www.udemy.com/api-2.0/courses/' + \
            urlparse(url).path.split('/')[2]
        try:
            coupon = parse_qs(urlparse(url).query)['couponCode'][0]
        except KeyError:
            coupon = ''
        # print(uurl)
        # print(ar.text)  # initial course data
        data = json.loads(requests.get(uurl).text)
        if 'detail' not in data.keys():
            uuurl = 'https://www.udemy.com/api-2.0/course-landing-components/' + \
                str(data['id']) + '/me/?couponCode=' + \
                str(coupon) + '&components=buy_button'
            # print(uuurl) #check for the coupons validity
            data = json.loads(requests.get(uuurl).text)
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
	<title>Udemies Global</title>
	<atom:link href="https://udemiesglobal.com/feed" rel="self" type="application/rss+xml" />
	<link>https://udemiesglobal.com</link>
	<description>Free Udemy, BitDegree, Skillshare &#38; More Online Courses</description>
	<lastBuildDate>Mon, 07 Sep 2020 14:35:10 +0000</lastBuildDate>
	<language>en-US</language>
	<sy:updatePeriod>hourly</sy:updatePeriod>
	<sy:updateFrequency>1</sy:updateFrequency>


<image>
        <url>https://media.udemiesglobal.com/2019/01/udemiesGlobalIcon-1-150x150.png</url>
        <title>udemies Global</title>
        <link>https://udemiesglobal.com</link>
        <width>32</width>
        <height>32</height>
</image>
    '''

        self.rss_foot = '''
</channel>
</rss>'''
        content = self.rss_head + \
            str(''.join(reversed(self.xmlitems))) + self.rss_foot
        with open('feed.xml', 'w') as f:
            f.write(content)

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

        content = self.html_head + \
            str(''.join(reversed(self.htmlitems))) + self.html_foot
        with open('feed.html', 'w', encoding='UTF-8') as f:
            f.write(content)

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
    #print(ud.oldcourses)
    #print(ud.rsscourses)
    
    try:
        ud.du(5)
    except Exception as e:
        logging.error('DU website has failed',e)
    try:
        ud.iv()
    except Exception as e:
        logging.error('IH website has failed',e)
    try:
        ud.fg()
    except Exception as e:
        logging.error('FG website has failed',e)
    try:
        ud.cs(7)
    except Exception as e:
        logging.error('CS website has failed',e)
        
    # print(ud.foundcourses)
    ud.newcourses = ud.foundcourses.difference(ud.oldcourses)
    # print(ud.newcourses)
    #ud.writeHTML()
    # ud.writeXML()
    ud.closeSQL()
    end = time.perf_counter()
    print(len(ud.newcourses), 'course id found in',
        round((end-start)/60, 2), 'minutes')
    
    if len(ud.newcourses) > 0:
        tg = 'https://api.telegram.org/bot' + BOT + '/sendMessage?chat_id=' + CHATID + '&text='
        msg = f"{len(ud.newcourses)} courses found in {round((end-start)/60,2)} minutes"
        requests.get(tg+msg)
    # if DEPLOYED == 1:
    #     print(f'waiting for: {str(round(INTERVAL/60,2))} minutes')               
    #     time.sleep(INTERVAL)