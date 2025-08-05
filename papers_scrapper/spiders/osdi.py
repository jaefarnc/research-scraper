import scrapy
from .base_spider import BaseSpider
from ..items import PdfFilesItem

class OsdiSpider(BaseSpider):
    name = 'osdi'
    allowed_domains = ['usenix.org']
    start_urls = [
        'https://www.usenix.org/conference/osdi23/technical-sessions'
    ]

    def __init__(self, conference: str = 'osdi', year: str = '2023'):
        BaseSpider.__init__(self, conference, year)

    def start_requests(self):
        for url in self.start_urls:
            self.logger.info(f'Start scraping {url} for {self.year}')
            yield scrapy.Request(url=url, callback=self.parse, dont_filter=True)

    def parse(self, response):
        self.logger.info(f'Successfully fetched page: {response.url}')
        # Find all links to individual research papers (those containing '/presentation' or '/presentations')
        paper_links = response.xpath('//a[contains(@href, "/presentation") or contains(@href, "/presentations")]/@href').getall()
        if paper_links:
            self.logger.info(f'Found {len(paper_links)} research paper links')
            for paper_url in paper_links:
                abs_url = response.urljoin(paper_url)
                yield scrapy.Request(url=abs_url, callback=self.parse_paper, dont_filter=True)
        else:
            # If this is an individual paper page, extract info from meta tags
            yield from self.parse_paper(response)

    def parse_paper(self, response):
        title = response.xpath('//meta[@name="citation_title"]/@content').get()
        authors = response.xpath('//meta[@name="citation_author"]/@content').getall()
        abstract = response.xpath('//meta[@name="description"]/@content').get()
        pdf_url = response.xpath('//meta[@name="citation_pdf_url"]/@content').get()
        item = PdfFilesItem()
        item['title'] = self.clean_html_tags(title) if title else ''
        item['authors'] = ', '.join(authors) if authors else ''
        item['abstract'] = self.clean_html_tags(abstract) if abstract else ''
        item['file_urls'] = [pdf_url] if pdf_url else []
        item['pdf_url'] = pdf_url if pdf_url else ''
        item['source_url'] = response.url
        item['abstract_url'] = response.url
        yield item
