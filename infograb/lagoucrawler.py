__author__ = 'jjzhu (jjzhu_ncu@163.com)'
import urllib.request
import urllib.parse
import urllib.error
import http.cookiejar
import json
import datetime
import re
from threading import Thread
from time import sleep
from queue import Queue
from bs4 import BeautifulSoup

from grabutil.mysqlconnection import MysqlConnection


class LagouCrawler:
    def __init__(self, db, max_count=50, thread_num=5):
        """
        :param db: 数据库名（mysql）
        :param max_count: 批量插入数据库的条数
        :param thread_num:  并行线程数
        :return:
        """
        self.position_default_url = "http://www.lagou.com/jobs/"
        self.seed_url = 'http://www.lagou.com/zhaopin/'
        self.lagou_url = "http://www.lagou.com/"
        self.base_request_url = "http://www.lagou.com/jobs/positionAjax.json?city="
        self.proxies = [{"HTTP": "58.248.137.228:80"}, {"HTTP": "58.251.132.181:8888"}, {"HTTP": "60.160.34.4:3128"},
                        {"HTTP": "60.191.153.12:3128"}, {"HTTP": "60.191.164.22:3128"}, {"HTTP": "80.242.219.50:3128"},
                        {"HTTP": "86.100.118.44:80"}, {"HTTP": "88.214.207.89:3128"}, {"HTTP": "91.183.124.41:80"},
                        {"HTTP": "93.51.247.104:80"}]
        self.to_add_infos = []
        self.max_count = max_count  # 批量插入的记录数
        self.thread_num = thread_num  # 线程数
        self.job_queue = Queue()  # 任务队列

        self.query = "insert into position_info.position(city, companyId, companyLabelList, companyName,  companyShortName, " \
            "companySize, education, financeStage, industryField, jobNature, leaderName, positionAdvantage," \
            "positionFirstType, positionId, positionName, positionType, pvScore, workYear, salary_min, salary_max)" \
            " values (%s, %s, %s, %s,%s, %s, %s, %s,%s, %s, %s, %s,%s, %s, %s,%s, %s, %s, %s, %s)"
        self.head = {
            'Connection': 'Keep-Alive',
            'Accept': 'text/html, application/xhtml+xml, */*',
            'Accept-Language': 'en-US,en;q=0.8,zh-Hans-CN;q=0.5,zh-Hans;q=0.3',
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.3; WOW64; Trident/7.0; rv:11.0) like Gecko'
        }
        self.index = 0
        self.mysqlconn = MysqlConnection(db=db)
        self.my_opener = self.make_my_opener()
        self.start_thread()  # 开启多线程

    def change_proxy(self):
        proxy_handler = urllib.request.ProxyHandler(self.proxies[self.index % self.proxies.__len__()])
        print("换代理了..."+str(self.proxies[self.index % self.proxies.__len__()]))
        self.index += 1
        if self.index >= 1000:
            self.index = 0
        # proxy_auth_handler = urllib.request.ProxyBasicAuthHandler()
        cj = http.cookiejar.CookieJar()  # cookie
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        header = []
        for key, value in self.head.items():
            elem = (key, value)
            header.append(elem)
        opener.addheaders = header
        opener.add_handler(proxy_handler)
        self.my_opener = opener

    # 开启多线程
    def start_thread(self):
        for i in range(self.thread_num):
            curr_thread = Thread(target=self.working)
            curr_thread.setDaemon(True)
            curr_thread.start()

    def make_my_opener(self):
        """
        模拟浏览器发送请求
        :return:
        """

        proxy_handler = urllib.request.ProxyHandler({"HTTP": "64.62.233.67:80"})
        # proxy_auth_handler = urllib.request.ProxyBasicAuthHandler()
        cj = http.cookiejar.CookieJar()  # cookie
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        header = []
        for key, value in self.head.items():
            elem = (key, value)
            header.append(elem)
        opener.addheaders = header
        opener.add_handler(proxy_handler)
        return opener

    def change_salary(self, salary):
        """
        :param salary: 处理拉钩的薪资
        :return:
        """
        salaries = re.findall("\d+", salary)
        if salaries.__len__() == 0:
            return 0, 0
        elif salaries.__len__() == 1:
            return int(salaries[0])*1000, int(salaries[0])*1000
        else:
            return int(salaries[0])*1000, int(salaries[1])*1000

    def position_detail(self, position_id):
        """
        处理职位详情
        :param position_id:
        :return:
        """
        position_url = self.position_default_url + str(position_id)+".html"
        print(position_url)
        op = self.my_opener.open(position_url, timeout=1000)
        detail_soup = BeautifulSoup(op.read().decode(), 'html.parser')
        job_company = detail_soup.find(class_='job_company')
        job_detail = detail_soup.find(id='job_detail')
        job_req = job_detail.find(class_='job_bt')
        c_feature = job_company.find(class_='c_feature')
        homePage = c_feature.find('a')
        homeUrl = homePage.get('href')
        return job_req, homeUrl

    def grab_city(self):
        """
        获取所有的城市
        :return:
        """
        print("开始获取所有城市")
        op = self.my_opener.open(self.seed_url)

        my_soup = BeautifulSoup(op.read().decode(), 'html.parser')
        all_positions_html = my_soup.find(class_='more more-positions')
        all_positions_hrefs = all_positions_html.find_all('a')
        all_cities = []
        for a_tag in all_positions_hrefs:
            all_cities.append(a_tag.contents[0])
        print("获取所有城市完成")
        return all_cities

    def grab_position(self):
        """
        获取所有招聘职位
        :return:
        """
        print("开始获取所有招聘职位")
        html = self.my_opener.open(self.lagou_url)
        soup = BeautifulSoup(html.read().decode(), "html.parser")
        side_bar = soup.find(id="sidebar")
        mainNavs = side_bar.find(class_="mainNavs")
        menu_boxes = mainNavs.find_all(class_="menu_box")
        all_positions = []
        for menu_box in menu_boxes:
            menu_sub = menu_box.find(class_="menu_sub")  # 所有职位
            all_a_tags = menu_sub.find_all("a")  # 找出所有职位的a标签
            for a_tag in all_a_tags:
                all_positions.append(a_tag.contents[0])
        print("获取所有职位完成")
        return all_positions

    def insert_into_database(self, result):
        """
        插入数据
        :param result:待插入的抓取信息
        :return:
        """
        city = result['city']
        companyId = result['companyId']
        companyLabelList = result['companyLabelList']
        companyLabel = ''
        for lable in companyLabelList:
            companyLabel += lable+" "
        companyName = result['companyName']
        companyShortName = result['companyShortName']
        companySize = result['companySize']
        education = result['education']
        financeStage = result['financeStage']
        industryField = result['industryField']
        jobNature = result['jobNature']
        leaderName = result['leaderName']
        positionAdvantage = result['positionAdvantage']
        positionFirstType = result['positionFirstType']
        positionId = result['positionId']
        # job_req, homeUrl = self.position_detail(positionId)  # 获取信息
        positionName = result['positionName']
        positionType = result['positionType']
        pvScore = result['pvScore']
        salary = result['salary']
        salaryMin, salaryMax = self.change_salary(salary)
        workYear = result['workYear']
        '''
        print(city, companyId, companyLabel, companyName,  companyShortName, companySize,
              education, financeStage, industryField, jobNature, leaderName, positionAdvantage,
            positionFirstType, positionId, positionName, positionType, pvScore, salary, workYear)
        '''
        self.to_add_infos.append((city, str(companyId), companyLabel, companyName,  companyShortName, companySize,
                                  education, financeStage, industryField, jobNature, leaderName, positionAdvantage,
                                  positionFirstType, positionId, positionName, positionType, pvScore, workYear,
                                  salaryMin, salaryMax))
        if self.to_add_infos.__len__() >= self.max_count:  # 批量插入
            try:
                self.mysqlconn.execute_many(sql=self.query, args=self.to_add_infos)
                print("------------------insert successful---------------")
            except Exception:
                print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!失败了！！！！！！！！！！！！！！！！！！！！！！！！！！！")
                pass
            self.to_add_infos.clear()  # 清空数据

    def working(self):
        while True:
            post_data = self.job_queue.get()  # 取任务
            try:
                self.grab(post_data)  # 抓取任务
            except Exception:
                pass
            sleep(3)
            self.job_queue.task_done()

    def grab(self, args):
        """
        根据参数args发请求，获取数据
        :param args:请求参数字典{'first': '？', 'kd': ？, 'city': ？, 'pn': ？}
        :return:
        """
        url = self.base_request_url + urllib.parse.quote(args['city'])
        url.encode(encoding='utf-8')
        print(url + "--------"+str(args))
        del args['city']  # 把city这个键删了，，，，不然，请求没有数据返回！！！
        post_data = urllib.parse.urlencode(args).encode()
        try:
            op = self.my_opener.open(url, post_data)
            return_json = json.loads(op.read().decode())
            content_json = return_json['content']
            result_list = content_json['result']

            for result in result_list:
                # 插入数据库啦
                print(result)
                self.insert_into_database(result)
        except Exception:
            pass

    def grab_category(self, city, kd):
        """
        分类抓取
        :param city:当前城市
        :param kd: 当前职位类型
        :return:
        """
        url = self.base_request_url+urllib.parse.quote(city)
        url.encode(encoding='utf-8')
        pn = 1
        postdata = urllib.parse.urlencode({'first': 'true', 'pn': pn, 'kd': kd}).encode()
        pn += 1
        try:
            print(url, postdata)
            op = self.my_opener.open(url, postdata)
        except Exception:
            sleep(60)
            return
        return_json = json.loads(op.read().decode())
        content_json = return_json['content']
        total_page = content_json['totalPageCount']
        result_list = content_json['result']
        for result in result_list:
            self.insert_into_database(result)

        while pn <= total_page:
            # 一个任务处理一页
            self.job_queue.put({'first': 'false', 'kd': kd, 'city': city, 'pn': pn})
            pn += 1
            if self.job_queue.qsize() == 5:
                self.job_queue.join()
                self.change_proxy()
        self.job_queue.join()

        print('successful')

    def start(self):
        print("开始抓取啦.............")
        all_cities = self.grab_city()
        all_positions = self.grab_position()

        for i in range(0, int(all_cities.__len__())):
            start_time = datetime.datetime.now()
            for j in range(0, int(all_positions.__len__())):

                grabed_cities_file = open("d:\\grabed3.txt", 'a')
                self.grab_category(city=all_cities[i], kd=all_positions[j])
                end_time = datetime.datetime.now()
                grabed_cities_file.write(all_cities[i]+"----职位："+all_positions[j]+"----耗时："
                                         + str((end_time-start_time).seconds)+"s\n")
                grabed_cities_file.close()
            end_time = datetime.datetime.now()
            grabed_cities_file = open("d:\\grabed1.txt", 'a')
            print((end_time-start_time).seconds)
            grabed_cities_file.write(all_cities[i]+"----耗时："+str((end_time-start_time).seconds)+"s\n")
            grabed_cities_file.close()
        self.mysqlconn.close()

        print("----------抓取完啦--------------")


def main():
    my_crawler = LagouCrawler(db='position_info', max_count=50, thread_num=5)

    my_crawler.start()

if __name__ == '__main__':
    main()
